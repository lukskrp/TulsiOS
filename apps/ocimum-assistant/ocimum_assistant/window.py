"""The chat window. The agent runs on a worker thread; every UI update is
marshalled back to the GTK main loop with GLib.idle_add."""

from __future__ import annotations

import os
import subprocess
import threading

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")

from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from . import markdown  # noqa: E402
from .agent import Agent, describe_outcome, describe_tool, to_provider_tools  # noqa: E402
from .mcp import DEFAULT_COMMAND, McpClient, McpError  # noqa: E402
from .providers import EFFORTS, MODELS, ProviderError, make_provider  # noqa: E402
from .settings import Keyring, Settings  # noqa: E402

WINDOW_TITLE = "Assistant"
EXAMPLES = [
    "Install a lightweight video player",
    "Turn on printing",
    "What did I change recently?",
]
CSS = b"""
.bubble { padding: 8px 12px; border-radius: 10px; }
.bubble-user { background-color: alpha(@theme_selected_bg_color, 0.18); }
.bubble-assistant { background-color: alpha(@theme_fg_color, 0.06); }
.tool-line { font-size: smaller; }
"""


def _idle(fn):
    """Decorator: run the wrapped method on the GTK main loop."""
    def wrapper(*args, **kwargs):
        GLib.idle_add(lambda: (fn(*args, **kwargs), GLib.SOURCE_REMOVE)[1])
    return wrapper


