"""The Nix Editor's window (ADR 0019).

Files in tabs on the left, the guide on the right, problems and the build log below.
nixd suggests names and marks problems; TulsiOS's own rules for local packages
(`tulsi recipe check`) are checked when a package.nix is opened and saved. A Recipe's
draft gets Build and Try and Install.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GtkSource", "4")
from gi.repository import Gdk, Gio, GLib, Gtk, GtkSource, Pango  # noqa: E402

from . import draft, lsp
from .completion import NixCompletion
from .guide import Guide, word_at
from .guide_pane import GuidePane
from .text import DARK_SCHEME, LIGHT_SCHEME, is_dark_theme

MAX_LOG_LINES = 3000


def log(text: str) -> None:
    print(f"nix-editor: {text}", file=sys.stderr, flush=True)


def iter_at(buffer, line: int, char16: int):
    """A buffer iter for an LSP position (line, UTF-16 column)."""
    line = max(0, min(line, buffer.get_line_count() - 1))
    start = buffer.get_iter_at_line(line)
    end = start.copy()
    if not end.ends_line():
        end.forward_to_line_end()
    text = start.get_text(end)
    it = start.copy()
    it.forward_chars(lsp.utf16_to_chars(text, char16))
    return it


class Problem:
    def __init__(self, source: str, message: str, line: int | None, column: int = 0,
                 end: tuple[int, int] | None = None, error: bool = True):
        self.source, self.message, self.line, self.column = source, message, line, column
        self.end, self.error = end, error


class Tab:
    """One file: its view, where it is saved, and its problems."""

    counter = 0

    def __init__(self, window: "Window", path: str | None, text: str = ""):
        self.window = window
        self.path = path
        Tab.counter += 1
        self.untitled = os.path.join(tempfile.gettempdir(), f"nix-editor-{os.getpid()}",
                                     f"untitled-{Tab.counter}.nix")
        self.buffer = GtkSource.Buffer()
        lang = GtkSource.LanguageManager.get_default().get_language("nix")
        if lang:
            self.buffer.set_language(lang)
        scheme = window.style_scheme()
        if scheme:
            self.buffer.set_style_scheme(scheme)
        self.buffer.begin_not_undoable_action()
        self.buffer.set_text(text)
        self.buffer.end_not_undoable_action()
        self.buffer.set_modified(False)
        self.buffer.place_cursor(self.buffer.get_start_iter())
        self.buffer.create_tag("error", underline=Pango.Underline.ERROR)
        self.buffer.create_tag("warning", underline=Pango.Underline.ERROR,
                               underline_rgba=Gdk.RGBA(0.9, 0.6, 0.1, 1))
        self.view = GtkSource.View(buffer=self.buffer, monospace=True, show_line_numbers=True,
                                   highlight_current_line=True, auto_indent=True, indent_width=2,
                                   tab_width=2, insert_spaces_instead_of_tabs=True,
                                   smart_home_end=GtkSource.SmartHomeEndType.BEFORE)
        self.buffer.set_highlight_matching_brackets(True)
        self.view.get_completion().add_provider(NixCompletion(window))
        self.view.get_completion().set_property("show-headers", False)
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.add(self.view)
        self.lsp_problems: list[Problem] = []
        self.tulsi_problems: list[Problem] = []
        self.change_timer = 0
        self.title = Gtk.Label()
        self.update_title()
        self.buffer.connect("modified-changed", lambda _b: (self.update_title(), window.update_title()))
        self.buffer.connect("changed", lambda _b: self._changed())
        self.buffer.connect("notify::cursor-position", lambda *_a: window.cursor_moved(self))
        self.monitor = None
        self.watch()

    def watch(self) -> None:
        """Reload the file when another program changes it, unless it has unsaved edits."""
        if self.monitor:
            self.monitor.cancel()
            self.monitor = None
        if not self.path:
            return
        try:
            self.monitor = Gio.File.new_for_path(self.path).monitor_file(Gio.FileMonitorFlags.NONE, None)
        except GLib.Error:
            return
        self.monitor.connect("changed", self._on_disk_change)

    def _on_disk_change(self, _monitor, _file, _other, event) -> None:
        if event not in (Gio.FileMonitorEvent.CHANGES_DONE_HINT, Gio.FileMonitorEvent.CREATED):
            return
        if self.buffer.get_modified():
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError):
            return
        if text == self.text():
            return
        cursor = self.buffer.get_iter_at_mark(self.buffer.get_insert()).get_offset()
        self.buffer.begin_not_undoable_action()
        self.buffer.set_text(text)
        self.buffer.end_not_undoable_action()
        self.buffer.place_cursor(self.buffer.get_iter_at_offset(min(cursor, self.buffer.get_char_count())))
        self.buffer.set_modified(False)
        log(f"reloaded {self.path}")
        self.window.check_tulsi(self)

    @property
    def lsp_path(self) -> str:
        return self.path or self.untitled

    @property
    def name(self) -> str:
        return os.path.basename(self.path) if self.path else "Untitled"

    @property
    def draft_dir(self) -> str:
        return draft.draft_of(self.path) if self.path else ""

    def text(self) -> str:
        return self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), True)

    def update_title(self) -> None:
        self.title.set_text(("• " if self.buffer.get_modified() else "") + self.name)

    def _changed(self) -> None:
        if self.change_timer:
            GLib.source_remove(self.change_timer)
        self.change_timer = GLib.timeout_add(300, self.flush_change)

    def flush_change(self) -> bool:
        if self.change_timer:
            GLib.source_remove(self.change_timer)
            self.change_timer = 0
        if self.window.lsp_ready():
            self.window.lsp.did_change(self.lsp_path, self.text())
        return False

    def mark(self) -> None:
        b = self.buffer
        b.remove_tag_by_name("error", b.get_start_iter(), b.get_end_iter())
        b.remove_tag_by_name("warning", b.get_start_iter(), b.get_end_iter())
        for p in self.lsp_problems + self.tulsi_problems:
            if p.line is None:
                continue
            start = iter_at(b, p.line, p.column)
            if p.end:
                end = iter_at(b, *p.end)
            else:
                end = start.copy()
                end.forward_chars(1)
            if end.equal(start):
                end.forward_char()
                if end.equal(start):
                    start.backward_char()
            b.apply_tag_by_name("error" if p.error else "warning", start, end)


class Window(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Nix Editor")
        self.set_default_size(1200, 760)
        self.set_icon_name("org.tulsi.NixEditor")
        self.log = log  # for the completion provider
        self.guide = Guide.load()
        self.tabs: list[Tab] = []
        self.lsp: lsp.Client | None = None
        self.transport = None
        self.lsp_state = "starting"
        self.cursor_timer = 0
        self.last_word = ""
        self.build_proc = None
        self.outcome: dict = {}

        header = Gtk.HeaderBar(show_close_button=True, title="Nix Editor")
        self.set_titlebar(header)
        self.header = header
        open_button = Gtk.Button.new_with_mnemonic("_Open")
        open_button.set_tooltip_text("Open a Nix file (Ctrl+O)")
        open_button.connect("clicked", lambda _b: self.open_dialog())
        header.pack_start(open_button)
        new_button = Gtk.Button.new_from_icon_name("document-new-symbolic", Gtk.IconSize.BUTTON)
        new_button.set_tooltip_text("New file (Ctrl+N)")
        new_button.connect("clicked", lambda _b: self.new_tab())
        header.pack_start(new_button)

        guide_button = Gtk.ToggleButton()
        guide_button.add(Gtk.Image.new_from_icon_name("help-contents-symbolic", Gtk.IconSize.BUTTON))
        guide_button.set_tooltip_text("Show or hide the Nix guide (F1)")
        guide_button.set_active(True)
        guide_button.connect("toggled", lambda b: self.guide_pane.set_visible(b.get_active()))
        self.guide_button = guide_button
        header.pack_end(guide_button)
        save = Gtk.Button.new_with_mnemonic("_Save")
        save.set_tooltip_text("Save (Ctrl+S); Save As is Ctrl+Shift+S")
        save.connect("clicked", lambda _b: self.save())
        header.pack_end(save)
        self.install_button = Gtk.Button.new_with_mnemonic("_Install")
        self.install_button.get_style_context().add_class("suggested-action")
        self.install_button.set_tooltip_text("Install what was built, through the Software Center")
        self.install_button.connect("clicked", lambda _b: self.install())
        header.pack_end(self.install_button)
        self.build_button = Gtk.Button.new_with_mnemonic("Build and _Try")
        self.build_button.set_tooltip_text("Save, check, build this package and try it in a sandbox")
        self.build_button.connect("clicked", lambda _b: self.build())
        header.pack_end(self.build_button)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(outer)
        self.info = Gtk.InfoBar(show_close_button=True)
        self.info.connect("response", lambda bar, _r: bar.hide())
        self.info_label = Gtk.Label(xalign=0, wrap=True)
        self.info.get_content_area().add(self.info_label)
        self.info.set_no_show_all(True)
        outer.pack_start(self.info, False, False, 0)

        sides = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        outer.pack_start(sides, True, True, 0)
        left = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        sides.pack1(left, True, False)
        self.notebook = Gtk.Notebook(scrollable=True)
        self.notebook.connect("switch-page", lambda _n, _p, num: GLib.idle_add(self._switched))
        left.pack1(self.notebook, True, False)

        bottom = Gtk.Notebook()
        self.bottom = bottom
        self.problems = Gtk.ListBox(activate_on_single_click=True)
        self.problems.connect("row-activated", self._problem_activated)
        problems_scroll = Gtk.ScrolledWindow()
        problems_scroll.add(self.problems)
        self.problems_label = Gtk.Label(label="Problems")
        bottom.append_page(problems_scroll, self.problems_label)
        build_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        status = Gtk.Box(spacing=8)
        status.set_border_width(4)
        self.spinner = Gtk.Spinner()
        status.pack_start(self.spinner, False, False, 0)
        self.build_status = Gtk.Label(xalign=0, wrap=True, label="Not built yet.")
        status.pack_start(self.build_status, True, True, 0)
        build_box.pack_start(status, False, False, 0)
        self.log_buffer = Gtk.TextBuffer()
        self.log_view = Gtk.TextView(buffer=self.log_buffer, editable=False, monospace=True,
                                     wrap_mode=Gtk.WrapMode.CHAR)
        log_scroll = Gtk.ScrolledWindow()
        log_scroll.add(self.log_view)
        build_box.pack_start(log_scroll, True, True, 0)
        bottom.append_page(build_box, Gtk.Label(label="Build"))
        left.pack2(bottom, False, True)
        left.set_position(520)

        self.guide_pane = GuidePane(self.guide, self.insert_text, log)
        self.guide_pane.set_size_request(320, -1)
        sides.pack2(self.guide_pane, False, True)
        sides.set_position(800)

        self._shortcuts()
        self.follow_theme()
        self.connect("delete-event", self._on_delete)
        self.status_line = ""
        self.start_lsp()

    # --------------------------------------------------------------- setup

    def theme_is_dark(self) -> bool:
        """Whether the desktop theme is dark: from its own background colour, which
        works for any theme; from its name if it does not say."""
        settings = Gtk.Settings.get_default()
        found, bg = self.get_style_context().lookup_color("theme_bg_color")
        return is_dark_theme(
            (bg.red, bg.green, bg.blue) if found else None,
            settings.get_property("gtk-theme-name") or "",
            bool(settings.get_property("gtk-application-prefer-dark-theme")))

    def style_scheme(self):
        manager = GtkSource.StyleSchemeManager.get_default()
        return manager.get_scheme(DARK_SCHEME if self.theme_is_dark() else LIGHT_SCHEME)

    def follow_theme(self) -> None:
        """Themes (Cinnamon's, or any XSettings change) switches the theme while the
        editor is open: the code's colours follow it."""
        settings = Gtk.Settings.get_default()
        for prop in ("gtk-theme-name", "gtk-application-prefer-dark-theme"):
            settings.connect(f"notify::{prop}", lambda *_a: self._theme_changed())
        self.connect("style-updated", lambda *_a: self._theme_changed())
        self.scheme_id = ""
        self.scheme_timer = 0

    def _theme_changed(self) -> None:
        # The new theme's colours are known once GTK has restyled: look then.
        if not self.scheme_timer:
            self.scheme_timer = GLib.idle_add(self.apply_scheme)

    def apply_scheme(self) -> bool:
        self.scheme_timer = 0
        scheme = self.style_scheme()
        if scheme is None or scheme.get_id() == self.scheme_id:
            return False
        self.scheme_id = scheme.get_id()
        for tab in self.tabs:
            tab.buffer.set_style_scheme(scheme)
        log(f"scheme: {self.scheme_id}")
        return False

    def _shortcuts(self) -> None:
        accel = Gtk.AccelGroup()
        self.add_accel_group(accel)

        def bind(key: str, func) -> None:
            k, mods = Gtk.accelerator_parse(key)
            accel.connect(k, mods, Gtk.AccelFlags.VISIBLE, lambda *_a: (func(), True)[1])

        bind("<Control>o", self.open_dialog)
        bind("<Control>s", self.save)
        bind("<Control><Shift>s", lambda: self.save(ask=True))
        bind("<Control>n", self.new_tab)
        bind("<Control>w", lambda: self.close_tab(self.current()))
        bind("F1", lambda: self.guide_button.set_active(not self.guide_button.get_active()))
        bind("<Control>b", lambda: self.build_button.get_visible() and self.build())

    def start_lsp(self) -> None:
        nixd = os.environ.get("NIX_EDITOR_NIXD") or shutil.which("nixd")
        if not nixd:
            self.lsp_state = "missing"
            self.set_status("nixd is not installed: no suggestions or problem marks, only highlighting.")
            log("lsp: nixd not found")
            return

        def make(write):
            self.lsp = lsp.Client(write, root=os.path.expanduser("~"))
            self.lsp.on_diagnostics = self.diagnostics
            self.lsp.on_ready = self._lsp_ready
            return self.lsp

        try:
            self.transport = lsp.GioTransport([nixd], make, on_exit=self._lsp_exited)
        except GLib.Error as e:
            self.lsp_state = "missing"
            log(f"lsp: cannot start nixd: {e.message}")
            return
        self.lsp.initialize()

    def _lsp_ready(self) -> None:
        # Files opened while nixd was starting are opened with it now.
        self.lsp_state = "ready"
        for tab in self.tabs:
            self.lsp.did_open(tab.lsp_path, tab.text())

    def _lsp_exited(self) -> None:
        if self.lsp_state != "stopping":
            self.lsp_state = "crashed"
            self.set_status("The Nix language server stopped: suggestions and problem marks are off.")
            log("lsp: nixd exited")

    def lsp_ready(self) -> bool:
        return self.lsp_state == "ready" and self.lsp is not None

    def set_status(self, text: str) -> None:
        self.status_line = text
        self.show_info(text, Gtk.MessageType.WARNING)

    def show_info(self, text: str, kind=Gtk.MessageType.INFO) -> None:
        self.info.set_message_type(kind)
        self.info_label.set_text(text)
        self.info.set_no_show_all(False)
        self.info.show_all()

    # ---------------------------------------------------------------- tabs

    def current(self) -> Tab | None:
        page = self.notebook.get_current_page()
        return self.tabs[page] if 0 <= page < len(self.tabs) else None

    def add_tab(self, tab: Tab) -> Tab:
        label = Gtk.Box(spacing=4)
        label.pack_start(tab.title, False, False, 0)
        close = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        close.set_relief(Gtk.ReliefStyle.NONE)
        close.connect("clicked", lambda _b: self.close_tab(tab))
        label.pack_start(close, False, False, 0)
        label.show_all()
        self.tabs.append(tab)
        self.notebook.append_page(tab.scroll, label)
        self.notebook.set_tab_reorderable(tab.scroll, False)
        tab.scroll.show_all()
        self.notebook.set_current_page(len(self.tabs) - 1)
        if self.lsp_ready():
            self.lsp.did_open(tab.lsp_path, tab.text())
        tab.view.grab_focus()
        self.check_tulsi(tab)
        self._switched()
        return tab

    def new_tab(self) -> Tab:
        return self.add_tab(Tab(self, None))

    def open_path(self, path: str) -> Tab | None:
        path = os.path.abspath(path)
        for i, tab in enumerate(self.tabs):
            if tab.path == path:
                self.notebook.set_current_page(i)
                return tab
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            text = ""
        except (OSError, UnicodeDecodeError) as e:
            self.error(f"Cannot open {path}", str(e))
            return None
        # Replace an empty, untouched Untitled tab.
        only = self.current()
        if only and not only.path and not only.buffer.get_modified() and not only.text():
            self.close_tab(only)
        log(f"opened {path}")
        return self.add_tab(Tab(self, path, text))

    def open_draft(self, directory: str) -> None:
        tab = self.open_path(os.path.join(directory, "package.nix"))
        if not tab:
            return
        info = draft.draft_info(directory)
        self.show_info(
            f"This is the Recipe's draft for {info.get('name') or os.path.basename(directory)}. "
            "The build log below says where it stopped; the guide on the right explains what "
            "you see. When you have changed it, choose Build and Try.")
        logfile = os.path.join(directory, "build.log")
        if os.path.isfile(logfile):
            with open(logfile, encoding="utf-8", errors="replace") as f:
                self.log_buffer.set_text(f.read())
            self.build_status.set_text("The Recipe's last build failed. Its log:")
            # Once the window is shown: a notebook ignores switching to a hidden page.
            GLib.idle_add(lambda: self.bottom.set_current_page(1) and False)

    def close_tab(self, tab: Tab | None) -> None:
        if tab is None:
            return
        if tab.buffer.get_modified() and not self.confirm_discard([tab]):
            return
        i = self.tabs.index(tab)
        self.notebook.remove_page(i)
        self.tabs.remove(tab)
        if self.lsp_ready():
            self.lsp.did_close(tab.lsp_path)
        if not self.tabs:
            self.new_tab()
        self._switched()

    def _switched(self) -> bool:
        tab = self.current()
        is_draft = bool(tab and tab.draft_dir)
        self.build_button.set_visible(is_draft)
        self.install_button.set_visible(is_draft)
        self.install_button.set_sensitive(is_draft and bool(self.outcome.get("ok"))
                                          and self.outcome.get("draftDir") == tab.draft_dir)
        self.update_title()
        self.refresh_problems()
        return False

    def update_title(self) -> None:
        tab = self.current()
        if tab:
            name = ("• " if tab.buffer.get_modified() else "") + tab.name
            # GTK 3 gives the window manager the header's title: name the file and the app.
            self.header.set_title(f"{name} — Nix Editor")
            self.header.set_subtitle(os.path.dirname(tab.path) if tab.path else "Nix Editor")

    # ------------------------------------------------------------- saving

    def open_dialog(self) -> None:
        dialog = Gtk.FileChooserNative(title="Open a Nix File", transient_for=self,
                                       action=Gtk.FileChooserAction.OPEN)
        nix = Gtk.FileFilter()
        nix.set_name("Nix files")
        nix.add_pattern("*.nix")
        dialog.add_filter(nix)
        every = Gtk.FileFilter()
        every.set_name("All files")
        every.add_pattern("*")
        dialog.add_filter(every)
        if os.path.isdir(draft.recipes_dir()):
            dialog.set_current_folder(draft.recipes_dir())
        if dialog.run() == Gtk.ResponseType.ACCEPT:
            self.open_path(dialog.get_filename())
        dialog.destroy()

    def save(self, ask: bool = False, tab: Tab | None = None) -> bool:
        tab = tab or self.current()
        if tab is None:
            return False
        if ask or not tab.path:
            dialog = Gtk.FileChooserNative(title="Save As", transient_for=self,
                                           action=Gtk.FileChooserAction.SAVE)
            dialog.set_do_overwrite_confirmation(True)
            dialog.set_current_name(tab.name if tab.path else "package.nix")
            ok = dialog.run() == Gtk.ResponseType.ACCEPT
            path = dialog.get_filename()
            dialog.destroy()
            if not ok or not path:
                return False
            if self.lsp_ready():
                self.lsp.did_close(tab.lsp_path)
            tab.path = os.path.abspath(path)
            tab.watch()
            if self.lsp_ready():
                self.lsp.did_open(tab.lsp_path, tab.text())
        try:
            tmp = tab.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(tab.text())
            os.replace(tmp, tab.path)
        except OSError as e:
            self.error(f"Cannot save {tab.path}", str(e))
            return False
        tab.buffer.set_modified(False)
        tab.update_title()
        log(f"saved {tab.path}")
        if self.lsp_ready():
            tab.flush_change()
            self.lsp.did_save(tab.lsp_path)
        self.check_tulsi(tab)
        self._switched()
        return True

    def confirm_discard(self, tabs: list[Tab]) -> bool:
        names = ", ".join(t.name for t in tabs)
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
                                   text=f"Save the changes to {names}?")
        dialog.format_secondary_text("If you close without saving, the changes are lost.")
        dialog.add_buttons("Close _Without Saving", Gtk.ResponseType.REJECT,
                           "_Cancel", Gtk.ResponseType.CANCEL, "_Save", Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.ACCEPT)
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.ACCEPT:
            return all(self.save(tab=t) for t in tabs)
        return response == Gtk.ResponseType.REJECT

    def _on_delete(self, *_args) -> bool:
        modified = [t for t in self.tabs if t.buffer.get_modified()]
        if modified and not self.confirm_discard(modified):
            return True
        self.lsp_state = "stopping"
        if self.transport:
            self.transport.stop()
        if self.build_proc and self.build_proc.poll() is None:
            self.build_proc.terminate()
        return False

    def error(self, text: str, detail: str = "") -> None:
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.ERROR,
                                   buttons=Gtk.ButtonsType.CLOSE, text=text)
        if detail:
            dialog.format_secondary_text(detail)
        dialog.run()
        dialog.destroy()

    # --------------------------------------------------------- the guide

    def insert_text(self, text: str) -> None:
        tab = self.current()
        if not tab or not text:
            return
        b = tab.buffer
        it = b.get_iter_at_mark(b.get_insert())
        if not it.starts_line():
            text = "\n" + text
        b.insert_at_cursor(text + "\n")
        tab.view.grab_focus()

    def cursor_moved(self, tab: Tab) -> None:
        if tab is not self.current() or not self.guide_pane.follow.get_active():
            return
        if self.cursor_timer:
            GLib.source_remove(self.cursor_timer)
        self.cursor_timer = GLib.timeout_add(400, self._explain_cursor)

    def _explain_cursor(self) -> bool:
        self.cursor_timer = 0
        tab = self.current()
        if not tab or not self.guide_pane.get_visible():
            return False
        b = tab.buffer
        it = b.get_iter_at_mark(b.get_insert())
        start = it.copy()
        start.set_line_offset(0)
        end = it.copy()
        if not end.ends_line():
            end.forward_to_line_end()
        line = start.get_text(end)
        word = word_at(line, it.get_line_offset())
        if not word or word == self.last_word:
            return False
        self.last_word = word
        entry = self.guide.lookup(word, prefixes=False)
        if entry:
            if entry is not self.guide_pane.current:
                self.guide_pane.show(entry)
            return False
        if self.lsp_ready():
            tab.flush_change()
            char16 = lsp.chars_to_utf16(line, it.get_line_offset())

            def hovered(text: str, word=word) -> None:
                if word != self.last_word:
                    return
                if text:
                    self.guide_pane.show_hover(word, text)
                else:
                    fallback = self.guide.lookup(word)
                    if fallback and fallback is not self.guide_pane.current:
                        self.guide_pane.show(fallback)

            self.lsp.hover(tab.lsp_path, it.get_line(), char16, hovered)
        else:
            fallback = self.guide.lookup(word)
            if fallback and fallback is not self.guide_pane.current:
                self.guide_pane.show(fallback)
        return False

    # ------------------------------------------------------- completion

    def request_completion(self, line: int, before: str, callback) -> None:
        tab = self.current()
        if not tab or not self.lsp_ready():
            callback([])
            return
        tab.flush_change()
        self.lsp.completion(tab.lsp_path, line, lsp.chars_to_utf16(before, len(before)), callback)

    # ------------------------------------------------------------ problems

    def diagnostics(self, uri: str, items: list) -> None:
        for tab in self.tabs:
            if lsp.file_uri(tab.lsp_path) == uri:
                tab.lsp_problems = [
                    Problem("nixd", d.get("message", ""), d["range"]["start"]["line"],
                            d["range"]["start"]["character"],
                            (d["range"]["end"]["line"], d["range"]["end"]["character"]),
                            error=d.get("severity", 1) == 1)
                    for d in items if "range" in d]
                seen = {(p.line, p.column, p.message) for p in tab.lsp_problems}
                if seen != getattr(tab, "lsp_seen", None):
                    tab.lsp_seen = seen
                    for p in tab.lsp_problems:
                        log(f"problem: nixd {p.line + 1}:{p.column + 1} {p.message}")
                tab.mark()
                if tab is self.current():
                    self.refresh_problems()

    def check_tulsi(self, tab: Tab) -> None:
        """TulsiOS's rules for local packages, for files named package.nix."""
        if not tab.path or os.path.basename(tab.path) != "package.nix" or not os.path.isfile(tab.path):
            tab.tulsi_problems = []
            return
        try:
            proc = Gio.Subprocess.new(draft.check_command(tab.path),
                                      Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE)
        except GLib.Error as e:
            log(f"cannot run tulsi recipe check: {e.message}")
            return
        text = tab.text()

        def done(p, result) -> None:
            try:
                _ok, out, _err = p.communicate_utf8_finish(result)
                found = json.loads(out or "[]")
            except (GLib.Error, ValueError):
                return
            tab.tulsi_problems = []
            for message in found:
                where = draft.locate(message, text)
                if where:
                    line, col, length = where
                    tab.tulsi_problems.append(Problem("TulsiOS", message, line, col, (line, col + length)))
                else:
                    tab.tulsi_problems.append(Problem("TulsiOS", message, None))
                log(f"problem: tulsios {message}")
            tab.mark()
            if tab is self.current():
                self.refresh_problems()

        proc.communicate_utf8_async(None, None, done)

    def refresh_problems(self) -> None:
        for row in self.problems.get_children():
            self.problems.remove(row)
        tab = self.current()
        problems = (tab.tulsi_problems + tab.lsp_problems) if tab else []
        for p in problems:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(spacing=8)
            box.set_border_width(3)
            icon = "dialog-error-symbolic" if p.error else "dialog-warning-symbolic"
            box.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU), False, False, 0)
            where = f"{p.line + 1}:{p.column + 1}" if p.line is not None else ""
            text = Gtk.Label(xalign=0, wrap=True)
            text.set_markup(f"<tt>{GLib.markup_escape_text(where):>7}</tt>  {GLib.markup_escape_text(p.message)}"
                            f"  <span alpha='60%'>{p.source}</span>")
            box.pack_start(text, True, True, 0)
            row.add(box)
            row.problem = p
            self.problems.add(row)
        self.problems.show_all()
        self.problems_label.set_text(f"Problems ({len(problems)})" if problems else "Problems")

    def _problem_activated(self, _list, row) -> None:
        tab = self.current()
        p = getattr(row, "problem", None)
        if not tab or not p or p.line is None:
            return
        it = iter_at(tab.buffer, p.line, p.column)
        tab.buffer.place_cursor(it)
        tab.view.scroll_to_iter(it, 0.2, False, 0, 0)
        tab.view.grab_focus()

    # --------------------------------------------------------- build, install

    def build(self) -> None:
        tab = self.current()
        if not tab or not tab.draft_dir or (self.build_proc and self.build_proc.poll() is None):
            return
        if tab.buffer.get_modified() and not self.save(tab=tab):
            return
        directory = tab.draft_dir
        self.outcome = {}
        self.install_button.set_sensitive(False)
        self.build_button.set_sensitive(False)
        self.log_buffer.set_text("")
        self.bottom.set_current_page(1)
        self.spinner.start()
        self.build_status.set_text("Checking and building…")
        command = draft.build_command(directory)
        log("build: " + " ".join(command))
        self.build_proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, text=True)
        stdout: list[str] = []
        proc = self.build_proc

        def read_out() -> None:
            stdout.append(proc.stdout.read())

        def read_err() -> None:
            for line in proc.stderr:
                GLib.idle_add(self._append_log, line)
            proc.wait()
            reader.join(5)
            GLib.idle_add(self._built, directory, "".join(stdout))

        reader = threading.Thread(target=read_out, daemon=True)
        reader.start()
        threading.Thread(target=read_err, daemon=True).start()

    def _append_log(self, line: str) -> bool:
        if line.startswith("tulsi-recipe: "):
            self.build_status.set_text(line.removeprefix("tulsi-recipe: ").strip().capitalize() + "…")
        self.log_buffer.insert(self.log_buffer.get_end_iter(), line)
        if self.log_buffer.get_line_count() > MAX_LOG_LINES:
            cut = self.log_buffer.get_iter_at_line(self.log_buffer.get_line_count() - MAX_LOG_LINES)
            self.log_buffer.delete(self.log_buffer.get_start_iter(), cut)
        self.log_view.scroll_to_iter(self.log_buffer.get_end_iter(), 0, False, 0, 1)
        return False

    def _built(self, directory: str, out: str) -> bool:
        self.spinner.stop()
        self.build_button.set_sensitive(True)
        try:
            outcome = json.loads(out)
        except ValueError:
            outcome = {"ok": False, "error": "The build's result could not be read."}
        outcome["draftDir"] = directory
        self.outcome = outcome
        log(f"build finished: ok={outcome.get('ok')} error={outcome.get('error', '')!r}")
        if outcome.get("ok"):
            lines = [f"Built {outcome.get('name')} {outcome.get('version', '')}."]
            tried = outcome.get("tried") or {}
            if tried.get("ok"):
                lines.append(f"{tried.get('program', '')} starts (tried in a sandbox).")
            lines += [f"⚠ {w}" for w in outcome.get("warnings") or []]
            lines.append("Install adds it to this computer, with the Software Center's confirmation and Undo.")
            self.build_status.set_text(" ".join(lines))
            self.bottom.set_current_page(1)
        else:
            self.build_status.set_text(outcome.get("error") or "The build failed.")
            if outcome.get("logTail") and not self.log_buffer.get_char_count():
                self.log_buffer.set_text(outcome["logTail"])
        self._switched()
        return False

    def install(self) -> None:
        o = self.outcome
        tab = self.current()
        if not o.get("ok") or not tab or o.get("draftDir") != tab.draft_dir:
            return
        try:
            ops = draft.ops_for(o)
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            self.error("Cannot prepare the installation", str(e))
            return
        log(f"installing {o.get('name')}")
        try:
            draft.software_center("apply-ops", draft.apply_ops_argument(o, ops))
        except GLib.Error as e:
            self.error("Cannot reach the Software Center", e.message)
            return
        self.build_status.set_text("The Software Center asks you to confirm the installation.")
