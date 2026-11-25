# ADR 0027: Home folder history, the Welcome window, and the trash

Status: accepted (2026-11-25).

## Context

TulsiOS can undo any change to the system, but nothing protected people's own
files.

- **Deleting was final.** A file deleted with `rm` (or by an agent), or
  overwritten, was gone. ADR 0014 said so: home files were outside undo.
- **The trash didn't help much.** It caught only file-manager deletes, was
  never emptied, and dwm had none.
- **The disk didn't help either.** The installer defaulted to ext4, which has
  no cheap snapshots.

## Decision

- **btrfs by default.** The installer's partition settings (TulsiOS's own
  `partition.conf`, replacing upstream's) make btrfs the default, with ext4, xfs
  and f2fs still on offer. As before, `/home` and `/nix` are subvolumes and
  everything is compressed with zstd.
- **Snapshots of `/home`, opt-in** (`tulsi.homeSnapshots`, off by default).
  - snapper keeps 24 hourly, 7 daily and 4 weekly snapshots in
    `/home/.snapshots`. Each costs only what changed since the one before.
  - Every home keeps its own permissions inside a snapshot, so people see only
    their own files.
  - Members of `wheel` may delete snapshots.
  - The setting asserts that `/home` is on btrfs.
- **The Welcome window** (`tulsi-welcome`) opens once per person, at their first
  login after TulsiOS is installed on a real computer. It doesn't open in
  virtual machines or on the live ISO.
  - It points to the Software Center, AI Agents, Themes and Agent Privileges.
  - It asks "Keep a history of your files?", explaining the space it takes and
  that snapshots are not a backup.
  - Turning it on is a `tulsi config` edit (`tulsi.homeSnapshots.enable =
    true;`): recorded, approved with the person's password, and undoable.
  - On ext4 it explains why the history isn't available.
  - `tulsi-welcome --turn-on-history` does the same from a terminal.
- **File History** (`ocimum-file-history`):
  - It lists the distinct earlier versions of a file or folder.
  - It can open one, restore it (what is there now goes to the trash first), or
    restore it as a dated copy.
  - **Free Space Now** deletes all but the newest N snapshots and reports the
    space freed.
  - It is opened from Nemo's and Dolphin's right-click "Previous Versions…" and
    from the menu. `tulsi-file-history list|restore|snapshots|free` does the
    same in a terminal, for dwm and agents.
- **The trash empties itself.** A daily user timer runs `trash-empty 30` on every
  desktop, and `trash-cli` gives terminals and dwm a trash too.
- **Agents are told** (the `tulsios` skill) to trash files instead of `rm`, and
  that `tulsi-file-history` can bring files back.

## Consequences

- An install on btrfs can turn the history on at any time. One on ext4 can't
  without reinstalling.
- Snapshots are on the same disk: they undo mistakes, not a disk failure. The
  Welcome window and File History both say so.
- Without btrfs quotas, File History can't say beforehand how much deleting a
  snapshot frees. It measures afterwards.
- Disk use: snapshots hold what was deleted or changed for up to four weeks.
  "Free Space Now" and the weekly limits bound it. The system's own cleanup is
  ADR 0025.

## Verification

- **`checks.home-snapshots`** (VM with a btrfs `/home`):
  - deleted and overwritten files and a folder come back, a version as a copy too;
  - restoring over a file puts it in the trash first;
  - another user can't read them;
  - "free space" keeps only the newest;
  - the trash timer is there;
  - the Welcome window stays closed at first login in a VM;
  - `--turn-on-history` adds the setting through `tulsi config`, and `tulsi undo`
    takes it back.
- **Unit tests** (`apps/ocimum-file-history/tests`): versions, restore,
  free space, the Welcome window's config edit and when it shows.
