# TulsiOS architecture

## Goals

1. Install and uninstall software without writing Nix (Ocimum Software Center).
2. Browser extensions become declarative automatically: the user installs one from the
   store as usual, the OS says it will be installed declaratively and moves it into
   Nix-managed policy (`tulsi-extwatch`).
3. Configuration through an agent: plain-language request → validated diff → user
   approves → rebuild (Ocimum Assistant, `tulsi-mcp`).
4. Keep NixOS guarantees: reproducible, atomic, rollback-able.

## The core rule: tools edit state, Nix builds the system

`/nix/store` is immutable and content-addressed. Nothing in TulsiOS writes to it
directly. Every component instead edits one declarative file:

```
/etc/nixos/tulsi/state.json      (schema: state/schema.json, Rust: crates/tulsi-state)
```

```
 Software Center ─┐
 Ocimum Assistant ─┼─ D-Bus ─▶ tulsid ─▶ state.json ─▶ git commit ─▶ nixos-rebuild switch
 tulsi-extwatch  ─┤            (root,     (validated)   (history)     (new generation,
 tulsi CLI       ─┘            polkit)                                 rollback = previous)
```

The `tulsi.state` NixOS module (`nix/modules/tulsi-state.nix`) maps the file to:

| state.json | NixOS |
|---|---|
| `packages[]` | `environment.systemPackages` (nixpkgs attribute paths) |
| `browserExtensions.firefox[]` | `programs.firefox.policies.ExtensionSettings` (force_installed) |
| `browserExtensions.chromium[]` | `programs.chromium.extensions` (Chromium, Chrome, Brave) |
| `services.<name>.enable` | `services.<name>.enable` |

Anything a user hand-writes in `configuration.nix` keeps working; `state.json` is an
additional, machine-managed layer. Browser **profile data** (`~/.mozilla`, `~/.config/chromium`)
is mutable user data and stays outside the store. Only the *set of installed extensions*
is declarative.

## Components

### tulsid, `crates/tulsid`, `nix/modules/tulsid.nix`
Root systemd service (`tulsi.daemon.enable`). Owns `<flakeDir>/tulsi/state.json`
(default `/etc/nixos`). D-Bus API `org.tulsi.Manager1` (client: `crates/tulsi-client`):

| Member | Notes |
|---|---|
| `GetState() → s` | state.json |
| `Plan(ops s) → s` | `{changes, state}`, applies nothing |
| `Apply(ops s) → t` | polkit `org.tulsi.apply` (`org.tulsi.extensions` for extensions only, `org.tulsi.configure` when adding a local package); job id (0 = nothing to do) |
| `ApplyConfig(contents s, summary s) → t` | polkit `org.tulsi.apply` if a rollback fully undoes the edit, else `org.tulsi.configure` (ADR 0014) |
| `Undo() → t` | `UndoChange` of the latest change |
| `UndoChange(commit s) → t` | takes back one earlier change, keeping later ones (ADR 0015); polkit: the action that change needed; refused if a later change edited the same lines |
| `PlanUndo(commit s) → s` | `{commit, summary, changes, action}`: what `UndoChange` would do; applies nothing |
| `History(limit u) → s` | `[{commit, time, summary, action, by}]`, from the commit's `Tulsi-Action:` and `Tulsi-By:` trailers |
| `Busy` (property), `Progress(t job, s line)`, `Finished(t job, b ok, s msg)` | job tracking |

`ops` is a JSON list of change operations (`crates/tulsi-state/src/ops.rs`), for example
`[{"op":"addPackage","name":"vlc"}]`. Other ops: `removePackage`, `addExtension`,
`removeExtension` (`browser`: `firefox`|`chromium`, `id`), `setService` (`name`, `enable`).

Transaction (one at a time): polkit check → apply ops + validate → write state.json →
`git add` → rebuild command (default `nixos-rebuild switch --flake <flakeDir>#<host>`;
output streamed as `Progress`) → on success, commit `state.json` (+ `flake.lock`) as
`tulsi: <summary>`; on failure, restore the previous state.json and return the log tail.
Undo commits the previous version of state.json as a new change, so history only grows.

