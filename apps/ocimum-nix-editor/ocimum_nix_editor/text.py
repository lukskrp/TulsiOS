"""Small text helpers for completion (no GTK)."""

from __future__ import annotations

import re

IDENT_CHARS = re.compile(r"[A-Za-z0-9_'\-]")


def typed_prefix(line_before_cursor: str) -> str:
    """The part of a name typed so far (after the last dot)."""
    i = len(line_before_cursor)
    while i > 0 and IDENT_CHARS.fullmatch(line_before_cursor[i - 1]):
        i -= 1
    return line_before_cursor[i:]


def indent_snippet(snippet: str, indent: str) -> str:
    lines = snippet.splitlines()
    return "\n".join([lines[0]] + [indent + line if line else line for line in lines[1:]]) if lines else ""


# GtkSourceView 4's own colour schemes for code, for dark and light desktop themes.
DARK_SCHEME = "oblivion"
LIGHT_SCHEME = "classic"


def is_dark_theme(background: tuple[float, float, float] | None, name: str = "",
                  prefer_dark: bool = False) -> bool:
    """A theme is dark when its background is (relative luminance below one half, from
    0-1 RGB). Without a colour: when it asks for dark, or its name says so
    (Mint-Y-Dark, Adwaita-dark)."""
    if background is not None:
        r, g, b = background
        return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.5
    return prefer_dark or "dark" in name.lower()
