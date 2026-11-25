"""The palette for TulsiOS' dwm session: X resources, GTK settings, wallpaper.

- dwm (dwm-colours-xrdb-6.8.diff) takes dwm.* resources whenever the resource
  database changes, so `xrdb -merge` recolours its bars, borders and tray at
  once; dmenu gets dwm's colours as arguments.
- st windows opened afterwards take *.color0-15 / *.foreground / *.background.
- GTK apps read ~/.config/gtk-3.0/settings.ini when they start (dwm runs no
  settings daemon): the generated GTK theme, icons and dark preference go there.
- The wallpaper is recorded in ~/.config/tulsi/theme.wallpaper, which the dwm
  session sets again at login (as it merges theme.Xresources).
"""

from __future__ import annotations

import configparser
from pathlib import Path

from . import run, store
from .palette import Palette, readable_on
from .terminal import ansi

# TulsiOS' dwm colours (data/dwm/config.h). dwm keeps the last colours it read,
# so going back to its own look means merging these, not removing ours.
DWM_DEFAULTS = {
    "dwm.normbgcolor": "#1b1f1c",
    "dwm.normbordercolor": "#3a423c",
    "dwm.normfgcolor": "#c9d1ca",
    "dwm.selbgcolor": "#3f8a4f",
    "dwm.selbordercolor": "#3f8a4f",
    "dwm.selfgcolor": "#ffffff",
}
GTK_KEYS = ("gtk-theme-name", "gtk-icon-theme-name", "gtk-application-prefer-dark-theme")


def resources(p: Palette) -> str:
    lines = [
        f"dwm.normbgcolor: {p['dark_background']}",
        f"dwm.normbordercolor: {p['muted']}",
        f"dwm.normfgcolor: {p['foreground']}",
        f"dwm.selbgcolor: {p['accent']}",
        f"dwm.selbordercolor: {p['accent']}",
        # Text on the accent (selected tag, focused title): black or white, whichever reads.
        f"dwm.selfgcolor: {readable_on(p['accent'])}",
        f"*.foreground: {p['foreground']}",
        f"*.background: {p['background']}",
        f"*.cursorColor: {p['bright_foreground']}",
    ]
    lines += [f"*.color{i}: {c}" for i, c in enumerate(ansi(p))]
    return "\n".join(lines) + "\n"


def resources_file() -> Path:
    return store.config_dir() / "theme.Xresources"


def wallpaper_file() -> Path:
    return store.config_dir() / "theme.wallpaper"


def gtk_settings_file() -> Path:
    return store.config_dir().parent / "gtk-3.0" / "settings.ini"


def _gtk_settings(values: dict[str, str] | None) -> None:
    """Set (or, with None, remove) our keys in the person's GTK 3 settings.ini."""
    f = gtk_settings_file()
    ini = configparser.ConfigParser(interpolation=None, strict=False)
    ini.optionxform = str  # keep the keys' case
    if f.exists():
        ini.read(f)
    if not ini.has_section("Settings"):
        ini.add_section("Settings")
    for key in GTK_KEYS:
        ini.remove_option("Settings", key)
    for key, value in (values or {}).items():
        ini.set("Settings", key, value)
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("w") as out:
        ini.write(out, space_around_delimiters=False)


def apply(p: Palette, background: Path | None, gtk_theme: str | None = None, icon_theme: str | None = None) -> None:
    f = resources_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(resources(p))
    if run.have("xrdb"):
        run.run("xrdb", "-merge", str(f))
    if gtk_theme:
        _gtk_settings({
            "gtk-theme-name": gtk_theme,
            "gtk-icon-theme-name": icon_theme or "Mint-Y",
            "gtk-application-prefer-dark-theme": "1" if p.dark else "0",
        })
    if background:
        wallpaper_file().write_text(str(background.resolve()) + "\n")
        if run.have("xwallpaper"):
            run.run("xwallpaper", "--zoom", str(background.resolve()))


def reset() -> None:
    """Back to the dwm session's own look: dwm's colours merged back in, the
    palette's other resources dropped, TulsiOS' GTK settings and wallpaper."""
    f = resources_file()
    ours = set()
    if f.exists():
        ours = {line.split(":", 1)[0] for line in f.read_text().splitlines() if ":" in line}
        f.unlink()
    if run.have("xrdb"):
        current = run.run("xrdb", "-query")
        kept = [line for line in current.splitlines() if line and line.split(":", 1)[0] not in ours]
        kept += [f"{k}:\t{v}" for k, v in DWM_DEFAULTS.items()]
        tmp = store.config_dir() / "theme.Xresources.rest"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text("\n".join(kept) + "\n")
        run.run("xrdb", "-load", str(tmp))
        tmp.unlink()
    if gtk_settings_file().exists():
        _gtk_settings(None)
    w = wallpaper_file()
    if w.exists():
        w.unlink()
