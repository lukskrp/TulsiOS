"""Versions of a file or folder in /home's snapshots (ADR 0027), without GTK.

snapper keeps snapshots of /home in /home/.snapshots/N/snapshot, with an
info.xml beside each. A snapshot is /home as it was, every home with its own
permissions, so a person can read their own files in it and nobody else's.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

HOME_ROOT = Path("/home")


def snapshots_dir() -> Path:
    return Path(os.environ.get("TULSI_SNAPSHOTS", str(HOME_ROOT / ".snapshots")))


def home_root() -> Path:
    return Path(os.environ.get("TULSI_HOME_ROOT", str(HOME_ROOT)))


@dataclass
class Snapshot:
    number: int
    date: datetime  # UTC
    description: str
    path: Path  # the snapshot's copy of /home

    @property
    def label(self) -> str:
        return self.date.astimezone().strftime("%Y-%m-%d %H:%M")


@dataclass
class Version:
    snapshot: Snapshot
    path: Path  # the file or folder inside the snapshot
    size: int
    mtime: float
    is_dir: bool


def snapshots() -> list[Snapshot]:
    """Every snapshot, newest first."""
    out = []
    root = snapshots_dir()
    if not root.is_dir():
        return out
    for entry in root.iterdir():
        if not entry.name.isdigit():
            continue
        info, snap = entry / "info.xml", entry / "snapshot"
        if not snap.is_dir():
            continue
        description, date = "", None
        try:
            tree = ET.parse(info)
            description = (tree.findtext("description") or "").strip()
            stamp = tree.findtext("date")
            if stamp:
                date = datetime.strptime(stamp.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except (OSError, ET.ParseError, ValueError):
            pass
        if date is None:
            date = datetime.fromtimestamp(snap.stat().st_mtime, timezone.utc)
        out.append(Snapshot(int(entry.name), date, description, snap))
    return sorted(out, key=lambda s: s.number, reverse=True)


def relative(path: Path) -> Path:
    """`path` relative to /home, or ValueError for anything outside it."""
    path = Path(os.path.abspath(path))
    try:
        rel = path.relative_to(home_root())
    except ValueError:
        raise ValueError(f"{path} is not in a home folder; only home folders have a history") from None
    if not rel.parts or rel.parts[0] == ".snapshots":
        raise ValueError(f"{path} is not a file or folder in a home folder")
    return rel


def _size(p: Path) -> int:
    if p.is_dir():
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file() and not f.is_symlink())
    return p.stat().st_size


def versions(path: Path) -> list[Version]:
    """The distinct versions of `path` in the snapshots, newest first: a version
    is listed once, at the newest snapshot that has it."""
    rel = relative(path)
    out: list[Version] = []
    for snap in snapshots():
        p = snap.path / rel
        try:
            st = p.stat()
        except (FileNotFoundError, PermissionError, NotADirectoryError):
            continue
        is_dir = p.is_dir()
        v = Version(snap, p, 0 if is_dir else st.st_size, st.st_mtime, is_dir)
        if out and not is_dir and (out[-1].mtime, out[-1].size) == (v.mtime, v.size):
            continue  # the same version as in the newer snapshot
        if out and is_dir and out[-1].is_dir and out[-1].mtime == v.mtime:
            continue
        out.append(v)
    return out


def version_at(path: Path, number: int) -> Version | None:
    """`path` as snapshot `number` has it, or None."""
    rel = relative(path)
    snap = next((s for s in snapshots() if s.number == number), None)
    if snap is None:
        return None
    p = snap.path / rel
    try:
        st = p.stat()
    except (FileNotFoundError, PermissionError, NotADirectoryError):
        return None
    return Version(snap, p, 0 if p.is_dir() else st.st_size, st.st_mtime, p.is_dir())


def trash(path: Path) -> None:
    """Moves `path` to the person's trash (restorable from the file manager)."""
    for cmd in (["gio", "trash", "--", str(path)], ["trash-put", "--", str(path)]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, check=True)
            return
    raise RuntimeError("no trash command (gio or trash-put) found")


def restore(path: Path, version: Version, as_copy: bool = False) -> Path:
    """Puts `version` back at `path`. The file there now goes to the trash first,
    so nothing is lost. With `as_copy`, it goes next to it instead, named after
    the snapshot's date. Returns where it went."""
    path = Path(os.path.abspath(path))
    if as_copy:
        stem, suffix = (path.name, "") if version.is_dir else (path.stem, path.suffix)
        target = path.with_name(f"{stem} (from {version.snapshot.label.replace(':', '.')}){suffix}")
    else:
        target = path
        if target.exists() or target.is_symlink():
            trash(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if version.is_dir:
        shutil.copytree(version.path, target, symlinks=True)
    else:
        shutil.copy2(version.path, target, follow_symlinks=False)
    return target


def free_bytes() -> int:
    st = os.statvfs(home_root())
    return st.f_bavail * st.f_frsize


def free_space(keep: int, *, wait: float = 5.0) -> tuple[list[int], int]:
    """Deletes all but the newest `keep` snapshots (snapper, as a member of
    wheel). Returns the numbers deleted and the bytes freed (btrfs frees the
    space in the background; this waits up to `wait` seconds for it)."""
    numbers = [s.number for s in snapshots()][max(keep, 0):]
    if not numbers:
        return [], 0
    before = free_bytes()
    subprocess.run(["snapper", "-c", "home", "delete", *map(str, numbers)], check=True)
    deadline = time.monotonic() + wait
    after = free_bytes()
    while after <= before and time.monotonic() < deadline:
        time.sleep(0.5)
        after = free_bytes()
    return numbers, max(after - before, 0)


def available() -> str | None:
    """None when snapshots can be browsed, else why not, for the person."""
    if not snapshots_dir().is_dir():
        return ("Your files have no history yet. Turn it on in the TulsiOS Welcome window "
                "(tulsi-welcome), or with `tulsi config`: tulsi.homeSnapshots.enable = true;")
    return None


def human(n: int) -> str:
    size = float(n)
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if size < 1000 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "bytes" else f"{size:.1f} {unit}"
        size /= 1000
    return f"{n} bytes"
