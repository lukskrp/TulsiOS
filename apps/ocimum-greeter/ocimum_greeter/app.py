"""The Ocimum greeter window (OTK).

Started by greetd, inside an X server of its own (XLibre, run as the `greeter` user by
the launcher in nix/modules/ocimum-greeter.nix). There is no window manager: the window
covers the monitor itself and takes the keyboard focus.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time

import gi

gi.require_version("Otk", "3.0")
gi.require_version("Odk", "3.0")
from gi.repository import GLib, Odk as Gdk, Otk as Gtk  # noqa: E402

from .config import Config  # noqa: E402
from .greetd import Greetd, GreetdError  # noqa: E402
from .login import Failed, Login, Notice, Prompt, Started  # noqa: E402
from .sessions import find_sessions  # noqa: E402

CSS = """
window.ocimum-greeter {
  background-color: #1d2b22;
  background-size: cover;
  background-position: center;
}
.card {
  background-color: rgba(20, 28, 24, 0.82);
  border-radius: 14px;
  padding: 28px 32px;
}
.title { font-size: 22pt; font-weight: bold; color: #eef3ee; }
.clock { font-size: 13pt; color: #c9d6cc; }
.message { color: #f0c7c7; }
.message.info { color: #c9d6cc; }
entry { min-width: 280px; min-height: 34px; }
button.suggested-action { min-height: 34px; }
"""


class GreeterWindow:
    def __init__(self, config: Config, greetd: Greetd):
        self.config = config
        self.login = Login(greetd, config.launcher)
        self.sessions = find_sessions(config.sessions_dir, config.default_session)
        self.busy = False
        self.awaiting_answer = False  # a later PAM prompt (after the password) is shown

        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL, title="Ocimum Greeter")
        self.window.get_style_context().add_class("ocimum-greeter")
        self.window.set_decorated(False)
        self._load_css()

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.get_style_context().add_class("card")
        card.set_halign(Gtk.Align.CENTER)
        card.set_valign(Gtk.Align.CENTER)

        title = Gtk.Label(label=config.title)
        title.get_style_context().add_class("title")
        self.clock = Gtk.Label()
        self.clock.get_style_context().add_class("clock")
        card.pack_start(title, False, False, 0)
        card.pack_start(self.clock, False, False, 6)

        self.user_entry = Gtk.Entry(placeholder_text="User name")
        self.user_entry.set_text(config.last_user() or "")
        self.password_entry = Gtk.Entry(placeholder_text="Password", visibility=False)
        self.password_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        card.pack_start(self.user_entry, False, False, 0)
        card.pack_start(self.password_entry, False, False, 0)

        self.session_combo = Gtk.ComboBoxText()
        for session in self.sessions:
            self.session_combo.append(session.id, session.name)
        if self.sessions:
            self.session_combo.set_active(0)
        card.pack_start(self.session_combo, False, False, 0)

        self.message = Gtk.Label(wrap=True, max_width_chars=40)
        self.message.get_style_context().add_class("message")
        card.pack_start(self.message, False, False, 0)

        self.login_button = Gtk.Button(label="Log in")
        self.login_button.get_style_context().add_class("suggested-action")
        card.pack_start(self.login_button, False, False, 0)

        power = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        power.set_halign(Gtk.Align.CENTER)
        for label, action in (("Restart", "reboot"), ("Shut down", "poweroff")):
            button = Gtk.Button(label=label)
            button.get_style_context().add_class("flat")
            button.connect("clicked", self._on_power, action)
            power.pack_start(button, False, False, 0)
        card.pack_start(power, False, False, 8)

        self.window.add(card)

        self.user_entry.connect("activate", self._on_user_activate)
        self.password_entry.connect("activate", self._on_submit)
        self.login_button.connect("clicked", self._on_submit)
        self.window.connect("destroy", lambda *_: Gtk.main_quit())
        self.window.connect("map-event", self._on_mapped)

        self._update_clock()
        GLib.timeout_add_seconds(10, self._update_clock)

        if not self.sessions:
            self._show_message("No desktop sessions are installed.", error=True)
            self.login_button.set_sensitive(False)
        self.session_combo.set_visible(len(self.sessions) > 1)
        self.session_combo.set_no_show_all(len(self.sessions) <= 1)

    # --- setup

    def _load_css(self) -> None:
        css = CSS
        if self.config.wallpaper:
            css += 'window.ocimum-greeter { background-image: url("file://%s"); }\n' % self.config.wallpaper
        provider = Gtk.CssProvider()
        try:
            provider.load_from_data(css.encode("utf-8"))
        except GLib.Error as error:  # e.g. the wallpaper cannot be loaded
            print(f"ocimum-greeter: {error.message}", file=sys.stderr)
            provider.load_from_data(CSS.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def show(self) -> None:
        # No window manager: cover the primary monitor ourselves.
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        area = monitor.get_geometry()
        self.window.move(area.x, area.y)
        self.window.set_default_size(area.width, area.height)
        root = Gdk.get_default_root_window()
        root.set_cursor(Gdk.Cursor.new_for_display(display, Gdk.CursorType.LEFT_PTR))
        self.window.show_all()

    def _on_mapped(self, *_):
        self.window.get_window().focus(Gdk.CURRENT_TIME)
        (self.password_entry if self.user_entry.get_text() else self.user_entry).grab_focus()
        return False

    def _update_clock(self) -> bool:
        self.clock.set_text(time.strftime("%A %-d %B, %H:%M"))
        return True

    # --- login

    def _on_user_activate(self, *_):
        if self.user_entry.get_text().strip():
            self.password_entry.grab_focus()

    def _on_submit(self, *_):
        if self.busy:
            return
        if self.awaiting_answer:
            answer = self.password_entry.get_text()
            self._run(lambda: self.login.respond(answer))
            return
        user = self.user_entry.get_text().strip()
        if not user:
            self.user_entry.grab_focus()
            return
        session = self._selected_session()
        if session is None:
            return
        self._run(lambda: self.login.begin(user, session))

    def _selected_session(self):
        session_id = self.session_combo.get_active_id()
        for session in self.sessions:
            if session.id == session_id:
                return session
        return self.sessions[0] if self.sessions else None

    def _run(self, request) -> None:
        """Talk to greetd on a worker thread (PAM may pause after a wrong password)."""
        self._set_busy(True)

        def work():
            try:
                step = request()
            except (GreetdError, OSError) as error:
                step = Failed(str(error))
            GLib.idle_add(self._handle, step)

        threading.Thread(target=work, daemon=True).start()

    def _handle(self, step) -> bool:
        self._set_busy(False)
        if isinstance(step, Prompt):
            if step.secret and not self.awaiting_answer and self.password_entry.get_text():
                # The first password prompt: answer with what was typed.
                answer = self.password_entry.get_text()
                self.awaiting_answer = True
                self._run(lambda: self.login.respond(answer))
                return False
            # A further question (new password, one-time code, ...).
            self.awaiting_answer = True
            self.password_entry.set_text("")
            self.password_entry.set_visibility(not step.secret)
            self.password_entry.set_placeholder_text(step.text)
            self._show_message(step.text, error=False)
            self.password_entry.grab_focus()
        elif isinstance(step, Notice):
            self._show_message(step.text, error=step.error)
            self._run(lambda: self.login.respond(None))
        elif isinstance(step, Started):
            self.config.remember_user(self.user_entry.get_text().strip())
            Gtk.main_quit()
        elif isinstance(step, Failed):
            self._reset_prompt()
            self._show_message(step.text, error=True)
            self.password_entry.grab_focus()
        return False

    def _reset_prompt(self) -> None:
        self.awaiting_answer = False
        self.password_entry.set_text("")
        self.password_entry.set_visibility(False)
        self.password_entry.set_placeholder_text("Password")

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        for widget in (self.user_entry, self.password_entry, self.login_button, self.session_combo):
            widget.set_sensitive(not busy)
        if not busy:
            self.login_button.set_sensitive(bool(self.sessions))

    def _show_message(self, text: str, error: bool) -> None:
        context = self.message.get_style_context()
        if error:
            context.remove_class("info")
        else:
            context.add_class("info")
        self.message.set_text(text)

    # --- power

    def _on_power(self, _button, action: str) -> None:
        self.login.cancel()
        subprocess.Popen(["systemctl", action])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ocimum-greeter", description="Ocimum's login screen for greetd")
    parser.add_argument("--config", required=True, help="JSON configuration (written by the NixOS module)")
    args = parser.parse_args(argv)

    config = Config.load(args.config)
    try:
        greetd = Greetd.connect()
    except (GreetdError, OSError) as error:
        print(f"ocimum-greeter: cannot reach greetd: {error}", file=sys.stderr)
        return 1

    Gtk.init(None)
    greeter = GreeterWindow(config, greetd)
    greeter.show()
    Gtk.main()
    greetd.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