With `tulsi.daemon.bootstrap.enable`, first start generates a system flake in
`<flakeDir>` whose `tulsi` input is the TulsiOS source the system was built from.
It imports `tulsi.nixosModules.default`, the host module, the user's
`configuration.nix` and `tulsi/state.json`. The pinned nixpkgs source ships in the system
closure, so evaluation works offline.

Package search: `Search(query s, limit u) → s` and `PackageInfo(attr s) → s` use an
index of the pinned nixpkgs (`nix/packages/package-index.nix`). It is generated at build
time with nixpkgs' own `packages-info.nix`, the source of search.nixos.org, and
shipped in the closure, so no evaluation happens at runtime. With the index,
`Plan`/`Apply` reject unknown top-level names with "did you mean" hints, and reject
unfree packages unless `nixpkgs.config.allowUnfree` is set, all before any rebuild.

### tulsi CLI, `crates/tulsi-cli`
`tulsi install|remove PKG…`, `tulsi search WORDS…`, `tulsi ext add|remove firefox|chromium ID`,
`tulsi service enable|disable NAME`, `tulsi config show|diff FILE|apply FILE --summary TEXT`
(any other NixOS setting, through tulsid's `GetConfig`/`PlanConfig`/`ApplyConfig`, like
tulsi-mcp's configuration tools), `tulsi undo [ID]`, `tulsi status`, `tulsi history`,
Recipes, upgrades, `--dry-run`. `service enable` refuses names that are settings, not
`services.*` (docker, podman, libvirtd, steam…), and points at `tulsi config`. Runs
`pkttyagent` for terminal password prompts when no desktop agent exists.

### Ocimum Software Center, `apps/ocimum-software-center`, `nix/modules/software-center.nix`
Python + PyGObject on GTK 3 (ADR 0005), so on TulsiOS it runs on GTK3-O. Pages:
Search (debounced, at most 200 rows), Installed, History. Every change runs Plan →
confirmation dialog listing the changes → Apply → bottom progress panel streaming the
rebuild log → success bar with **Undo**. Errors keep the log visible. Also exposes the
`Gtk.Application` actions `install(s)`, `remove(s)`, `search(s)` and `undo` on the
session bus, for tests and later the Assistant. These still go through the confirmation dialog.

### GTK3-O, `nix/modules/gtk3-o.nix`
The Ocimum fork of GTK 3.24 (package `gtk3-o` in tulsipkgs). It is ABI-stable and grafted
system-wide with `system.replaceDependencies`, so every GTK 3 app uses it without being
rebuilt (ADR 0006). `checks.gtk3-o-abi` guards against removed exported symbols.

### Declarative browser extensions, `crates/tulsi-extwatch`, `nix/modules/browser-extensions.nix`
ADR 0007. `tulsi-extwatch` is a systemd user service in the graphical session
(`tulsi.browserExtensions.adopt`, on with tulsid):
1. It watches Firefox `extensions.json` and Chromium/Chrome/Brave `Secure Preferences`
   in every profile, checking modification times every 3 s.
2. A user-installed extension from addons.mozilla.org or the Chrome Web Store that is
   not yet in `state.json` triggers a notification: *"Extension will be installed
   declaratively"*, with a **Keep it imperative** button during the grace period.
3. It calls tulsid `Apply([addExtension])`. Extension-only changes use the polkit action
   `org.tulsi.extensions`, which is password-free for active local users by default.
4. The rebuild changes only the browser policy. The notification is replaced with the
   result: Firefox completes the switch on restart; Chromium applies it automatically.

The Software Center's **Extensions** tab lists declarative extensions and removes
them. `tulsi ext add|remove` does the same from a terminal.

### Install the TulsiOS way, `nix/modules/adopt.nix`, `tulsi-adopt`
ADR 0013. Package-command shims (`apt`, `dnf`, …), the default handler for downloaded
packages and archives, and a replaced ELF-loader stub all open `tulsi-adopt`; so do the
install commands of `pip`, `npm -g`, `cargo`, `gem`, `go` and `flatpak` (ADR 0018). It
reads the download with `tulsi inspect` (`crates/tulsi-inspect`: kind, a .deb's or .rpm's
own name, the programs inside) and asks tulsid's `Match` (`crates/tulsid/src/matching.rs`:
`data/name-map.json`, other distributions' naming rules, the program index
`nix/packages/program-index.nix`). It offers those packages or services, each with its
reason. When nothing fits, a Recipe (`crates/tulsi-recipes`, `apps/…/recipe_ui.py`)
packages the download from tested templates without a model, or the Assistant
packages it; which one can be remembered.
Approved results are local packages: `/etc/nixos/tulsi/pkgs/<name>/package.nix` plus
`meta.json`, listed in state.json `localPackages` and installed by `tulsi.state` with
`callPackage`. tulsid (`localpkg.rs`) writes them with history and Undo.
`tulsi_state::check_expression` refuses unsafe expressions.

