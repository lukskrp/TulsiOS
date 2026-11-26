# Updating TulsiOS

TulsiOS tells you when a new release is out, upgrades without losing your
apps and files, and can always go back.

- **Update Manager** (app menu → Update Manager): the release (Check Again,
  Upgrade), Older Versions (every change adds a system version; restart and
  pick one in the boot menu to go back with your files untouched; Remove Old
  Versions Now frees space the same way the weekly cleanup does), and
  Snapshots (take one now, open File History to browse them).
- **Before every upgrade** a snapshot of /home is taken automatically (needs
  File History on — the installer's default on btrfs). The upgrade itself
  adds a new version; undo it any time in the Software Center's History or
  with `tulsi undo`.
- **Notifications:** once per release a notification appears; its button
  opens the Software Center's Updates page, which upgrades the same way.
- **Terminals:** `tulsi upgrade --check` asks, `tulsi upgrade` upgrades
  (snapshotting first with `tulsi-upgrade`), `tulsi history` lists changes,
  `nix-env -p /nix/var/nix/profiles/system --list-generations` lists versions.
- **Snapshots are on the same disk** as your files: they undo deletes and
  bad edits, they are not a backup. Old versions delete themselves weekly
  (newest 10 kept), and the boot menu lists at most 10.
