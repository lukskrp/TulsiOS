# ADR 0007: Adopt store-installed extensions instead of a bridge extension

Status: accepted (2026-11-11). Supersedes the "Ocimum Bridge" part of ADR 0003;
rendering extensions as browser policies (the rest of ADR 0003) stands.

## Context
Goal: when a user installs a browser extension, the OS says it will be installed
declaratively and makes it so, without the user writing anything.

The original plan was a force-installed "Ocimum Bridge" WebExtension that replaces
the stores' "Add to …" buttons and talks to tulsid over native messaging. It is not
workable without outside dependencies:
- Firefox release builds only load Mozilla-signed extensions, policy-installed
  ones included. That means an AMO developer account and a signing step in every
  release.
- Chrome removed `--load-extension`, and self-hosted packed extensions need signing
  infrastructure as well.
- Rewriting store pages breaks whenever the stores change their markup.

## Decision
Let the browser install the extension the normal way, then **adopt** it:
- `tulsi-extwatch` (`crates/tulsi-extwatch`) runs as a systemd **user** service in the
  graphical session. It watches the browsers' own profile files: Firefox
  `extensions.json` (also under `$XDG_CONFIG_HOME/mozilla`), and Chromium, Chrome and
  Brave `Secure Preferences` / `Preferences`.
- It adopts only extensions the user installed from **addons.mozilla.org** or the
  **Chrome Web Store**, because the policy can fetch those again by id. Side-loaded,
  built-in and policy-installed extensions are ignored.
- For each new one it shows a desktop notification: *"Extension will be installed
  declaratively"*. A **Keep it imperative** button can be used during a short
  grace period (`tulsi.browserExtensions.adopt.grace`, default 8 s), and that choice is
  remembered. Then it calls tulsid `Apply([addExtension])`, waits for the result and
  replaces the notification with the outcome.
- tulsid authorizes extension-only changes with the polkit action
  **`org.tulsi.extensions`** instead of `org.tulsi.apply`. With
  `adopt.withoutPassword` (default on), active local users may do these changes
  without a password. Packages, services and undo still require an administrator.
- From then on the browser policy (`ExtensionSettings` / `ExtensionInstallForcelist`)
  installs and owns the extension. Removal happens through the Software Center's
  Extensions tab or `tulsi ext remove`.

## Consequences
- Works for Firefox and every Chromium-family browser, with no signing, no store-page
  scraping and no browser patches.
- The notice comes right *after* the browser installs the extension, not before.
  The user never sees an imperative-only state persist.
- Extensions apply system-wide, to all users of the machine. That fits a personal
  desktop. Multi-user machines can set `adopt.withoutPassword = false`.
- `blockImperativeInstalls` remains available for locked-down machines. It turns
  adoption off.
