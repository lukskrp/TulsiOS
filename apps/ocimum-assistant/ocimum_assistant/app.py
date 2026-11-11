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


def main() -> int:
    if "--version" in sys.argv:
        print(f"ocimum-assistant {__version__}")
        return 0
    GLib.set_application_name("Assistant")
    GLib.set_prgname(APP_ID)
    return Application().run(sys.argv)
