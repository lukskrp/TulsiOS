"""`tulsi-theme look`: draw a theme as a small desktop, without applying it.

For people and agents alike (Omarchy's `omarchy agent look theme` idea): the
first background, a panel, a window with text and buttons in the palette's
colours, and the 16 terminal colours, plus a list of problems to fix.
"""

from __future__ import annotations

from pathlib import Path

from . import store
from .palette import Palette, readable_on, rgb
from .terminal import ansi

W, H = 960, 540
MIN_BACKGROUND = (1920, 1080)


def _rgb(c: str) -> tuple[float, float, float]:
    r, g, b = rgb(c)
    return r / 255, g / 255, b / 255


def problems(theme: store.Theme) -> list[str]:
    out = theme.palette.problems()
    for bg in theme.backgrounds:
        size = image_size(bg)
        if size and (size[0] < MIN_BACKGROUND[0] or size[1] < MIN_BACKGROUND[1]):
            out.append(f"{bg.name} is {size[0]}x{size[1]}; backgrounds need {MIN_BACKGROUND[0]}x{MIN_BACKGROUND[1]}")
    if theme.stock and not (theme.path / "CREDITS.md").is_file():
        out.append("a stock theme needs CREDITS.md (palette author, licence, backgrounds)")
    return out


def image_size(path: Path) -> tuple[int, int] | None:
    try:
        import gi

        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf

        _, w, h = GdkPixbuf.Pixbuf.get_file_info(str(path))
        return (w, h) if w else None
    except Exception:
        return None


def draw(theme: store.Theme, out: Path, background: Path | None = None) -> Path:
    import cairo

    p: Palette = theme.palette
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
    cr = cairo.Context(surface)

    cr.set_source_rgb(*_rgb(p["darker_background"]))
    cr.paint()
    bg = background or (theme.backgrounds[0] if theme.backgrounds else None)
    if bg:
        try:
            import gi

            gi.require_version("Gdk", "3.0")
            gi.require_version("GdkPixbuf", "2.0")
            from gi.repository import Gdk, GdkPixbuf

            pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(bg), W, H, False)
            Gdk.cairo_set_source_pixbuf(cr, pix, 0, 0)
            cr.paint()
        except Exception:
            pass

    # Panel along the bottom, as Ocimum's.
    cr.set_source_rgb(*_rgb(p["dark_background"]))
    cr.rectangle(0, H - 36, W, 36)
    cr.fill()
    cr.set_source_rgb(*_rgb(p["accent"]))
    cr.rectangle(10, H - 30, 24, 24)
    cr.fill()

    # A window: header, body text, a selected row, buttons.
    x, y, w, h = 120, 70, 520, 330
    cr.set_source_rgb(*_rgb(p["dark_background"]))
    cr.rectangle(x, y, w, 34)
    cr.fill()
    cr.set_source_rgb(*_rgb(p["background"]))
    cr.rectangle(x, y + 34, w, h - 34)
    cr.fill()
    cr.select_font_face("sans-serif")
    cr.set_font_size(15)
    cr.set_source_rgb(*_rgb(p["foreground"]))
    cr.move_to(x + 14, y + 22)
    cr.show_text(f"{theme.name} ({p.mode})")
    for i, line in enumerate(("Body text on the background", "Muted, secondary text")):
        cr.set_source_rgb(*_rgb(p["foreground"] if i == 0 else p["dark_foreground"]))
        cr.move_to(x + 20, y + 70 + i * 26)
        cr.show_text(line)
    cr.set_source_rgb(*_rgb(p["accent"]))
    cr.rectangle(x + 14, y + 120, w - 28, 28)
    cr.fill()
    cr.set_source_rgb(*_rgb(readable_on(p["accent"])))
    cr.move_to(x + 22, y + 139)
    cr.show_text("A selected row")
    for i, key in enumerate(("red", "yellow", "green", "blue")):
        cr.set_source_rgb(*_rgb(p[key]))
        cr.rectangle(x + 20 + i * 120, y + 170, 104, 30)
        cr.fill()
        cr.set_source_rgb(*_rgb(readable_on(p[key])))
        cr.move_to(x + 30 + i * 120, y + 190)
        cr.show_text(key)

    # Terminal colours.
    tx, ty = 680, 70
    cr.set_source_rgb(*_rgb(p["background"]))
    cr.rectangle(tx, ty, 250, 170)
    cr.fill()
    for i, c in enumerate(ansi(p)):
        cr.set_source_rgb(*_rgb(c))
        cr.rectangle(tx + 10 + (i % 8) * 29, ty + 20 + (i // 8) * 60, 25, 50)
        cr.fill()

    out.parent.mkdir(parents=True, exist_ok=True)
    surface.write_to_png(str(out))
    return out
