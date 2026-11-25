"""The Themes window: a grid of theme cards, and the chosen theme's details.

Clicking a card shows the theme; "Use This Theme" switches to it (in a thread,
since a first switch compiles the theme for a few seconds), with an Undo bar.
"""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from tulsi_theme import apply, install, store  # noqa: E402
from tulsi_theme.palette import rgb  # noqa: E402

CARD_W, CARD_H = 216, 122
SWATCHES = ("background", "lighter_background", "foreground", "accent", "red", "yellow", "green", "blue", "magenta")


def _set_rgb(cr, hex_colour: str) -> None:
    r, g, b = rgb(hex_colour)
    cr.set_source_rgb(r / 255, g / 255, b / 255)


def plain(markdown: str) -> str:
    """Credits as plain text: no Markdown marks, wrapped lines joined."""
    import re

    text = re.sub(r"\*\*|`", "", markdown)
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    text = re.sub(r"\n(?=[ \t]+\S)", " ", text)  # a continued bullet
    return re.sub(r"[ \t]{2,}", " ", text).strip()


_thumbs: dict[tuple[str, int, int], GdkPixbuf.Pixbuf | None] = {}


def thumbnail(path: Path | None, w: int, h: int) -> GdkPixbuf.Pixbuf | None:
    if path is None:
        return None
    key = (str(path), w, h)
    if key not in _thumbs:
        try:
            pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), w * 2, h * 2, True)
            # Crop to the card's shape, centred, then scale down.
            sw, sh = pix.get_width(), pix.get_height()
            ratio = w / h
            cw, ch = (sh * ratio, sh) if sw / sh > ratio else (sw, sw / ratio)
            sub = pix.new_subpixbuf(int((sw - cw) / 2), int((sh - ch) / 2), int(cw), int(ch))
            _thumbs[key] = sub.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)
        except GLib.Error:
            _thumbs[key] = None
    return _thumbs[key]


def draw_preview(cr, theme: store.Theme, w: int, h: int, background: Path | None) -> None:
    p = theme.palette
    pix = thumbnail(background, w, h)
    if pix:
        Gdk.cairo_set_source_pixbuf(cr, pix, 0, 0)
        cr.paint()
    else:
        _set_rgb(cr, p["darker_background"])
        cr.paint()
    # A small window in the theme's colours, over the background.
    wx, wy, ww, wh = w * 0.12, h * 0.14, w * 0.62, h * 0.56
    _set_rgb(cr, p["dark_background"])
    cr.rectangle(wx, wy, ww, wh * 0.18)
    cr.fill()
    _set_rgb(cr, p["background"])
    cr.rectangle(wx, wy + wh * 0.18, ww, wh * 0.82)
    cr.fill()
    _set_rgb(cr, p["foreground"])
    for i in range(3):
        cr.rectangle(wx + 10, wy + wh * (0.32 + i * 0.16), ww * (0.7 - i * 0.15), 4)
        cr.fill()
    _set_rgb(cr, p["accent"])
    cr.rectangle(wx + ww - 46, wy + wh - 20, 36, 12)
    cr.fill()
    # Panel and swatches along the bottom.
    _set_rgb(cr, p["dark_background"])
    cr.rectangle(0, h - 18, w, 18)
    cr.fill()
    sw = (w - 8) / len(SWATCHES)
    for i, key in enumerate(SWATCHES):
        _set_rgb(cr, p[key])
        cr.rectangle(4 + i * sw, h - 14, sw - 2, 10)
        cr.fill()


