"""File History's window: a file or folder, its earlier versions, and Restore."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

from gi.repository import GLib, Gtk

from . import history


def _label(text: str = "", dim: bool = False, wrap: bool = False) -> Gtk.Label:
    label = Gtk.Label(label=text, xalign=0, wrap=wrap)
    if dim:
        label.get_style_context().add_class("dim-label")
    return label


class Window(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, path: Path | None):
        super().__init__(application=app, title="File History", default_width=760, default_height=520)
        header = Gtk.HeaderBar(show_close_button=True, title="File History")
        self.set_titlebar(header)
        free = Gtk.Button.new_with_mnemonic("_Free Space Now…")
        free.connect("clicked", lambda _b: self.free_space())
        header.pack_end(free)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=14)
        self.add(box)
        why = history.available()
        if why:
            free.set_sensitive(False)
            box.pack_start(_label(why, wrap=True), False, False, 0)
            return

        top = Gtk.Box(spacing=8)
        top.pack_start(_label("Show the history of"), False, False, 0)
        self.file_button = Gtk.FileChooserButton(title="Choose a file", action=Gtk.FileChooserAction.OPEN)
        self.file_button.connect("file-set", lambda b: self.show(Path(b.get_filename())))
        top.pack_start(self.file_button, True, True, 0)
        folder = Gtk.Button(label="A Folder…")
        folder.connect("clicked", lambda _b: self.choose_folder())
        top.pack_start(folder, False, False, 0)
        box.pack_start(top, False, False, 0)

        self.title = _label(wrap=True)
        box.pack_start(self.title, False, False, 0)
        self.store = Gtk.ListStore(int, str, str, object)  # number, date, size, Version
        self.view = Gtk.TreeView(model=self.store)
        for i, name in ((1, "Saved"), (2, "Size")):
            col = Gtk.TreeViewColumn(name, Gtk.CellRendererText(), text=i)
            col.set_expand(i == 1)
            self.view.append_column(col)
        self.view.get_selection().connect("changed", lambda _s: self._update_buttons())
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.add(self.view)
        box.pack_start(scroller, True, True, 0)

        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        self.open_button = Gtk.Button.new_with_mnemonic("_Open")
        self.open_button.connect("clicked", lambda _b: self.open_selected())
        self.copy_button = Gtk.Button.new_with_mnemonic("Restore as _Copy")
        self.copy_button.connect("clicked", lambda _b: self.restore_selected(True))
        self.restore_button = Gtk.Button.new_with_mnemonic("_Restore")
        self.restore_button.get_style_context().add_class("suggested-action")
        self.restore_button.connect("clicked", lambda _b: self.restore_selected(False))
        for b in (self.open_button, self.copy_button, self.restore_button):
            buttons.pack_start(b, False, False, 0)
        box.pack_start(buttons, False, False, 0)
        box.pack_start(_label("Restoring puts what is there now in the trash first. The history "
                              "is on the same disk as your files: it is not a backup.", dim=True, wrap=True),
                       False, False, 0)
        self.path: Path | None = None
        self._update_buttons()
        if path is not None:
            self.show(path)

    # ------------------------------------------------------------------ list

    def choose_folder(self) -> None:
        dialog = Gtk.FileChooserNative.new("Choose a folder", self, Gtk.FileChooserAction.SELECT_FOLDER, None, None)
        if dialog.run() == Gtk.ResponseType.ACCEPT:
            self.show(Path(dialog.get_filename()))

    def show(self, path: Path) -> None:
        self.path = path
        self.store.clear()
        try:
            found = history.versions(path)
        except ValueError as e:
            self.title.set_text(str(e))
            self._update_buttons()
            return
        name = GLib.markup_escape_text(str(path))
        if not found:
            self.title.set_markup(f"<b>{name}</b>\nNo earlier versions.")
        else:
            self.title.set_markup(f"<b>{name}</b>\n{len(found)} earlier versions, newest first.")
        for v in found:
            size = "folder" if v.is_dir else history.human(v.size)
            self.store.append([v.snapshot.number, v.snapshot.label, size, v])
        self._update_buttons()

    def _selected(self):
        model, it = self.view.get_selection().get_selected()
        return model[it][3] if it else None

    def _update_buttons(self) -> None:
        on = self._selected() is not None
        for b in (self.open_button, self.copy_button, self.restore_button):
            b.set_sensitive(on)

    # --------------------------------------------------------------- actions

    def open_selected(self) -> None:
        v = self._selected()
        if v:
            subprocess.Popen(["xdg-open", str(v.path)], start_new_session=True)

    def restore_selected(self, as_copy: bool) -> None:
        v = self._selected()
        if not v or self.path is None:
            return
        try:
            where = history.restore(self.path, v, as_copy=as_copy)
        except (OSError, RuntimeError, subprocess.CalledProcessError) as e:
            self._message(Gtk.MessageType.ERROR, "Could not restore", str(e))
            return
        self._message(Gtk.MessageType.INFO, "Restored", f"{where}\nfrom {v.snapshot.label}.")
        self.show(self.path)

    def free_space(self) -> None:
        snaps = history.snapshots()
        dialog = Gtk.Dialog(title="Free Space Now", transient_for=self, modal=True)
        dialog.add_buttons("_Cancel", Gtk.ResponseType.CANCEL, "_Delete", Gtk.ResponseType.OK)
        dialog.get_widget_for_response(Gtk.ResponseType.OK).get_style_context().add_class("destructive-action")
        area = dialog.get_content_area()
        area.set_spacing(8)
        area.set_border_width(12)
        oldest = snaps[-1].label if snaps else "–"
        area.add(_label(f"Your files' history has {len(snaps)} snapshots, the oldest from {oldest}. "
                        "Deleting old ones frees the space of what changed since; your files "
                        "stay as they are now.", wrap=True))
        row = Gtk.Box(spacing=8)
        row.pack_start(_label("Keep only the newest"), False, False, 0)
        keep = Gtk.SpinButton.new_with_range(0, max(len(snaps), 1), 1)
        keep.set_value(min(3, len(snaps)))
        row.pack_start(keep, False, False, 0)
        row.pack_start(_label("snapshots"), False, False, 0)
        area.add(row)
        dialog.show_all()
        answer = dialog.run()
        n = int(keep.get_value())
        dialog.destroy()
        if answer != Gtk.ResponseType.OK:
            return

        def work() -> None:
            try:
                numbers, freed = history.free_space(n)
                text = (f"Deleted {len(numbers)} snapshots, freeing about {history.human(freed)}."
                        if numbers else "There was nothing to delete.")
                GLib.idle_add(self._message, Gtk.MessageType.INFO, "Space freed", text)
            except Exception as e:  # snapper refused, …
                GLib.idle_add(self._message, Gtk.MessageType.ERROR, "Could not delete snapshots", str(e))
            if self.path is not None:
                GLib.idle_add(self.show, self.path)

        threading.Thread(target=work, daemon=True).start()

    def _message(self, kind, title: str, text: str) -> bool:
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=kind,
                                   buttons=Gtk.ButtonsType.CLOSE, text=title)
        dialog.format_secondary_text(text)
        dialog.run()
        dialog.destroy()
        return GLib.SOURCE_REMOVE
