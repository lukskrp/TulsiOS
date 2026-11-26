"""What the Update Manager shows and does, through `tulsi` (ADR 0038).

Updates themselves go through tulsid (`tulsi upgrade`), so every change is
recorded and can be undone; generations and snapshots are only ever listed
here, never silently changed. Anything this module cannot do (no tulsid, no
btrfs, offline) is a plain message, not a crash: the window says so.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


PROFILE = "/nix/var/nix/profiles/system"


def _run(*cmd: str, timeout: int = 120) -> subprocess.CompletedProcess:
    """Runs a command; a missing program is a failure, not a crash."""
    try:
        return subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout)
    except OSError as e:
        return subprocess.CompletedProcess(list(cmd), 127, "", f"{cmd[0]}: {e.strerror}")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(list(cmd), 124, "", f"{cmd[0]}: timed out")


# ------------------------------------------------------------ the release


def current_version(os_release: str = "/etc/os-release") -> str:
    """This machine's TulsiOS version, from os-release (TULSIOS_VERSION)."""
    try:
        for line in Path(os_release).read_text().splitlines():
            if line.startswith("TULSIOS_VERSION="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return "unknown"


@dataclass
class ReleaseCheck:
    current: str
    follows: str
    available: bool
    available_version: str
    error: str


def parse_check(output: str) -> ReleaseCheck:
    """Parses `tulsi upgrade --check` (see tulsi-cli's print_upgrade_info).

    Prints, in order: `TulsiOS <version> (<rev>)`, optionally
    `follows <branch>`, then `cannot check for a newer release: <why>`,
    `TulsiOS <version> is available (<rev>): run \\`tulsi upgrade\\``, or
    `This is the newest release.`
    """
    current, follows = "", ""
    available, available_version, error = False, "", ""
    for line in output.splitlines():
        m = re.fullmatch(r"TulsiOS (\S+) \([0-9a-f]{4,40}\)", line.strip())
        if m and not current:
            current = m.group(1)
            continue
        m = re.fullmatch(r"follows (\S+)", line.strip())
        if m:
            follows = m.group(1)
            continue
        m = re.fullmatch(r"cannot check for a newer release: (.*)", line.strip())
        if m:
            error = m.group(1)
            continue
        m = re.fullmatch(r"TulsiOS (\S+) is available \([0-9a-f]{4,40}\): run `tulsi upgrade`", line.strip())
        if m:
            available, available_version = True, m.group(1)
            continue
    return ReleaseCheck(current, follows, available, available_version, error)


def check_release() -> ReleaseCheck:
    done = _run("tulsi", "upgrade", "--check", timeout=180)
    if done.returncode != 0 and not done.stdout.strip():
        return ReleaseCheck("", "", False, "", done.stderr.strip() or "tulsi upgrade --check failed")
    return parse_check(done.stdout)


def upgrade_command() -> list[str]:
    """The release upgrade, snapshotting /home first when that is set up.

    `tulsi-upgrade` (from tulsi.updater) takes a snapper snapshot and then
    runs `tulsi upgrade`; without it, plain `tulsi upgrade`.
    """
    if shutil.which("tulsi-upgrade"):
        return ["tulsi-upgrade"]
    return ["tulsi", "upgrade"]


def upgrade() -> tuple[bool, str]:
    """Runs the release upgrade. Takes a long time; callers thread this."""
    done = _run(*upgrade_command(), timeout=7200)
    return done.returncode == 0, (done.stdout + done.stderr).strip()


# ------------------------------------------------------------ history


def history(n: int = 10) -> str:
    """`tulsi history`, or why it is not available."""
    done = _run("tulsi", "history", str(n))
    out = (done.stdout + done.stderr).strip()
    return out if out else "No history yet."


# ------------------------------------------------------------ generations


@dataclass
class Generation:
    number: int
    date: str
    current: bool


def parse_generations(output: str) -> list[Generation]:
    """Parses `nix-env -p <profile> --list-generations`.

    Lines look like `  12   2026-11-20 10:00:00` with `   (current)` after the
    date on the running generation.
    """
    found = []
    for line in output.splitlines():
        m = re.fullmatch(r"\s*(\d+)\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*(\(current\))?", line.rstrip())
        if m:
            found.append(Generation(int(m.group(1)), m.group(2), bool(m.group(3))))
    return found


def generations(profile: str = PROFILE) -> list[Generation]:
    done = _run("nix-env", "-p", profile, "--list-generations")
    if done.returncode != 0:
        return []
    return parse_generations(done.stdout)


# ------------------------------------------------------------ snapshots


@dataclass
class Snapshot:
    number: int
    date: str
    description: str


def parse_snapshots(output: str) -> list[Snapshot]:
    """Parses `snapper -c home list` (`# | Type | Pre # | Date | ...`)."""
    found = []
    for line in output.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 8 or cells[0].strip("# ") == "":
            continue
        try:
            number = int(cells[0])
        except ValueError:
            continue  # the header row
        found.append(Snapshot(number, cells[3], cells[6]))
    return found


def snapshots() -> tuple[list[Snapshot] | None, str]:
    """This machine's /home snapshots, or (None, why not)."""
    if shutil.which("snapper") is None:
        return None, "Snapper is not installed."
    done = _run("snapper", "-c", "home", "list")
    if done.returncode != 0:
        detail = done.stderr.strip() or done.stdout.strip()
        if "btrfs" in detail.lower() or "not a btrfs" in detail.lower() or not detail:
            return None, "Snapshots need /home on btrfs (this machine's is not)."
        return None, detail
    return parse_snapshots(done.stdout), ""


def take_snapshot(description: str) -> tuple[bool, str]:
    done = _run("snapper", "-c", "home", "create", "--description", description, "--cleanup-algorithm", "number")
    return done.returncode == 0, (done.stdout + done.stderr).strip()


# ------------------------------------------------------------ cleanup


def cleanup_now() -> tuple[bool, str]:
    """Removes old system versions now (`tulsi-cleanup`, ADR 0025)."""
    if shutil.which("tulsi-cleanup") is None:
        return False, "tulsi-cleanup is not installed."
    done = _run("tulsi-cleanup", timeout=3600)
    return done.returncode == 0, (done.stdout + done.stderr).strip()


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local/state")
    return Path(base) / "tulsi"