class Card(Gtk.FlowBoxChild):
    def __init__(self, theme: store.Theme, current: bool):
        super().__init__()
        self.theme = theme
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=6)
        area = Gtk.DrawingArea()
        area.set_size_request(CARD_W, CARD_H)
        area.connect("draw", lambda w, cr: draw_preview(
            cr, theme, w.get_allocated_width(), w.get_allocated_height(), apply.background_for(theme, 0)))
        frame = Gtk.Frame()
        frame.add(area)
        box.pack_start(frame, False, False, 0)
        row = Gtk.Box(spacing=6)
        name = Gtk.Label(xalign=0)
        escaped = GLib.markup_escape_text(theme.name)
        name.set_markup(f"<b>{escaped}</b>" if current else escaped)
        row.pack_start(name, True, True, 0)
        badge = Gtk.Label(label=("● " if current else "") + ("Dark" if theme.palette.dark else "Light"))
        badge.get_style_context().add_class("dim-label")
        row.pack_end(badge, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.add(box)


class Window(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Themes")
        self.set_default_size(1100, 680)
        self.set_icon_name("org.tulsi.Themes")
        self.filter = "all"
        self.selected: store.Theme | None = None
        self.background_index = 0

        header = Gtk.HeaderBar(show_close_button=True, title="Themes")
        self.set_titlebar(header)
        filters = Gtk.Box(spacing=0)
        filters.get_style_context().add_class("linked")
        group = None
        for key, label in (("all", "All"), ("dark", "Dark"), ("light", "Light")):
            b = Gtk.RadioButton.new_with_label_from_widget(group, label)
            b.set_mode(False)
            group = group or b
            b.connect("toggled", self._on_filter, key)
            filters.pack_start(b, False, False, 0)
        header.set_custom_title(filters)
        install_button = Gtk.Button(label="Install from Git…")
        install_button.connect("clicked", self._on_install)
        header.pack_end(install_button)
        folder = Gtk.Button.new_from_icon_name("folder-open-symbolic", Gtk.IconSize.BUTTON)
        folder.set_tooltip_text("Open your themes folder")
        folder.connect("clicked", self._on_folder)
        header.pack_end(folder)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(outer)
        self.infobar = Gtk.InfoBar(show_close_button=True)
        self.infobar.set_no_show_all(True)
        self.info_label = Gtk.Label(xalign=0)
        self.infobar.get_content_area().add(self.info_label)
        self.undo_button = self.infobar.add_button("Undo", 1)
        self.infobar.connect("response", self._on_info_response)
        outer.pack_start(self.infobar, False, False, 0)

        paned = Gtk.Paned()
        outer.pack_start(paned, True, True, 0)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.grid = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.SINGLE, homogeneous=True, max_children_per_line=6,
            row_spacing=6, column_spacing=6, margin=12, valign=Gtk.Align.START,
        )
        self.grid.connect("child-activated", self._on_card)
        self.grid.set_filter_func(self._filter_card)
        scroller.add(self.grid)
        paned.pack1(scroller, True, False)
        paned.pack2(self._detail_pane(), False, False)
        paned.set_position(720)

        self.reload()

    # --- detail pane -----------------------------------------------------

    def _detail_pane(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=14)
        box.set_size_request(340, -1)
        self.preview = Gtk.DrawingArea()
        self.preview.set_size_request(320, 180)
        self.preview.connect("draw", self._draw_detail)
        frame = Gtk.Frame()
        frame.add(self.preview)
        box.pack_start(frame, False, False, 0)
        self.title_label = Gtk.Label(xalign=0)
        box.pack_start(self.title_label, False, False, 0)
        self.backgrounds = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.SINGLE, max_children_per_line=4)
        self.backgrounds.connect("child-activated", self._on_background)
        box.pack_start(self.backgrounds, False, False, 0)
        actions = Gtk.Box(spacing=6)
        self.use_button = Gtk.Button(label="Use This Theme")
        self.use_button.get_style_context().add_class("suggested-action")
        self.use_button.connect("clicked", self._on_use)
        self.spinner = Gtk.Spinner()
        actions.pack_start(self.use_button, False, False, 0)
        actions.pack_start(self.spinner, False, False, 0)
        self.remove_button = Gtk.Button(label="Remove")
        self.remove_button.set_no_show_all(True)  # only for themes the person installed
        self.remove_button.connect("clicked", self._on_remove)
        actions.pack_end(self.remove_button, False, False, 0)
        box.pack_start(actions, False, False, 0)
        credits_title = Gtk.Label(xalign=0)
        credits_title.set_markup("<b>Credits</b>")
        box.pack_start(credits_title, False, False, 0)
        scroller = Gtk.ScrolledWindow()
        self.credits = Gtk.Label(xalign=0, yalign=0, wrap=True, selectable=True)
        self.credits.set_line_wrap(True)
        scroller.add(self.credits)
        box.pack_start(scroller, True, True, 0)
        return box

    def _draw_detail(self, widget, cr) -> None:
        if self.selected:
            w, h = widget.get_allocated_width(), widget.get_allocated_height()
            draw_preview(cr, self.selected, w, h, apply.background_for(self.selected, self.background_index))

    def show_theme(self, theme: store.Theme) -> None:
        self.selected = theme
        self.background_index = 0
        current, _ = store.current()
        state = "  (on now)" if theme.slug == current else ""
        self.title_label.set_markup(
            f"<big><b>{GLib.markup_escape_text(theme.name)}</b></big>{state}\n"
            f"<span alpha='70%'>{'Dark' if theme.palette.dark else 'Light'} · "
            f"{'stock theme' if theme.stock else 'your theme'}</span>"
        )
        for child in self.backgrounds.get_children():
            self.backgrounds.remove(child)
        for path in theme.backgrounds:
            img = Gtk.Image.new_from_pixbuf(thumbnail(path, 72, 40))
            img.set_tooltip_text(path.name)
            self.backgrounds.add(img)
        self.backgrounds.show_all()
        self.credits.set_text(plain(theme.credits) if theme.credits else "This theme has no credits or licence file.")
        self.remove_button.set_visible(not theme.stock)
        self.preview.queue_draw()

    # --- the grid ----------------------------------------------------------

    def reload(self, select: str | None = None) -> None:
        for child in self.grid.get_children():
            self.grid.remove(child)
        current, _ = store.current()
        themes = store.themes()
        for theme in themes.values():
            card = Card(theme, theme.slug == current)
            self.grid.add(card)
            if theme.slug == (select or current):
                self.grid.select_child(card)
                self.show_theme(theme)
        self.grid.show_all()
        if self.selected is None and themes:
            self.show_theme(next(iter(themes.values())))

    def _filter_card(self, child: Card) -> bool:
        if self.filter == "all":
            return True
        return child.theme.palette.mode == self.filter

    def _on_filter(self, button, key) -> None:
        if button.get_active():
            self.filter = key
            self.grid.invalidate_filter()

    def _on_card(self, _grid, child: Card) -> None:
        self.show_theme(child.theme)

    def _on_background(self, _box, child) -> None:
        self.background_index = child.get_index()
        self.preview.queue_draw()

    # --- actions -----------------------------------------------------------

    def _busy(self, busy: bool) -> None:
        self.use_button.set_sensitive(not busy)
        (self.spinner.start if busy else self.spinner.stop)()

    def _in_thread(self, work, done) -> None:
        self._busy(True)

        def run():
            try:
                result, error = work(), None
            except Exception as e:  # shown to the person, not lost
                result, error = None, e
            GLib.idle_add(lambda: (self._busy(False), done(result, error)) and False)

        threading.Thread(target=run, daemon=True).start()

    def _say(self, text: str, undo: bool = False, error: bool = False) -> None:
        self.info_label.set_text(text)
        self.infobar.set_message_type(Gtk.MessageType.ERROR if error else Gtk.MessageType.INFO)
        self.undo_button.set_visible(undo)
        self.infobar.show()
        self.info_label.show()

    def _on_use(self, _button) -> None:
        theme, index = self.selected, self.background_index
        if theme is None:
            return

        def done(_result, error):
            if error:
                self._say(f"Couldn't switch to {theme.name}: {error}", error=True)
            else:
                self._say(f"{theme.name} is on.", undo=True)
                self.reload(select=theme.slug)

        self._in_thread(lambda: apply.switch(theme, index), done)

    def _on_info_response(self, bar, response) -> None:
        bar.hide()
        if response == 1:

            def done(slug, error):
                if error:
                    self._say(f"Couldn't go back: {error}", error=True)
                elif slug:
                    self._say("Back to the desktop's own look." if slug == "default" else f"Back to {store.title(slug)}.")
                    self.reload(select=slug)

            self._in_thread(apply.undo, done)

    def _on_install(self, _button) -> None:
        dialog = Gtk.Dialog(title="Install a Theme from Git", transient_for=self, modal=True)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Install", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        area = dialog.get_content_area()
        area.set_spacing(8)
        area.set_border_width(12)
        area.add(Gtk.Label(
            label="The repository's colours, images and text are kept; nothing in it is run.\n"
            "Omarchy theme repositories work too.",
            xalign=0,
        ))
        entry = Gtk.Entry(placeholder_text="https://github.com/…/…-theme", activates_default=True)
        entry.set_width_chars(48)
        area.add(entry)
        dialog.show_all()
        response, url = dialog.run(), entry.get_text().strip()
        dialog.destroy()
        if response != Gtk.ResponseType.OK or not url:
            return

        def done(result, error):
            if error:
                self._say(f"Couldn't install that theme: {error}", error=True)
                return
            theme, _dropped = result
            self.reload(select=theme.slug)
            self._show_licence(theme)

        self._in_thread(lambda: install.install(url), done)

    def _show_licence(self, theme: store.Theme) -> None:
        licence = install.licence_text(theme)
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK, text=f"{theme.name} is installed",
        )
        dialog.format_secondary_text(
            (licence.strip()[:1500] if licence else
             "The repository has no licence file. You can use it yourself; check its README before sharing it.")
        )
        dialog.run()
        dialog.destroy()

    def _on_remove(self, _button) -> None:
        if self.selected and not self.selected.stock:
            install.remove(self.selected.slug)
            self.selected = None
            self.reload()

    def _on_folder(self, _button) -> None:
        d = store.user_themes_dir()
        d.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["xdg-open", str(d)], env=os.environ)
