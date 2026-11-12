# Roadmap

| Phase | Goal | Exit criteria | Status |
|---|---|---|---|
| 0 | Dev environment | WSL on D:, Nix with flakes, KVM available | done |
| 1 | Repo skeleton + state contract | `nix flake check` green; VM boots Cinnamon; editing `state.json` + rebuild installs a package | done |
| 2 | `tulsid` + CLI + polkit + git-backed state | `tulsi install <pkg>` works in the VM; `tulsi undo` works | done |
| 3 | Ocimum Software Center + GTK3-O | install/uninstall from GUI with progress and undo; GTK3-O used system-wide | done |
| 4 | Declarative browser extensions | store install → notice → adopted into policy (Firefox, Chromium, Chrome, Brave) | done |
| 5 | `tulsi-mcp` (agent interface) | agent request → plan/diff → human approves → applied; config edits | done |
| 5b | Ocimum Assistant | chat window: plain-language request → tulsi-mcp → approve → applied | done |
| 6a | tulsipkgs + TulsiOS cache | flake on tulsipkgs; CI builds TulsiOS-owned packages and pushes them to cache.skarptech.org | in progress (cache server pending) |
| 6b | Ocimum Desktop | hard fork of Cinnamon 6.8 built by tulsipkgs; branding, TulsiOS defaults, Tulsi applets | in progress |
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

## Phase 5b (done): Ocimum Assistant
- [x] Chat window (Python/GTK 3): streaming answers, thinking summary in the status line, tool activity,
      Stop, new conversation, example prompts
- [x] Claude provider (`claude-opus-5-5` default; Sonnet/Haiku selectable; effort low/medium/high),
      prompt caching, refusal fallbacks, error mapping; pluggable provider interface
- [x] API key in the keyring (libsecret); falls back to `ANTHROPIC_API_KEY` / `ant auth login`
- [x] Tests: agent loop, MCP client, Markdown, offline SDK integration (local stand-in API server),
      `checks.assistant` VM test (scripted model -> real tulsi-mcp -> tulsid -> state)

Known limits, picked up later:
- No live test against the real Anthropic API in CI (needs a key and costs money); try it with your key.
- Conversations are not saved between sessions.
- Panel applet and global keyboard shortcut come with the Cinnamon fork (Phase 6).

## Phase 6a (in progress): tulsipkgs and the TulsiOS cache (ADR 0008)
- [x] tulsipkgs, a hard fork of nixpkgs (branch `tulsi-unstable`), is the flake's `nixpkgs` input
- [x] `gtk3-o` and `otk` packaged in tulsipkgs (the `gtk3-o` flake input is gone)
- [x] `tulsi-release.nix` (`built` / `curated`) and `check-upstream.sh`; `tulsi-build` and daily `tulsi-sync` workflows
- [x] Attic deployment files for cache.skarptech.org (SkarpTech_Website `deploy/attic/`); `tulsi.cache` module
- [x] Cache server running; CI secrets set; `tulsi.cache.publicKey` filled in
- [ ] A clean machine downloads Cinnamon from the TulsiOS cache instead of building it

## Phase 6b (in progress): Ocimum Desktop
- [x] `lukskrp/ocimum-desktop` branch `ocimum`: hard fork of Cinnamon 6.8.0 with session name, logo,
      System Info and pinned Software Center / Assistant
- [x] The whole Cinnamon 6.8 suite built by tulsipkgs; `cinnamon` PAM service for the 6.8 screen locker
- [x] `ocimum.desktop`: Mint-Y-Dark, basil wallpaper, Super+A opens the Assistant; `checks.ocimum-desktop`
- [ ] Panel applet for the Assistant; TulsiOS default panel layout
- [x] Background daemon on OTK (OTK 1 API: monitor list model, connector, `gtk_disable_portals()`);
      Ocimum is X11-only; `checks.ocimum-desktop` checks the painted wallpaper colour live
- [ ] OTK: port GTK 4's rendering engine as the OSK module (ADR 0009)
- [ ] Package Velocitty, or choose the default terminal for good

Known limits:
- Super+Space stays Cinnamon's keyboard-layout switcher, so the Assistant uses Super+A.
- Cinnamon no longer uses GTK 4, but upstream `ibus` (its GTK 4 input-method module) still
  brings `gtk4` into the desktop closure, and `xapp` brings the GTK 3 `gtk-layer-shell`.
- No Wayland session: Ocimum runs on X11 (XLibre to come, ADR 0009).
