# TulsiOS architecture

## Goals

1. Install and uninstall software without writing Nix (Ocimum Software Center).
2. Browser extensions become declarative automatically: the user clicks "Add", and the OS
   installs the extension through Nix-managed policy (Ocimum Bridge).
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
 Browser bridge  ─┤            (root,     (validated)   (history)     (new generation,
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

### tulsi CLI, `crates/tulsi-cli`
`tulsi install|remove PKG…`, `tulsi ext add|remove firefox|chromium ID`,
`tulsi service enable|disable NAME`, `tulsi undo`, `tulsi status`, `tulsi history`,
`--dry-run`. Runs `pkttyagent` for terminal password prompts when no desktop agent exists.

### Ocimum Software Center (Phase 3), `crates/ocimum-software-center`
GTK4/libadwaita (relm4). Searches nixpkgs metadata, shows installed state, toggles
install/uninstall, shows rebuild progress and history ("undo last change").

### Ocimum Bridge (Phase 4), `browser/`
- Policy blocks imperative installs (`tulsi.browserExtensions.blockImperativeInstalls`).
- A force-installed WebExtension injects "Install with Ocimum" on addons.mozilla.org and
  the Chrome Web Store, and catches blocked-install attempts.
- It talks over **native messaging** to `tulsi-browser-host`, which calls tulsid.
- The user sees a desktop notification: *"This extension will be installed declaratively."*
  On confirm, tulsid adds the ID to `state.json` and rebuilds. Only the policy changes, so
  this is fast. The browser then picks up the policy (Firefox: restart prompt; Chromium:
  policy reload).

### tulsi-mcp + Ocimum Assistant (Phase 5)
`tulsi-mcp` is an MCP server over tulsid with tools `search_packages`, `get_state`,
`propose_change`, `validate`, `apply`, `rollback`, `list_generations`, `edit_nix_file`.
`apply` always requires interactive user approval, and agents never get a root shell.
Free-form Nix edits are AST-aware and must pass parse + format + dry-build before they
are offered. The Ocimum Assistant (Cinnamon panel applet + chat window) runs the agent
loop with a pluggable LLM provider (Claude API default; local models later). Any
external agent can use the same MCP server.

### Ocimum Desktop (Phase 6), `desktop/`, `nix/modules/ocimum-desktop.nix`
Phase 1 wraps stock nixpkgs Cinnamon behind `ocimum.desktop.enable`. Phase 6 adds a
`linuxmint/cinnamon` fork (submodule), built through the overlay by replacing `src`,
plus branding, theme, default panel layout and Tulsi applets. Other Cinnamon
components (muffin, nemo, …) are forked only when needed.

## Security model (summary)
- Unprivileged UIs → D-Bus → tulsid. Every mutating call is polkit-authorized.
- `state.json` is strictly validated (crates/tulsi-state). Package names are attribute
  paths, never shell strings.
- Every change is a git commit and a NixOS generation, so changes can be audited and undone.
- The agent can only propose changes. A human approves every apply.
