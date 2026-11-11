"""Main window: Search, Installed and History pages plus the change flow.

Change flow (same for every page): Plan -> confirmation dialog -> Apply ->
progress panel follows Progress signals -> on Finished refresh everything and
offer Undo.
"""

from __future__ import annotations

from gi.repository import GLib, Gtk

from . import dialogs
from .client import Client, TulsiError
from .model import (
    MAX_RESULTS,
    JobTracker,
    Package,
    describe_change,
    done_text,
    history_title,
    normalize_query,
    ops_install,
    ops_remove,
)
from .progress import ProgressPanel
from .rows import HistoryRow, PackageRow, placeholder

WINDOW_TITLE = "Software Center"
HISTORY_LIMIT = 50


def _clear(listbox: Gtk.ListBox) -> None:
    for child in listbox.get_children():
        listbox.remove(child)


def _scrolled(child: Gtk.Widget) -> Gtk.ScrolledWindow:
    scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
    scroller.add(child)
    return scroller


def _listbox() -> Gtk.ListBox:
    listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    listbox.set_header_func(_separator_header)
    return listbox


def _separator_header(row: Gtk.ListBoxRow, before: Gtk.ListBoxRow | None) -> None:
    if before is not None and row.get_header() is None:
        row.set_header(Gtk.Separator())


