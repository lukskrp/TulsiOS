"""The Drivers window (ADR 0029): one section per device, its driver choices and
extras, and Apply, which takes effect at the next restart, on trial."""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from . import catalogue, config, detect, system  # noqa: E402

NVIDIA_LICENSE = "https://www.nvidia.com/en-us/drivers/nvidia-license/"


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
        super().__init__(application=app, title="Drivers", default_width=720, default_height=620)
        self.set_icon_name("org.tulsi.Drivers")
        header = Gtk.HeaderBar(show_close_button=True, title="Drivers")
        self.set_titlebar(header)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(outer)
        self.bar = Gtk.InfoBar(show_close_button=False, no_show_all=True)
        self.bar_label = _label("")
        self.bar.get_content_area().add(self.bar_label)
        self.bar.connect("response", self._bar_response)
        outer.pack_start(self.bar, False, False, 0)

        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, margin=18)
        scroll.add(self.list)
        outer.pack_start(scroll, True, True, 0)

        actions = Gtk.Box(spacing=8, margin=12)
        self.spinner = Gtk.Spinner()
        self.status = _label("", dim=True)
        actions.pack_start(self.spinner, False, False, 0)
        actions.pack_start(self.status, True, True, 0)
        self.revert = Gtk.Button(label="Revert")
        self.revert.connect("clicked", lambda _b: self.load())
        self.apply_button = Gtk.Button(label="Apply Changes")
        self.apply_button.get_style_context().add_class("suggested-action")
        self.apply_button.connect("clicked", lambda _b: self._apply())
        actions.pack_end(self.apply_button, False, False, 0)
        actions.pack_end(self.revert, False, False, 0)
        outer.pack_start(Gtk.Separator(), False, False, 0)
        outer.pack_start(actions, False, False, 0)

        self.current = config.Settings()
        self.chosen = config.Settings()
        self.load()

    # ------------------------------------------------------------ loading

    def load(self) -> None:
        for child in self.list.get_children():
            self.list.remove(child)
        try:
            self.current = system.current_settings()
        except RuntimeError as e:
            self.list.pack_start(_label(f"Can't read the system's settings: {_esc(str(e))}"), False, False, 0)
            self.current = config.Settings()
        self.chosen = self.current
        self.hw = detect.detect()
        self.rows = catalogue.rows(self.hw, self.current)
        for row in self.rows:
            self.list.pack_start(self._section(row), False, False, 0)
        self.list.show_all()
        self._show_trial(system.trial_status())
        self._changed()

    def _section(self, row: catalogue.Row) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.pack_start(_label(f"<b>{_esc(row.title)}</b>"), False, False, 0)
        box.pack_start(_label(_esc(row.subtitle), dim=True), False, False, 0)
        if row.status:
            box.pack_start(_label(_esc(row.status)), False, False, 0)
        group = None
        for c in row.choices:
            text = c.label + ("  (recommended)" if c.recommended else "")
            radio = Gtk.RadioButton.new_with_label_from_widget(group, text)
            group = group or radio
            radio.set_active(c.selected)
            radio.set_sensitive(c.available)
            radio.connect("toggled", self._choice_toggled, row, c)
            box.pack_start(radio, False, False, 0)
            detail = c.detail if c.available else c.reason
            if c.unfree and c.available:
                detail += " Unfree."
            if detail:
                d = _label(_esc(detail), dim=True)
                d.set_margin_start(26)
                box.pack_start(d, False, False, 0)
        for e in row.extras:
            check = Gtk.CheckButton(label=e.label + ("  (recommended)" if e.recommended and not e.on else ""))
            check.set_active(e.on)
            check.connect("toggled", self._extra_toggled, e)
            box.pack_start(check, False, False, 0)
            d = _label(_esc(e.detail), dim=True)
            d.set_margin_start(26)
            box.pack_start(d, False, False, 0)
        frame = Gtk.Frame()
        inner = Gtk.Box(margin=12)
        inner.pack_start(box, True, True, 0)
        frame.add(inner)
        return frame

    # ------------------------------------------------------------ choosing

    def _choice_toggled(self, radio: Gtk.RadioButton, row: catalogue.Row, c: catalogue.Choice) -> None:
        if not radio.get_active():
            return
        from dataclasses import replace

        if row.kind == "gpu":
            self.chosen = replace(self.chosen, nvidia=c.settings.nvidia)
        else:
            self.chosen = replace(self.chosen, broadcom=c.settings.broadcom)
        self._changed()

    def _extra_toggled(self, check: Gtk.CheckButton, e: catalogue.Extra) -> None:
        from dataclasses import replace

        target = e.settings_on if check.get_active() else e.settings_off
        fields = [k for k in target.__dataclass_fields__ if getattr(e.settings_on, k) != getattr(e.settings_off, k)]
        self.chosen = replace(self.chosen, **{k: getattr(target, k) for k in fields})
        self._changed()

    def _changed(self) -> None:
        dirty = config.changed(self.current, self.chosen)
        self.apply_button.set_sensitive(dirty)
        self.revert.set_sensitive(dirty)
        if dirty:
            self.status.set_markup(_esc(system.summary(self.current, self.chosen)))
        else:
            self.status.set_markup("")

    # ------------------------------------------------------------ applying

    def _confirm_unfree(self) -> bool:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text="Use an unfree driver?",
        )
        parts = []
        if self.chosen.nvidia is not None:
            parts.append(
                f'NVIDIA\'s driver comes under <a href="{NVIDIA_LICENSE}">NVIDIA\'s licence</a>, '
                "which you accept by continuing."
            )
        if self.chosen.printers:
            parts.append(
                "The printer drivers from Canon, Samsung and HP come under their makers' "
                "licences, which you accept by continuing."
            )
        if self.chosen.broadcom:
            parts.append(
                "Broadcom's STA driver is unmaintained and has known security problems. Use it "
                "only if the open driver doesn't work with your card."
            )
        parts.append(
            "Unfree drivers need unfree software turned on for the whole system: the Software "
            "Center can then install unfree apps too."
        )
        dialog.format_secondary_markup("\n\n".join(parts))
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        accept = dialog.add_button("Accept and Continue", Gtk.ResponseType.ACCEPT)
        accept.get_style_context().add_class("suggested-action")
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.ACCEPT

    def _apply(self) -> None:
        if self.chosen.needs_unfree and not self.current.unfree and not self._confirm_unfree():
            return
        self.apply_button.set_sensitive(False)
        self.revert.set_sensitive(False)
        self.spinner.start()
        self.status.set_markup("Building the new drivers for the next start… (this takes a few minutes)")
        chosen = self.chosen

        def work() -> None:
            try:
                ok, out = system.apply(chosen)
            except RuntimeError as e:
                ok, out = False, str(e)
            GLib.idle_add(self._applied, ok, out)

        threading.Thread(target=work, daemon=True).start()

    def _applied(self, ok: bool, out: str) -> bool:
        self.spinner.stop()
        if not ok:
            last = out.strip().splitlines()[-1] if out.strip() else "unknown error"
            self.status.set_markup(f"Not applied: {_esc(last)}")
            self._changed()
            return GLib.SOURCE_REMOVE
        self.load()
        trial = system.trial_status()
        if trial.get("state") == "pending":
            self._ask_restart()
        return GLib.SOURCE_REMOVE

    def _ask_restart(self) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.NONE,
            text="Restart to use the new drivers",
        )
        dialog.format_secondary_markup(
            "The drivers are ready for the next start. After it, TulsiOS asks whether everything "
            "works: keep the new drivers then.\n\nIf the screen stays black, restart again "
            "(hold the power button if you must): the drivers before come back by themselves."
        )
        dialog.add_button("Later", Gtk.ResponseType.CANCEL)
        now = dialog.add_button("Restart Now", Gtk.ResponseType.ACCEPT)
        now.get_style_context().add_class("suggested-action")
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.ACCEPT:
            system.restart()

    # ------------------------------------------------------------ the trial

    def _show_trial(self, trial: dict) -> None:
        for button in self.bar.get_action_area().get_children():
            self.bar.get_action_area().remove(button)
        state = trial.get("state", "none")
        summary = _esc(trial.get("summary", "").removeprefix("tulsi: edit configuration.nix: "))
        if state == "pending":
            self.bar.set_message_type(Gtk.MessageType.INFO)
            self.bar_label.set_markup(f"Waiting for a restart: {summary}")
            self.bar.add_button("Undo", 2)
            self.bar.add_button("Restart Now", 1)
        elif state == "testing":
            self.bar.set_message_type(Gtk.MessageType.QUESTION)
            self.bar_label.set_markup(f"You started with new drivers: {summary}. Does everything work?")
            self.bar.add_button("Go Back", 2)
            self.bar.add_button("Keep", 3)
        elif state == "reverted":
            self.bar.set_message_type(Gtk.MessageType.WARNING)
            self.bar_label.set_markup(f"Undone: {summary}. {_esc(trial.get('notice', ''))}")
            self.bar.add_button("OK", 4)
        else:
            self.bar.hide()
            self.apply_button.set_sensitive(False)
            return
        self.bar.show_all()
        # A change on trial comes first.
        if state in ("pending", "testing"):
            for child in self.list.get_children():
                child.set_sensitive(False)

    def _bar_response(self, _bar: Gtk.InfoBar, response: int) -> None:
        if response == 1:
            system.restart()
            return
        if response == 4:
            system.trial("dismiss")
            self.load()
            return
        if response == 3:
            ok, out = system.trial("keep")
            self.status.set_markup(_esc(out.strip().splitlines()[-1] if out.strip() else ""))
            self.load()
            return
        if response == 2:
            self.spinner.start()
            self.status.set_markup("Undoing… (this takes a few minutes)")

            def work() -> None:
                ok, out = system.trial("undo")
                GLib.idle_add(self._undone, ok, out)

            threading.Thread(target=work, daemon=True).start()

    def _undone(self, ok: bool, out: str) -> bool:
        self.spinner.stop()
        self.load()
        last = out.strip().splitlines()[-1] if out.strip() else ""
        self.status.set_markup(_esc(("Undone. Restart to go back. " if ok else "Not undone: ") + last))
        return GLib.SOURCE_REMOVE
