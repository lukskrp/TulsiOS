# ADR 0010: Login screen: greetd and the Ocimum Greeter

Status: accepted (2026-11-13)

## Context

TulsiOS needs a login screen for Ocimum Desktop, which runs on X11 served by XLibre
(ADR 0009). The candidates:

- **LightDM**, the Cinnamon default TulsiOS used so far: avoided entirely, it has been
  buggy.
- **SDDM** depends on Qt and KDE libraries, and its current versions prefer Wayland.
- **GDM** was the first choice, as the most stable. But GDM 51 (tulsipkgs, GNOME 51) shows
  its login screen only as gnome-shell running as a Wayland compositor: GNOME 50 removed
  the X11 greeter, and NixOS removed `services.displayManager.gdm.wayland = false`
  ("no longer supported with GNOME 50"). It still starts X11 sessions afterwards, but the
  login screen itself would be Wayland, with gnome-shell, mutter and GTK 4.

## Decision

- **greetd** (in nixpkgs, unchanged) is the login daemon. It runs on VT1, authenticates
  through PAM and starts sessions. It has no toolkit or display server of its own.
- **The Ocimum Greeter** (`apps/ocimum-greeter`, Python + OTK) is the login screen. It
  runs inside an XLibre server of its own, started as the unprivileged `greeter` user
  through logind (`nix/modules/ocimum-greeter.nix`).
  - It shows the user name, password, the X sessions in
    `services.displayManager.sessionData`, Restart and Shut down.
  - It passes PAM's prompts through, so further questions such as a new password or a
    one-time code also work.
  - It remembers the last user.
- After a login, `ocimum-x-session` starts the chosen session on a fresh XLibre server
  running as the user, through NixOS's session wrapper, like every NixOS display manager.
  Autologin uses greetd's `initial_session` with the same launcher.

## Consequences

- No Wayland, Qt or LightDM anywhere in the login path; neither X server runs as root.
- The login screen is TulsiOS's own code, styled like the desktop and built on OTK, so it
  can follow OTK and OSK (e.g. `OTK_RENDERER`).
- TulsiOS maintains the greeter: login flow, accessibility, multi-monitor layout and
  on-screen keyboard are its job. The first version covers one monitor and keyboard
  input.
- `checks.greeter-login` logs in through the greeter (wrong password, right password,
  logout). `checks.ocimum-desktop` logs in through greetd's autologin.
