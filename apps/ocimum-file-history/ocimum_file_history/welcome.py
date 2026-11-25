"""The TulsiOS Welcome window's logic, without GTK (ADR 0027).

Shown once per person, at their first login after TulsiOS is installed on a
computer (not in a virtual machine, where it would only get in the way of
tests; TULSI_WELCOME_FORCE=1 shows it anyway). It offers what TulsiOS leaves
for the person to choose, first of all a history of their files: snapshots of
/home, which is a system setting, turned on with `tulsi config` so it is
recorded and can be undone like any change.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

SETTING = "tulsi.homeSnapshots.enable"
SNAPPER_CONFIG = Path("/etc/snapper/configs/home")


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local/state")
    return Path(base) / "tulsi"


def marker() -> Path:
    return state_dir() / "welcome-shown"


def is_virtual() -> bool:
    try:
        return subprocess.run(["systemd-detect-virt", "--quiet"]).returncode == 0
    except OSError:
        return False


def should_show(first_login: bool) -> bool:
    """`tulsi-welcome` always shows; `--first-login` (the autostart) only once,
    and only on real hardware."""
    if os.environ.get("TULSI_WELCOME_FORCE") == "1" or not first_login:
        return True
    return not marker().exists() and not is_virtual()


def mark_shown() -> None:
    marker().parent.mkdir(parents=True, exist_ok=True)
    marker().touch()


def fs_type(path: str = "/home", mounts: str = "/proc/self/mounts") -> str:
    """The file system `path` is on, from the longest mount point above it."""
    best, kind = "", ""
    try:
        lines = Path(mounts).read_text().splitlines()
    except OSError:
        return ""
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        point = parts[1].replace("\\040", " ")
        if (path == point or path.startswith(point.rstrip("/") + "/")) and len(point) >= len(best):
            best, kind = point, parts[2]
    return kind


def snapshots_on() -> bool:
    return SNAPPER_CONFIG.exists()


def with_setting(config: str, value: bool = True) -> str:
    """configuration.nix with `tulsi.homeSnapshots.enable = VALUE;`, changing
    the line if there is one, else adding it before the final `}`."""
    line = f"{SETTING} = {'true' if value else 'false'};"
    pattern = re.compile(rf"^(\s*){re.escape(SETTING)}\s*=\s*\w+\s*;", re.M)
    if pattern.search(config):
        return pattern.sub(lambda m: m.group(1) + line, config, count=1)
    if not config.strip():
        return "{ config, lib, pkgs, ... }:\n{\n  " + line + "\n}\n"
    end = config.rstrip().rfind("}")
    if end < 0:
        raise ValueError("configuration.nix has no closing brace")
    head = config[:end].rstrip("\n")
    return (head + "\n\n  # A history of everyone's files (File History), from the Welcome window.\n  "
            + line + "\n" + config[end:].rstrip() + "\n")


def turn_on_snapshots() -> tuple[bool, str]:
    """Adds the setting with `tulsi config` (asks for the person's password).
    Returns success and what tulsi said."""
    show = subprocess.run(["tulsi", "config", "show"], capture_output=True, text=True)
    if show.returncode != 0:
        return False, show.stderr.strip() or "tulsi config show failed"
    new = with_setting(show.stdout)
    path = state_dir() / "configuration.nix"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new)
    applied = subprocess.run(
        ["tulsi", "-q", "config", "apply", str(path), "--summary", "Keep a history of home folders"],
        capture_output=True, text=True,
    )
    out = (applied.stdout + applied.stderr).strip()
    return applied.returncode == 0, out
