"""ocimum-approve: asks the human to approve a system change requested by an
AI agent (used by tulsi-mcp).

Reads a JSON request on stdin:
    {"title": str, "reason": str, "changes": [str], "diff": str?, "requester": str}
Exit status: 0 approved, 1 rejected or closed, 2 invalid input.
Reject is the default button, so pressing Enter never approves by accident.
"""

from __future__ import annotations

import json
import sys

APPROVED, REJECTED, INVALID = 0, 1, 2


def parse_request(text: str) -> dict:
    """Validates the request; raises ValueError with a readable message."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"not JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    changes = data.get("changes")
    if not isinstance(changes, list) or not changes or not all(isinstance(c, str) for c in changes):
        raise ValueError("'changes' must be a non-empty list of strings")
    return {
        "title": str(data.get("title") or "A program wants to change this system"),
        "reason": str(data.get("reason") or "(no reason given)"),
        "changes": changes,
        "diff": data.get("diff") if isinstance(data.get("diff"), str) else None,
        "requester": str(data.get("requester") or "an unknown program"),
    }


def run_dialog(request: dict) -> int:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import GLib, Gtk, Pango

    dialog = Gtk.Dialog(title="Approve System Change", modal=True)
    dialog.set_default_size(560, -1)
    dialog.set_keep_above(True)
    dialog.set_urgency_hint(True)
    dialog.set_position(Gtk.WindowPosition.CENTER)

    reject = dialog.add_button("Reject", Gtk.ResponseType.REJECT)
    approve = dialog.add_button("Approve and Apply", Gtk.ResponseType.ACCEPT)
    approve.get_style_context().add_class("suggested-action")
    dialog.set_default_response(Gtk.ResponseType.REJECT)

    area = dialog.get_content_area()
    area.set_spacing(10)
    area.set_border_width(16)

    top = Gtk.Box(spacing=14)
    icon = Gtk.Image.new_from_icon_name("dialog-warning", Gtk.IconSize.DIALOG)
    icon.set_valign(Gtk.Align.START)
    top.pack_start(icon, False, False, 0)
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

    def label(markup: str, *, dim: bool = False) -> Gtk.Label:
        lbl = Gtk.Label(xalign=0, wrap=True, max_width_chars=70, selectable=True)
        lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        lbl.set_markup(markup)
        if dim:
            lbl.get_style_context().add_class("dim-label")
        return lbl

    esc = GLib.markup_escape_text
    text.pack_start(label(f"<span size='large' weight='bold'>{esc(request['title'])}</span>"), False, False, 0)
    text.pack_start(label(f"Requested by {esc(request['requester'])}.", dim=True), False, False, 0)
    text.pack_start(label(f"<b>Reason given:</b> {esc(request['reason'])}"), False, False, 0)
    from .model import describe_change

    changes = "\n".join(f"• {esc(describe_change(c))}" for c in request["changes"])
    text.pack_start(label(f"<b>Changes:</b>\n{changes}"), False, False, 0)
    text.pack_start(
        label("The system configuration will be rebuilt. You can undo this later in the "
              "Software Center's History tab.", dim=True),
        False, False, 0,
    )
    top.pack_start(text, True, True, 0)
    area.pack_start(top, False, False, 0)

    if request["diff"]:
        expander = Gtk.Expander(label="Show the exact change", expanded=True)
        scroller = Gtk.ScrolledWindow(min_content_height=220, max_content_height=360)
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True)
        buffer = view.get_buffer()
        added = buffer.create_tag("added", foreground="#2e7d32")
        removed = buffer.create_tag("removed", foreground="#c62828")
        for line in request["diff"].splitlines():
            tag = added if line.startswith("+") and not line.startswith("+++") else (
                removed if line.startswith("-") and not line.startswith("---") else None)
            end = buffer.get_end_iter()
            if tag:
                buffer.insert_with_tags(end, line + "\n", tag)
            else:
                buffer.insert(end, line + "\n")
        scroller.add(view)
        expander.add(scroller)
        area.pack_start(expander, True, True, 0)

    dialog.show_all()
    reject.grab_focus()
    response = dialog.run()
    dialog.destroy()
    return APPROVED if response == Gtk.ResponseType.ACCEPT else REJECTED


def main() -> int:
    try:
        request = parse_request(sys.stdin.read())
    except ValueError as e:
        print(f"ocimum-approve: invalid request: {e}", file=sys.stderr)
        return INVALID
    return run_dialog(request)


if __name__ == "__main__":
    sys.exit(main())