### tulsi-mcp, `crates/tulsi-mcp` (docs/MCP.md, ADR 0004)
MCP server (stdio, JSON-RPC; protocol versions 2024-11-05 … 2025-11-25) over tulsid.
- Read-only tools: `search_packages`, `package_info`, `get_state`, `read_configuration`,
  `history`, `plan_change`, `propose_configuration_edit`.
- Packaging tools (ADR 0013): `fetch_source`, `build_package`, `try_package` work in the
  agent's own workspace and Nix's sandbox. `propose_local_package` is a change tool.
- Change tools: `apply_change`, `apply_configuration_edit`, `undo_last_change`. Each
  plans first, then asks the human through `ocimum-approve` (desktop dialog, Reject by
  default) or MCP elicitation, then applies and waits for the rebuild. If no approval
  channel exists, the change is refused.

tulsid gained `GetConfig`, `PlanConfig` (syntax check via `nix-instantiate --parse` +
unified diff) and `ApplyConfig`. Transactions now cover any managed file
(`tulsi/state.json`, `configuration.nix`), so config edits share history, rollback and
undo with everything else.

### Nix Editor, `apps/ocimum-nix-editor`, `nix/modules/nix-editor.nix`
ADR 0019. A GTK 3 editor for Nix files: nixd (wrapped in, evaluating
`/etc/tulsi/nixpkgs`) for completion, hover and problems; `tulsi recipe check` for the
local-package rules; a Nix guide (`ocimum_nix_editor/guide/*.md`) on the right that
follows the cursor. Opened on a failed Recipe's draft (`--draft DIR`, from the install
window's "Edit It Yourself"), it builds it with `tulsi recipe build-draft` and installs it
through the Software Center's `apply-ops`.

