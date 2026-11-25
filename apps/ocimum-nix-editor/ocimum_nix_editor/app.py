"""Nix Editor: write and fix Nix packages, with nixd and a Nix guide (ADR 0019).

    ocimum-nix-editor [FILE...]
    ocimum-nix-editor --draft DIR     a Recipe's draft (package.nix + recipe.json)
"""

from __future__ import annotations

import argparse
import os
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkSource", "4")
from gi.repository import Gio, Gtk  # noqa: E402

APP_ID = "org.tulsi.NixEditor"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ocimum-nix-editor", description=__doc__.split("\n")[0])
    parser.add_argument("--draft", help="a Recipe's draft folder to fix, build and install")
    parser.add_argument("files", nargs="*")
    return parser.parse_args(argv)


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None

    def do_command_line(self, command_line) -> int:
        args = parse_args(command_line.get_arguments()[1:])
        cwd = command_line.get_cwd() or os.getcwd()
        from .window import Window

        if self.window is None:
            self.window = Window(self)
        win = self.window
        opened = False
        if args.draft:
            win.open_draft(os.path.join(cwd, args.draft))
            opened = True
        for f in args.files:
            opened = win.open_path(os.path.join(cwd, f)) is not None or opened
        if not opened and not win.tabs:
            win.new_tab()
        win.show_all()
        win._switched()
        win.present()
        return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else [sys.argv[0], *argv]
    return App().run(argv)


if __name__ == "__main__":
    sys.exit(main())
