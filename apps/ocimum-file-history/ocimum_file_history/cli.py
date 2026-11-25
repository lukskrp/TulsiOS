"""tulsi-file-history: earlier versions of files in your home folder (ADR 0027).

  tulsi-file-history list PATH                 the versions of PATH in the snapshots
  tulsi-file-history restore PATH [--from N] [--copy]
                                               put a version back (newest by default);
                                               what is there now goes to the trash first;
                                               --copy puts it next to it instead
  tulsi-file-history snapshots                 every snapshot
  tulsi-file-history free [--keep N]           delete all but the newest N snapshots
                                               (default 3) to free disk space
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import history


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tulsi-file-history", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("list")
    p.add_argument("path", type=Path)
    p = sub.add_parser("restore")
    p.add_argument("path", type=Path)
    p.add_argument("--from", dest="number", type=int)
    p.add_argument("--copy", action="store_true")
    sub.add_parser("snapshots")
    p = sub.add_parser("free")
    p.add_argument("--keep", type=int, default=3)
    args = parser.parse_args(argv)

    why = history.available()
    if why:
        print(why, file=sys.stderr)
        return 1
    try:
        if args.command == "snapshots":
            for s in history.snapshots():
                print(f"{s.number}\t{s.label}\t{s.description}")
            return 0
        if args.command == "free":
            numbers, freed = history.free_space(args.keep)
            if not numbers:
                print("Nothing to delete.")
            else:
                print(f"Deleted {len(numbers)} snapshots, freeing about {history.human(freed)}.")
            return 0
        found = history.versions(args.path)
        if args.command == "list":
            if not found:
                print(f"No earlier versions of {args.path}.")
            for v in found:
                size = "folder" if v.is_dir else history.human(v.size)
                print(f"{v.snapshot.number}\t{v.snapshot.label}\t{size}")
            return 0
        # restore
        if args.number is not None:
            at = history.version_at(args.path, args.number)
            found = [at] if at else []
        if not found:
            print(f"No version of {args.path} to restore.", file=sys.stderr)
            return 1
        where = history.restore(args.path, found[0], as_copy=args.copy)
        print(f"Restored {where} from {found[0].snapshot.label}.")
        return 0
    except (ValueError, OSError, RuntimeError) as e:
        print(f"tulsi-file-history: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # snapper failing, …
        print(f"tulsi-file-history: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
