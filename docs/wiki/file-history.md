# Your files' history

## The trash

Files you delete in the file manager go to the trash, and stay there for 30 days. In a
terminal, `trash FILE` (or `trash-put FILE`) does the same; `rm` deletes for good.

## File History

If you turned it on (the Welcome window, or **File History** in the app menu), TulsiOS
keeps snapshots of the home folders: every hour for a day, every day for a week, every
week for a month.

- **Get a file back:** right-click it (or the folder it was in) › **Previous Versions…**,
  or open **File History** and choose it. **Restore** puts the old version back (what is
  there now goes to the trash first); **Restore as Copy** puts it next to it.
- **In a terminal:** `tulsi-file-history list FILE`, then
  `tulsi-file-history restore FILE` (or `--from N` for an older one, `--copy` for a copy).
- **Free space:** File History › **Free Space Now…** deletes older snapshots.

Each person sees only their own files in the history.

Snapshots are on the same disk as your files: they protect against mistakes, not
against a broken or lost disk. Keep a backup too.

File History needs the btrfs file system, TulsiOS' default. On a computer installed
with another file system it isn't available.