### Themes, `apps/ocimum-themes`, `nix/modules/themes.nix`
ADR 0021. A theme is Omarchy's `colors.toml` palette plus optional backgrounds
(stock ones in `share/tulsi/themes`, a person's in `~/.config/tulsi/themes`).
`tulsi-theme set` turns it into the running desktop's own theme, per person and with
no rebuild: on Ocimum, Mint-Y's SASS recoloured and compiled with libsass into
`~/.local/share/themes/Tulsi-<slug>` (GTK 3 + Cinnamon, accent images re-rendered),
the nearest Mint-Y icon colour, a GNOME Terminal profile and the background; on
SonicDE a KDE colour scheme; on dwm X resources. `tulsi-theme undo` steps back to the
desktop's own look. The Themes app (`ocimum-themes`) is the window over it; tulsi-mcp
offers `list_themes` / `set_theme` / `undo_theme`.

### Agent skills, `agents/`, `nix/modules/agent-skills.nix`
ADR 0022. `SKILL.md` files (`tulsios`, `tulsios-make-theme`, `tulsios-diagnose-crash`)
and an `AGENTS.md` at `/etc/tulsi/agents`, linked at login into the folders of the
coding-agent CLIs a person uses, never over their own files, so those agents change
the system through `tulsi`.

### Ocimum Assistant, `apps/ocimum-assistant` (docs/ASSISTANT.md)
Chat window (Python/GTK 3). It runs `tulsi-mcp` as a subprocess and drives a manual
tool loop with a pluggable provider: Claude (`claude-opus-5-5` by default, streaming,
adaptive thinking with summaries, automatic prompt caching, server-side refusal
fallbacks) or a scripted fake for tests. The API key lives in the user's keyring
(libsecret). Changes go through tulsi-mcp's approval dialog like any other agent's.

### tulsipkgs and the TulsiOS cache (ADR 0008), `nix/modules/cache.nix`
The flake's `nixpkgs` input is tulsipkgs (`github:lukskrp/tulsipkgs/tulsi-unstable`),
TulsiOS's hard fork of nixpkgs: upstream `nixos-unstable`, merged daily, plus the
software TulsiOS owns (the Ocimum Desktop suite, `gtk3-o`, `otk`). Everything else is
the unchanged upstream derivation and comes from cache.nixos.org. TulsiOS's own builds
come from `https://cache.skarptech.org/tulsi` (`tulsi.cache`).

### Ocimum Desktop, `nix/modules/ocimum-desktop.nix`
Ocimum Desktop is a hard fork of Cinnamon (`github.com/lukskrp/ocimum-desktop`, branch
`ocimum`, forked from 6.8.0). tulsipkgs builds `cinnamon` from it, with the rest of the
Cinnamon 6.8 suite. The fork carries the session name, logo, System Info and pinned
apps, the TulsiOS start button (`tulsi-start`, `tulsi-start-white`) and the Tulsi Leaf
wallpaper; `ocimum.desktop` adds the TulsiOS defaults (Mint-Y-Dark theme, that wallpaper,
the start icon chosen by `ocimum.desktop.startIcon`, Super+A for the Assistant) as gsettings/dconf defaults, which users can change.
It also ships the browser, Brave Origin (`ocimum.desktop.browser`), as the default for web
links, and seeds the panel's launchers (Files, Brave Origin, Terminal) through Cinnamon's
old `panel-launchers` key, which the launchers applet imports once per new user.
`checks.ocimum-desktop` verifies the installed session and these defaults.

### SonicDE, `nix/modules/sonic-desktop.nix` (ADR 0020)
SonicDE is a fork of KDE Plasma 6 that keeps X11. tulsipkgs builds the whole Sonic stack
as `sonicPackages` (`pkgs/sonic`: nixpkgs' KDE recipes with Sonic's sources; sonic-win,
Silver, SonicLogging and SonicIpc of its own). `sonic.desktop` is an X11 counterpart of
nixpkgs' Wayland-only `plasma6` module: the `sonicde` session on XLibre through the Ocimum
Greeter; Ecco, Sonic Terminal, System Monitor and Screenies; TulsiOS's apps and Brave
Origin. `sonic-tulsi-defaults` adds the "TulsiOS (Silver)" look-and-feel: the Tulsi Leaf
wallpaper, the start button, and the pinned apps. Super+A is `X-KDE-Shortcuts` in the
Assistant's `.desktop` file. On these machines `kdePackages` is overlaid with
`sonicPackages`, so KDE apps installed later are Sonic builds. `checks.sonic-desktop`
verifies the session and these defaults.

### Desktops and the installer (ADR 0016), `nix/modules/{desktop,dwm,installer}.nix`
`tulsi.desktop.session` is `"ocimum"`, `"sonic"` or `"dwm"` (suckless dwm 6.8 with the
systray patch, plus what a bare window manager lacks: XDG autostart, a polkit agent,
dunst, the GTK theme). All three log in through the Ocimum Greeter on XLibre. SonicDE is
not on the ISO: it installs online from the TulsiOS cache. Calamares' `tulsios-online`
job refuses it before partitioning when the cache does not answer, and each release
pushes `packages.sonic-cache` to the cache (`docs/RELEASING.md`).

Installed machines use the host module `nix/hosts/desktop`. `tulsi-install-system`
(`apps/tulsi-installer`) writes their `/etc/nixos`:
- `flake.nix` from `data/system-flake.nix.in`, the template tulsid's bootstrap also uses;
- `configuration.nix` with hostname, users, locale, keyboard, boot loader and desktop;
- `hardware-configuration.nix`;
- `tulsi/state.json`.

It then runs `nixos-install --flake`. That works offline, because reference installs'
closures are kept in the live system (`tulsi.installer.offlineSystems`). On the ISO,
Calamares (`calamares-tulsios-extensions`) collects the answers, and its `tulsios` job
hands them to `tulsi-install-system`.

## Security model (summary)
- Unprivileged UIs → D-Bus → tulsid. Every mutating call is polkit-authorized.
- `state.json` is strictly validated (crates/tulsi-state). Package names are attribute
  paths, never shell strings.
- Every change is a git commit and a NixOS generation, so changes can be audited and undone.
- The agent can only propose changes. A human approves every apply.
