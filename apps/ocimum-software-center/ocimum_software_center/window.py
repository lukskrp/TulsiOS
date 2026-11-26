"""Main window: Search, AI Agents, Installed, Extensions, History and Updates
pages plus the change flow.

Change flow (same for every page): Plan -> confirmation dialog -> Apply ->
progress panel follows Progress signals -> on Finished refresh everything and
offer Undo.
"""

from __future__ import annotations

import threading

from gi.repository import Gio, GLib, Gtk

from . import dialogs
from .client import Client, TulsiError
from .links import LinkError, firefox_extension_id, parse_extension_link
from .model import (
    BROWSER_TITLES,
    MAX_RESULTS,
    JobTracker,
    Package,
    describe_change,
    done_text,
    extensions_of,
    history_title,
    normalize_query,
    ops_add_extension,
    ops_enable_service,
    ops_install,
    ops_keep_source,
    ops_remove,
    ops_remove_extension,
    upgrade_status,
)
from .progress import ProgressPanel
from .rows import ExtensionRow, HistoryRow, PackageRow, placeholder

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
        self.extensions: list[tuple[str, str]] = []
        self._search_serial = 0
        self._last_change_was_undo = False

        client.connect("progress", self._on_progress)
        client.connect("finished", self._on_finished)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        # Featured first: what to start with (ADR 0034).
        self.featured_lists: list[Gtk.ListBox] = []
        self.stack.add_titled(self._build_featured_page(), "featured", "Featured")
        self.stack.add_titled(self._build_search_page(), "search", "Search")
        self.stack.add_titled(self._build_ai_page(), "ai", "AI Agents")
        self.stack.add_titled(self._build_installed_page(), "installed", "Installed")
        self.stack.add_titled(self._build_extensions_page(), "extensions", "Extensions")
        self.stack.add_titled(self._build_history_page(), "history", "History")
        self.stack.add_titled(self._build_updates_page(), "updates", "Updates")
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
        clamp = Gtk.Box(halign=Gtk.Align.CENTER, spacing=8)
        self.search_entry.set_size_request(520, -1)
        clamp.pack_start(self.search_entry, False, False, 0)
        # Downloads and links: the step-by-step "Install the TulsiOS Way" window (ADR 0018).
        from_file = Gtk.Button.new_with_mnemonic("Install from a _File or Link…")
        from_file.connect("clicked", lambda _b: self.install_from_file_or_link())
        clamp.pack_start(from_file, False, False, 0)
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

    def _build_featured_page(self) -> Gtk.Widget:
        """Good software to start with, by what people want to do (featured.json)."""
        from . import featured

        sections = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=12)
        for section in featured.load():
            heading = Gtk.Label(xalign=0, margin_top=6)
            heading.set_markup(f"<b>{GLib.markup_escape_text(section.title)}</b>")
            sections.pack_start(heading, False, False, 0)
            if section.intro:
                note = Gtk.Label(label=section.intro, xalign=0, wrap=True)
                note.get_style_context().add_class("dim-label")
                sections.pack_start(note, False, False, 0)
            listbox = _listbox()
            for app in section.apps:
                package = Package(attr=app.attr, pname=app.name, description=app.blurb)
                package.installed = app.attr in self.installed
                listbox.add(self._package_row(package))
            frame = Gtk.Frame()
            frame.add(listbox)
            sections.pack_start(frame, False, False, 0)
            self.featured_lists.append(listbox)
        sections.pack_start(self._build_webapps_section(), False, False, 0)
        return _scrolled(sections)

    def _build_webapps_section(self) -> Gtk.Widget:
        """Suggested web apps (webapps.json, ADR 0036): a site in its own window,
        added to the menu only on click. Web App Manager adds any other site."""
        from . import webapps

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        heading = Gtk.Label(xalign=0, margin_top=6)
        heading.set_markup("<b>Web apps</b>")
        box.pack_start(heading, False, False, 0)
        note = Gtk.Label(
            label="Websites as apps in the menu, each in its own window with its own "
            "logins. Web App Manager (in the menu) adds any other site.",
            xalign=0, wrap=True)
        note.get_style_context().add_class("dim-label")
        box.pack_start(note, False, False, 0)
        listbox = _listbox()
        for suggestion in webapps.suggestions():
            listbox.add(self._webapp_row(suggestion))
        frame = Gtk.Frame()
        frame.add(listbox)
        box.pack_start(frame, False, False, 0)
        return box

    def _webapp_row(self, suggestion) -> Gtk.ListBoxRow:
        from . import webapps

        row = Gtk.ListBoxRow(activatable=False)
        hbox = Gtk.Box(spacing=12, margin=8)
        icon = Gtk.Image.new_from_icon_name("webapp-manager", Gtk.IconSize.DND)
        hbox.pack_start(icon, False, False, 0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(xalign=0)
        title.set_markup(f"<b>{GLib.markup_escape_text(suggestion.name)}</b>")
        text.pack_start(title, False, False, 0)
        blurb = Gtk.Label(label=suggestion.blurb, xalign=0, wrap=True)
        blurb.get_style_context().add_class("dim-label")
        text.pack_start(blurb, False, False, 0)
        hbox.pack_start(text, True, True, 0)
        button = Gtk.Button(valign=Gtk.Align.CENTER)

        def refresh() -> None:
            added = webapps.find(suggestion.url) is not None
            button.set_label("Remove" if added else "Add to Menu")
            button.set_sensitive(True)

        def done(error: str | None) -> bool:
            refresh()
            if error:
                dialogs.show_error(self, f"Could not change the {suggestion.name} web app", error)
            return GLib.SOURCE_REMOVE

        def clicked(_button) -> None:
            button.set_sensitive(False)
            existing = webapps.find(suggestion.url)

            def work() -> None:
                try:
                    if existing:
                        webapps.remove(existing)
                    else:
                        webapps.add(suggestion.name, suggestion.url, suggestion.category)
                    GLib.idle_add(done, None)
                except Exception as e:  # shown to the person
                    GLib.idle_add(done, str(e))

            threading.Thread(target=work, daemon=True).start()

        button.connect("clicked", clicked)
        refresh()
        hbox.pack_start(button, False, False, 0)
        row.add(hbox)
        return row

    def _build_ai_page(self) -> Gtk.Widget:
        """Agent CLIs and local model runners, picked out of the package index
        (ai-agents.json, ADR 0023), with the hardware check one click away."""
        from . import ai_agents, ai_check

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=12)
        top = Gtk.Box(spacing=12)
        icon = Gtk.Image.new_from_icon_name("org.tulsi.AIAgents", Gtk.IconSize.DIALOG)
        icon.set_pixel_size(48)
        top.pack_start(icon, False, False, 0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        intro = Gtk.Label(
            label="Cloud agents run on their company's servers: you need an account, not a "
            "fast computer. Local models run here, privately, if your hardware allows.",
            xalign=0,
            wrap=True,
        )
        text.pack_start(intro, False, False, 0)
        self.ai_verdict = Gtk.Label(xalign=0, wrap=True)
        self.ai_verdict.get_style_context().add_class("dim-label")
        text.pack_start(self.ai_verdict, False, False, 0)
        top.pack_start(text, True, True, 0)
        check = Gtk.Button.new_with_mnemonic("_Check What My Computer Can Run…")
        check.set_valign(Gtk.Align.CENTER)
        check.connect("clicked", lambda _b: self.run_ai_check())
        top.pack_end(check, False, False, 0)
        page.pack_start(top, False, False, 0)

        sections = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.ai_lists: list[Gtk.ListBox] = []
        runner = ai_check.last_runner()
        for section in ai_agents.load():
            heading = Gtk.Label(xalign=0, margin_top=6)
            heading.set_markup(f"<b>{GLib.markup_escape_text(section.title)}</b>")
            sections.pack_start(heading, False, False, 0)
            note = Gtk.Label(label=section.intro, xalign=0, wrap=True)
            note.get_style_context().add_class("dim-label")
            sections.pack_start(note, False, False, 0)
            listbox = _listbox()
            for agent in section.agents:
                # The hardware check's pick (ollama-cuda, …) in place of the plain runner.
                attr = runner if runner in agent.variants.values() else agent.attr
                package = Package(
                    attr=attr,
                    pname=agent.name,
                    description=f"{agent.vendor} · {agent.blurb} Needs: {agent.needs}.",
                )
                package.installed = attr in self.installed
                listbox.add(self._package_row(package))
            frame = Gtk.Frame()
            frame.add(listbox)
            sections.pack_start(frame, False, False, 0)
            self.ai_lists.append(listbox)
        page.pack_start(_scrolled(sections), True, True, 0)

        # The check (in a terminal) writes its result; show it when it does.
        self._ai_monitor = Gio.File.new_for_path(str(ai_check.cache_file())).monitor_file(
            Gio.FileMonitorFlags.NONE, None)
        self._ai_monitor.connect("changed", lambda *_a: self._show_ai_verdict())
        self._show_ai_verdict()
        return page

    def _show_ai_verdict(self) -> None:
        from . import ai_check

        verdict = ai_check.last_verdict()
        self.ai_verdict.set_text(
            f"Last hardware check: {verdict}" if verdict
            else "Not sure what your computer can run? Check it first.")

    def run_ai_check(self) -> None:
        """tulsi-ai-check in the desktop's terminal, kept open to read."""
        import shutil
        import subprocess

        terminal = shutil.which("tulsi-terminal")
        if not terminal:
            self.show_message("tulsi-terminal is not installed.", error=True)
            return
        subprocess.Popen([terminal, "--hold", "--", "tulsi-ai-check"], start_new_session=True,
                         stdin=subprocess.DEVNULL)

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

    def _build_extensions_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        intro = Gtk.Label(
            label="Extensions you install from the Firefox Add-ons site or the Chrome Web Store "
            "are made declarative automatically and listed here. Removing one uninstalls it "
            "from the browser.",
            xalign=0,
            wrap=True,
        )
        intro.get_style_context().add_class("dim-label")
        page.pack_start(intro, False, False, 0)
        # Or add one by its store page's link.
        link_row = Gtk.Box(spacing=6)
        self.extension_link = Gtk.Entry(
            placeholder_text="Link to an extension on addons.mozilla.org or the Chrome Web Store"
        )
        self.extension_link.set_hexpand(True)
        add_button = Gtk.Button.new_with_mnemonic("_Add by Link")

        def add_link(_widget) -> None:
            url = self.extension_link.get_text().strip()
            if url:
                self.add_extension_link(url)
                self.extension_link.set_text("")

        add_button.connect("clicked", add_link)
        self.extension_link.connect("activate", add_link)
        link_row.pack_start(self.extension_link, True, True, 0)
        link_row.pack_start(add_button, False, False, 0)
        page.pack_start(link_row, False, False, 0)
        self.extensions_stack = Gtk.Stack()
        self.extensions_stack.add_named(
            placeholder(
                "application-x-addon",
                "No declarative extensions yet",
                "Install an extension in your browser as usual; it appears here moments later.",
            ),
            "empty",
        )
        self.extensions_list = _listbox()
        frame = Gtk.Frame()
        frame.add(_scrolled(self.extensions_list))
        self.extensions_stack.add_named(frame, "list")
        page.pack_start(self.extensions_stack, True, True, 0)
        return page

    def refresh_extensions(self) -> None:
        _clear(self.extensions_list)
        if not self.extensions:
            self.extensions_stack.set_visible_child_name("empty")
            return
        self.extensions_stack.set_visible_child_name("list")
        for browser, ext_id in self.extensions:
            row = ExtensionRow(browser, ext_id, BROWSER_TITLES.get(browser, browser))
            row.set_busy(self.jobs.busy)
            row.connect("remove-requested", self._on_extension_remove)
            self.extensions_list.add(row)

    def _on_extension_remove(self, _row, browser: str, ext_id: str) -> None:
        self.request_change(
            ops_remove_extension(browser, ext_id), f"Removing {ext_id}", "Remove"
        )

    def _build_history_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        top = Gtk.Box(spacing=8)
        intro = Gtk.Label(
            label="Every change is recorded, by you or by an agent. Undo any of them; "
            "later changes stay.",
            xalign=0,
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

    def _build_updates_page(self) -> Gtk.Widget:
        page = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin=24,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
        )
        icon = Gtk.Image.new_from_icon_name("system-software-update", Gtk.IconSize.DIALOG)
        icon.set_pixel_size(64)
        page.pack_start(icon, False, False, 0)
        self.updates_title = Gtk.Label(label="TulsiOS")
        self.updates_title.get_style_context().add_class("title-2")
        self.updates_title.set_markup("<big><b>TulsiOS</b></big>")
        page.pack_start(self.updates_title, False, False, 0)
        self.updates_detail = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER, max_width_chars=60)
        self.updates_detail.get_style_context().add_class("dim-label")
        page.pack_start(self.updates_detail, False, False, 0)
        self.updates_spinner = Gtk.Spinner()
        page.pack_start(self.updates_spinner, False, False, 0)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        self.updates_check = Gtk.Button(label="Check Again")
        self.updates_check.connect("clicked", lambda _b: self.refresh_updates())
        self.updates_upgrade = Gtk.Button(label="Upgrade")
        self.updates_upgrade.get_style_context().add_class("suggested-action")
        self.updates_upgrade.connect("clicked", lambda _b: self.request_upgrade())
        buttons.pack_start(self.updates_check, False, False, 0)
        buttons.pack_start(self.updates_upgrade, False, False, 0)
        page.pack_start(buttons, False, False, 0)
        self._upgrade_info: dict = {}
        return page

    def refresh_updates(self) -> None:
        self.updates_title.set_markup("<big><b>Checking for a newer TulsiOS…</b></big>")
        self.updates_detail.set_text("")
        self.updates_upgrade.set_visible(False)
        self.updates_check.set_sensitive(False)
        self.updates_spinner.start()

        def show(info: dict) -> None:
            self._upgrade_info = info
            title, detail, can_upgrade = upgrade_status(info)
            self.updates_title.set_markup(f"<big><b>{GLib.markup_escape_text(title)}</b></big>")
            self.updates_detail.set_text(detail)
            self.updates_upgrade.set_visible(can_upgrade)
            self.updates_upgrade.set_sensitive(can_upgrade and not self.jobs.busy)
            self.updates_check.set_sensitive(True)
            self.updates_spinner.stop()

        def failed(error: TulsiError) -> None:
            show({"following": "?", "error": error.message})

        self.client.check_upgrade(show, failed)

    def show_updates(self) -> None:
        """The Updates page, checked afresh (the upgrade notification opens it)."""
        if self.stack.get_visible_child_name() == "updates":
            self.refresh_updates()
        else:
            self.stack.set_visible_child_name("updates")
        self.present()

    def request_upgrade(self) -> None:
        if self.jobs.busy:
            self.show_message("Another change is still being applied.", error=True)
            return
        info = self._upgrade_info
        new = info.get("availableVersion") or "the newest release"
        lines = [
            f"From TulsiOS {info.get('currentVersion') or 'unknown'} to {new}",
            "Your apps, files and settings stay as they are",
            "Undo it any time in History; restart afterwards to finish",
        ]
        if dialogs.confirm(self, f"Upgrade to TulsiOS {new}?", lines, "Upgrade"):
            self._start(self.client.upgrade, f"Upgrading TulsiOS to {new}")

    def _on_page_changed(self, stack: Gtk.Stack, _pspec) -> None:
        name = stack.get_visible_child_name()
        if name == "updates":
            self.refresh_updates()
        elif name == "installed":
            self.refresh_installed()
        elif name == "extensions":
            self.refresh_extensions()
        elif name == "history":
            self.refresh_history()
        elif name == "search":
            self.search_entry.grab_focus()
        elif name == "ai":
            self._show_ai_verdict()

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
            self.install(attr)
        else:
            self.request_change(ops_remove(attr), f"Removing {attr}", "Remove")

    def _on_keep_requested(self, _row, attr: str, keep: bool) -> None:
        verb = "Keeping" if keep else "Releasing"
        self.request_change(ops_keep_source(attr, keep), f"{verb} the download of {attr}", "Apply")

    # ------------------------------------------------------- state & lists

    def refresh_state(self) -> None:
        def done(state: dict) -> None:
            self.installed = set(state.get("packages", []))
            self.kept = set(state.get("keepSources", []))
            self.extensions = extensions_of(state)
            self._sync_rows()
            page = self.stack.get_visible_child_name()
            if page == "installed":
                self.refresh_installed()
            elif page == "extensions":
                self.refresh_extensions()

        self.client.get_state(done, lambda e: self.show_message(e.message, error=True))

    def _sync_rows(self) -> None:
        for row in [r for box in (self.search_list, *self.ai_lists, *self.featured_lists)
                    for r in box.get_children()]:
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
            if (info or {}).get("local"):
                row = PackageRow(package, kept=attr in getattr(self, "kept", set()))
                row.set_busy(self.jobs.busy)
                row.connect("requested", self._on_row_requested)
                row.connect("keep-requested", self._on_keep_requested)
                self.installed_list.add(row)
            else:
                self.installed_list.add(self._package_row(package))

        # Details are optional: fall back to the bare name if lookup fails.
        self.client.package_info(attr, add, lambda _e: add(None))

    def refresh_history(self) -> None:
        def done(entries: list[dict]) -> None:
            _clear(self.history_list)
            # A short history ends where it starts, which cannot be undone.
            complete = len(entries) < HISTORY_LIMIT
            for i, entry in enumerate(entries):
                start = complete and i == len(entries) - 1
                row = HistoryRow(entry, None if start else self.request_undo_change)
                row.set_busy(self.jobs.busy)
                self.history_list.add(row)
            self.history_undo.set_sensitive(len(entries) > 1 and not self.jobs.busy)

        self.client.history(HISTORY_LIMIT, done, lambda e: self.show_message(e.message, error=True))

    # ---------------------------------------------------------- change flow

    def install(self, attr: str) -> None:
        """Installs `attr`; for an allow-listed unfree agent, asks to accept its licence first."""

        def with_info(info: dict | None) -> None:
            package = Package.from_json(info) if info else Package(attr=attr)
            accept = False
            if package.needs_license:
                if not dialogs.accept_license(
                    self, package.title, package.license_name, package.license_url
                ):
                    return
                accept = True
            self.request_change(
                ops_install(attr, accept_license=accept), f"Installing {attr}", "Install"
            )

        self.client.package_info(attr, with_info, lambda _e: with_info(None))

    def install_from_file_or_link(self) -> None:
        """Chooses a downloaded file, or takes a link, and opens tulsi-adopt with it."""
        choice = dialogs.file_or_link(self)
        if choice is None:
            return
        kind, value = choice
        self.open_adopt(kind, value)

    def open_adopt(self, kind: str, value: str) -> None:
        """tulsi-adopt --file PATH or --url LINK, in its own process."""
        import shutil
        import subprocess

        tulsi_adopt = shutil.which("tulsi-adopt")
        if not tulsi_adopt:
            self.show_message("tulsi-adopt is not installed.", error=True)
            return
        flag = "--file" if kind == "file" else "--url"
        subprocess.Popen([tulsi_adopt, flag, value], start_new_session=True,
                         stdin=subprocess.DEVNULL)

    def enable_service(self, name: str) -> None:
        """Turns on the NixOS service `name` (services.<name>.enable)."""
        self.request_change(ops_enable_service(name), f"Enabling {name}", "Turn On")

    def add_extension_link(self, url: str) -> None:
        """Adds the extension a store link points at (looked up for Firefox)."""
        try:
            browser, ref, lookup = parse_extension_link(url)
        except LinkError as e:
            self.show_message(str(e), error=True)
            return

        def add(ext_id: str) -> bool:
            self.request_change(
                ops_add_extension(browser, ext_id), f"Adding {ext_id}", "Add"
            )
            return GLib.SOURCE_REMOVE

        def failed(message: str) -> bool:
            self.show_message(message, error=True)
            return GLib.SOURCE_REMOVE

        if not lookup:
            add(ref)
            return

        def resolve() -> None:
            try:
                ext_id = firefox_extension_id(ref)
            except LinkError as e:
                GLib.idle_add(failed, str(e))
                return
            GLib.idle_add(add, ext_id)

        threading.Thread(target=resolve, daemon=True).start()

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
            else:
                # Controls that started the change (a checkbox) show the state again.
                self.refresh_state()

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

    def request_undo_change(self, entry: dict) -> None:
        """Undo one earlier change from the History page; later changes stay."""
        if self.jobs.busy:
            self.show_message("Another change is still being applied.", error=True)
            return
        commit = entry["commit"]
        title = history_title(entry["summary"])

        def planned(plan: dict) -> None:
            changes = [describe_change(c) for c in plan.get("changes", [])] or [title]
            if dialogs.confirm(self, f"Undo “{title}”?", changes, "Undo"):
                self._start(
                    lambda ok, err: self.client.undo_change(commit, ok, err),
                    f"Undoing “{title}”",
                    is_undo=True,
                )

        # tulsid works out what it means today, or explains why it cannot.
        self.client.plan_undo(commit, planned, self._on_request_error)

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
        for listbox in (self.search_list, self.installed_list, self.extensions_list,
                        *self.ai_lists, *self.featured_lists):
            for row in listbox.get_children():
                if isinstance(row, (PackageRow, ExtensionRow)):
                    row.set_busy(busy)
        for row in self.history_list.get_children():
            if isinstance(row, HistoryRow):
                row.set_busy(busy)
        self.history_undo.set_sensitive(not busy)
        self.updates_upgrade.set_sensitive(not busy and bool(self._upgrade_info.get("available")))

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

