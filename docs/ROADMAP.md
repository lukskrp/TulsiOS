# Roadmap

| Phase | Goal | Exit criteria | Status |
|---|---|---|---|
| 0 | Dev environment | WSL on D:, Nix with flakes, KVM available | done |
| 1 | Repo skeleton + state contract | `nix flake check` green; VM boots Cinnamon; editing `state.json` + rebuild installs a package | in progress |
| 2 | `tulsid` + CLI + polkit + git-backed state | `tulsi install vlc` works in the VM; `tulsi rollback` works | |
| 3 | Ocimum Software Center | install/uninstall from GUI with progress and undo | |
| 4 | Declarative browser extensions | store click → notice → installed via policy (Firefox, Chromium, Brave) | |
| 5 | `tulsi-mcp` + Ocimum Assistant | plain-language request → diff → approve → applied | |
| 6 | Ocimum Desktop fork | branded Cinnamon fork built from `desktop/`, Tulsi applets | |
| 7 | Installer ISO + release | Calamares ISO installs TulsiOS on Hyper-V / bare metal | |

## Next up: Phase 2 tasks
- [ ] D-Bus interface definition `org.tulsi.Manager1` (zbus)
- [ ] polkit actions `org.tulsi.apply`, `org.tulsi.rollback`
- [ ] Transaction runner: validate → eval → dry-build → switch, streamed logs
- [ ] Git-backed `/etc/nixos/tulsi/` (commit per change, revert = rollback)
- [ ] Bootstrap: first-boot creation of `/etc/nixos/tulsi/state.json` + flake wiring
- [ ] `tulsi install/remove/ext add/apply/rollback`
- [ ] NixOS test: install + rollback round trip
