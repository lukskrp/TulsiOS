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


def with_setting(config: str, value: bool = True, setting: str = SETTING,
                 comment: str = "A history of everyone's files (File History), from the Welcome window.") -> str:
    """configuration.nix with `SETTING = VALUE;` (tulsi.homeSnapshots.enable by
    default), changing the line if there is one, else adding it before the final `}`."""
    line = f"{setting} = {'true' if value else 'false'};"
    pattern = re.compile(rf"^(\s*){re.escape(setting)}\s*=\s*\w+\s*;", re.M)
    if pattern.search(config):
        return pattern.sub(lambda m: m.group(1) + line, config, count=1)
    if not config.strip():
        return "{ config, lib, pkgs, ... }:\n{\n  " + line + "\n}\n"
    end = config.rstrip().rfind("}")
    if end < 0:
        raise ValueError("configuration.nix has no closing brace")
    head = config[:end].rstrip("\n")
    return (head + f"\n\n  # {comment}\n  "
            + line + "\n" + config[end:].rstrip() + "\n")


def _apply_setting(setting: str, comment: str, summary: str) -> tuple[bool, str]:
    """Turns SETTING on with `tulsi config` (asks for the person's password).
    Returns success and what tulsi said."""
    show = subprocess.run(["tulsi", "config", "show"], capture_output=True, text=True)
    if show.returncode != 0:
        return False, show.stderr.strip() or "tulsi config show failed"
    new = with_setting(show.stdout, True, setting, comment)
    path = state_dir() / "configuration.nix"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new)
    applied = subprocess.run(
        ["tulsi", "-q", "config", "apply", str(path), "--summary", summary],
        capture_output=True, text=True,
    )
    out = (applied.stdout + applied.stderr).strip()
    return applied.returncode == 0, out


def turn_on_snapshots() -> tuple[bool, str]:
    return _apply_setting(
        SETTING,
        "A history of everyone's files (File History), from the Welcome window.",
        "Keep a history of home folders",
    )


# ADR 0035: the common media codecs, when the installer left them off.
CODECS_SETTING = "tulsi.codecs.enable"
CODECS_MARKER = Path("/run/current-system/sw/lib/gstreamer-1.0/libgstlibav.so")


def codecs_on(marker: Path = CODECS_MARKER) -> bool:
    return marker.exists()


def turn_on_codecs() -> tuple[bool, str]:
    return _apply_setting(
        CODECS_SETTING,
        "MP3, AAC, H.264 and other common formats for every app, DVDs, RAR and 7z.",
        "Play all common media formats",
    )


def drivers_needed() -> str | None:
    """What the Drivers app recommends when a device needs a driver the system
    doesn't have yet (an NVIDIA card on Nouveau, a Broadcom card without Wi-Fi),
    else None (ADR 0029)."""
    try:
        check = subprocess.run(["tulsi-drivers", "recommend", "--check"], capture_output=True, timeout=30)
        if check.returncode != 10:
            return None
        rec = subprocess.run(["tulsi-drivers", "recommend"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    first = rec.stdout.strip().splitlines()[:1]
    return first[0].removeprefix("Recommended: ") if first else ""
