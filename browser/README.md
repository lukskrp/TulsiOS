# Browser integration

Browser extensions become declarative through **adoption**, not a browser-side
bridge. See [ADR 0007](../docs/adr/0007-adopt-store-installed-extensions.md).

- Watcher: `crates/tulsi-extwatch` (user service, `tulsi.browserExtensions.adopt`)
- Policies: `nix/modules/tulsi-state.nix` renders `state.json` extensions into Firefox
  `ExtensionSettings` and Chromium `ExtensionInstallForcelist`
- Polkit: extension-only changes use `org.tulsi.extensions`

This directory is kept for a possible future signed companion extension, for example
an "Installed declaratively" badge on store pages. Nothing here is needed today.
