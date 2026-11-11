# Roadmap

| Phase | Goal | Exit criteria | Status |
|---|---|---|---|
| 0 | Dev environment | WSL on D:, Nix with flakes, KVM available | done |
| 1 | Repo skeleton + state contract | `nix flake check` green; VM boots Cinnamon; editing `state.json` + rebuild installs a package | done |
| 2 | `tulsid` + CLI + polkit + git-backed state | `tulsi install <pkg>` works in the VM; `tulsi undo` works | done |
| 3 | Ocimum Software Center | install/uninstall from GUI with progress and undo | next |
| 4 | Declarative browser extensions | store click → notice → installed via policy (Firefox, Chromium, Brave) | |
| 5 | `tulsi-mcp` + Ocimum Assistant | plain-language request → diff → approve → applied | |
| 6 | Ocimum Desktop fork | branded Cinnamon fork built from `desktop/`, Tulsi applets | |
| 7 | Installer ISO + release | Calamares ISO installs TulsiOS on Hyper-V / bare metal | |

## Phase 2 (done)
- [x] D-Bus API `org.tulsi.Manager1` (zbus): `GetState`, `Plan`, `Apply`, `Undo`, `History`, `Busy`, `Progress`/`Finished` signals
- [x] polkit action `org.tulsi.apply` (admins, `auth_admin_keep`; optional password-less for `wheel`)
- [x] Transaction: validate → write state → rebuild (streamed) → git commit, or restore on failure
- [x] Git-backed system flake dir; undo = revert latest change as a new commit
- [x] Bootstrap: first start generates `/etc/nixos/{flake.nix,configuration.nix,tulsi/state.json}`
- [x] `tulsi install|remove|ext|service|undo|status|history`, `--dry-run`
- [x] NixOS test `checks.tulsid` (fake rebuild) + `scripts/vm-e2e.sh` (real rebuild in the dev VM)

Known limits, picked up later:
- Unknown package names are caught by the rebuild (evaluation error, state restored), not before it.
  A fast pre-check (`nix eval` of the attribute) belongs in Phase 3 together with package search.
- `tulsid` is not restarted on upgrade (`restartIfChanged = false`), so new versions start after a reboot.

## Next up: Phase 3 tasks
- [ ] Package metadata index (name, description, version, homepage) generated from the pinned nixpkgs
- [ ] `Search(query)` and package pre-validation in tulsid
- [ ] GTK4/libadwaita app (relm4): search, details, install/remove toggles, progress view, history + undo
- [ ] Desktop entry + icon; `ocimum.softwareCenter.enable` installs it
- [ ] NixOS test driving the app headless (or its view model) against tulsid
