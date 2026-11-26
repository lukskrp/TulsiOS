"""Backing up and restoring through rsync, with a manifest (ADR 0039).

A backup is `<target>/<hostname>/<timestamp>/` holding `home/` (an rsync
mirror of the home folder) and `manifest.json` (when, what system, which
software). Restoring merges files back — it never deletes what is already
there. The software itself reinstalls from the manifest's package list
(`tulsi install`, or the Software Center): the backup carries names, not
gigabytes of store paths.

Snapshots (Update Manager, File History) undo mistakes on this disk; a backup
is for a dead disk or a new machine. Anything missing (no rsync, no target,
no manifest) is a plain message, not a crash.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import socket
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

MANIFEST = "manifest.json"
HOME_DIR = "home"

# Caches and trash bloat a backup and rebuild themselves; leave them out.
DEFAULT_EXCLUDES = (".cache", ".local/share/Trash")


def _run(*cmd: str, timeout: int = 7200) -> subprocess.CompletedProcess:
    """Runs a command; a missing program is a failure, not a crash."""
    try:
        return subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout)
    except OSError as e:
        return subprocess.CompletedProcess(list(cmd), 127, "", f"{cmd[0]}: {e.strerror}")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(list(cmd), 124, "", f"{cmd[0]}: timed out")


def rsync_available() -> bool:
    return shutil.which("rsync") is not None


def current_version(os_release: str = "/etc/os-release") -> str:
    try:
        for line in Path(os_release).read_text().splitlines():
            if line.startswith("TULSIOS_VERSION="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return "unknown"


def software_list(state_file: str = "/etc/nixos/tulsi/state.json") -> list[str]:
    """The software chosen in the Software Center, from state.json."""
    try:
        state = json.loads(Path(state_file).read_text())
    except (OSError, ValueError):
        return []
    packages = state.get("packages", [])
    return [p for p in packages if isinstance(p, str)]


def stamp(now: datetime.datetime | None = None) -> str:
    return (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")


@dataclass
class Manifest:
    version: int
    date: str
    hostname: str
    tulsios_version: str
    packages: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2) + "\n"

    @staticmethod
    def from_json(text: str) -> "Manifest":
        data = json.loads(text)
        return Manifest(
            version=int(data.get("version", 1)),
            date=str(data.get("date", "")),
            hostname=str(data.get("hostname", "")),
            tulsios_version=str(data.get("tulsios_version", "unknown")),
            packages=[p for p in data.get("packages", []) if isinstance(p, str)],
        )


def backup_dir(target: str | Path, hostname: str | None = None, when: str | None = None) -> Path:
    host = hostname or socket.gethostname()
    return Path(target) / host / (when or stamp())


def backup(home: str | Path, target: str | Path, excludes: tuple[str, ...] = DEFAULT_EXCLUDES) -> tuple[bool, str]:
    """Mirrors home into a new timestamped backup. Returns (ok, message)."""
    home_path = Path(home).expanduser()
    if not home_path.is_dir():
        return False, f"{home_path} is not a folder."
    if not rsync_available():
        return False, "rsync is not installed."
    dest = backup_dir(target)
    try:
        dest_home = dest / HOME_DIR
        dest_home.mkdir(parents=True)
    except OSError as e:
        return False, f"Cannot write to {dest}: {e.strerror}"
    cmd = ["rsync", "-a", "--delete"]
    cmd += [f"--exclude={e}" for e in excludes]
    cmd += [f"{home_path}/", f"{dest_home}/"]
    done = _run(*cmd)
    if done.returncode != 0:
        return False, (done.stderr.strip() or done.stdout.strip()) or "rsync failed."
    manifest = Manifest(
        version=1,
        date=stamp(),
        hostname=socket.gethostname(),
        tulsios_version=current_version(),
        packages=software_list(),
    )
    try:
        (dest / MANIFEST).write_text(manifest.to_json())
    except OSError as e:
        return False, f"Backup copied, but the manifest failed: {e.strerror}"
    return True, str(dest)


def list_backups(target: str | Path) -> list[tuple[Path, Manifest | None]]:
    """Every backup under target (newest first), with its manifest if readable."""
    found: list[tuple[Path, Manifest | None]] = []
    target_path = Path(target)
    if not target_path.is_dir():
        return found
    for host in sorted(target_path.iterdir()):
        if not host.is_dir():
            continue
        for dated in sorted(host.iterdir(), reverse=True):
            manifest_path = dated / MANIFEST
            if not manifest_path.is_file() or not (dated / HOME_DIR).is_dir():
                continue
            try:
                manifest: Manifest | None = Manifest.from_json(manifest_path.read_text())
            except (OSError, ValueError):
                manifest = None
            found.append((dated, manifest))
    return found


def restore(backup_path: str | Path, home: str | Path) -> tuple[bool, str]:
    """Merges a backup's files back into home. Never deletes. Returns (ok, message)."""
    src = Path(backup_path) / HOME_DIR
    if not src.is_dir():
        return False, f"{backup_path} is not a backup (no {HOME_DIR}/)."
    home_path = Path(home).expanduser()
    if not home_path.is_dir():
        return False, f"{home_path} is not a folder."
    if not rsync_available():
        return False, "rsync is not installed."
    done = _run("rsync", "-a", f"{src}/", f"{home_path}/")
    if done.returncode != 0:
        return False, (done.stderr.strip() or done.stdout.strip()) or "rsync failed."
    return True, f"Restored into {home_path}."


def removable_targets() -> list[Path]:
    """Mounted USB drives and cards, best guesses first (largest free space)."""
    found: list[tuple[int, Path]] = []
    try:
        mounts = Path("/proc/mounts").read_text().splitlines()
    except OSError:
        return []
    for line in mounts:
        parts = line.split()
        if len(parts) < 4:
            continue
        device, point, fstype, _opts = parts[0], parts[1], parts[2], parts[3]
        if not point.startswith(("/run/media", "/media", "/mnt")):
            continue
        if fstype in ("tmpfs", "overlay", "squashfs"):
            continue
        if device.startswith("/dev/loop"):
            continue
        try:
            free = shutil.disk_usage(point).free
        except OSError:
            continue
        found.append((free, Path(point)))
    return [p for _, p in sorted(found, reverse=True)]


def default_home() -> Path:
    return Path(os.environ.get("HOME") or str(Path.home()))
