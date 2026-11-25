# ADR 0020: SonicDE, a KDE-style desktop on X11

Status: accepted (2026-11-24).

## Context

The installer offers Ocimum Desktop (a Cinnamon fork) and dwm (ADR 0016). People who prefer a KDE-style desktop had no choice, and KDE Plasma itself is Wayland-only since 6.8. TulsiOS runs on XLibre.

[SonicDE](https://github.com/Sonic-DE) is a community fork of KDE Plasma 6 that keeps X11.
- **About 145 repositories:** frameworks, Plasma, apps.
- **Its releases track KDE's:** Frameworks 6.31.0.x, Plasma 6.8.2, apps 26.08.3.
- **It keeps KDE's internal names** (`KF6…`, `plasma-workspace`, KWin's X11 build), so each fork stands in for its KDE original.
- **Its X11 session** is `sonicde.desktop`.
- **Its desktop depends on Sonic's own frameworks.** They add API KDE does not have; for example, Silver (Sonic's theme) and its Qt theme bridge use `KToolsArea` from Sonic's KColorScheme. They also use Sonic-only libraries (`SonicLogging`, `SonicIpc`).

## Decision

**SonicDE is a third desktop:** `tulsi.desktop.session = "sonic"`, offered in Calamares as "SonicDE (KDE-style)".

**Packages: tulsipkgs' `sonicPackages` (`pkgs/sonic`), the whole Sonic stack.**
- It is `kdePackages.overrideScope`. Each fork keeps tulsipkgs' KDE recipe and takes Sonic's tagged source (`sources.json`).
- **`update.py`** builds `sources.json`. It maps each Sonic repository to its KDE upstream through sonicde-builder's configuration, and picks Sonic's newest release tags.
- **Projects Sonic has not forked or tagged** use KDE's tarball of the same Frameworks (6.31.0) or Plasma (6.8.2) release, so each layer is one release.
- **Its own recipes:**
  - `kwin` (sonic-win, KWin's X11 build);
  - `silver`, `kgamma`, `sonic-logging`, `sonic-ipc`.
- **Adjustments to nixpkgs' KDE recipes,** each commented in `default.nix`:
  - Sonic's forks get Sonic's libraries and lose KDE's Wayland-only dependencies;
  - Sonic's ECM learns the QML import path, as KDE's ECM does since 6.32;
  - Qt 5 outputs and patches for files Sonic removed are dropped;
  - a few inputs Sonic's forks need are added: FFmpeg and PulseAudio for Screenies, libei for the portal.
- **KDE's own set stays as `kdePackagesKDE`.** `sonicPackages` is built from it, and the KDE scope splices by that name.

**The desktop: TulsiOS's `sonic.desktop` module (`nix/modules/sonic-desktop.nix`).** It is an X11 counterpart of nixpkgs' Wayland-only `plasma6` module.
- XLibre, logging in through the Ocimum Greeter (the `sonicde` session).
- **The same services:** polkit agent, KWallet, the portal, udisks, power profiles, the lock screen's PAM service.
- **Sonic's apps:** Ecco (files), Sonic Terminal, System Monitor, Screenies (screenshots).
- **TulsiOS's apps and integrations, as on Ocimum:** Starah, the Software Center, the Assistant, the Nix Editor, `tulsi.adopt`, and Brave Origin as the default browser.
- **Defaults (`sonic-tulsi-defaults`),** which users can change:
  - a look-and-feel, "TulsiOS (Silver)": Sonic's default with the Tulsi Leaf wallpaper and the TulsiOS start button;
  - pinned apps: files, browser, terminal, Software Center, Assistant;
  - chosen for new users through `/etc/xdg/kdeglobals`.
- **Super+A opens the Assistant on SonicDE** through `X-KDE-Shortcuts=Meta+A` in the Assistant's own `.desktop` file, the way Konsole declares Ctrl+Alt+T. kglobalacceld reads that line on first start. It ignores `/etc/xdg/kglobalshortcutsrc`, because it opens that file with no system cascade. Ocimum binds the same key through gsettings.
- **KDE apps on a SonicDE machine are Sonic builds.** The module overlays `kdePackages` with `sonicPackages`, so `kdePackages.kate` from the Software Center or `tulsi install` is built on Sonic's frameworks. A session then has one copy of each KDE library, and the apps keep X11.

**Installing is online only.** The ISO carries Ocimum and dwm, and its size does not change.
- SonicDE comes from the TulsiOS cache during the installation.
- A new Calamares job, `tulsios-online`, runs before partitioning. If SonicDE is chosen and the cache does not answer, it stops with a clear message, before anything is written to the disk.

## Sonic's names

Sonic renames some programs and D-Bus objects. Scripts and tests that talk to the session use these names:

| KDE | SonicDE |
| --- | --- |
| `kwin_x11` | `sonic-win` |
| `plasmashell`, `org.kde.plasmashell` `/PlasmaShell` | `sonicshell`, `org.sonicde.sonicshell` `/SonicShell` (`evaluateScript` as before) |
| `spectacle` | `sonic-screenies` (package and `.desktop` file keep `spectacle` / `org.kde.spectacle.desktop`) |
| `dolphin`, `konsole`, `plasma-systemmonitor` | unchanged (shown as Ecco, Sonic Terminal, System Monitor) |

## Consequences

- **A KDE-style desktop on XLibre,** in the installer, with TulsiOS's own apps and defaults. `checks.sonic-desktop` covers it: greeter login on XLibre, sonic-win and the shell, the look-and-feel and pinned apps, Super+A, the four apps.
- **Sonic is a large second stack to build:** about 75 frameworks, 50 Plasma projects and the apps.
  - **First builds take hours.** Every TulsiOS release builds the SonicDE system closure and pushes it to the TulsiOS cache before the ISO is published (`docs/RELEASING.md`).
  - **Popular KDE apps,** as Sonic builds, are pushed with it; otherwise installing one on SonicDE compiles it.
- **Following Sonic's releases** means re-running `update.py` and building. A fork that moves past nixpkgs' recipe needs an adjustment in `pkgs/sonic`.
- **Sonic's frameworks lag KDE's by a release** (6.31 vs 6.32). On a SonicDE machine all KDE software uses Sonic's.
- **Sonic's KWindowSystem robustness fix** (an unreleased commit after 6.31.0, for headless callers) comes with Sonic's next frameworks tag. It is not patched in.
- **The Wayland-only pieces are left out:** KDE's `layer-shell-qt`, `kwayland`, `plasma-nano` and KInfoCenter's Wayland page.
- **Qt's XLibre platform plugin (QXLibre) is not packaged yet.** The session asks for `xlibre;xcb`, and Qt falls back to its xcb plugin, which works. Packaging QXLibre is a follow-up.
- **Known rough edge:** the splash screen's D-Bus name times out (about 60 s after login, in the log only); the desktop is usable before then.
