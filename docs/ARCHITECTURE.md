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
| `Apply(ops s) → t` | polkit `org.tulsi.apply`; job id (0 = nothing to do) |
| `Undo() → t` | polkit `org.tulsi.apply`; reverts the latest change |
| `History(limit u) → s` | `[{commit, time, summary}]` |
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
`tulsi service enable|disable NAME`, `tulsi undo`, `tulsi status`, `tulsi history`,
`--dry-run`. Runs `pkttyagent` for terminal password prompts when no desktop agent exists.

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

### tulsi-mcp, `crates/tulsi-mcp` (docs/MCP.md, ADR 0004)
MCP server (stdio, JSON-RPC; protocol versions 2024-11-05 … 2025-11-25) over tulsid.
- Read-only tools: `search_packages`, `package_info`, `get_state`, `read_configuration`,
  `history`, `plan_change`, `propose_configuration_edit`.
- Change tools: `apply_change`, `apply_configuration_edit`, `undo_last_change`. Each
  plans first, then asks the human through `ocimum-approve` (desktop dialog, Reject by
  default) or MCP elicitation, then applies and waits for the rebuild. If no approval
  channel exists, the change is refused.

tulsid gained `GetConfig`, `PlanConfig` (syntax check via `nix-instantiate --parse` +
unified diff) and `ApplyConfig`. Transactions now cover any managed file
(`tulsi/state.json`, `configuration.nix`), so config edits share history, rollback and
undo with everything else.

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
apps; `ocimum.desktop` adds the TulsiOS defaults (Mint-Y-Dark theme, basil wallpaper,
Super+A for the Assistant) as gsettings/dconf defaults, which users can change.
`checks.ocimum-desktop` verifies the installed session and these defaults.

## Security model (summary)
- Unprivileged UIs → D-Bus → tulsid. Every mutating call is polkit-authorized.
- `state.json` is strictly validated (crates/tulsi-state). Package names are attribute
  paths, never shell strings.
- Every change is a git commit and a NixOS generation, so changes can be audited and undone.
- The agent can only propose changes. A human approves every apply.
