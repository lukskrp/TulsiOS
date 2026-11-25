"""Confirmation and error dialogs."""

from __future__ import annotations

from gi.repository import Gtk

CONFIRM_TITLE = "Confirm Changes"


def confirm(parent: Gtk.Window, heading: str, changes: list[str], apply_label: str) -> bool:
    """Shows what will change; returns True if the user chose to apply."""
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.NONE,
        text=heading,
        title=CONFIRM_TITLE,
    )
    body = "\n".join(f"• {c}" for c in changes)
    dialog.format_secondary_text(
        f"{body}\n\nThe system configuration is rebuilt; this can take a few minutes. "
        "You can undo it later."
    )
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    apply_button = dialog.add_button(apply_label, Gtk.ResponseType.OK)
    apply_button.get_style_context().add_class("suggested-action")
    dialog.set_default_response(Gtk.ResponseType.OK)
    response = dialog.run()
    dialog.destroy()
    return response == Gtk.ResponseType.OK


FROM_FILE_TITLE = "Install from a File or Link"


def file_or_link(parent: Gtk.Window) -> tuple[str, str] | None:
    """A downloaded file ("file", path) or a link ("url", link); None if cancelled."""
    dialog = Gtk.Dialog(title=FROM_FILE_TITLE, transient_for=parent, modal=True)
    dialog.add_button("_Cancel", Gtk.ResponseType.CANCEL)
    go = dialog.add_button("_Continue", Gtk.ResponseType.OK)
    go.get_style_context().add_class("suggested-action")
    dialog.set_default_response(Gtk.ResponseType.OK)
    area = dialog.get_content_area()
    area.set_spacing(8)
    area.set_border_width(12)
    intro = Gtk.Label(
        label="A .deb, .rpm, AppImage, archive or program you downloaded, or a link to an "
        "extension's store page or a download page.",
        xalign=0,
        wrap=True,
        max_width_chars=60,
    )
    area.pack_start(intro, False, False, 0)
    chooser = Gtk.FileChooserButton(title="Choose a Downloaded File")
    downloads = _downloads_dir()
    if downloads:
        chooser.set_current_folder(downloads)
    area.pack_start(chooser, False, False, 0)
    link = Gtk.Entry(placeholder_text="…or paste a link", activates_default=True)
    area.pack_start(link, False, False, 0)

    def update(*_args) -> None:
        go.set_sensitive(bool(chooser.get_filename() or link.get_text().strip()))

    chooser.connect("file-set", update)
    link.connect("changed", update)
    update()
    dialog.show_all()
    try:
        if dialog.run() != Gtk.ResponseType.OK:
            return None
        if link.get_text().strip():
            return "url", link.get_text().strip()
        if chooser.get_filename():
            return "file", chooser.get_filename()
        return None
    finally:
        dialog.destroy()


def _downloads_dir() -> str:
    from gi.repository import GLib

    return GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD) or ""


LICENSE_TITLE = "Software Licence"


def accept_license(parent: Gtk.Window, title: str, license_name: str, url: str) -> bool:
    """Asks a person to accept an unfree package's licence; True if they accept."""
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.NONE,
        text=f"{title} is proprietary software",
        title=LICENSE_TITLE,
    )
    dialog.format_secondary_text(
        "It is distributed under its vendor's licence, not a free-software licence:\n"
        f"{license_name}\n\n"
        "To install it, you must accept this licence. TulsiOS records that you did, "
        "and allows this one package. AI agents cannot accept licences for you."
    )
    if url:
        link = Gtk.LinkButton(uri=url, label="Read the licence")
        link.set_halign(Gtk.Align.START)
        dialog.get_message_area().pack_start(link, False, False, 0)
        link.show()
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    accept = dialog.add_button("_Accept Licence", Gtk.ResponseType.OK)
    accept.get_style_context().add_class("suggested-action")
    dialog.set_default_response(Gtk.ResponseType.CANCEL)
    response = dialog.run()
    dialog.destroy()
    return response == Gtk.ResponseType.OK


def show_error(parent: Gtk.Window, heading: str, message: str, details: str = "") -> None:
    first, _, rest = message.partition("\n")
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.CLOSE,
        text=heading,
        title=heading,
    )
    dialog.format_secondary_text(first)
    more = "\n".join(part for part in (rest.strip(), details.strip()) if part)
    if more:
        expander = Gtk.Expander(label="Details")
        scroller = Gtk.ScrolledWindow(min_content_height=200, min_content_width=520)
        view = Gtk.TextView(editable=False, monospace=True, cursor_visible=False)
        view.get_buffer().set_text(more)
        scroller.add(view)
        expander.add(scroller)
        dialog.get_message_area().pack_start(expander, True, True, 0)
        expander.show_all()
    dialog.run()
    dialog.destroy()
