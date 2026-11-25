"""Reading and changing the system's drivers through `tulsi` (ADR 0029).

A driver change is a `tulsi config` edit made "at restart": tulsid builds the
new system for the next start and keeps the one before as the default, so if
the new driver leaves a black screen, restarting brings the old one back. After
a start with the new driver the person keeps it (`tulsi trial keep`), or it is
undone.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from . import config


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local/state")
    return Path(base) / "tulsi"


def _run(*cmd: str) -> subprocess.CompletedProcess:
    """Runs a command; a missing program (no tulsid on this system) is a failure, not a crash."""
    try:
        return subprocess.run(list(cmd), capture_output=True, text=True)
    except OSError as e:
        return subprocess.CompletedProcess(list(cmd), 127, "", f"{cmd[0]}: {e.strerror}")


def read_config() -> str:
    show = _run("tulsi", "config", "show")
    if show.returncode != 0:
        raise RuntimeError(show.stderr.strip() or "tulsi config show failed")
    return show.stdout


def current_settings() -> config.Settings:
    return config.parse(read_config())


def summary(old: config.Settings, new: config.Settings) -> str:
    parts = []
    if (old.nvidia is None) != (new.nvidia is None) or old.nvidia != new.nvidia:
        if new.nvidia is None:
            parts.append("Nouveau for the NVIDIA card")
        else:
            mode = {"offload": ", power saving", "sync": ", for everything"}.get(new.nvidia.prime, "")
            parts.append(f"NVIDIA's {new.nvidia.branch} driver{mode}")
    if old.broadcom != new.broadcom:
        parts.append("Broadcom STA Wi-Fi driver" if new.broadcom else "the open Broadcom Wi-Fi driver")
    for field, label in (
        ("intel_va", "Intel video decoding"),
        ("intel_compute", "Intel compute"),
        ("amd_compute", "AMD compute"),
        ("amd_legacy", "amdgpu for older AMD cards"),
        ("games32", "32-bit graphics libraries"),
    ):
        if getattr(old, field) != getattr(new, field):
            parts.append(("" if getattr(new, field) else "no ") + label)
    return "Drivers: " + (", ".join(parts) if parts else "no change")


def apply(new: config.Settings, at_restart: bool = True) -> tuple[bool, str]:
    """Write the drivers block and apply it. Returns (ok, output)."""
    text = read_config()
    old = config.parse(text)
    # Unfree software, once allowed, stays allowed (see config.render).
    if old.unfree and not new.unfree:
        from dataclasses import replace

        new = replace(new, unfree=True)
    updated = config.with_settings(text, new)
    if updated == text:
        return True, "Nothing to change."
    path = state_dir() / "drivers-configuration.nix"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated)
    cmd = ["tulsi", "-q", "config", "apply", str(path), "--summary", summary(old, new)]
    if at_restart:
        cmd.append("--at-restart")
    applied = _run(*cmd)
    return applied.returncode == 0, (applied.stdout + applied.stderr).strip()


def trial(action: str) -> tuple[bool, str]:
    """`tulsi trial status|keep|undo`."""
    done = _run("tulsi", "trial", action)
    return done.returncode == 0, (done.stdout + done.stderr).strip()


def trial_status() -> dict:
    done = _run("tulsi", "trial", "status", "--json")
    if done.returncode != 0:
        return {"state": "none"}
    try:
        return json.loads(done.stdout)
    except ValueError:
        return {"state": "none"}


def restart() -> None:
    subprocess.run(["systemctl", "reboot"], check=False)
