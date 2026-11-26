"""The Backup window (ADR 0039): back up now, restore a backup, see what's there."""

from __future__ import annotations

import threading
from pathlib import Path

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
        super().__init__(application=app, title="Backup", default_width=680, default_height=560)
        self.set_icon_name("org.tulsi.Backup")
        header = Gtk.HeaderBar(show_close_button=True, title="Backup")
        self.set_titlebar(header)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(outer)

        target_row = Gtk.Box(spacing=8, margin=12)
        target_row.pack_start(Gtk.Label(label="Back up to:"), False, False, 0)
        self.targets = Gtk.ComboBoxText(hexpand=True)
        self.reload_targets()
        target_row.pack_start(self.targets, True, True, 0)
        choose = Gtk.Button(label="Choose…")
        choose.connect("clicked", lambda _b: self._choose_target())
        target_row.pack_start(choose, False, False, 0)
        outer.pack_start(target_row, False, False, 0)
        outer.pack_start(Gtk.Separator(), False, False, 0)

        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True, margin=12)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        scroll.add(self.list)
        outer.pack_start(scroll, True, True, 0)
        outer.pack_start(Gtk.Separator(), False, False, 0)

        actions = Gtk.Box(spacing=8, margin=12)
        self.spinner = Gtk.Spinner()
        self.status = _label("", dim=True)
        actions.pack_start(self.spinner, False, False, 0)
        actions.pack_start(self.status, True, True, 0)
        self.backup_button = Gtk.Button(label="Back Up Now")
        self.backup_button.get_style_context().add_class("suggested-action")
        self.backup_button.connect("clicked", lambda _b: self._backup())
        actions.pack_end(self.backup_button, False, False, 0)
        outer.pack_start(actions, False, False, 0)

        self.busy = False
        self.load()

    # ------------------------------------------------------------ loading

    def target(self) -> str:
        return self.targets.get_active_text() or ""

    def reload_targets(self) -> None:
        self.targets.remove_all()
        for path in system.removable_targets():
            self.targets.append_text(str(path))
        if self.targets.get_active() < 0:
            self.targets.set_active(0)

    def load(self) -> None:
        for child in self.list.get_children():
            self.list.remove(child)
        if not self.target():
            self.list.pack_start(
                _label("Plug in a USB drive: it appears above. Backups hold your files "
                       "and which software you chose — snapshots stay for mistakes on this disk."),
                False, False, 0)
            self.backup_button.set_sensitive(False)
        else:
            self.backup_button.set_sensitive(not self.busy)
            self._work(system.list_backups, self.target(), self._listed)
        self.list.show_all()

    def _listed(self, result) -> None:
        backups, _ = result
        if not backups:
            self.list.pack_start(_label("No backups here yet.", dim=True), False, False, 0)
        for path, manifest in backups:
            if manifest is None:
                self.list.pack_start(_label(f"<b>{_esc(path.name)}</b> — unreadable manifest", ), False, False, 0)
                continue
            row = Gtk.Box(spacing=8)
            row.pack_start(_label(
                f"<b>{_esc(manifest.date)}</b> — TulsiOS {_esc(manifest.tulsios_version)}, "
                f"{len(manifest.packages)} packages"), True, True, 0)
            restore = Gtk.Button(label="Restore…")
            restore.connect("clicked", lambda _b, p=path: self._restore(p))
            row.pack_start(restore, False, False, 0)
            self.list.pack_start(Gtk.Separator(), False, False, 0)
            self.list.pack_start(row, False, False, 0)
        self.list.show_all()

    # ------------------------------------------------------------ working

    def _work(self, fn, *args) -> None:
        self.busy = True
        self.backup_button.set_sensitive(False)
        self.spinner.start()
        self.status.set_markup("Working…")

        def work() -> None:
            try:
                ok, message = fn(*args)
                result: object = (ok, message)
            except Exception as e:  # noqa: BLE001 — shown, never crashes
                result = e
            GLib.idle_add(self._done, result)

        threading.Thread(target=work, daemon=True).start()

    def _done(self, result: object) -> bool:
        self.busy = False
        self.spinner.stop()
        if isinstance(result, Exception):
            self.status.set_markup(f"Failed: {_esc(str(result))}")
        else:
            ok, message = result  # type: ignore[misc]
            self.status.set_markup(_esc(message if ok else f"Failed: {message}"))
        self.load()
        return GLib.SOURCE_REMOVE

    def _backup(self) -> None:
        target = self.target()
        if target:
            self._work(system.backup, str(system.default_home()), target)

    def _restore(self, path: Path) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=f"Restore {path.name}?",
        )
        dialog.format_second_markup(
            "Its files are merged into your home folder — nothing already there is "
            "deleted. Afterwards, reinstall its software from the list it kept.")
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        go = dialog.add_button("Restore", Gtk.ResponseType.ACCEPT)
        go.get_style_context().add_class("suggested-action")
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.ACCEPT:
            self._work(system.restore, path, str(system.default_home()))

    def _choose_target(self) -> None:
        dialog = Gtk.FileChooserDialog(
            transient_for=self, title="Back up to…", action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Choose", Gtk.ResponseType.ACCEPT)
        if dialog.run() == Gtk.ResponseType.ACCEPT:
            folder = dialog.get_filename()
            dialog.destroy()
            if folder:
                self.targets.prepend_text(folder)
                self.targets.set_active(0)
                self.load()
            return
        dialog.destroy()
