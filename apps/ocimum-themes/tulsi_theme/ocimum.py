"""Switching Ocimum (Cinnamon) to a generated theme.

Cinnamon reloads its shell theme on `changed::name` of org.cinnamon.theme
(js/ui/themeManager.js), and finds ~/.local/share/themes first; GTK 3 apps
reload on a new gtk-theme name. No rebuild, nothing outside the user's home.
"""

from __future__ import annotations

from pathlib import Path

from . import run
from .palette import Palette, hue

# Mint-Y icon colours (mint-themes' constants.py and mint-y-icons).
ICON_ACCENTS = {
    "Mint-Y": "#35a854",
    "Mint-Y-Aqua": "#1f9ede",
    "Mint-Y-Blue": "#0c75de",
    "Mint-Y-Orange": "#ff7139",
    "Mint-Y-Pink": "#e54980",
    "Mint-Y-Purple": "#8c5dd9",
    "Mint-Y-Red": "#e82127",
    "Mint-Y-Sand": "#c5a07c",
    "Mint-Y-Teal": "#199ca8",
}


def icon_theme(accent: str) -> str:
    """The Mint-Y icon colour nearest the accent; Grey for a colourless one."""
    h, s, _ = hue(accent)
    if s < 0.18:
        return "Mint-Y-Grey"

    def distance(item: tuple[str, str]) -> float:
        ih, is_, _ = hue(item[1])
        d = abs(ih - h)
        return min(d, 360 - d) + abs(is_ - s) * 40

    return min(ICON_ACCENTS.items(), key=distance)[0]


def gsettings(p: Palette, name: str, background: Path | None) -> list[tuple[str, str, str]]:
    """(schema, key, value) for gsettings set."""
    out = [
        ("org.cinnamon.desktop.interface", "gtk-theme", name),
        ("org.cinnamon.desktop.interface", "icon-theme", icon_theme(p["accent"])),
        ("org.cinnamon.theme", "name", name),
        # Cinnamon's own "Dark mode" setting; libadwaita/portal apps follow it.
        ("org.x.apps.portal", "color-scheme", "prefer-dark" if p.dark else "prefer-light"),
        ("org.gnome.desktop.interface", "gtk-theme", name),
        ("org.gnome.desktop.interface", "color-scheme", "prefer-dark" if p.dark else "prefer-light"),
    ]
    if background:
        out += [
            ("org.cinnamon.desktop.background", "picture-uri", background.resolve().as_uri()),
            ("org.cinnamon.desktop.background", "picture-options", "zoom"),
        ]
    return out


def reset() -> None:
    """Back to the system's defaults (TulsiOS': Mint-Y-Dark, Tulsi Leaf)."""
    if not run.have("gsettings"):
        return
    schemas = set(run.run("gsettings", "list-schemas").split())
    for schema, key in KEYS:
        if schema in schemas:
            try:
                run.run("gsettings", "reset", schema, key)
            except Exception:
                pass  # a key this Cinnamon doesn't have


# Every key a switch may set, which undoing the first switch resets.
KEYS = (
    ("org.cinnamon.desktop.interface", "gtk-theme"),
    ("org.cinnamon.desktop.interface", "icon-theme"),
    ("org.cinnamon.theme", "name"),
    ("org.x.apps.portal", "color-scheme"),
    ("org.gnome.desktop.interface", "gtk-theme"),
    ("org.gnome.desktop.interface", "color-scheme"),
    ("org.cinnamon.desktop.background", "picture-uri"),
    ("org.cinnamon.desktop.background", "picture-options"),
    # Ocimum's background daemon moves picture-uri into its per-monitor list.
    ("org.cinnamon.desktop.background", "picture-uri-list"),
)


def apply(p: Palette, name: str, background: Path | None, reload: bool = False) -> None:
    if not run.have("gsettings"):
        return
    schemas = None
    for schema, key, value in gsettings(p, name, background):
        if schemas is None:
            schemas = set(run.run("gsettings", "list-schemas").split())
        if schema not in schemas:
            continue
        if reload and key in ("gtk-theme", "name"):
            # The same name again: GTK and Cinnamon only reload on a change.
            run.run("gsettings", "set", schema, key, "Mint-Y-Dark")
        run.run("gsettings", "set", schema, key, value)
