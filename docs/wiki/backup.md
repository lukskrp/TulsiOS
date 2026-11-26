# Backing up

Two different safeties for two different disasters:

- **Snapshots** (automatic, hourly/daily/weekly) undo mistakes on this disk:
  browse them in File History. They die with the disk.
- **Backups** survive a dead disk or a new machine: your files *and* which
  software you chose, on a USB drive.

Back up (app menu → Backup, or `tulsi-backup backup /run/media/you/STICK`):
each run makes a new timestamped folder with your home folder and a manifest
(when, which TulsiOS, which packages). Caches and trash are skipped.

Restore (`tulsi-backup restore <backup>` or the window's Restore): files merge
back — nothing already there is deleted. Then reinstall the software the
manifest kept: `tulsi install` lists them, or pick them in the Software
Center.

Backups are plain files, readable anywhere. Plug the drive into any computer
to copy a file out by hand.
