"""The Update Manager window (ADR 0038): release, generations, snapshots."""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from . import system  # noqa: E402


def _label(markup: str, dim: bool = False, wrap: bool = True) -> Gtk.Label:
    label = Gtk.Label(xalign=0, wrap=wrap, max_width_chars=72)
    label.set_markup(markup)
    if dim:
        label.get_style_context().add_class("dim-label")
    return label


def _esc(text: str) -> str:
    return GLib.markup_escape_text(text)


class Window(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Update Manager", default_width=680, default_height=560)
        self.set_icon_name("org.tulsi.UpdateManager")
        header = Gtk.HeaderBar(show_close_button=True, title="Update Manager")
        self.set_titlebar(header)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(outer)
        self.bar = Gtk.InfoBar(show_close_button=False, no_show_all=True)
        self.bar_label = _label("")
        self.bar.get_content_area().add(self.bar_label)
        outer.pack_start(self.bar, False, False, 0)

        self.tabs = Gtk.Notebook(margin=12, vexpand=True)
        outer.pack_start(self.tabs, True, True, 0)
        self.release_tab = self._release_tab()
        self.tabs.append_page(self.release_tab, Gtk.Label(label="Release"))
        self.generations_tab = self._generations_tab()
        self.tabs.append_page(self.generations_tab, Gtk.Label(label="Older Versions"))
        self.snapshots_tab = self._snapshots_tab()
        self.tabs.append_page(self.snapshots_tab, Gtk.Label(label="Snapshots"))

        actions = Gtk.Box(spacing=8, margin=12)
        self.spinner = Gtk.Spinner()
        self.status = _label("", dim=True)
        actions.pack_start(self.spinner, False, False, 0)
        actions.pack_start(self.status, True, True, 0)
        self.refresh_button = Gtk.Button(label="Check Again")
        self.refresh_button.connect("clicked", lambda _b: self.load())
        actions.pack_end(self.refresh_button, False, False, 0)
        outer.pack_start(Gtk.Separator(), False, False, 0)
        outer.pack_start(actions, False, False, 0)

        self.busy: set[str] = set()
        self.load()

    # ------------------------------------------------------------ loading

    def load(self) -> None:
        self._release_loading()
        self._generations_loading()
        self._snapshots_loading()
        self.bar.hide()
        self._work("check", system.check_release, self._release_done)
        self._work("generations", system.generations, self._generations_done)
        self._work("snapshots", system.snapshots, self._snapshots_done)

    def _work(self, name: str, fn, done) -> None:
        self.busy.add(name)
        self.spinner.start()
        self.status.set_markup("Loading…")

        def work() -> None:
            try:
                result = fn()
            except Exception as e:  # noqa: BLE001 — shown, never crashes
                result = e
            GLib.idle_add(self._finished, name, done, result)

        threading.Thread(target=work, daemon=True).start()

    def _finished(self, name: str, done, result) -> bool:
        self.busy.discard(name)
        if not self.busy:
            self.spinner.stop()
            self.status.set_markup("")
        if isinstance(result, Exception):
            self.status.set_markup(f"Couldn't load {name}: {_esc(str(result))}")
            return GLib.SOURCE_REMOVE
        done(result)
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------ release

    def _release_tab(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=18)
        self.release_version = _label("")
        box.pack_start(self.release_version, False, False, 0)
        self.release_state = _label("")
        box.pack_start(self.release_state, False, False, 0)
        row = Gtk.Box(spacing=8)
        self.upgrade_button = Gtk.Button(label="Upgrade…")
        self.upgrade_button.get_style_context().add_class("suggested-action")
        self.upgrade_button.connect("clicked", lambda _b: self._upgrade())
        row.pack_start(self.upgrade_button, False, False, 0)
        box.pack_start(row, False, False, 0)
        box.pack_start(_label(
            "Upgrading keeps your apps and settings: it adds a new system version, "
            "which you can undo afterwards. A home snapshot is taken first when "
            "snapshots are on.", dim=True), False, False, 0)
        return box

    def _release_loading(self) -> None:
        self.release_version.set_markup(f"This system: <b>{_esc(system.current_version())}</b>")
        self.release_state.set_markup("Checking for a new release…")
        self.upgrade_button.set_sensitive(False)

    def _release_done(self, check: system.ReleaseCheck) -> None:
        if check.error:
            self.release_state.set_markup(f"Couldn't check: {_esc(check.error)}")
            return
        if check.available:
            self.release_state.set_markup(f"<b>TulsiOS {_esc(check.available_version)} is available.</b>")
            self.upgrade_button.set_sensitive(True)
            return
        self.release_state.set_markup("This is the newest release.")

    def _upgrade(self) -> None:
        self.upgrade_button.set_sensitive(False)
        self.refresh_button.set_sensitive(False)
        self.spinner.start()
        self.status.set_markup("Upgrading… (this takes a while; the window stays usable)")

        def work() -> None:
            ok, out = system.upgrade()
            GLib.idle_add(self._upgraded, ok, out)

        threading.Thread(target=work, daemon=True).start()

    def _upgraded(self, ok: bool, out: str) -> bool:
        self.spinner.stop()
        self.refresh_button.set_sensitive(True)
        last = out.strip().splitlines()[-1] if out.strip() else "unknown error"
        if ok:
            self.bar.set_message_type(Gtk.MessageType.INFO)
            self.bar_label.set_markup(f"Upgraded. {_esc(last)} Restart to use the new release.")
            self.bar.show_all()
            self.status.set_markup("")
        else:
            self.status.set_markup(f"Not upgraded: {_esc(last)}")
        self.load()
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------ generations

    def _generations_tab(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=18)
        box.pack_start(_label(
            "Every change, undo and upgrade adds a system version. The boot menu "
            "lists the newest ones: restart and pick an older version to go back, "
            "with your files untouched."), False, False, 0)
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        self.generations_store = Gtk.ListStore(str, str, str)
        tree = Gtk.TreeView(model=self.generations_store)
        for i, title in enumerate(("Version", "Made", "Running")):
            column = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i)
            tree.append_column(column)
        scroll.add(tree)
        box.pack_start(scroll, True, True, 0)
        row = Gtk.Box(spacing=8)
        self.cleanup_button = Gtk.Button(label="Remove Old Versions Now")
        self.cleanup_button.connect("clicked", lambda _b: self._cleanup())
        row.pack_start(self.cleanup_button, False, False, 0)
        box.pack_start(row, False, False, 0)
        return box

    def _generations_loading(self) -> None:
        self.generations_store.clear()
        self.cleanup_button.set_sensitive(False)

    def _generations_done(self, generations: list[system.Generation]) -> None:
        for g in sorted(generations, key=lambda g: g.number, reverse=True):
            self.generations_store.append((str(g.number), g.date, "yes" if g.current else ""))
        if not generations:
            self.generations_store.append(("", "", "No older versions yet — every change adds one."))
        self.cleanup_button.set_sensitive(True)

    def _cleanup(self) -> None:
        self.cleanup_button.set_sensitive(False)
        self.spinner.start()
        self.status.set_markup("Removing old versions…")

        def work() -> None:
            ok, out = system.cleanup_now()
            GLib.idle_add(self._cleaned, ok, out)

        threading.Thread(target=work, daemon=True).start()

    def _cleaned(self, ok: bool, out: str) -> bool:
        self.spinner.stop()
        last = out.strip().splitlines()[-1] if out.strip() else ""
        self.status.set_markup(_esc(last if ok else f"Not cleaned: {last}"))
        self._work("generations", system.generations, self._generations_done)
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------ snapshots

    def _snapshots_tab(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=18)
        box.pack_start(_label(
            "Snapshots are instant copies of /home (needs btrfs, the installer's "
            "default). They undo deleted or changed files — browse them in File "
            "History — but they are on the same disk, so they are not a backup."), False, False, 0)
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        self.snapshots_store = Gtk.ListStore(str, str, str)
        tree = Gtk.TreeView(model=self.snapshots_store)
        for i, title in enumerate(("Number", "Made", "Description")):
            column = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i)
            tree.append_column(column)
        scroll.add(tree)
        box.pack_start(scroll, True, True, 0)
        row = Gtk.Box(spacing=8)
        self.snapshot_button = Gtk.Button(label="Take a Snapshot Now")
        self.snapshot_button.connect("clicked", lambda _b: self._snapshot())
        row.pack_start(self.snapshot_button, False, False, 0)
        history = Gtk.Button(label="Open File History")
        history.connect("clicked", lambda _b: self._file_history())
        row.pack_start(history, False, False, 0)
        box.pack_start(row, False, False, 0)
        return box

    def _snapshots_loading(self) -> None:
        self.snapshots_store.clear()
        self.snapshot_button.set_sensitive(False)

    def _snapshots_done(self, result: tuple) -> None:
        snapshots, reason = result
        if snapshots is None:
            self.snapshots_store.append(("", "", reason))
            return
        for s in sorted(snapshots, key=lambda s: s.number, reverse=True):
            self.snapshots_store.append((str(s.number), s.date, s.description))
        self.snapshot_button.set_sensitive(True)

    def _snapshot(self) -> None:
        self.snapshot_button.set_sensitive(False)
        self.spinner.start()
        self.status.set_markup("Taking a snapshot…")

        def work() -> None:
            ok, out = system.take_snapshot("from Update Manager")
            GLib.idle_add(self._snapshotted, ok, out)

        threading.Thread(target=work, daemon=True).start()

    def _snapshotted(self, ok: bool, out: str) -> bool:
        self.spinner.stop()
        last = out.strip().splitlines()[-1] if out.strip() else ""
        self.status.set_markup(_esc("Snapshot taken." if ok else f"Not taken: {last}"))
        self._work("snapshots", system.snapshots, self._snapshots_done)
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _file_history() -> None:
        import subprocess

        for cmd in ("ocimum-file-history", "tulsi-file-history"):
            try:
                subprocess.Popen([cmd])  # noqa: S603 — a fixed TulsiOS program name
                return
            except OSError:
                continue
