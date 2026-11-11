# Roadmap

| Phase | Goal | Exit criteria | Status |
|---|---|---|---|
| 0 | Dev environment | WSL on D:, Nix with flakes, KVM available | done |
| 1 | Repo skeleton + state contract | `nix flake check` green; VM boots Cinnamon; editing `state.json` + rebuild installs a package | done |
| 2 | `tulsid` + CLI + polkit + git-backed state | `tulsi install <pkg>` works in the VM; `tulsi undo` works | done |
| 3 | Ocimum Software Center + GTK3-O | install/uninstall from GUI with progress and undo; GTK3-O used system-wide | done |
| 4 | Declarative browser extensions | store click → notice → installed via policy (Firefox, Chromium, Brave) | next |
| 5 | `tulsi-mcp` + Ocimum Assistant | plain-language request → diff → approve → applied | |
| 6 | Ocimum Desktop fork | branded Cinnamon fork built from `desktop/`, Tulsi applets | |
| 7 | Installer ISO + release | Calamares ISO installs TulsiOS on Hyper-V / bare metal | |

## Phase 3 (done)
- [x] Toolkit decision: GTK 3 via GTK3-O, GUI apps in Python + PyGObject (ADR 0005)
- [x] GTK3-O package (flake input `gtk3-o`) + exported-symbol ABI check (`checks.gtk3-o-abi`)
- [x] GTK3-O grafted system-wide with `system.replaceDependencies` (`ocimum.gtk3o`, ADR 0006)
- [x] Package index of the pinned nixpkgs, built from nixpkgs' own `packages-info.nix` (~137k packages)
- [x] tulsid `Search` / `PackageInfo`; unknown names ("did you mean") and unfree packages refused before rebuild
- [x] `tulsi search`
- [x] Ocimum Software Center: Search / Installed / History, confirm dialog, live progress, Undo
- [x] `checks.software-center` (X11 VM test with screenshots; single libgtk-3 = GTK3-O in the app and in `yad`)
- [x] `scripts/vm-e2e.sh`: Cinnamon processes and the Software Center load GTK3-O; screenshots

Known limits, picked up later:
- Search ranking has no popularity signal, so for "video player" niche players can outrank VLC.
  Add curated "featured"/popular weighting or AppStream data.
- No app icons for most packages (nixpkgs has no icon metadata); a generic icon is shown.
- Nested attributes (e.g. `python3Packages.*`) are not pre-validated; the rebuild still checks them.
- `tulsid` is not restarted on upgrade (`restartIfChanged = false`); new versions start after a reboot.

## Next up: Phase 4 tasks
- [ ] `browser/bridge-extension`: Manifest V3 WebExtension for Firefox and Chromium; content
      scripts on addons.mozilla.org / Chrome Web Store replace "Add to …" with "Install with Ocimum"
- [ ] `browser/native-host`: native messaging host `org.tulsi.bridge` → tulsid `Plan`/`Apply`
- [ ] Desktop notification "This extension will be installed declaratively" + confirm
- [ ] `tulsi.browserExtensions.blockImperativeInstalls` on by default with the bridge force-installed
- [ ] NixOS test: Firefox + Chromium headless, simulated store click → policy contains the id
