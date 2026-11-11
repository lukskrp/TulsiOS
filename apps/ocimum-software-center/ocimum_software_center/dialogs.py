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
