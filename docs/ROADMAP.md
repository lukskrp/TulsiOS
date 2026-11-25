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
| 6a | tulsipkgs + TulsiOS cache | flake on tulsipkgs; CI builds TulsiOS-owned packages and pushes them to cache.skarptech.org | done |
| 6b | Ocimum Desktop | hard fork of Cinnamon 6.8 built by tulsipkgs; branding, TulsiOS defaults, Tulsi applets | in progress |
| 7 | Installer ISO + release | Calamares ISO installs TulsiOS (Ocimum, SonicDE or dwm) on Hyper-V / bare metal | in progress |

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

## Phase 6a (done): tulsipkgs and the TulsiOS cache (ADR 0008)
- [x] tulsipkgs, a hard fork of nixpkgs (branch `tulsi-unstable`), is the flake's `nixpkgs` input
- [x] `gtk3-o` and `otk` packaged in tulsipkgs (the `gtk3-o` flake input is gone)
- [x] `tulsi-release.nix` (`built` / `curated`) and `check-upstream.sh`; `tulsi-build` and daily `tulsi-sync` workflows
- [x] Attic deployment files for cache.skarptech.org (SkarpTech_Website `deploy/attic/`); `tulsi.cache` module
- [x] Cache server running; CI secrets set; `tulsi.cache.publicKey` filled in
- [x] A clean machine downloads Cinnamon from the TulsiOS cache instead of building it
      (an Ocimum Desktop install on a ThinkCentre E72, online)

## Phase 6b (in progress): Ocimum Desktop
- [x] `lukskrp/ocimum-desktop` branch `ocimum`: hard fork of Cinnamon 6.8.0 with session name, logo,
      System Info and pinned Software Center / Assistant
- [x] The whole Cinnamon 6.8 suite built by tulsipkgs; `cinnamon` PAM service for the 6.8 screen locker
- [x] `ocimum.desktop`: Mint-Y-Dark, Tulsi Leaf wallpaper, TulsiOS start button (colour, or white
      for dark panels), Super+A opens the Assistant; `checks.ocimum-desktop`
- [ ] Panel applet for the Assistant; TulsiOS default panel layout
- [x] Brave Origin comes with the desktop (also on the live USB): installed, the default browser,
      and in the panel's launchers (Files, Brave Origin, Terminal) for new users
      (`ocimum.desktop.browser`, `ocimum.desktop.panelLaunchers`); `checks.ocimum-desktop`
- [x] Background daemon on OTK (OTK 1 API: monitor list model, connector, `gtk_disable_portals()`);
      Ocimum is X11-only; `checks.ocimum-desktop` checks the painted wallpaper colour live
- [x] OSK core (ADR 0009): GTK 4.24's render nodes, `.node` format, textures and Cairo renderer as
      `libosk-3` (`osk-3.0`, `Osk-3.0`); GTK 4's GSK tests pass with the Cairo renderer
- [x] OSK: `GtkSnapshot` and the widget `snapshot` vfunc (OTK 2, `libotk-3.so.1`),
      `OTK_RENDERER=legacy|cairo|gl`; GTK 3's suites give identical results with both renderers