class Window(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title=WINDOW_TITLE, default_width=720, default_height=760)
        self.settings = Settings.load()
        self.keyring = Keyring()
        self.mcp: McpClient | None = None
        self.agent: Agent | None = None
        self.busy = False
        self._bubble: Gtk.Label | None = None
        self._bubble_text = ""
        self._undo_button: Gtk.Button | None = None

        provider_css = Gtk.CssProvider()
        provider_css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        header = Gtk.HeaderBar(show_close_button=True, title=WINDOW_TITLE)
        self._update_subtitle(header)
        new_button = Gtk.Button.new_from_icon_name("document-new-symbolic", Gtk.IconSize.BUTTON)
        new_button.set_tooltip_text("New conversation")
        new_button.connect("clicked", lambda _b: self.new_conversation())
        header.pack_start(new_button)
        history_button = Gtk.Button.new_from_icon_name("document-open-recent-symbolic", Gtk.IconSize.BUTTON)
        history_button.set_tooltip_text("Recent changes (with Undo)")
        history_button.connect("clicked", lambda _b: self.open_history())
        header.pack_start(history_button)
        settings_button = Gtk.Button.new_from_icon_name("emblem-system-symbolic", Gtk.IconSize.BUTTON)
        settings_button.set_tooltip_text("Settings")
        settings_button.connect("clicked", lambda _b: self.open_settings())
        header.pack_end(settings_button)
        self.header = header
        self.set_titlebar(header)

        self.infobar = Gtk.InfoBar(show_close_button=True, revealed=False)
        self.info_label = Gtk.Label(xalign=0, wrap=True)
        self.infobar.get_content_area().add(self.info_label)
        self.infobar.connect("response", lambda bar, _r: bar.set_revealed(False))

        self.chat = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=14)
        self.scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.scroller.add(self.chat)

        self.status = Gtk.Box(spacing=8, margin_start=14, margin_end=14)
        self.spinner = Gtk.Spinner()
        self.status_label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.status_label.get_style_context().add_class("dim-label")
        self.status.pack_start(self.spinner, False, False, 0)
        self.status.pack_start(self.status_label, True, True, 0)

        self.entry = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, accepts_tab=False)
        self.entry.set_left_margin(8)
        self.entry.set_right_margin(8)
        self.entry.set_top_margin(6)
        self.entry.set_bottom_margin(6)
        self.entry.connect("key-press-event", self._on_key)
        entry_scroll = Gtk.ScrolledWindow(min_content_height=60, max_content_height=140)
        entry_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        entry_scroll.add(self.entry)
        entry_frame = Gtk.Frame()
        entry_frame.add(entry_scroll)
        self.send_button = Gtk.Button(label="Send", valign=Gtk.Align.END)
        self.send_button.get_style_context().add_class("suggested-action")
        self.send_button.connect("clicked", lambda _b: self.send_or_stop())
        bottom = Gtk.Box(spacing=8, margin=12)
        bottom.pack_start(entry_frame, True, True, 0)
        bottom.pack_end(self.send_button, False, False, 0)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main.pack_start(self.infobar, False, False, 0)
        main.pack_start(self.scroller, True, True, 0)
        main.pack_start(self.status, False, False, 0)
        main.pack_end(bottom, False, False, 0)
        self.add(main)

        self.connect("destroy", lambda _w: self.mcp and self.mcp.close())
        self.show_all()
        self.infobar.set_revealed(False)
        self._show_intro()
        self.entry.grab_focus()

    # ---------------------------------------------------------- conversation

    def _show_intro(self) -> None:
        intro = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=40)
        title = Gtk.Label()
        title.set_markup("<span size='x-large' weight='bold'>What would you like to change?</span>")
        intro.pack_start(title, False, False, 0)
        body = Gtk.Label(
            label="Ask in plain words to install software, turn features on or off, or adjust "
            "settings. Every change can be undone; anything a restart cannot undo, such as "
            "accounts or disks, asks you first.",
            wrap=True, justify=Gtk.Justification.CENTER, max_width_chars=60,
        )
        body.get_style_context().add_class("dim-label")
        intro.pack_start(body, False, False, 0)
        chips = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, halign=Gtk.Align.CENTER,
                            max_children_per_line=3, column_spacing=8, row_spacing=8)
        for example in EXAMPLES:
            chip = Gtk.Button(label=example)
            chip.connect("clicked", lambda _b, text=example: self.ask(text))
            chips.add(chip)
        intro.pack_start(chips, False, False, 6)
        intro.show_all()
        self.chat.pack_start(intro, False, False, 0)

    def new_conversation(self) -> None:
        if self.busy:
            return
        for child in self.chat.get_children():
            self.chat.remove(child)
        self._undo_button = None
        if self.agent:
            self.agent.reset()
        self._show_intro()

    def _add_bubble(self, text: str, user: bool) -> Gtk.Label:
        label = Gtk.Label(xalign=0, wrap=True, selectable=True, max_width_chars=60)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        if user:
            label.set_text(text)
        else:
            label.set_markup(markdown.to_pango(text) or " ")
        box = Gtk.Box()
        box.get_style_context().add_class("bubble")
        box.get_style_context().add_class("bubble-user" if user else "bubble-assistant")
        box.add(label)
        row = Gtk.Box(halign=Gtk.Align.END if user else Gtk.Align.START)
        row.add(box)
        row.show_all()
        self.chat.pack_start(row, False, False, 0)
        self._scroll_down()
        return label

    def _add_tool_line(self, text: str, icon: str, undo: bool = False) -> None:
        row = Gtk.Box(spacing=6, margin_start=6)
        row.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU), False, False, 0)
        label = Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=70)
        label.get_style_context().add_class("dim-label")
        label.get_style_context().add_class("tool-line")
        row.pack_start(label, True, True, 0)
        if undo:
            button = Gtk.Button(label="Undo", valign=Gtk.Align.CENTER)
            button.set_tooltip_text("Undo the latest system change")
            button.connect("clicked", lambda b: self.undo_latest(b))
            row.pack_end(button, False, False, 0)
            # Only the newest change can be undone: older Undo buttons go away.
            if self._undo_button is not None:
                self._undo_button.destroy()
            self._undo_button = button
        row.show_all()
        self.chat.pack_start(row, False, False, 0)
        self._scroll_down()

    def _scroll_down(self) -> None:
        def go():
            adj = self.scroller.get_vadjustment()
            adj.set_value(adj.get_upper())
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(50, go)

    # ------------------------------------------------------------- input

    def _on_key(self, _view, event) -> bool:
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and not (event.state & Gdk.ModifierType.SHIFT_MASK):
            self.send_or_stop()
            return True
        return False

    def send_or_stop(self) -> None:
        if self.busy:
            if self.agent:
                self.agent.cancelled = True
                self._set_status("Stopping after the current step…")
            return
        buffer = self.entry.get_buffer()
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False).strip()
        if text:
            buffer.set_text("")
            self.ask(text)

    def ask(self, text: str) -> None:
        if self.busy:
            return
        for child in self.chat.get_children():
            if isinstance(child, Gtk.Box) and child.get_orientation() == Gtk.Orientation.VERTICAL:
                self.chat.remove(child)  # the intro
        self._add_bubble(text, user=True)
        self._set_busy(True, "Thinking…")
        threading.Thread(target=self._worker, args=(text,), daemon=True).start()

    def _set_busy(self, busy: bool, status: str = "") -> None:
        self.busy = busy
        self.send_button.set_label("Stop" if busy else "Send")
        style = self.send_button.get_style_context()
        style.remove_class("suggested-action" if busy else "destructive-action")
        style.add_class("destructive-action" if busy else "suggested-action")
        if busy:
            self.spinner.start()
        else:
            self.spinner.stop()
        self._set_status(status)

    def _set_status(self, text: str) -> None:
        self.status_label.set_text(text)

    # ------------------------------------------------------------ worker

    def _ensure_agent(self) -> Agent:
        if self.agent:
            return self.agent
        scripted = os.environ.get("OCIMUM_ASSISTANT_PROVIDER", "").startswith("fake:")
        api_key = None if scripted else self.keyring.get()
        provider = make_provider(api_key, self.settings.model, self.settings.effort)
        mcp = McpClient(os.environ.get("OCIMUM_ASSISTANT_MCP", DEFAULT_COMMAND))
        mcp.start()
        self.mcp = mcp
        self.agent = Agent(provider, mcp, to_provider_tools(mcp.list_tools()), mcp.instructions)
        return self.agent

    def _worker(self, text: str) -> None:
        try:
            self._ensure_agent().ask(text, self)
        except ProviderError as e:
            self._error(str(e), needs_key=e.needs_key)
        except McpError as e:
            self._error(f"The TulsiOS tool service is unavailable: {e}")
            if self.mcp:
                self.mcp.close()
            self.mcp, self.agent = None, None
        except Exception as e:  # noqa: BLE001 - keep the window alive
            self._error(f"Unexpected error: {e}")
        finally:
            self._finish()

    # Events from the agent (worker thread) -> main loop.

    @_idle
    def text(self, delta: str) -> None:
        if self._bubble is None:
            self._bubble_text = ""
            self._bubble = self._add_bubble(" ", user=False)
        self._bubble_text += delta
        self._bubble.set_markup(markdown.to_pango(self._bubble_text) or " ")
        self._set_status("Writing…")
        self._scroll_down()

    @_idle
    def thinking(self, delta: str) -> None:
        snippet = " ".join(delta.split())[-90:]
        if snippet:
            self._set_status(f"Thinking: {snippet}")

    @_idle
    def turn_done(self, text: str) -> None:
        if self._bubble is not None and text:
            self._bubble.set_markup(markdown.to_pango(text) or " ")
        self._bubble = None

    @_idle
    def tool_started(self, name: str, arguments: dict) -> None:
        self._add_tool_line(describe_tool(name, arguments), "system-run-symbolic")
        if name.startswith(("apply_", "undo_", "propose_local")):
            self._set_status("Changing the system (you may be asked to approve), then rebuilding…")
        else:
            self._set_status("Working…")

    @_idle
    def tool_finished(self, name: str, ok: bool, text: str) -> None:
        if name.startswith(("apply_", "undo_")):
            first = text.strip().splitlines()[0] if text.strip() else ""
            icon = "object-select-symbolic" if ok else "dialog-warning-symbolic"
            self._add_tool_line(first or ("Done" if ok else "Not applied"), icon)
        self._set_status("Thinking…")

    @_idle
    def notice(self, text: str) -> None:
        self._add_tool_line(text, "dialog-information-symbolic")

    @_idle
    def outcome(self, receipts: list[dict], note: str) -> None:
        """The receipt line under a reply: what actually changed, with Undo."""
        kind, text = describe_outcome(receipts)
        if kind == "changed":
            self._add_tool_line(text, "emblem-ok-symbolic", undo=True)
        elif kind in ("rolled_back", "rejected"):
            self._add_tool_line(text, "dialog-warning-symbolic")
        if note:
            self._add_tool_line(note, "dialog-information-symbolic")

    # ----------------------------------------------------- undo and history

    def undo_latest(self, button: Gtk.Button) -> None:
        """Undo straight through tulsi-mcp (no model turn); the model hears about
        it with the next message."""
        if self.busy or self.mcp is None:
            return
        button.set_sensitive(False)
        self._set_busy(True, "Undoing the latest change…")

        def work() -> None:
            try:
                result = self.mcp.call_tool(
                    "undo_last_change", {"reason": "The user pressed Undo in the Assistant."}
                )
                receipt = (result.structured or {}).get("receipt") or {}
                if receipt.get("outcome") == "applied" and self.agent:
                    self.agent.pending_notes.append(
                        "the user pressed Undo, which reverted the latest system change."
                    )
                first = result.text.strip().splitlines()[0] if result.text.strip() else ""
                self._undo_done(not result.is_error, first, button)
            except McpError as e:
                self._undo_done(False, f"Could not undo: {e}", button)
            finally:
                self._finish()

        threading.Thread(target=work, daemon=True).start()

    @_idle
    def _undo_done(self, ok: bool, text: str, button: Gtk.Button) -> None:
        if ok:
            button.destroy()
            if self._undo_button is button:
                self._undo_button = None
        else:
            button.set_sensitive(True)
        self._add_tool_line(
            ("Undone. " if ok else "") + text,
            "edit-undo-symbolic" if ok else "dialog-warning-symbolic",
        )

    def open_history(self) -> None:
        """Recent changes live in the Software Center's History page."""
        try:
            subprocess.Popen(["ocimum-software-center", "--history"], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            self._error(f"Cannot open the Software Center: {e}")

    @_idle
    def _error(self, text: str, needs_key: bool = False) -> None:
        self.info_label.set_text(text)
        self.infobar.set_message_type(Gtk.MessageType.ERROR)
        self.infobar.set_revealed(True)
        if needs_key:
            self.open_settings()

    @_idle
    def _finish(self) -> None:
        self._bubble = None
        self._set_busy(False)

    # ---------------------------------------------------------- settings

    def _update_subtitle(self, header: Gtk.HeaderBar) -> None:
        header.set_subtitle(MODELS.get(self.settings.model, self.settings.model).split(" (")[0])

    def open_settings(self) -> None:
        dialog = Gtk.Dialog(title="Assistant Settings", transient_for=self, modal=True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        save = dialog.add_button("Save", Gtk.ResponseType.OK)
        save.get_style_context().add_class("suggested-action")
        grid = Gtk.Grid(row_spacing=10, column_spacing=12, margin=16)

        model = Gtk.ComboBoxText()
        for model_id, title in MODELS.items():
            model.append(model_id, title)
        model.set_active_id(self.settings.model)
        effort = Gtk.ComboBoxText()
        for level in EFFORTS:
            effort.append(level, level.capitalize())
        effort.set_active_id(self.settings.effort)
        key = Gtk.Entry(visibility=False, hexpand=True)
        has_key = self.keyring.get() is not None
        key.set_placeholder_text("Stored in your keyring" if has_key else "sk-ant-…")

        rows = [("Model", model), ("Thoroughness", effort), ("Anthropic API key", key)]
        for i, (title, widget) in enumerate(rows):
            grid.attach(Gtk.Label(label=title, xalign=1), 0, i, 1, 1)
            grid.attach(widget, 1, i, 1, 1)
        hint = Gtk.Label(wrap=True, xalign=0, max_width_chars=50)
        hint.set_markup(
            "Get a key at <a href='https://platform.claude.com'>platform.claude.com</a>. Without one, "
            "the <tt>ANTHROPIC_API_KEY</tt> environment variable or an <tt>ant auth login</tt> "
            "profile is used." + ("" if self.keyring.available else
                                  "\n<b>No keyring is available, so a key cannot be stored.</b>")
        )
        hint.get_style_context().add_class("dim-label")
        grid.attach(hint, 1, len(rows), 1, 1)
        if has_key:
            forget = Gtk.Button(label="Forget stored key", halign=Gtk.Align.START)
            forget.connect("clicked", lambda _b: (self.keyring.clear(), key.set_placeholder_text("sk-ant-…")))
            grid.attach(forget, 1, len(rows) + 1, 1, 1)
        dialog.get_content_area().add(grid)
        dialog.show_all()

        if dialog.run() == Gtk.ResponseType.OK:
            self.settings.model = model.get_active_id() or self.settings.model
            self.settings.effort = effort.get_active_id() or self.settings.effort
            self.settings.save()
            new_key = key.get_text().strip()
            if new_key and not self.keyring.set(new_key):
                self._error("The key could not be stored in the keyring.")
            self._update_subtitle(self.header)
            # Rebuild the provider with the new settings on the next message,
            # keeping the conversation.
            if self.agent and not self.busy:
                try:
                    self.agent.provider = make_provider(self.keyring.get(), self.settings.model, self.settings.effort)
                except ProviderError as e:
                    self._error(str(e))
        dialog.destroy()
