# ADR 0003: Browser extensions are installed through enterprise policies

Status: accepted (2026-11-11). The "Ocimum Bridge" part is superseded by
[ADR 0007](0007-adopt-store-installed-extensions.md): store installs are adopted
by `tulsi-extwatch` instead of being redirected by a bridge extension.

## Context
Users install extensions imperatively from web stores. We want these installs to be declarative and reproducible without making the user aware of Nix.

## Decision
Extensions are expressed as IDs in `state.json` and rendered into browser enterprise policies (Firefox `ExtensionSettings`, Chromium `ExtensionInstallForcelist`). Once the Ocimum Bridge exists (Phase 4), imperative installs are blocked by policy and store clicks are redirected to tulsid via a force-installed WebExtension + native messaging host.

## Consequences
Works for Firefox, Chromium, Chrome and Brave with no browser patches. Extension updates come from the stores (pinned XPI/CRX in the Nix store can come later for full reproducibility). Profile data remains mutable user data.
