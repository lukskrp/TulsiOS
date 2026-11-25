"""The guide pane on the right: an entry, a search, a contents list (ADR 0019)."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GtkSource", "4")
from gi.repository import Gdk, Gtk, Pango  # noqa: E402

from .guide import Entry, Guide, spans


class GuidePane(Gtk.Box):
    def __init__(self, guide: Guide, on_insert: Callable[[str], None], log: Callable[[str], None]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.guide = guide
        self.on_insert = on_insert
        self.log = log
        self.current: Entry | None = None
        self.history: list[str] = []
        self.set_border_width(6)

        top = Gtk.Box(spacing=4)
        self.back = Gtk.Button.new_from_icon_name("go-previous-symbolic", Gtk.IconSize.BUTTON)
        self.back.set_tooltip_text("Back")
        self.back.connect("clicked", lambda _b: self.go_back())
        top.pack_start(self.back, False, False, 0)
        self.search = Gtk.SearchEntry(placeholder_text="Search the Nix guide")
        self.search.connect("search-changed", lambda _e: self._on_search())
        self.search.connect("activate", lambda _e: self._open_first())
        top.pack_start(self.search, True, True, 0)
        contents = Gtk.Button.new_from_icon_name("view-list-symbolic", Gtk.IconSize.BUTTON)
        contents.set_tooltip_text("All topics")
        contents.connect("clicked", lambda _b: self.show_contents())
        top.pack_start(contents, False, False, 0)
        self.follow = Gtk.ToggleButton()
        self.follow.add(Gtk.Image.new_from_icon_name("find-location-symbolic", Gtk.IconSize.BUTTON))
        self.follow.set_tooltip_text("Follow the cursor: explain the word under it")
        self.follow.set_active(True)
        top.pack_start(self.follow, False, False, 0)
        self.pack_start(top, False, False, 0)

        self.stack = Gtk.Stack()
        self.pack_start(self.stack, True, True, 0)

        # An entry.
        self.buffer = Gtk.TextBuffer()
        self._tags()
        self.view = Gtk.TextView(buffer=self.buffer, editable=False, cursor_visible=False,
                                 wrap_mode=Gtk.WrapMode.WORD_CHAR, left_margin=8, right_margin=8,
                                 top_margin=6, bottom_margin=6)
        self.view.connect("event-after", self._on_click)
        self.view.connect("motion-notify-event", self._on_motion)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.add(self.view)
        entry_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        entry_box.pack_start(scroll, True, True, 0)
        self.insert = Gtk.Button.new_with_mnemonic("Insert _Example")
        self.insert.set_tooltip_text("Put this entry's example into the file, at the cursor")
        self.insert.connect("clicked", lambda _b: self.current and self.on_insert(self.current.example))
        entry_box.pack_start(self.insert, False, False, 0)
        self.stack.add_named(entry_box, "entry")

        # A list: search results or all topics.
        self.list = Gtk.ListBox(activate_on_single_click=True)
        self.list.connect("row-activated", lambda _l, row: self.show(self.guide.by_id[row.entry_id]))
        list_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        list_scroll.add(self.list)
        self.stack.add_named(list_scroll, "list")

        start = guide.by_id.get("start") or (guide.entries[0] if guide.entries else None)
        if start:
            self.show(start, remember=False)

    def _tags(self) -> None:
        b = self.buffer
        b.create_tag("title", weight=Pango.Weight.BOLD, scale=1.35, pixels_below_lines=8)
        b.create_tag("heading", weight=Pango.Weight.BOLD, scale=1.1, pixels_above_lines=6)
        b.create_tag("bold", weight=Pango.Weight.BOLD)
        b.create_tag("code", family="monospace")
        b.create_tag("codeblock", family="monospace", left_margin=20,
                     paragraph_background_rgba=Gdk.RGBA(0.5, 0.5, 0.5, 0.12))
        b.create_tag("bullet", left_margin=20, indent=-12)
        b.create_tag("link", underline=Pango.Underline.SINGLE, foreground="#3d8fd1")
        b.create_tag("dim", foreground="#8a8a8a")
        b.create_tag("hover", family="monospace", wrap_mode=Gtk.WrapMode.WORD_CHAR)

    # ------------------------------------------------------------ showing

    def _render(self, runs) -> None:
        self.buffer.set_text("")
        self.links: list[tuple[Gtk.TextMark, Gtk.TextMark, str]] = []
        for text, tags, target in runs:
            end = self.buffer.get_end_iter()
            start_mark = self.buffer.create_mark(None, end, True)
            self.buffer.insert_with_tags_by_name(end, text, *tags) if tags else self.buffer.insert(end, text)
            if target:
                end_mark = self.buffer.create_mark(None, self.buffer.get_end_iter(), True)
                self.links.append((start_mark, end_mark, target))
        self.view.scroll_to_iter(self.buffer.get_start_iter(), 0, False, 0, 0)
        self.stack.set_visible_child_name("entry")

    def show(self, entry: Entry, remember: bool = True) -> None:
        if remember and self.current and self.current.id != entry.id:
            self.history.append(self.current.id)
        self.current = entry
        titles = {e.id: e.title for e in self.guide.entries}
        self._render(spans(entry, titles))
        self.insert.set_sensitive(bool(entry.example))
        self.insert.set_visible(True)
        self.back.set_sensitive(bool(self.history))
        self.log(f"guide: {entry.id}")

    def show_hover(self, word: str, text: str) -> None:
        """What nixd says about a name the guide has no entry for (a package, say)."""
        if self.current:
            self.history.append(self.current.id)
        self.current = None
        runs = [(word + "\n", ("title",), "")]
        for line in text.replace("## ", "").splitlines():
            runs.append((line + "\n", (), ""))
        runs.append(("\nFrom the language server (nixd). ", ("dim",), ""))
        runs.append(("How a package uses others", ("link",), "package-file"))
        runs.append(("\n", (), ""))
        self._render(runs)
        self.insert.set_visible(False)
        self.back.set_sensitive(bool(self.history))
        self.log(f"hover: {word}")

    def go_back(self) -> None:
        while self.history:
            entry = self.guide.by_id.get(self.history.pop())
            if entry:
                self.show(entry, remember=False)
                return

    def show_contents(self) -> None:
        self.search.set_text("")
        self._fill(self.guide.entries, group=True)

    def _on_search(self) -> None:
        text = self.search.get_text()
        if not text.strip():
            if self.current:
                self.stack.set_visible_child_name("entry")
            return
        self._fill(self.guide.search(text), group=False)

    def _open_first(self) -> None:
        row = self.list.get_row_at_index(0)
        if row is not None and self.stack.get_visible_child_name() == "list":
            self.show(self.guide.by_id[row.entry_id])

    def _fill(self, entries: list[Entry], group: bool) -> None:
        for child in self.list.get_children():
            self.list.remove(child)
        topic = None
        names = {"language": "The language", "builtins": "Built-in functions", "lib": "lib",
                 "packaging": "Packaging", "tulsios": "TulsiOS"}
        for e in entries:
            if group and e.topic != topic:
                topic = e.topic
                head = Gtk.Label(xalign=0)
                head.set_markup(f"<b>{names.get(topic, topic)}</b>")
                head.set_margin_top(8)
                row = Gtk.ListBoxRow(selectable=False, activatable=False)
                row.add(head)
                row.entry_id = ""
                self.list.add(row)
            row = Gtk.ListBoxRow()
            label = Gtk.Label(label=e.title, xalign=0)
            label.set_margin_start(12 if group else 4)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            row.add(label)
            row.entry_id = e.id
            self.list.add(row)
        if not entries:
            row = Gtk.ListBoxRow(selectable=False, activatable=False)
            row.add(Gtk.Label(label="Nothing in the guide matches.", xalign=0))
            row.entry_id = ""
            self.list.add(row)
        self.list.show_all()
        self.stack.set_visible_child_name("list")

    # -------------------------------------------------------------- links

    def _link_at(self, x: int, y: int) -> str:
        bx, by = self.view.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, x, y)
        found, it = self.view.get_iter_at_location(bx, by)
        if not found:
            return ""
        offset = it.get_offset()
        for start, end, target in getattr(self, "links", []):
            if (self.buffer.get_iter_at_mark(start).get_offset() <= offset
                    < self.buffer.get_iter_at_mark(end).get_offset()):
                return target
        return ""

    def _on_click(self, _view, event) -> None:
        if event.type != Gdk.EventType.BUTTON_RELEASE or event.button.button != 1:
            return
        if self.buffer.get_has_selection():
            return
        target = self._link_at(int(event.x), int(event.y))
        if target in self.guide.by_id:
            self.show(self.guide.by_id[target])

    def _on_motion(self, view, event) -> bool:
        window = view.get_window(Gtk.TextWindowType.TEXT)
        if window is not None:
            name = "pointer" if self._link_at(int(event.x), int(event.y)) else "text"
            window.set_cursor(Gdk.Cursor.new_from_name(view.get_display(), name))
        return False