class Window(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, client: Client):
        super().__init__(application=app, title=WINDOW_TITLE, default_width=920, default_height=680)
        self.client = client
        self.jobs = JobTracker()
        self.installed: set[str] = set()
        self._search_serial = 0
        self._last_change_was_undo = False

        client.connect("progress", self._on_progress)
        client.connect("finished", self._on_finished)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_titled(self._build_search_page(), "search", "Search")
        self.stack.add_titled(self._build_installed_page(), "installed", "Installed")
        self.stack.add_titled(self._build_history_page(), "history", "History")
        self.stack.connect("notify::visible-child-name", self._on_page_changed)

        header = Gtk.HeaderBar(show_close_button=True)
        header.set_custom_title(Gtk.StackSwitcher(stack=self.stack))
        self.set_titlebar(header)

        self.infobar = Gtk.InfoBar(show_close_button=True, revealed=False)
        self.infobar.connect("response", self._on_infobar_response)
        self.info_label = Gtk.Label(xalign=0, wrap=True)
        self.infobar.get_content_area().add(self.info_label)
        self.undo_button = self.infobar.add_button("Undo", 1)

        self.progress = ProgressPanel()

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main.pack_start(self.infobar, False, False, 0)
        main.pack_start(self.stack, True, True, 0)
        main.pack_end(self.progress, False, False, 0)
        self.add(main)
        self.show_all()
        self.infobar.set_revealed(False)
        self.undo_button.hide()

        self.refresh_state()
        self.search_entry.grab_focus()

    # ---------------------------------------------------------------- pages

    def _build_search_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        self.search_entry = Gtk.SearchEntry(placeholder_text="Search for software to install")
        self.search_entry.connect("search-changed", self._on_search_changed)
        clamp = Gtk.Box(halign=Gtk.Align.CENTER)
        self.search_entry.set_size_request(520, -1)
        clamp.pack_start(self.search_entry, False, False, 0)
        page.pack_start(clamp, False, False, 0)

        self.search_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.search_hint = placeholder(
            "system-software-install",
            "Find software",
            "Type a name or what it does, e.g. “video player” or “gimp”.",
        )
        self.search_stack.add_named(self.search_hint, "hint")
        spinner = Gtk.Spinner(active=True, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        spinner.set_size_request(32, 32)
        self.search_stack.add_named(spinner, "loading")
        self.search_empty = placeholder("edit-find", "No results")
        self.search_stack.add_named(self.search_empty, "empty")
        self.search_list = _listbox()
        self.search_stack.add_named(_scrolled(self.search_list), "results")
        page.pack_start(self.search_stack, True, True, 0)
        return page

    def _build_installed_page(self) -> Gtk.Widget:
        self.installed_stack = Gtk.Stack()
        self.installed_stack.add_named(
            placeholder(
                "package-x-generic",
                "Nothing installed yet",
                "Software you install here is listed on this page.",
            ),
            "empty",
        )
        self.installed_list = _listbox()
        self.installed_stack.add_named(_scrolled(self.installed_list), "list")
        return self.installed_stack

    def _build_history_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        top = Gtk.Box(spacing=8)
        intro = Gtk.Label(
            label="Every change is recorded. Undo reverts the most recent one.", xalign=0
        )
        intro.get_style_context().add_class("dim-label")
        top.pack_start(intro, True, True, 0)
        self.history_undo = Gtk.Button(label="Undo Latest Change")
        self.history_undo.connect("clicked", lambda _b: self.request_undo())
        top.pack_end(self.history_undo, False, False, 0)
        page.pack_start(top, False, False, 0)
        self.history_list = _listbox()
        frame = Gtk.Frame()
        frame.add(_scrolled(self.history_list))
        page.pack_start(frame, True, True, 0)
        return page

    def _on_page_changed(self, stack: Gtk.Stack, _pspec) -> None:
        name = stack.get_visible_child_name()
        if name == "installed":
            self.refresh_installed()
        elif name == "history":
            self.refresh_history()
        elif name == "search":
            self.search_entry.grab_focus()

    # --------------------------------------------------------------- search

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self._search_serial += 1
        serial = self._search_serial
        query = normalize_query(entry.get_text())
        if query is None:
            self.search_stack.set_visible_child_name("hint")
            return
        self.search_stack.set_visible_child_name("loading")

        def done(results: list[dict]) -> None:
            if serial != self._search_serial:
                return  # a newer search is underway
            self._show_results([Package.from_json(r) for r in results], query)

        def failed(error: TulsiError) -> None:
            if serial != self._search_serial:
                return
            self.search_empty.body.set_text(error.message)
            self.search_stack.set_visible_child_name("empty")

        self.client.search(query, MAX_RESULTS, done, failed)

    def _show_results(self, packages: list[Package], query: str) -> None:
        _clear(self.search_list)
        if not packages:
            self.search_empty.body.set_text(f"Nothing matches “{query}”.")
            self.search_stack.set_visible_child_name("empty")
            return
        for package in packages:
            self.search_list.add(self._package_row(package))
        self.search_stack.set_visible_child_name("results")

    def _package_row(self, package: Package) -> PackageRow:
        row = PackageRow(package)
        row.set_busy(self.jobs.busy)
        row.connect("requested", self._on_row_requested)
        return row

    def _on_row_requested(self, _row: PackageRow, attr: str, install: bool) -> None:
        if install:
            self.request_change(ops_install(attr), f"Installing {attr}", "Install")
        else:
            self.request_change(ops_remove(attr), f"Removing {attr}", "Remove")

    # ------------------------------------------------------- state & lists

    def refresh_state(self) -> None:
        def done(state: dict) -> None:
            self.installed = set(state.get("packages", []))
            self._sync_rows()
            if self.stack.get_visible_child_name() == "installed":
                self.refresh_installed()

        self.client.get_state(done, lambda e: self.show_message(e.message, error=True))

    def _sync_rows(self) -> None:
        for row in self.search_list.get_children():
            if isinstance(row, PackageRow):
                row.set_installed(row.package.attr in self.installed)
                row.set_busy(self.jobs.busy)

    def refresh_installed(self) -> None:
        _clear(self.installed_list)
        if not self.installed:
            self.installed_stack.set_visible_child_name("empty")
            return
        self.installed_stack.set_visible_child_name("list")
        for attr in sorted(self.installed):
            self._add_installed_row(attr)

    def _add_installed_row(self, attr: str) -> None:
        def add(info: dict | None) -> None:
            package = Package.from_json(info) if info else Package(attr=attr)
            package.installed = True
            self.installed_list.add(self._package_row(package))

        # Details are optional: fall back to the bare name if lookup fails.
        self.client.package_info(attr, add, lambda _e: add(None))

    def refresh_history(self) -> None:
        def done(entries: list[dict]) -> None:
            _clear(self.history_list)
            for entry in entries:
                self.history_list.add(HistoryRow(entry))
            self.history_undo.set_sensitive(len(entries) > 1 and not self.jobs.busy)

        self.client.history(HISTORY_LIMIT, done, lambda e: self.show_message(e.message, error=True))

    # ---------------------------------------------------------- change flow

    def request_change(self, ops: list[dict], label: str, apply_label: str) -> None:
        if self.jobs.busy:
            self.show_message("Another change is still being applied.", error=True)
            return

        def planned(plan: dict) -> None:
            changes = [describe_change(c) for c in plan.get("changes", [])]
            if not changes:
                self.show_message("Nothing to change.")
                return
            heading = "Apply these changes?" if len(changes) > 1 else f"{changes[0]}?"
            if dialogs.confirm(self, heading, changes, apply_label):
                self._start(lambda ok, err: self.client.apply(ops, ok, err), label)

        self.client.plan(ops, planned, self._on_request_error)

    def request_undo(self) -> None:
        if self.jobs.busy:
            self.show_message("Another change is still being applied.", error=True)
            return

        def got_history(entries: list[dict]) -> None:
            if len(entries) < 2:
                self.show_message("There is nothing to undo.")
                return
            latest = history_title(entries[0]["summary"])
            if dialogs.confirm(self, "Undo the latest change?", [latest], "Undo"):
                self._start(self.client.undo, f"Undoing “{latest}”", is_undo=True)

        self.client.history(2, got_history, self._on_request_error)

    def _start(self, call, label: str, *, is_undo: bool = False) -> None:
        self._last_change_was_undo = is_undo
        self.jobs.begin(label)
        self._set_busy()
        self.progress.start(f"{label}…")

        def started(job: int) -> None:
            if job == 0:
                self.jobs.cancel()
                self._set_busy()
                self.progress.finish(True, "Nothing to change.")
                return
            lines, result = self.jobs.started(job)
            for line in lines:
                self.progress.append(line)
            if result is not None:
                self._job_done(*result)

        def failed(error: TulsiError) -> None:
            self.jobs.cancel()
            self._set_busy()
            self.progress.finish(False, error.message)
            self._on_request_error(error)

        call(started, failed)

    def _on_progress(self, _client, job: int, line: str) -> None:
        if self.jobs.progress(job, line):
            self.progress.append(line)

    def _on_finished(self, _client, job: int, success: bool, message: str) -> None:
        if self.jobs.finished(job, success, message):
            self._job_done(success, message)
        else:
            # Someone else (CLI, another window) changed the system.
            self.refresh_state()

    def _job_done(self, success: bool, message: str) -> None:
        self._set_busy()
        label = self.jobs.label
        if success:
            self.progress.finish(True, "Done.")
            self.show_message(done_text(label), undo=not self._last_change_was_undo)
        else:
            self.progress.finish(False, "The change failed; nothing was changed.")
            self.show_message("The change failed; your system was left as it was.", error=True)
            dialogs.show_error(self, "The change could not be applied", message)
        self.refresh_state()
        if self.stack.get_visible_child_name() == "history":
            self.refresh_history()

    def _set_busy(self) -> None:
        busy = self.jobs.busy
        for listbox in (self.search_list, self.installed_list):
            for row in listbox.get_children():
                if isinstance(row, PackageRow):
                    row.set_busy(busy)
        self.history_undo.set_sensitive(not busy)

    def _on_request_error(self, error: TulsiError) -> None:
        if error.kind == "NotAuthorized":
            self.show_message("You are not allowed to change the system.", error=True)
        else:
            dialogs.show_error(self, "The change could not be made", error.message)

    # --------------------------------------------------------------- infobar

    def show_message(self, text: str, *, error: bool = False, undo: bool = False) -> None:
        self.info_label.set_text(text)
        self.infobar.set_message_type(Gtk.MessageType.ERROR if error else Gtk.MessageType.INFO)
        self.undo_button.set_visible(undo)
        self.infobar.set_revealed(True)

    def _on_infobar_response(self, infobar: Gtk.InfoBar, response: int) -> None:
        infobar.set_revealed(False)
        if response == 1:
            # Leave the InfoBar's signal handler before opening a dialog.
            def undo() -> bool:
                self.request_undo()
                return GLib.SOURCE_REMOVE

            GLib.idle_add(undo)

