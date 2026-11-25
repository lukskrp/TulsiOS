"""A theme's palette: Omarchy's colors.toml format, unchanged (ADR 0021).

The keys and their meaning are Omarchy's (github.com/omacom/omarchy, MIT,
(c) David Heinemeier Hansson), so Omarchy themes and theme repos work as they
are. This module reads and checks a palette and has the colour arithmetic the
desktops' translators share.
"""

from __future__ import annotations

import colorsys
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

# Every key a colors.toml must have (Omarchy's omarchy-make-theme skill).
KEYS = (
    "accent",
    "selection",
    "muted",
    "background",
    "dark_background",
    "darker_background",
    "lighter_background",
    "foreground",
    "dark_foreground",
    "light_foreground",
    "bright_foreground",
    "red",
    "yellow",
    "orange",
    "green",
    "cyan",
    "blue",
    "magenta",
    "brown",
    "bright_red",
    "bright_yellow",
    "bright_green",
    "bright_cyan",
    "bright_blue",
    "bright_magenta",
)

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class PaletteError(ValueError):
    """A colors.toml that is missing keys or holds something that is not a colour."""


def rgb(hex_colour: str) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def hexc(r: float, g: float, b: float) -> str:
    clamp = lambda v: max(0, min(255, round(v)))  # noqa: E731
    return "#%02x%02x%02x" % (clamp(r), clamp(g), clamp(b))


def mix(a: str, b: str, weight: float) -> str:
    """`weight` of a, the rest of b (SASS's mix(a, b, weight))."""
    (r1, g1, b1), (r2, g2, b2) = rgb(a), rgb(b)
    w = weight
    return hexc(r1 * w + r2 * (1 - w), g1 * w + g2 * (1 - w), b1 * w + b2 * (1 - w))


def luminance(hex_colour: str) -> float:
    """WCAG relative luminance."""

    def channel(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb(hex_colour)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio, 1 to 21."""
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def hue(hex_colour: str) -> tuple[float, float, float]:
    """(hue 0-360, saturation 0-1, lightness 0-1)."""
    r, g, b = (c / 255 for c in rgb(hex_colour))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, s, l


def readable_on(background: str) -> str:
    """Black or white, whichever reads better on `background`."""
    return "#ffffff" if contrast("#ffffff", background) >= contrast("#000000", background) else "#000000"


@dataclass(frozen=True)
class Palette:
    mode: str  # "dark" or "light"
    colours: dict[str, str]

    def __getitem__(self, key: str) -> str:
        return self.colours[key]

    @property
    def dark(self) -> bool:
        return self.mode == "dark"

    def problems(self) -> list[str]:
        """Readability problems, as Omarchy's theme check measures them."""
        out = []
        body = contrast(self["foreground"], self["background"])
        if body < 7:
            out.append(f"foreground on background is {body:.1f}:1; body text needs 7:1")
        for key in ("accent", "red", "yellow", "green", "blue"):
            c = contrast(self[key], self["background"])
            if c < 3:
                out.append(f"{key} on background is {c:.1f}:1; it needs 3:1")
        return out


def parse(text: str, source: str = "colors.toml") -> Palette:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise PaletteError(f"{source}: {e}") from None
    mode = data.get("mode", "dark")
    if mode not in ("dark", "light"):
        raise PaletteError(f"{source}: mode must be \"dark\" or \"light\", not {mode!r}")
    missing = [k for k in KEYS if k not in data]
    if missing:
        raise PaletteError(f"{source}: missing {', '.join(missing)}")
    colours = {}
    for key, value in data.items():
        if key == "mode" or not isinstance(value, str) or not value.startswith("#"):
            continue
        if not _HEX.match(value):
            raise PaletteError(f"{source}: {key} = {value!r} is not a #rrggbb colour")
        colours[key] = value.lower()
    return Palette(mode=mode, colours=colours)


def load(path: Path) -> Palette:
    return parse(path.read_text(encoding="utf-8"), str(path))
