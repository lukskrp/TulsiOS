"""The palette as a KDE colour scheme, for SonicDE (and Qt apps elsewhere).

Adapted from Omarchy's qtengine.colors.tpl (github.com/omacom/omarchy, MIT,
(c) David Heinemeier Hansson): content on `background`, window chrome on
`dark_background`, selected text in the background colour on the accent.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import run
from .palette import Palette, mix, rgb


def _rgb(hex_colour: str) -> str:
    return ",".join(str(c) for c in rgb(hex_colour))


def _group(p: Palette, bg: str, alt: float) -> dict[str, str]:
    return {
        "BackgroundNormal": _rgb(bg),
        "BackgroundAlternate": _rgb(mix(p["foreground"], bg, alt)),
        "ForegroundNormal": _rgb(p["foreground"]),
        "ForegroundInactive": _rgb(mix(bg, p["foreground"], 0.34)),
        "ForegroundActive": _rgb(p["accent"]),
        "ForegroundLink": _rgb(p["blue"]),
        "ForegroundVisited": _rgb(p["magenta"]),
        "ForegroundNegative": _rgb(p["red"]),
        "ForegroundNeutral": _rgb(p["yellow"]),
        "ForegroundPositive": _rgb(p["green"]),
        "DecorationFocus": _rgb(p["accent"]),
        "DecorationHover": _rgb(p["accent"]),
    }


def scheme(p: Palette, name: str) -> str:
    selection = {
        "BackgroundNormal": _rgb(p["accent"]),
        "BackgroundAlternate": _rgb(mix(p["accent"], p["background"], 0.3)),
        "ForegroundNormal": _rgb(p["background"]),
        "ForegroundInactive": _rgb(mix(p["background"], p["accent"], 0.3)),
        **{k: _rgb(p["background"]) for k in (
            "ForegroundActive", "ForegroundLink", "ForegroundVisited",
            "ForegroundNegative", "ForegroundNeutral", "ForegroundPositive",
        )},
        "DecorationFocus": _rgb(p["accent"]),
        "DecorationHover": _rgb(p["accent"]),
    }
    groups = {
        "Window": _group(p, p["dark_background"], 0.05),
        "View": _group(p, p["background"], 0.04),
        "Button": _group(p, p["background"], 0.06),
        "Selection": selection,
        "Tooltip": _group(p, p["background"], 0.05),
        "Header": _group(p, p["dark_background"], 0.05),
        "Complementary": _group(p, p["dark_background"], 0.05),
    }
    lines = [
        "[General]",
        f"ColorScheme={name}",
        f"Name={name}",
        "",
        "[KDE]",
        "contrast=4",
        "",
        "[ColorEffects:Disabled]",
        "Enable=true",
        "IntensityEffect=0",
        "ColorEffect=0",
        "ContrastEffect=1",
        "ContrastAmount=0.55",
        "",
        "[ColorEffects:Inactive]",
        "Enable=false",
        "ChangeSelectionColor=false",
    ]
    for group, values in groups.items():
        # An explicit Inactive subgroup, so KColorScheme doesn't inherit kdeglobals' colours.
        for section in (f"[Colors:{group}]", f"[Colors:{group}][Inactive]"):
            lines += ["", section, *(f"{k}={v}" for k, v in values.items())]
    lines += [
        "",
        "[WM]",
        f"activeBackground={_rgb(p['dark_background'])}",
        f"activeForeground={_rgb(p['foreground'])}",
        f"inactiveBackground={_rgb(p['darker_background'])}",
        f"inactiveForeground={_rgb(p['dark_foreground'])}",
        f"activeBlend={_rgb(p['accent'])}",
        f"inactiveBlend={_rgb(p['muted'])}",
    ]
    return "\n".join(lines) + "\n"


def schemes_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    return base / "color-schemes"


def reset() -> None:
    """Back to SonicDE's own colours: the look-and-feel's (Silver)."""
    if run.have("plasma-apply-colorscheme"):
        run.run("plasma-apply-colorscheme", "SilverLight")
    if run.have("kwriteconfig6"):
        for f in ("gtk-3.0/settings.ini", "gtk-4.0/settings.ini"):
            run.run("kwriteconfig6", "--file", str(Path.home() / ".config" / f), "--group", "Settings",
                    "--key", "gtk-theme-name", "--delete")


def apply(p: Palette, name: str, background: Path | None, gtk_theme: str | None) -> None:
    """Write the scheme and switch SonicDE to it (Sonic's plasma-apply-* tools
    already talk to sonicshell)."""
    d = schemes_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.colors").write_text(scheme(p, name))
    if run.have("plasma-apply-colorscheme"):
        run.run("plasma-apply-colorscheme", name)
    if background and run.have("plasma-apply-wallpaperimage"):
        run.run("plasma-apply-wallpaperimage", str(background.resolve()))
    if gtk_theme and run.have("kwriteconfig6"):
        # GTK apps on SonicDE take the palette's generated GTK theme too.
        for f in ("gtk-3.0/settings.ini", "gtk-4.0/settings.ini"):
            run.run("kwriteconfig6", "--file", str(Path.home() / ".config" / f), "--group", "Settings",
                    "--key", "gtk-theme-name", gtk_theme)
