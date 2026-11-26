"""Update Manager (ADR 0038).

usage: tulsi-update-manager

Three tabs: the TulsiOS release (check, upgrade), older system versions
(generations, cleanup), and /home snapshots (take one, open File History).
Upgrades run in the background; generations are never deleted here except
through the same `tulsi-cleanup` the weekly timer uses.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, Gtk  # noqa: E402

APP_ID = "org.tulsi.UpdateManager"


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window = None

    def do_activate(self):
        from .window import Window

        if self.window is None:
            self.window = Window(self)
        self.window.show_all()
        self.window.present()


def main(argv: list[str] | None = None) -> int:
    return App().run([__import__("sys").argv[0]])


if __name__ == "__main__":
    import sys

    sys.exit(main())
