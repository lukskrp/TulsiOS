# ADR 0038: Update Manager and Timeshift, Tulsi-style

Status: accepted (2026-11-27).

## Context

Mint has two apps TulsiOS lacked: Update Manager (staged release and package
updates with changelogs, kernel picker, one-click) and Timeshift (snapshot
before, restore when broken). TulsiOS had the machinery but no window:

- `tulsi upgrade` / `tulsi upgrade --check --notify` (a desktop notification
  once per release, opening the Software Center's Updates page), `tulsi
  history`, `tulsi undo`, generations in the boot menu, weekly cleanup of old
  versions (ADR 0025), hourly/daily/weekly /home snapshots with File History
  (ADR 0027).
- Nothing checked daily on its own, nothing took a snapshot before an upgrade,
  and generations/snapshots were terminal-only (`nix-env --list-generations`,
  `snapper -c home list`).

## Decision

**`tulsi.updater`** (`nix/modules/updater.nix`): on with any TulsiOS desktop
(Ocimum, SonicDE, dwm), off on the live installer.

- **Daily release check:** a per-user systemd timer runs `tulsi upgrade
  --check --notify` (`checkInterval`, default `daily`). The notify path is
  unchanged: once per release, a notification whose button opens the Software
  Center's Updates page.
- **Snapshot before upgrading:** `tulsi-upgrade` snapshots /home (snapper,
  `number` cleanup) and then runs `tulsi upgrade`. The Update Manager runs
  this; terminals keep plain `tulsi upgrade`. Without snapper on /home it
  upgrades as today.
- **The window** (`tulsi-update-manager`, three tabs): the release (version,
  check result, Upgrade through tulsid like the CLI), Older Versions (the
  generations with dates and the running one, boot-menu guidance, "Remove Old
  Versions Now" running the same `tulsi-cleanup` as the weekly timer), and
  Snapshots (take one, open File History). Release upgrades themselves stay
  in the Software Center too — both are frontends to `tulsid.upgrade`.
- Going back is never destructive here: older versions boot from the boot
  menu with files untouched, and snapshots browse in File History. The window
  deletes generations only via `tulsi-cleanup` (newest kept, current and booted
  always kept).

## Consequences

- People learn about releases without opening a terminal, and upgrading
  snapshots /home first — Mint's safety net, declarative underneath.
- Upgrades stay undoable (`tulsi undo`, History) and rebuildable (git in
  /etc/nixos); the trial-boot machinery (ADR 0029) is untouched — releases
  apply immediately like all tulsid changes, since a bad one undoes cleanly.
- A user timer per desktop user (not a system timer): checks run in the
  session, where the notification can be shown and clicked.

## Verification

- `tulsi-update-manager` package: 12 unit tests (release-check parsing for
  up-to-date/available/offline/empty, generations and snapshot parsing,
  os-release reading, wrapper preference).
- `checks.updater`: the app and `tulsi-upgrade` installed with menu entry and
  icon, the daily user timer units present with `--check --notify`,
  generations listed with the running one marked, the offline check saying it
  cannot check, `tulsi history` working.
