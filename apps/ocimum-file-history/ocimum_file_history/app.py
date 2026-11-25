"""File History: earlier versions of your files, from /home's snapshots (ADR 0027).

usage: ocimum-file-history [PATH]
"""

from __future__ import annotations

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, Gtk  # noqa: E402

APP_ID = "org.tulsi.FileHistory"


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.path: Path | None = None

    def do_activate(self):
        from .window import Window

        window = Window(self, self.path)
        window.show_all()
        window.present()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    app = App()
    args = [a for a in argv if not a.startswith("-")]
    if args:
        # Nemo and Dolphin pass a file:// URI or a path.
        arg = args[0]
        app.path = Path(Gio.File.new_for_commandline_arg(arg).get_path() or arg)
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
