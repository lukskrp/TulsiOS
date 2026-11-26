"""The TulsiOS Welcome window (ADR 0027).

usage: tulsi-welcome [--first-login | --turn-on-history]
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from . import welcome  # noqa: E402

APP_ID = "org.tulsi.Welcome"


def _label(markup: str, dim: bool = False) -> Gtk.Label:
    label = Gtk.Label(xalign=0, wrap=True, max_width_chars=70)
    label.set_markup(markup)
    if dim:
        label.get_style_context().add_class("dim-label")
    return label


def _launch(*cmd: str) -> None:
    if shutil.which(cmd[0]):
        subprocess.Popen(list(cmd), start_new_session=True)


class Window(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Welcome to TulsiOS", default_width=640, default_height=480)
        self.set_icon_name("tulsi-start")
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.add_titled(self._welcome_page(), "welcome", "Welcome")
        self.stack.add_titled(self._history_page(), "history", "Your Files' History")
        # Only when a device needs a driver (ADR 0029).
        self.drivers = welcome.drivers_needed()
        if self.drivers is not None:
            self.stack.add_titled(self._drivers_page(self.drivers), "drivers", "Drivers")
        # Only when the installer left the codecs off (ADR 0035).
        if not welcome.codecs_on():
            self.stack.add_titled(self._media_page(), "media", "Media")
        header = Gtk.HeaderBar(show_close_button=True)
        header.set_custom_title(Gtk.StackSwitcher(stack=self.stack))
        self.set_titlebar(header)
        self.add(self.stack)

    def _page(self) -> Gtk.Box:
        return Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=24)

    def _welcome_page(self) -> Gtk.Widget:
        page = self._page()
        page.pack_start(_label("<big><b>Welcome to TulsiOS</b></big>"), False, False, 0)
        page.pack_start(_label(
            "Every change to the system is recorded and can be undone, whether you make it "
            "or an AI agent does. A few things to start with:"), False, False, 0)
        for title, text, cmd in (
            ("Software Center", "install and remove apps, and undo any change", ("ocimum-software-center",)),
            ("AI Agents", "coding agents and local models, and what your computer can run",
             ("ocimum-software-center", "--page", "ai")),
            ("Themes", "the desktop's colours and background", ("ocimum-themes",)),
            ("Drivers", "graphics card, Wi-Fi and other hardware drivers", ("tulsi-drivers-app",)),
            ("Agent Privileges", "what AI agents may do on their own", ("starah-session", "--show")),
            ("TulsiOS Wiki", "help for all of this, on your computer", ("tulsi-wiki",)),
        ):
            row = Gtk.Box(spacing=12)
            button = Gtk.Button(label=title)
            button.set_size_request(170, -1)
            button.connect("clicked", lambda _b, c=cmd: _launch(*c))
            row.pack_start(button, False, False, 0)
            row.pack_start(_label(text, dim=True), True, True, 0)
            page.pack_start(row, False, False, 0)
        page.pack_start(_label("<b>AI agents and your files</b>"), False, False, 0)
        page.pack_start(_label(
            "Coding agents you start in a terminal (Claude Code, Codex, OpenCode, …) run as "
            "their own accounts, not as you: they see only the folder you start them in, keep "
            "their own logins, and their changes to the system follow the level you choose in "
            "Agent Privileges. There you can also let an agent use <b>your whole home "
            "folder</b>: then it works with your logins and settings, your SSH keys (it can "
            "push with git) and your other projects. Only do that for agents you trust."),
            False, False, 0)
        page.pack_start(_label(
            "⚠ This holds only for agents installed through TulsiOS (the Software Center's "
            "AI Agents page). An agent installed another way (npm, pip, a script from a "
            "website, a downloaded program) runs as you, with access to all your files."),
            False, False, 0)
        more = Gtk.Button(label="Read: AI Agents and Starah", halign=Gtk.Align.START)
        more.connect("clicked", lambda _b: _launch("tulsi-wiki", "ai-agents"))
        page.pack_start(more, False, False, 0)
        nxt = Gtk.Button(label="Next: Your Files' History", halign=Gtk.Align.END, valign=Gtk.Align.END, vexpand=True)
        nxt.get_style_context().add_class("suggested-action")
        nxt.connect("clicked", lambda _b: self.stack.set_visible_child_name("history"))
        page.pack_start(nxt, True, True, 0)
        return page

    def _history_page(self) -> Gtk.Widget:
        page = self._page()
        page.pack_start(_label("<big><b>Keep a history of your files?</b></big>"), False, False, 0)
        page.pack_start(_label(
            "TulsiOS can take a snapshot of the home folders every hour, and keep the last day of "
            "hourly ones, a week of daily ones and a month of weekly ones. Deleted or overwritten "
            "a file? <b>File History</b> (or right-click › Previous Versions) brings it back."), False, False, 0)
        page.pack_start(_label(
            "A snapshot only takes the space of what changed since the one before, and File History "
            "can free that space at any time. Snapshots are on the same disk as your files: they "
            "protect against mistakes, not a broken disk. Keep a backup too."), False, False, 0)
        self.status = _label("", dim=True)
        page.pack_start(self.status, False, False, 0)
        self.spinner = Gtk.Spinner()
        page.pack_start(self.spinner, False, False, 0)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END, valign=Gtk.Align.END, vexpand=True)
        later = Gtk.Button(label="Not Now")
        later.connect("clicked", lambda _b: self.close())
        self.turn_on = Gtk.Button(label="Turn On File History")
        self.turn_on.get_style_context().add_class("suggested-action")
        self.turn_on.connect("clicked", lambda _b: self._turn_on())
        buttons.pack_start(later, False, False, 0)
        buttons.pack_start(self.turn_on, False, False, 0)
        page.pack_start(buttons, True, True, 0)
        self._refresh()
        return page

    def _media_page(self) -> Gtk.Widget:
        page = self._page()
        page.pack_start(_label("<big><b>Play all common media?</b></big>"), False, False, 0)
        page.pack_start(_label(
            "TulsiOS was installed with patent-free formats only. The video player still "
            "plays most videos, but other apps may not play MP3, AAC or MP4 files, and "
            "DVDs and RAR archives don't open."), False, False, 0)
        page.pack_start(_label(
            "Turning the common codecs on adds them for every app. Some of these formats "
            "are covered by software patents in a few countries. It asks for your "
            "password, and the Software Center's History can undo it."), False, False, 0)
        self.media_status = _label("", dim=True)
        page.pack_start(self.media_status, False, False, 0)
        self.media_spinner = Gtk.Spinner()
        page.pack_start(self.media_spinner, False, False, 0)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END, valign=Gtk.Align.END, vexpand=True)
        self.media_button = Gtk.Button(label="Turn On Codecs")
        self.media_button.get_style_context().add_class("suggested-action")
        self.media_button.connect("clicked", lambda _b: self._turn_on_codecs())
        buttons.pack_start(self.media_button, False, False, 0)
        page.pack_start(buttons, True, True, 0)
        return page

    def _turn_on_codecs(self) -> None:
        self.media_button.set_sensitive(False)
        self.media_spinner.start()
        self.media_status.set_markup("Turning on the codecs… (this takes a few minutes)")

        def work() -> None:
            ok, out = welcome.turn_on_codecs()
            GLib.idle_add(self._codecs_done, ok, out)

        threading.Thread(target=work, daemon=True).start()

    def _codecs_done(self, ok: bool, out: str) -> bool:
        self.media_spinner.stop()
        if ok:
            self.media_status.set_markup("The codecs are on. Apps you start from now play them.")
        else:
            last = out.strip().splitlines()[-1] if out.strip() else "unknown error"
            self.media_status.set_markup(f"Could not turn them on: {GLib.markup_escape_text(last)}")
            self.media_button.set_sensitive(True)
        return GLib.SOURCE_REMOVE

    def _drivers_page(self, recommended: str) -> Gtk.Widget:
        page = self._page()
        page.pack_start(_label("<big><b>Drivers for your hardware</b></big>"), False, False, 0)
        page.pack_start(_label(
            "TulsiOS found hardware that works better, or only, with its maker's driver:"), False, False, 0)
        page.pack_start(_label(f"<b>{GLib.markup_escape_text(recommended)}</b>"), False, False, 0)
        page.pack_start(_label(
            "Open <b>Drivers</b> to choose. New drivers take effect when you restart, and "
            "TulsiOS then asks whether everything works; if the screen stays black, restarting "
            "again brings the drivers before back by themselves."), False, False, 0)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END, valign=Gtk.Align.END, vexpand=True)
        more = Gtk.Button(label="Read: Drivers")
        more.connect("clicked", lambda _b: _launch("tulsi-wiki", "drivers"))
        open_ = Gtk.Button(label="Open Drivers")
        open_.get_style_context().add_class("suggested-action")
        open_.connect("clicked", lambda _b: _launch("tulsi-drivers-app"))
        buttons.pack_start(more, False, False, 0)
        buttons.pack_start(open_, False, False, 0)
        page.pack_start(buttons, True, True, 0)
        return page

    def _refresh(self) -> None:
        if welcome.snapshots_on():
            self.status.set_markup("File History is on.")
            self.turn_on.set_sensitive(False)
        elif welcome.fs_type("/home") != "btrfs":
            self.status.set_markup(
                "Not available here: your home folders are on "
                f"{welcome.fs_type('/home') or 'a file system'} without snapshots. TulsiOS "
                "installs on btrfs by default; this computer was installed with another choice.")
            self.turn_on.set_sensitive(False)
        else:
            self.status.set_markup("It is off. Turning it on asks for your password, and can be "
                                   "undone in the Software Center's History.")

    def _turn_on(self) -> None:
        self.turn_on.set_sensitive(False)
        self.spinner.start()
        self.status.set_markup("Turning on File History… (this rebuilds the system; it takes a few minutes)")

        def work() -> None:
            ok, out = welcome.turn_on_snapshots()
            GLib.idle_add(self._done, ok, out)

        threading.Thread(target=work, daemon=True).start()

    def _done(self, ok: bool, out: str) -> bool:
        self.spinner.stop()
        if ok:
            self.status.set_markup("File History is on. The first snapshot comes within the hour.")
        else:
            last = out.strip().splitlines()[-1] if out.strip() else "unknown error"
            self.status.set_markup(f"Could not turn it on: {GLib.markup_escape_text(last)}")
            self.turn_on.set_sensitive(True)
        return GLib.SOURCE_REMOVE


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self):
        window = self.get_active_window() or Window(self)
        window.show_all()
        window.present()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--turn-on-history" in argv:
        # The window's "Turn On File History", without the window.
        ok, out = welcome.turn_on_snapshots()
        print(out)
        return 0 if ok else 1
    first_login = "--first-login" in argv
    if not welcome.should_show(first_login):
        return 0
    if first_login:
        welcome.mark_shown()
    return App().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
