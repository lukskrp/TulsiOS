"""Backup (ADR 0039).

usage: tulsi-backup-app

Your files and your software list, to a USB drive and back. Snapshots undo
mistakes on this disk; a backup is for a dead disk or a new machine. The
terminal way is `tulsi-backup`.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, Gtk  # noqa: E402

APP_ID = "org.tulsi.Backup"


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
