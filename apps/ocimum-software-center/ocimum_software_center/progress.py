"""Bottom panel showing a running change and its rebuild output."""

from __future__ import annotations

from gi.repository import GLib, Gtk, Pango

MAX_BUFFER_LINES = 2000


class ProgressPanel(Gtk.Revealer):
    def __init__(self):
        super().__init__(transition_type=Gtk.RevealerTransitionType.SLIDE_UP)

        frame = Gtk.Frame()
        frame.get_style_context().add_class("view")
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        bar = Gtk.Box(spacing=10, margin=8)
        self.spinner = Gtk.Spinner()
        bar.pack_start(self.spinner, False, False, 0)
        self.status = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        bar.pack_start(self.status, True, True, 0)
        self.details_button = Gtk.ToggleButton(label="Details")
        self.details_button.connect("toggled", self._on_details_toggled)
        bar.pack_end(self.details_button, False, False, 0)
        outer.pack_start(bar, False, False, 0)

        self.details = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        scroller = Gtk.ScrolledWindow(min_content_height=180, max_content_height=180)
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True)
        self.view.set_wrap_mode(Gtk.WrapMode.CHAR)
        self.view.set_left_margin(8)
        scroller.add(self.view)
        self.details.add(scroller)
        outer.pack_start(self.details, False, False, 0)

        frame.add(outer)
        self.add(frame)
        self.show_all()
        self.set_reveal_child(False)

    def _on_details_toggled(self, button: Gtk.ToggleButton) -> None:
        self.details.set_reveal_child(button.get_active())

    def start(self, text: str) -> None:
        self.view.get_buffer().set_text("")
        self.status.set_text(text)
        self.spinner.start()
        self.set_reveal_child(True)

    def append(self, line: str) -> None:
        buffer = self.view.get_buffer()
        buffer.insert(buffer.get_end_iter(), line + "\n")
        excess = buffer.get_line_count() - MAX_BUFFER_LINES
        if excess > 0:
            buffer.delete(buffer.get_start_iter(), buffer.get_iter_at_line(excess))
        self.status.set_text(line.strip() or self.status.get_text())
        mark = buffer.create_mark(None, buffer.get_end_iter(), False)
        self.view.scroll_mark_onscreen(mark)
        buffer.delete_mark(mark)

    def finish(self, success: bool, text: str) -> None:
        self.spinner.stop()
        self.status.set_text(text)
        if success:
            # Leave the log available for a moment, then get out of the way.
            GLib.timeout_add_seconds(2, self._hide)
        else:
            self.details_button.set_active(True)

    def _hide(self) -> bool:
        if not self.spinner.get_property("active"):
            self.details_button.set_active(False)
            self.set_reveal_child(False)
        return GLib.SOURCE_REMOVE

    def log_text(self) -> str:
        buffer = self.view.get_buffer()
        return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
