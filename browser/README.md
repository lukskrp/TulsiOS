# Ocimum Bridge (Phase 4)

- `bridge-extension/`: WebExtension (Firefox + Chromium, Manifest V3) force-installed by policy.
  Injects "Install with Ocimum" on addons.mozilla.org / Chrome Web Store.
- `native-host/`: native messaging host `org.tulsi.bridge` that forwards requests to tulsid over D-Bus.

See docs/ARCHITECTURE.md and docs/adr/0003-browser-extensions-via-policies.md.
