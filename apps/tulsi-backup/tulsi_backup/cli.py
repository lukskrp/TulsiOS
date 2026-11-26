"""tulsi-backup: the terminal way (the window does the same through buttons).

usage: tulsi-backup backup TARGET [--home DIR] [--exclude NAME...]
       tulsi-backup restore BACKUP [--home DIR]
       tulsi-backup list TARGET
"""

from __future__ import annotations

import argparse
import sys

from . import system


def _backup(args: argparse.Namespace) -> int:
    ok, message = system.backup(args.home, args.target, tuple(args.exclude or system.DEFAULT_EXCLUDES))
    print(message)
    return 0 if ok else 1


def _restore(args: argparse.Namespace) -> int:
    ok, message = system.restore(args.backup, args.home)
    print(message)
    if ok:
        _packages(args.backup)
    return 0 if ok else 1


def _packages(backup: str) -> None:
    from pathlib import Path

    try:
        manifest = system.Manifest.from_json((Path(backup) / system.MANIFEST).read_text())
    except (OSError, ValueError):
        return
    if manifest.packages:
        print("Software in this backup (reinstall with `tulsi install ...`):")
        for package in manifest.packages:
            print(f"  {package}")


def _list(args: argparse.Namespace) -> int:
    backups = system.list_backups(args.target)
    if not backups:
        print(f"No backups in {args.target}.")
        return 0
    for path, manifest in backups:
        if manifest is None:
            print(f"{path} (unreadable manifest)")
        else:
            print(f"{path} — {manifest.date}, {manifest.tulsios_version}, {len(manifest.packages)} packages")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tulsi-backup", description="Back up your files and software list, and restore them.")
    sub = parser.add_subparsers(dest="command", required=True)
    backup = sub.add_parser("backup", help="mirror home into a new timestamped backup")
    backup.add_argument("target", help="a folder on a USB drive, e.g. /run/media/you/STICK")
    backup.add_argument("--home", default=str(system.default_home()), help="the home folder to back up")
    backup.add_argument("--exclude", action="append", default=[], help="a top-level name to skip (repeatable)")
    backup.set_defaults(func=_backup)
    restore = sub.add_parser("restore", help="merge a backup's files back (never deletes)")
    restore.add_argument("backup", help="the timestamped backup folder")
    restore.add_argument("--home", default=str(system.default_home()), help="the home folder to restore into")
    restore.set_defaults(func=_restore)
    listing = sub.add_parser("list", help="list the backups on a drive")
    listing.add_argument("target", help="the folder backups were made in")
    listing.set_defaults(func=_list)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
