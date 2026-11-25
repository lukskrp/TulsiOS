"""Gtk.Application entry point.

Exposes actions on the session bus (org.gtk.Actions on /org/tulsi/SoftwareCenter)
so other tools, tests and later the Ocimum Assistant can open the app on a
specific change. Actions still show the confirmation dialog:
    install(s)  remove(s)  service(s)  add-extension(s)  apply-ops(s)  undo  search(s)
    show-page(s)  history  upgrade
(service: turn on services.<name>; add-extension: a store page's link; apply-ops:
{"ops": [...], "label": "..."}, e.g. a local package a recipe built.)
"""

from __future__ import annotations

import json
import sys

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, __version__  # noqa: E402
from .model import ops_remove  # noqa: E402


class Application(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.window = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        string = GLib.VariantType.new("s")
        self._action("install", string, lambda attr: self._win().install(attr))
        self._action("remove", string, lambda attr: self._win().request_change(
            ops_remove(attr), f"Removing {attr}", "Remove"))
        self._action("service", string, lambda name: self._win().enable_service(name))
        self._action("add-extension", string, self._add_extension)
        self._action("apply-ops", string, self._apply_ops)
        # "Install from a file or link": the step-by-step tulsi-adopt window with it.
        self._action("install-file", string, lambda path: self._win().open_adopt("file", path))
        self._action("search", string, self._search)
        # show-page: a page by name (ai: the AI Agents page, the desktops' shortcut).
        self._action("show-page", string, self._show_page)
        self._action("undo", None, lambda _: self._win().request_undo())
        self._action("history", None, lambda _: self._history())
        self._action("upgrade", None, lambda _: self._win().show_updates())
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

    def _show_page(self, name: str) -> None:
        window = self._win()
        if window.stack.get_child_by_name(name) is not None:
            window.stack.set_visible_child_name(name)
        window.present()

    def _apply_ops(self, payload: str) -> None:
        """{"ops": [...], "label": "Installing frob"}: any change, with the usual
        confirmation (tulsi-adopt's recipes install local packages this way)."""
        window = self._win()
        try:
            data = json.loads(payload)
            ops, label = data["ops"], data.get("label") or "Applying changes"
        except (ValueError, KeyError, TypeError) as e:
            window.show_message(f"Invalid change request: {e}", error=True)
            return
        window.stack.set_visible_child_name("installed")
        window.request_change(ops, label, "Install")

    def _add_extension(self, url: str) -> None:
        window = self._win()
        window.stack.set_visible_child_name("extensions")
        window.add_extension_link(url)

    def _history(self) -> None:
        window = self._win()
        if window.stack.get_visible_child_name() == "history":
            window.refresh_history()
        else:
            window.stack.set_visible_child_name("history")
        window.present()

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
    app = Application()
    # --page NAME: that page (--page ai: the AI Agents shortcut).
    page = None
    if "--page" in sys.argv:
        i = sys.argv.index("--page")
        if i + 1 < len(sys.argv):
            page = sys.argv[i + 1]
            del sys.argv[i : i + 2]
    if page is not None:
        app.register(None)
        app.activate_action("show-page", GLib.Variant("s", page))
        if app.get_is_remote():
            connection = app.get_dbus_connection()
            if connection is not None:
                connection.flush_sync(None)
            return 0
        return app.run(sys.argv)
    # --history: the History page (the Assistant's "Recent changes"); --upgrade: the
    # Updates page (the upgrade notification's button). In the running instance if
    # there is one.
    for flag, action in (("--history", "history"), ("--upgrade", "upgrade")):
        if flag in sys.argv:
            sys.argv.remove(flag)
            app.register(None)
            app.activate_action(action, None)
            if app.get_is_remote():
                connection = app.get_dbus_connection()
                if connection is not None:
                    connection.flush_sync(None)
                return 0
            break
    return app.run(sys.argv)
