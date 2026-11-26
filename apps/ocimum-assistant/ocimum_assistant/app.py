"""Gtk.Application entry point. Action `ask(s)` (org.gtk.Actions on the
session bus) opens the window and asks a question, for launchers and tests."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, __version__  # noqa: E402


class Application(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.window = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        ask = Gio.SimpleAction.new("ask", GLib.VariantType.new("s"))
        ask.connect("activate", self._on_ask)
        self.add_action(ask)
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Primary>q"])

    def _on_ask(self, _action, param) -> None:
        text = param.unpack()

        def run() -> bool:
            self.do_activate()
            self.window.ask(text)
            return GLib.SOURCE_REMOVE

        GLib.idle_add(run)

    def do_activate(self) -> None:
        if self.window is None:
            from .window import Window

            self.window = Window(self)
        self.window.present()


def _explain(path: str) -> int:
    """--explain FILE: ask about the file's text (explain.py, ADR 0037), in the
    running Assistant if there is one."""
    from pathlib import Path

    from . import explain

    try:
        question = explain.question_for(Path(path))
    except explain.CannotExplain as e:
        dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.INFO,
                                   buttons=Gtk.ButtonsType.CLOSE, text="Can't explain this file")
        dialog.format_secondary_text(str(e))
        dialog.run()
        return 1
    app = Application()
    app.register(None)
    app.activate_action("ask", GLib.Variant("s", question))
    if app.get_is_remote():
        app.get_dbus_connection().flush_sync(None)
        return 0
    return app.run([sys.argv[0]])


def main() -> int:
    if "--version" in sys.argv:
        print(f"ocimum-assistant {__version__}")
        return 0
    GLib.set_application_name("Assistant")
    GLib.set_prgname(APP_ID)
    if len(sys.argv) == 3 and sys.argv[1] == "--explain":
        return _explain(sys.argv[2])
    return Application().run(sys.argv)
