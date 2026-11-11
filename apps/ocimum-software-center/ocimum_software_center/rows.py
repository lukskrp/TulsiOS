"""List rows used by the Search, Installed and History pages."""

from __future__ import annotations

from gi.repository import GLib, GObject, Gtk, Pango

from .model import Package, history_title, relative_time

FALLBACK_ICON = "package-x-generic"


def _icon_name(package: Package) -> str:
    theme = Gtk.IconTheme.get_default()
    for name in (package.pname, package.attr.rsplit(".", 1)[-1]):
        if name and theme.has_icon(name):
            return name
    return FALLBACK_ICON


def _label(text: str = "", *, css: str | None = None, wrap: bool = False) -> Gtk.Label:
    label = Gtk.Label(label=text, xalign=0, selectable=False)
    if wrap:
        label.set_line_wrap(True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_lines(2)
        label.set_ellipsize(Pango.EllipsizeMode.END)
    else:
        label.set_ellipsize(Pango.EllipsizeMode.END)
    if css:
        label.get_style_context().add_class(css)
    return label


class PackageRow(Gtk.ListBoxRow):
    """Icon, name, version and description, with an Install or Remove button."""

    __gsignals__ = {
        # (attr, install?)
        "requested": (GObject.SignalFlags.RUN_FIRST, None, (str, bool)),
    }

    def __init__(self, package: Package):
        super().__init__(activatable=False, selectable=False)
        self.package = package

        box = Gtk.Box(spacing=12, margin=10)
        icon = Gtk.Image.new_from_icon_name(_icon_name(package), Gtk.IconSize.DIALOG)
        icon.set_pixel_size(48)
        box.pack_start(icon, False, False, 0)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        title = _label()
        title.set_markup(f"<b>{GLib.markup_escape_text(package.title)}</b>")
        text.pack_start(title, False, False, 0)
        if package.subtitle:
            text.pack_start(_label(package.subtitle, css="dim-label"), False, False, 0)
        if package.description:
            text.pack_start(_label(package.description, wrap=True), False, False, 0)
        box.pack_start(text, True, True, 0)

        self.button = Gtk.Button(valign=Gtk.Align.CENTER)
        self.button.set_size_request(96, -1)
        self.button.connect("clicked", self._on_clicked)
        box.pack_end(self.button, False, False, 0)
        self._update_button()

        self.add(box)
        self.show_all()

    def _update_button(self) -> None:
        style = self.button.get_style_context()
        style.remove_class("suggested-action")
        style.remove_class("destructive-action")
        if self.package.installed:
            self.button.set_label("Remove")
            style.add_class("destructive-action")
            self.button.set_tooltip_text(f"Remove {self.package.title} from this system")
        else:
            self.button.set_label("Install")
            style.add_class("suggested-action")
            self.button.set_tooltip_text(f"Install {self.package.title} on this system")

    def _on_clicked(self, _button) -> None:
        self.emit("requested", self.package.attr, not self.package.installed)

    def set_installed(self, installed: bool) -> None:
        self.package.installed = installed
        self._update_button()

    def set_busy(self, busy: bool) -> None:
        self.button.set_sensitive(not busy)


class HistoryRow(Gtk.ListBoxRow):
    def __init__(self, entry: dict):
        super().__init__(activatable=False, selectable=False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin=10)
        title = _label()
        title.set_markup(f"<b>{GLib.markup_escape_text(history_title(entry['summary']))}</b>")
        box.pack_start(title, False, False, 0)
        when = f"{relative_time(entry['time'])} · {entry['commit']}"
        box.pack_start(_label(when, css="dim-label"), False, False, 0)
        self.add(box)
        self.show_all()


def placeholder(icon: str, title: str, text: str = "") -> Gtk.Box:
    """Centered icon + message, used for empty and error states."""
    box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=8,
        valign=Gtk.Align.CENTER,
        halign=Gtk.Align.CENTER,
        margin=24,
    )
    image = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.DIALOG)
    image.set_pixel_size(64)
    image.get_style_context().add_class("dim-label")
    box.pack_start(image, False, False, 0)
    heading = Gtk.Label(justify=Gtk.Justification.CENTER)
    heading.set_markup(f"<span size='large' weight='bold'>{GLib.markup_escape_text(title)}</span>")
    box.pack_start(heading, False, False, 0)
    body = Gtk.Label(label=text, justify=Gtk.Justification.CENTER, wrap=True, max_width_chars=60)
    body.get_style_context().add_class("dim-label")
    box.pack_start(body, False, False, 0)
    box.body = body  # so callers can update the message
    box.show_all()
    return box
