"""Gtk.Application entry point.

Exposes actions on the session bus (org.gtk.Actions on /org/tulsi/SoftwareCenter)
so other tools, tests and later the Ocimum Assistant can open the app on a
specific change. Actions still show the confirmation dialog:
    install(s)  remove(s)  undo  search(s)
"""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, __version__  # noqa: E402
from .model import ops_install, ops_remove  # noqa: E402


class Application(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.window = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        string = GLib.VariantType.new("s")
        self._action("install", string, lambda attr: self._win().request_change(
            ops_install(attr), f"Installing {attr}", "Install"))
        self._action("remove", string, lambda attr: self._win().request_change(
            ops_remove(attr), f"Removing {attr}", "Remove"))
        self._action("search", string, self._search)
        self._action("undo", None, lambda _: self._win().request_undo())
        self._action("quit", None, lambda _: self.quit())
        self.set_accels_for_action("app.quit", ["<Primary>q"])

    def _action(self, name: str, param_type, handler) -> None:
        action = Gio.SimpleAction.new(name, param_type)

        def activate(_action, param):
            # Run outside the D-Bus dispatch so modal dialogs work.
            def run() -> bool:
                handler(param.unpack() if param is not None else None)
                return GLib.SOURCE_REMOVE

            GLib.idle_add(run)

        action.connect("activate", activate)
        self.add_action(action)

    def _win(self):
        if self.window is None:
            self.do_activate()
        return self.window

    def _search(self, text: str) -> None:
        window = self._win()
        window.stack.set_visible_child_name("search")
        window.search_entry.set_text(text)

    def do_activate(self) -> None:
        if self.window is None:
            from .client import Client
            from .window import Window

            try:
                client = Client()
            except GLib.Error as e:
                dialog = Gtk.MessageDialog(
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.CLOSE,
                    text="Cannot connect to the system bus",
                )
                dialog.format_secondary_text(e.message)
                dialog.run()
                dialog.destroy()
                self.quit()
                return
            self.window = Window(self, client)
        self.window.present()


def main() -> int:
    if "--version" in sys.argv:
        print(f"ocimum-software-center {__version__}")
        return 0
    GLib.set_application_name("Software Center")
    GLib.set_prgname(APP_ID)
    return Application().run(sys.argv)
