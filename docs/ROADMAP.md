# Roadmap

| Phase | Goal | Exit criteria | Status |
|---|---|---|---|
| 0 | Dev environment | WSL on D:, Nix with flakes, KVM available | done |
| 1 | Repo skeleton + state contract | `nix flake check` green; VM boots Cinnamon; editing `state.json` + rebuild installs a package | done |
| 2 | `tulsid` + CLI + polkit + git-backed state | `tulsi install <pkg>` works in the VM; `tulsi undo` works | done |
| 3 | Ocimum Software Center + GTK3-O | install/uninstall from GUI with progress and undo; GTK3-O used system-wide | done |
| 4 | Declarative browser extensions | store install → notice → adopted into policy (Firefox, Chromium, Chrome, Brave) | done |
| 5 | `tulsi-mcp` (agent interface) | agent request → plan/diff → human approves → applied; config edits | done |
| 5b | Ocimum Assistant | chat window: plain-language request → tulsi-mcp → approve → applied | next |
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

## Phase 4 (done)
- [x] Design change: adopt store installs instead of a bridge extension (ADR 0007; signing made the bridge impractical)
- [x] `tulsi-extwatch` user service: watches Firefox and Chromium/Chrome/Brave profiles, store installs only
- [x] Notice "Extension will be installed declaratively" with a "Keep it imperative" grace period (remembered)
- [x] polkit action `org.tulsi.extensions`; password-free for active local users (`adopt.withoutPassword`)
- [x] Software Center **Extensions** tab (list + remove)
- [x] `checks.browser-extensions` (non-admin adoption, side-loaded ignored, keep honored, packages still need admin)
- [x] `scripts/vm-e2e.sh`: adoption in Cinnamon with a real rebuild into Firefox policy

Known limits, picked up later:
- The Extensions tab shows extension ids, not names (state.json stores ids only).
- Extensions apply to all users of the machine (policies are system-wide).
- Extensions installed from sources other than the two official stores stay imperative.

## Phase 5 (done): tulsi-mcp
- [x] MCP server (stdio, JSON-RPC, protocol 2024-11-05 … 2025-11-25), 10 tools (docs/MCP.md)
- [x] Mandatory approval: `ocimum-approve` desktop dialog (Reject by default) → MCP elicitation → refuse
- [x] tulsid `GetConfig` / `PlanConfig` / `ApplyConfig`: configuration.nix edits with syntax check, diff,
      rollback on failed rebuild, history and undo (transactions now cover any managed file)
- [x] Tests: 9 protocol unit tests (fake backend), `checks.mcp` VM test (approve, deny, invalid input,
      config edit, failed-rebuild rollback, undo, real dialog), `vm-e2e.sh` agent config edit with a real rebuild

Known limits, picked up later:
- Validation before approval is syntax-only; option/type errors show up in the rebuild (then rolled back).
- Approval cannot stop an agent that also has a shell; see docs/MCP.md.

## Next up: Phase 5b, Ocimum Assistant
- [ ] Chat window (Python/GTK 3) with a Claude API provider (pluggable), tool loop over tulsi-mcp
- [ ] API key storage in the user keyring (libsecret), model choice, conversation history
- [ ] Cinnamon panel applet / keyboard shortcut to open it
- [ ] Tests with a scripted fake LLM provider
