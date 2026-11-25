"""Switching to a theme: generate what the desktop needs, then point it there."""

from __future__ import annotations

import os
from pathlib import Path

from . import kde, mint, ocimum, store, terminal, xres
from .store import Theme


def desktop() -> str:
    """"ocimum", "sonic", "dwm", or "" when there is no session to theme."""
    d = (os.environ.get("TULSI_THEME_DESKTOP") or os.environ.get("XDG_CURRENT_DESKTOP") or "").lower()
    if "cinnamon" in d:
        return "ocimum"
    if "kde" in d or "sonic" in d:
        return "sonic"
    if "dwm" in d or (not d and _runs("dwm")):
        return "dwm"
    return ""


def _runs(program: str) -> bool:
    """This person runs `program` (a bare window manager may set no XDG_CURRENT_DESKTOP)."""
    uid = os.getuid()
    for proc in Path("/proc").iterdir():
        try:
            if proc.name.isdigit() and proc.stat().st_uid == uid and (proc / "comm").read_text().strip() == program:
                return True
        except OSError:
            continue
    return False


def default_background() -> Path | None:
    p = os.environ.get("TULSI_THEME_DEFAULT_BACKGROUND")
    return Path(p) if p and Path(p).is_file() else None


def background_for(theme: Theme, index: int) -> Path | None:
    bgs = theme.backgrounds
    if bgs:
        return bgs[index % len(bgs)]
    return default_background()


def switch(theme: Theme, background: int = 0, record: bool = True, which: str | None = None) -> Path:
    """Apply `theme` to the running desktop. Returns the generated GTK theme dir."""
    which = desktop() if which is None else which
    p = theme.palette
    name = theme.generated_name
    previous, _ = store.current()
    dest = mint.generate(p, name, store.generated_themes_dir())
    bg = background_for(theme, background)
    if which in ("ocimum", ""):
        ocimum.apply(p, name, bg, reload=previous == theme.slug)
        terminal.apply(p, theme.name)
    elif which == "sonic":
        kde.apply(p, name, bg, gtk_theme=name)
    elif which == "dwm":
        xres.apply(p, bg, gtk_theme=name, icon_theme=ocimum.icon_theme(p["accent"]))
    if record:
        store.record(theme.slug, background)
    return dest


def restore_default(which: str | None = None) -> None:
    """Back to the desktop's own look: undo what switching changed."""
    which = desktop() if which is None else which
    if which in ("ocimum", ""):
        ocimum.reset()
        terminal.reset()
    elif which == "sonic":
        kde.reset()
    elif which == "dwm":
        xres.reset()


def undo() -> str | None:
    """Go back one switch. Returns the theme now on ("default" for the desktop's own)."""
    prev = store.pop_previous()
    if prev is None:
        return None
    slug, background = prev
    if slug is None:
        restore_default()
        return "default"
    switch(store.get(slug), background, record=False)
    return slug
