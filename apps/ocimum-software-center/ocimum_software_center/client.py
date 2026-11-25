"""Asynchronous client for tulsid (D-Bus org.tulsi.Manager1), using Gio.

All calls take `on_ok` and `on_error` callbacks and never block the UI.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

from gi.repository import Gio, GLib, GObject

BUS_NAME = "org.tulsi.Manager1"
OBJECT_PATH = "/org/tulsi/Manager1"
INTERFACE = "org.tulsi.Manager1"

# Apply/Undo may wait for the user at a polkit password prompt.
NO_TIMEOUT = GLib.MAXINT
DEFAULT_TIMEOUT = 30_000
# CheckUpgrade downloads the release branch's newest source.
CHECK_TIMEOUT = 300_000


class TulsiError(Exception):
    """An error reported by tulsid (or by D-Bus on its behalf)."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message

    @classmethod
    def from_glib(cls, error: GLib.Error) -> "TulsiError":
        remote = Gio.DBusError.get_remote_error(error) or ""
        Gio.DBusError.strip_remote_error(error)
        if remote in (
            "org.freedesktop.DBus.Error.ServiceUnknown",
            "org.freedesktop.DBus.Error.NameHasNoOwner",
        ):
            return cls("Unavailable", "The TulsiOS system service (tulsid) is not running.")
        kind = remote.rsplit(".", 1)[-1] if remote.startswith("org.tulsi.Error.") else "Error"
        return cls(kind, error.message)


OnOk = Callable[[Any], None]
OnError = Callable[[TulsiError], None]


class Client(GObject.Object):
    """Wraps the tulsid D-Bus API; re-emits its signals as GObject signals."""

    __gsignals__ = {
        "progress": (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_UINT64, str)),
        "finished": (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_UINT64, bool, str)),
    }

    def __init__(self, bus_type: Gio.BusType | None = None):
        super().__init__()
        if bus_type is None:
            session = os.environ.get("TULSI_BUS") == "session"
            bus_type = Gio.BusType.SESSION if session else Gio.BusType.SYSTEM
        self._proxy = Gio.DBusProxy.new_for_bus_sync(
            bus_type,
            Gio.DBusProxyFlags.DO_NOT_AUTO_START | Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES,
            None,
            BUS_NAME,
            OBJECT_PATH,
            INTERFACE,
            None,
        )
        self._proxy.connect("g-signal", self._on_signal)

    def _on_signal(self, _proxy, _sender, name: str, params: GLib.Variant) -> None:
        if name == "Progress":
            job, line = params.unpack()
            self.emit("progress", job, line)
        elif name == "Finished":
            job, success, message = params.unpack()
            self.emit("finished", job, success, message)

    def _call(
        self,
        method: str,
        params: GLib.Variant | None,
        on_ok: OnOk,
        on_error: OnError,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        decode_json: bool = False,
    ) -> None:
        def done(proxy: Gio.DBusProxy, result: Gio.AsyncResult) -> None:
            try:
                reply = proxy.call_finish(result)
            except GLib.Error as e:
                on_error(TulsiError.from_glib(e))
                return
            value = reply.unpack()[0] if reply.n_children() else None
            if decode_json:
                try:
                    value = json.loads(value)
                except (TypeError, ValueError) as e:
                    on_error(TulsiError("Error", f"Unexpected reply from tulsid: {e}"))
                    return
            on_ok(value)

        flags = Gio.DBusCallFlags.ALLOW_INTERACTIVE_AUTHORIZATION
        self._proxy.call(method, params, flags, timeout, None, done)

    def get_state(self, on_ok: OnOk, on_error: OnError) -> None:
        self._call("GetState", None, on_ok, on_error, decode_json=True)

    def search(self, query: str, limit: int, on_ok: OnOk, on_error: OnError) -> None:
        self._call(
            "Search", GLib.Variant("(su)", (query, limit)), on_ok, on_error, decode_json=True
        )

    def match(self, hint: dict, limit: int, on_ok: OnOk, on_error: OnError) -> None:
        """What TulsiOS has for what someone tried to install (ADR 0018).

        `hint`: {names, programs, provides, tool}. on_ok receives candidates, best
        first: {kind: "package", attr, pname, …, reason} or
        {kind: "service", name, enabled, reason}."""
        self._call(
            "Match",
            GLib.Variant("(su)", (json.dumps(hint), limit)),
            on_ok,
            on_error,
            decode_json=True,
        )

    def package_info(self, attr: str, on_ok: OnOk, on_error: OnError) -> None:
        self._call("PackageInfo", GLib.Variant("(s)", (attr,)), on_ok, on_error, decode_json=True)

    def plan(self, ops: list[dict], on_ok: OnOk, on_error: OnError) -> None:
        self._call(
            "Plan", GLib.Variant("(s)", (json.dumps(ops),)), on_ok, on_error, decode_json=True
        )

    def apply(self, ops: list[dict], on_ok: OnOk, on_error: OnError) -> None:
        """on_ok receives the job id (0 = nothing to change)."""
        self._call(
            "Apply", GLib.Variant("(s)", (json.dumps(ops),)), on_ok, on_error, timeout=NO_TIMEOUT
        )

    def undo(self, on_ok: OnOk, on_error: OnError) -> None:
        self._call("Undo", None, on_ok, on_error, timeout=NO_TIMEOUT)

    def undo_change(self, commit: str, on_ok: OnOk, on_error: OnError) -> None:
        """Takes back one earlier change; on_ok receives the job id."""
        self._call(
            "UndoChange", GLib.Variant("(s)", (commit,)), on_ok, on_error, timeout=NO_TIMEOUT
        )

    def plan_undo(self, commit: str, on_ok: OnOk, on_error: OnError) -> None:
        """on_ok receives {commit, summary, changes, action}."""
        self._call("PlanUndo", GLib.Variant("(s)", (commit,)), on_ok, on_error, decode_json=True)

    def history(self, limit: int, on_ok: OnOk, on_error: OnError) -> None:
        self._call("History", GLib.Variant("(u)", (limit,)), on_ok, on_error, decode_json=True)

    def check_upgrade(self, on_ok: OnOk, on_error: OnError) -> None:
        """on_ok receives {following, currentVersion, availableVersion, available, error, …}.
        Fetches the release branch, which can take a while."""
        self._call("CheckUpgrade", None, on_ok, on_error, timeout=CHECK_TIMEOUT, decode_json=True)

    def upgrade(self, on_ok: OnOk, on_error: OnError) -> None:
        """Moves to the newest TulsiOS release; on_ok receives the job id."""
        self._call("Upgrade", None, on_ok, on_error, timeout=NO_TIMEOUT)
