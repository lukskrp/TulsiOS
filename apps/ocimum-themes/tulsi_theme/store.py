"""Where themes live, and which one is on.

A theme is a directory named by its slug (`tokyo-night` shows as "Tokyo
Night") holding colors.toml, optional backgrounds/ and, for stock themes,
CREDITS.md. A user's theme of the same slug replaces the stock one.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import palette

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
DEFAULT_THEME = "tulsi-leaf"


def _xdg(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / fallback)


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / "tulsi"


def user_themes_dir() -> Path:
    return config_dir() / "themes"


def state_file() -> Path:
    return _xdg("XDG_STATE_HOME", ".local/state") / "tulsi-theme" / "state.json"


def generated_themes_dir() -> Path:
    """Where GTK and Cinnamon look for a user's themes first."""
    return _xdg("XDG_DATA_HOME", ".local/share") / "themes"


def stock_dirs() -> list[Path]:
    """Stock themes: $TULSI_THEME_STOCK (the package sets it), then XDG data dirs."""
    dirs = []
    if os.environ.get("TULSI_THEME_STOCK"):
        dirs.append(Path(os.environ["TULSI_THEME_STOCK"]))
    for d in (os.environ.get("XDG_DATA_DIRS") or "/run/current-system/sw/share").split(":"):
        if d:
            dirs.append(Path(d) / "tulsi" / "themes")
    return dirs


def title(slug: str) -> str:
    return " ".join(w.capitalize() for w in slug.replace("_", "-").split("-"))


@dataclass
class Theme:
    slug: str
    path: Path
    stock: bool
    palette: palette.Palette = field(repr=False)

    @property
    def name(self) -> str:
        return title(self.slug)

    @property
    def backgrounds(self) -> list[Path]:
        d = self.path / "backgrounds"
        if not d.is_dir():
            return []
        return sorted(p for p in d.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)

    @property
    def credits(self) -> str | None:
        for name in ("CREDITS.md", "LICENSE", "LICENSE.md", "README.md"):
            p = self.path / name
            if p.is_file():
                return p.read_text(encoding="utf-8", errors="replace")
        return None

    @property
    def generated_name(self) -> str:
        """The GTK/Cinnamon theme name this palette is generated under."""
        return "Tulsi-" + self.slug


def _load(path: Path, stock: bool) -> Theme | None:
    colors = path / "colors.toml"
    if not colors.is_file():
        return None
    try:
        return Theme(path.name, path, stock, palette.load(colors))
    except palette.PaletteError:
        return None


def themes() -> dict[str, Theme]:
    """Every usable theme by slug; user themes override stock ones."""
    found: dict[str, Theme] = {}
    for d in reversed(stock_dirs()):
        if d.is_dir():
            for p in sorted(d.iterdir()):
                if t := _load(p, stock=True):
                    found[t.slug] = t
    u = user_themes_dir()
    if u.is_dir():
        for p in sorted(u.iterdir()):
            if t := _load(p, stock=False):
                found[t.slug] = t
    return dict(sorted(found.items()))


def get(slug: str) -> Theme:
    try:
        return themes()[slug]
    except KeyError:
        raise LookupError(f"no theme called {slug!r} (see `tulsi-theme list`)") from None


# --- state: the theme that is on, and the ones before it (for undo) ---------

def read_state() -> dict:
    try:
        return json.loads(state_file().read_text())
    except (OSError, ValueError):
        return {}


def write_state(state: dict) -> None:
    f = state_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    tmp.replace(f)


def current() -> tuple[str, int]:
    s = read_state()
    return s.get("theme", DEFAULT_THEME), int(s.get("background", 0))


def record(slug: str, background: int) -> None:
    """Make (slug, background) current, keeping the previous one for undo.

    Before the first switch the desktop has its own look (Ocimum's Mint-Y-Dark);
    that is kept as theme None, so undo can go all the way back to it.
    """
    s = read_state()
    history = s.get("history", [])
    history.append({"theme": s.get("theme"), "background": s.get("background", 0)})
    s.update(theme=slug, background=background, history=history[-20:])
    write_state(s)


def pop_previous() -> tuple[str | None, int] | None:
    """Drop the current theme from the state and return the one before it
    (theme None: the desktop's own look)."""
    s = read_state()
    history = s.get("history", [])
    if not history:
        return None
    prev = history.pop()
    if prev.get("theme") is None:
        s = {"history": history}
    else:
        s.update(theme=prev["theme"], background=prev.get("background", 0), history=history)
    write_state(s)
    return prev.get("theme"), int(prev.get("background", 0))
