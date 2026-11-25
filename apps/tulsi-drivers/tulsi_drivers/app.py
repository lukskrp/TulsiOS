"""Drivers (ADR 0029).

usage: tulsi-drivers-app [--trial-prompt]

--trial-prompt (at login): after starting with new drivers, asks whether
everything works (Keep / Go Back); after a change was undone by itself, says why.
"""

from __future__ import annotations

import sys
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from . import system  # noqa: E402

APP_ID = "org.tulsi.Drivers"


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


def _summary(trial: dict) -> str:
    return trial.get("summary", "").removeprefix("tulsi: edit configuration.nix: ").removeprefix("Drivers: ")


def trial_prompt() -> int:
    trial = system.trial_status()
    state = trial.get("state")
    if state == "reverted":
        dialog = Gtk.MessageDialog(
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK,
            text="Your new drivers were undone",
        )
        dialog.format_secondary_text(f"{_summary(trial)}\n\n{trial.get('notice', '')}")
        dialog.set_title("Drivers")
        dialog.run()
        dialog.destroy()
        system.trial("dismiss")
        return 0
    if state != "testing":
        return 0
    grub = trial.get("bootLoader") != "systemd-boot"
    dialog = Gtk.MessageDialog(
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.NONE,
        text="Do your new drivers work?",
    )
    dialog.set_title("Drivers")
    dialog.set_keep_above(True)
    text = (
        f"You started with: {_summary(trial)}.\n\nIf the screen, the Wi-Fi and everything else "
        "work, keep them. Otherwise go back to the drivers before."
    )
    if grub:
        text += " If you don't answer within 10 minutes, they are undone."
    else:
        text += " (Restarting without keeping them also goes back.)"
    dialog.format_secondary_text(text)
    dialog.add_button("Go Back", Gtk.ResponseType.REJECT)
    keep = dialog.add_button("Keep", Gtk.ResponseType.ACCEPT)
    keep.get_style_context().add_class("suggested-action")
    response = dialog.run()
    dialog.destroy()
    if response == Gtk.ResponseType.ACCEPT:
        ok, out = system.trial("keep")
        return 0 if ok else 1
    if response == Gtk.ResponseType.REJECT:
        return _go_back()
    return 0


def _go_back() -> int:
    """Undo (a rebuild, minutes) with a window saying so, then offer to restart."""
    win = Gtk.Window(title="Drivers", default_width=420)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=18)
    label = Gtk.Label(label="Going back to the drivers before… (this takes a few minutes)", wrap=True, xalign=0)
    spinner = Gtk.Spinner()
    spinner.start()
    box.pack_start(label, False, False, 0)
    box.pack_start(spinner, False, False, 0)
    buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
    restart = Gtk.Button(label="Restart Now", sensitive=False)
    restart.get_style_context().add_class("suggested-action")
    restart.connect("clicked", lambda _b: system.restart())
    close = Gtk.Button(label="Close")
    close.connect("clicked", lambda _b: Gtk.main_quit())
    buttons.pack_start(close, False, False, 0)
    buttons.pack_start(restart, False, False, 0)
    box.pack_start(buttons, False, False, 0)
    win.add(box)
    win.connect("destroy", lambda _w: Gtk.main_quit())
    win.show_all()
    result = {"ok": False}

    def done(ok: bool, out: str) -> bool:
        spinner.stop()
        result["ok"] = ok
        if ok:
            label.set_text("Done. Restart to use the drivers before.")
            restart.set_sensitive(True)
        else:
            last = out.strip().splitlines()[-1] if out.strip() else "unknown error"
            label.set_text(f"Could not go back: {last}\nRestarting without keeping the new drivers also goes back.")
        return GLib.SOURCE_REMOVE

    def work() -> None:
        ok, out = system.trial("undo")
        GLib.idle_add(done, ok, out)

    threading.Thread(target=work, daemon=True).start()
    Gtk.main()
    return 0 if result["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--trial-prompt" in argv:
        return trial_prompt()
    return App().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
