# Disk space

TulsiOS keeps every version of the system side by side, so any change can be undone.
To stop that from filling the disk, once a week it:

- removes system versions older than 30 days (always keeping the newest 10, and the one
  you started);
- deletes files no system version uses any more;
- and, as files are added, stores identical ones only once.

Undo works however old the change is: TulsiOS rebuilds the earlier system from its
record. Only the boot menu's "older versions" are limited to the newest 10.

The system's log is kept under 1 GB, and the trash empties what has been there over 30
days.

## Freeing more

- Empty the trash.
- File History › **Free Space Now…** deletes older snapshots of your files.
- The Software Center's Installed page: remove what you don't use.
- In a terminal, as an administrator: `sudo tulsi-cleanup` runs the weekly cleanup now.
