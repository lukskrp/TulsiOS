"""Themes: pick the desktop's colours and background from palettes (ADR 0021)."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, Gtk  # noqa: E402

APP_ID = "org.tulsi.Themes"


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
    argv = sys.argv if argv is None else [sys.argv[0], *argv]
    return App().run(argv)


if __name__ == "__main__":
    sys.exit(main())
