"""The palette as a GNOME Terminal profile (Ocimum's terminal).

The 16 colours follow Omarchy's terminal templates (MIT, (c) David Heinemeier
Hansson): black is the background, white the foreground, the bright black
`muted`, and the bright colours the palette's bright_ keys.
"""

from __future__ import annotations

from . import run
from .palette import Palette

# One profile of our own, so the user's profiles are never touched.
PROFILE = "6f3f5d1e-7a1c-4b8e-9d2f-71c5a1e0b0a1"
BASE = "/org/gnome/terminal/legacy/profiles:/"
BUILTIN_DEFAULT = "b1dcc9dd-5262-4d8d-a863-c897e6d979b9"  # GNOME Terminal's own first profile


def ansi(p: Palette) -> list[str]:
    normal = [p["background"], p["red"], p["green"], p["yellow"], p["blue"], p["magenta"], p["cyan"], p["foreground"]]
    bright = [
        p["muted"],
        p["bright_red"],
        p["bright_green"],
        p["bright_yellow"],
        p["bright_blue"],
        p["bright_magenta"],
        p["bright_cyan"],
        p["bright_foreground"],
    ]
    return normal + bright


def settings(p: Palette, name: str) -> dict[str, str]:
    """dconf key -> GVariant text, under the profile's path."""
    return {
        "visible-name": run.gvariant_str(f"TulsiOS theme ({name})"),
        "use-theme-colors": "false",
        "palette": run.gvariant_strv(ansi(p)),
        "foreground-color": run.gvariant_str(p["foreground"]),
        "background-color": run.gvariant_str(p["background"]),
        "bold-color-same-as-fg": "true",
        "cursor-colors-set": "true",
        "cursor-background-color": run.gvariant_str(p["bright_foreground"]),
        "cursor-foreground-color": run.gvariant_str(p["background"]),
        "highlight-colors-set": "true",
        "highlight-background-color": run.gvariant_str(p["selection"]),
        "highlight-foreground-color": run.gvariant_str(p["bright_foreground"]),
    }


def _profiles() -> list[str]:
    text = run.run("dconf", "read", BASE + "list").strip()
    if not text.startswith("["):
        return []
    return [s.strip(" '\"") for s in text.strip("[]").split(",") if s.strip(" '\"")]


def reset() -> None:
    """Back to the user's own profile: ours leaves the list and stops being the default."""
    if not run.have("dconf"):
        return
    profiles = [p for p in _profiles() if p != PROFILE]
    if profiles:
        run.run("dconf", "write", BASE + "list", run.gvariant_strv(profiles))
        run.run("dconf", "write", BASE + "default", run.gvariant_str(profiles[0]))
    else:
        run.run("dconf", "reset", BASE + "list")
        run.run("dconf", "reset", BASE + "default")
    run.run("dconf", "reset", "-f", f"{BASE}:{PROFILE}/")


def apply(p: Palette, name: str) -> None:
    if not run.have("dconf"):
        return
    path = f"{BASE}:{PROFILE}/"
    for key, value in settings(p, name).items():
        run.run("dconf", "write", path + key, value)
    profiles = _profiles()
    if not profiles:
        # An unset list means GNOME Terminal's built-in profile alone; keep it listed.
        current = run.run("dconf", "read", BASE + "default").strip().strip("'\"")
        profiles = [current or BUILTIN_DEFAULT]
    if PROFILE not in profiles:
        run.run("dconf", "write", BASE + "list", run.gvariant_strv([*profiles, PROFILE]))
    run.run("dconf", "write", BASE + "default", run.gvariant_str(PROFILE))