- [x] XLibre 25.1.11 is the X server (tulsipkgs' `xorg-server`), with XLibre's forks of every
      `xf86-*` driver; `checks.ocimum-desktop` checks the session runs on XLibre's server and drivers
- [x] Login screen (ADR 0010): greetd + the Ocimum Greeter (OTK) on XLibre, X servers run as
      the user; no LightDM/SDDM/GDM; `checks.greeter-login` logs in through it
- [x] TulsiOS boots the newest stable kernel (`linuxPackages_latest`, 7.3.4) with redistributable
      firmware (`nix/modules/kernel.nix`); LTS via `boot.kernelPackages = pkgs.linuxPackages`
- [x] Starah (ADR 0011, `~/Starah`): levels of privilege for agents; the Assistant's tulsi-mcp runs as
      the sandboxed agent `assistant`; first-login setup window; `checks.starah-setup`
- [ ] Starah: Landlock/network rules per agent, panel indicator for requests
- [x] AI agent CLIs (ADR 0012): tulsipkgs fast-tracks free ones (`tulsi-agents.yml`, PR per release);
      proprietary ones install after a person accepts their licence in the Software Center
- [x] Install the TulsiOS way (ADR 0013): `apt`/`dnf`/… shims, downloaded packages and foreign
      binaries open `tulsi-adopt`; the Assistant packages unpackaged software as a local package
      (`tulsi/pkgs/<name>`), a person approves, Undo removes it; `checks.adopt`, `checks.local-package-eval`
- [ ] Share local packages back to tulsipkgs (opt-in)
- [x] Find the package first (ADR 0018, milestone 1): tulsid `Match` (curated names and
      services, other distributions' naming rules, `pip`/`npm`/… package sets, the program
      index from nix-index-database), `tulsi-inspect` (`tulsi inspect`: .deb/.rpm metadata,
      programs inside), `pip`/`npm -g`/`cargo`/`gem`/`go`/`flatpak` install shims, extension
      store links ("Add by Link", `tulsi-adopt --url`); `checks.adopt`
- [x] Recipes (ADR 0018, milestone 2): `tulsi-recipes` (`tulsi recipe plan|build|install`)
      packages AppImages, prebuilt programs (.deb, .rpm, tar, zip) and CMake/Meson/autotools/
      make/Cargo/Go source without a model, fixing missing libraries, build dependencies and
      dependency hashes itself, and tries the result in a bubblewrap sandbox; the popup's
      Recipe-or-Assistant choice, remembered (`~/.config/tulsi/packaging.json`, also in
      Starah's window); kept downloads (state.json `keepSources`, `tulsi keep-source`);
      `checks.adopt`, `checks.local-package-eval`
- [ ] Recipes: fonts, Qt applications (`wrapQtAppsHook`), Python projects
- [x] Install wizard (ADR 0018, milestone 3): step-by-step `tulsi-adopt` (What it is, In
      TulsiOS, How to package it, Details, Build and try, Install; opens on the matches when
      there are any); "Install from a File or Link…" in the Software Center; `checks.adopt`
      walks it by keyboard to an install
- [x] Nix Editor (ADR 0019): `ocimum-nix-editor` with nixd (completion, hover, problems,
      offline against the pinned nixpkgs), TulsiOS's local-package rules, and a Nix guide
      written for TulsiOS beside the file; "Edit It Yourself" opens a failed Recipe's draft,
      with Build and Try and Install (`tulsi recipe check|build-draft|ops`);
      `checks.nix-editor`, `checks.nix-guide`, `checks.adopt`
- [ ] tulsi-index-database-xx: TulsiOS's own program index (packages' main programs,
      nix-index-database with a weekly PR, a hand-kept list); shelved for now
- [x] Reversible changes don't ask (ADR 0014): `org.tulsi.apply` (rollback undoes it) vs
      `org.tulsi.configure` (accounts, boot, scripts, local packages; `configuration.nix` edits
      are checked by `tulsi_state::unreversible_settings`); the Assistant's agent defaults to
      level 2; tulsi-mcp receipts; the Assistant's receipt line with Undo and claim check
- [x] Undo any change (ADR 0015): `UndoChange`/`PlanUndo` (state.json by meaning,
      configuration.nix three-way with a conflict refusal), `Tulsi-By` records who; History page
      rows with Undo and "by the Assistant", `tulsi undo ID`, tulsi-mcp `undo_change`
- [ ] Greeter: several monitors, user list with avatars, accessibility (screen reader, on-screen keyboard)
- [x] `cinnamon-session-quit` works: tulsipkgs' cinnamon-session wraps its typelibs; `otk`
      propagates `graphene`, so Python OTK apps need only `otk`
- [ ] OSK: GSK's GL renderer on X11
- [ ] Package Velocitty, or choose the default terminal for good

Known limits:
- Super+Space stays Cinnamon's keyboard-layout switcher, so the Assistant uses Super+A.
- Cinnamon no longer uses GTK 4, but upstream `ibus` (its GTK 4 input-method module) still
  brings `gtk4` into the desktop closure, and `xapp` brings the GTK 3 `gtk-layer-shell`.
- No Wayland session: Ocimum runs on X11, served by XLibre (ADR 0009).
- `tigervnc` (and Xvfb in build sandboxes) still use Xorg 21.1, as `xorg-server-xorg` in tulsipkgs.

## Phase 7 (in progress): installer, ISO, release (ADR 0016)
- [x] `tulsi.desktop.session = "ocimum" | "dwm"`; only the chosen desktop is installed
- [x] dwm 6.8 + systray patch (ported), TulsiOS `config.h` (Super, Super+A/S); XDG autostart,
      polkit agent, dunst, nm-applet, slstatus, GTK theme; `checks.dwm-session`
- [x] `nix/hosts/desktop` for installed machines; one flake template for tulsid and the installer
- [x] `tulsi-install-system` (`apps/tulsi-installer`): validated answers -> system flake ->
      `nixos-install --flake`, offline (`tulsi.installer.offlineSystems`, `nix/lib/install-closure.nix`,
      `nix/lib/offline-rebuild-inputs.nix`)
- [x] Calamares: `calamares-tulsios-extensions` (desktop page, `tulsios` job, branding, slideshow)
- [x] `checks.install-dwm`, `checks.install-ocimum`: empty disk -> offline install -> boots, greeter
      login, `/etc/nixos` evaluates to the running system
- [x] Live ISO `nixosConfigurations.tulsi-iso` (hybrid ISO = the dd image), artwork (boot menus);
      `checks.live-session`, `checks.install-iso-references`, `checks.iso-boot`
- [ ] Calamares run by hand in QEMU (BIOS and UEFI), Hyper-V Gen 2 and one bare-metal machine
- [ ] Artwork package of its own (wallpaper and logo without Cinnamon), dwm wallpaper
- [x] Upgrades (ADR 0017): installed flakes follow `stable`, pinned offline at install;
      `tulsi upgrade [--check]`, tulsid `CheckUpgrade`/`Upgrade` (undoable), daily
      notification, Software Center Updates page; `VERSION`; `docs/RELEASING.md`
- [ ] Create the `stable` branch; a real upgrade over the network, checked by hand
- [x] Live ISO boot hang under UEFI (2026-11-20): Plymouth raced the graphics driver's
      takeover from the firmware framebuffer and stopped forwarding the console it
      redirects, stalling systemd. The ISO has no boot splash now (boot messages show)
- [ ] Release v0.1.0: ISO + SHA-256 on GitHub Releases

### SonicDE, the third desktop (ADR 0020)
- [x] tulsipkgs `sonicPackages` (`pkgs/sonic`): the whole Sonic stack (Frameworks 6.31.0.x,
      Plasma 6.8.2, apps 26.08.3) on nixpkgs' KDE recipes; sonic-win, Silver, SonicLogging/Ipc
- [x] `sonic.desktop` module, `tulsi.desktop.session = "sonic"`: XLibre, Ocimum Greeter,
      Ecco / Sonic Terminal / System Monitor / Screenies, TulsiOS apps, Brave Origin;
      look-and-feel "TulsiOS (Silver)" (wallpaper, start button, pinned apps), Super+A;
      `kdePackages` is Sonic's set on SonicDE machines
- [x] Calamares: third desktop item (online only); `tulsios-online` job refuses before
      partitioning when the cache does not answer
- [x] `checks.sonic-desktop`
- [x] `checks.install-sonic`: install from a cache node (Harmonia); the refusal without one is covered by the installer's unit tests (`test_online_job.py`)
- [ ] The release pipeline pushes the SonicDE closure and popular Sonic-built KDE apps to the cache
- [ ] QXLibre (Qt's XLibre platform plugin); the splash screen's D-Bus timeout at login

Known limits:
- The Calamares GUI is not covered by automated tests; its install job is (`tulsi-install-system`).
