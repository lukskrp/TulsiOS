# ADR 0039: Backup for people, not just snapshots

Status: accepted (2026-11-27).

## Context

Mint's Backup Tool saves two things: your files, and the list of software you
chose — so a new machine becomes yours again in minutes. TulsiOS had half of
each:

- /home snapshots + File History (ADR 0027) undo mistakes on *this* disk;
  a dead disk takes everything with them.
- `tulsi/state.json` already *is* the software list, declarative and in git;
  no window ever offered to carry it to a new machine with the files.

## Decision

**`tulsi.backup`** (`nix/modules/backup.nix`): on with any TulsiOS desktop,
off on the live installer. Installs the Backup app, `tulsi-backup`, and rsync.

- **A backup is `<drive>/<hostname>/<timestamp>/`** with `home/` (an rsync
  mirror of the home folder, caches and trash skipped) and `manifest.json`
  (when, which TulsiOS, which packages). Repeated backups to the same drive
  accumulate; each is complete on its own.
- **Restoring merges** — files come back, nothing already there is deleted.
  Afterwards the manifest's package list is printed to reinstall
  (`tulsi install ...`, or the Software Center): names travel, not gigabytes
  of store paths.
- **Two frontends, one backend:** `tulsi-backup backup|restore|list`
  (terminals, dwm, scripts) and the Backup window (target picker suggesting
  plugged-in USB drives, backup list with Restore, File History linked in
  spirit — snapshots stay where they are).

## Consequences

- People can survive a dead disk and seed a new machine; snapshots stay the
  fast undo for daily mistakes. The wiki says which is which.
- Backups are plain files (rsync + JSON): readable without TulsiOS, rsyncable
  to a NAS, encryptable by putting them on an encrypted drive. No proprietary
  images, no database.
- A backup is only as fresh as its last run — no automatic schedule in this
  slice (a weekly user timer is the obvious follow-up).

## Verification

- `tulsi-backup` package: 10 unit tests (manifest round-trip, rsync command
  shape and excludes, listings newest-first, restore without `--delete`,
  CLI backup/list/restore with software hints, missing-home/no-rsync errors).
- `checks.backup`: app, CLI, rsync and menu entry present; backup writes a
  timestamped manifest + files; two backups list newest-first; restore brings
  back a deleted file while keeping a newer local one.
