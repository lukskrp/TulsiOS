"""The "Install the TulsiOS Way" window, step by step (ADR 0018, milestone 3).

1. What it is      what was typed, or what the download is (from `tulsi inspect`)
2. In TulsiOS      what TulsiOS has for it (tulsid's `Match`); installing one ends here
3. How to package  a recipe (no AI model) or the Assistant, and whether to remember it
4. Details         the recipe's few questions
5. Build and try   the recipe's build log; the program tried in a sandbox
6. Install         what was built, then the Software Center's confirmation

Steps that do not apply are skipped: when TulsiOS has a match, the window opens on
step 2 (step 1 stays first for downloads that need packaging); a remembered choice
skips step 3 when nothing matches; asking the Assistant ends at step 3. Enter goes
to the next step.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

from . import recipe_ui
from .adopt import (
    EXPLANATION,
    KIND_WORDS,
    Request,
    _activate,
    _software_center,
    add_file_to_store,
    assistant_prompt,
    inspect_file,
    match_hint,
)

STEPS = (
    ("about", "What it is"),
    ("match", "In TulsiOS"),
    ("how", "How to package it"),
    ("details", "Details"),
    ("build", "Build and try"),
    ("install", "Install"),
)

KIND_TITLES = {
    "deb": "Debian/Ubuntu package (.deb)",
    "rpm": "Fedora/openSUSE package (.rpm)",
    "appimage": "AppImage",
    "binary": "Program built for another Linux distribution",
    "archive": "Archive",
    "installer": "Installer script",
    "flatpakref": "Flatpak reference",
    "url": "Link",
}


def log(text: str) -> None:
    print(f"tulsi-adopt: {text}", file=sys.stderr, flush=True)


def step_bar_markup(current: str, esc) -> str:
    """The step bar: done steps dimmed, the current one bold."""
    names = [n for n, _ in STEPS]
    at = names.index(current)
    parts = []
    for i, (_name, title) in enumerate(STEPS):
        text = esc(f"{i + 1} {title}")
        if i == at:
            parts.append(f"<b>{text}</b>")
        elif i < at:
            parts.append(f"<span alpha='55%'>{text}</span>")
        else:
            parts.append(f"<span alpha='75%'>{text}</span>")
    return "  ›  ".join(parts)


class Wizard:
    def __init__(self, req: Request):
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import GLib, Gtk

        from .client import Client

        self.Gtk, self.GLib, self.esc = Gtk, GLib, GLib.markup_escape_text
        self.req = req
        self.client = Client()
        self.plan: dict | None = None
        self.matches: list | None = None
        self.lookup_error = ""
        self.outcome: dict = {}
        self.answers: dict = {}
        self.build_view = None
        self.history: list[str] = []
        self.assistant_installed, self.assistant_ready = recipe_ui.assistant_state()

        # What the download is, from its content (a .deb's own name, the programs inside).
        self.info = inspect_file(req.file) if req.file and req.kind != "binary" else {}
        if self.info.get("kind") and self.info["kind"] != "unknown":
            req.kind = self.info["kind"]
        self.hint = match_hint(req, self.info)
        self.what = (self.hint["names"] or [""])[0]

        w = Gtk.Window(title="Install the TulsiOS Way")
        w.set_default_size(620, 440)
        w.set_position(Gtk.WindowPosition.CENTER)
        w.set_border_width(16)
        w.connect("destroy", self._on_destroy)
        self.window = w
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        w.add(outer)
        self.bar = Gtk.Label(xalign=0, wrap=True)
        outer.pack_start(self.bar, False, False, 0)
        outer.pack_start(Gtk.Separator(), False, False, 0)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        outer.pack_start(self.stack, True, True, 0)

        buttons = Gtk.Box(spacing=8)
        self.cancel = Gtk.Button.new_with_mnemonic("_Cancel")
        self.cancel.connect("clicked", lambda _b: self.window.destroy())
        buttons.pack_start(self.cancel, False, False, 0)
        self.next = Gtk.Button.new_with_mnemonic("_Next")
        self.next.set_can_default(True)
        self.next.get_style_context().add_class("suggested-action")
        self.next.connect("clicked", lambda _b: self._on_next())
        buttons.pack_end(self.next, False, False, 0)
        self.back = Gtk.Button.new_with_mnemonic("_Back")
        self.back.connect("clicked", lambda _b: self._on_back())
        buttons.pack_end(self.back, False, False, 0)
        outer.pack_end(buttons, False, False, 0)

        for name, _title in STEPS:
            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            self.stack.add_named(page, name)
        self._build_about()

    # ------------------------------------------------------------------ helpers

    def page(self, name: str):
        return self.stack.get_child_by_name(name)

    def clear(self, name: str):
        page = self.page(name)
        for child in page.get_children():
            page.remove(child)
        return page

    def label(self, text: str = "", markup: str = "", dim: bool = False):
        lab = self.Gtk.Label(xalign=0, wrap=True, max_width_chars=72)
        if markup:
            lab.set_markup(markup)
        else:
            lab.set_text(text)
        if dim:
            lab.get_style_context().add_class("dim-label")
        return lab

    def heading(self, text: str):
        return self.label(markup=f"<big><b>{self.esc(text)}</b></big>")

    def go(self, name: str, remember: bool = True) -> None:
        current = self.stack.get_visible_child_name()
        if remember and current and current != name and (not self.history or self.history[-1] != current):
            self.history.append(current)
        getattr(self, f"_enter_{name}")()
        self.stack.set_visible_child_name(name)
        self.bar.set_markup(step_bar_markup(name, self.esc))
        self.back.set_visible(bool(self.history) and name not in ("build",))
        self.window.show_all()
        self.back.set_visible(bool(self.history) and name not in ("build",))
        self.next.grab_default()
        # Enter goes on; on Details, the name field has focus (and Enter there does too).
        if name != "details" and self.next.get_sensitive():
            self.next.grab_focus()
        log(f"step: {name}")

    def set_next(self, label: str | None, sensitive: bool = True) -> None:
        if label is None:
            self.next.hide()
            self.next.set_no_show_all(True)
            return
        self.next.set_no_show_all(False)
        self.next.set_label(label)
        self.next.set_use_underline(True)
        self.next.set_sensitive(sensitive)
        self.next.show()

    def _on_back(self) -> None:
        if self.history:
            self.go(self.history.pop(), remember=False)

    def _on_next(self) -> None:
        handler = getattr(self, f"_next_{self.stack.get_visible_child_name()}", None)
        if handler:
            handler()

    def _on_destroy(self, _w) -> None:
        if self.build_view:
            self.build_view.cancel()
        self.Gtk.main_quit()

    def get_plan(self) -> dict:
        if self.plan is None:
            self.plan = recipe_ui.recipe_plan(self.req.file) if self.req.file else {}
        return self.plan

    # ------------------------------------------------------------ 1 What it is

    def _build_about(self) -> None:
        req, info = self.req, self.info
        page = self.page("about")
        if req.kind == "binary":
            title = f"“{os.path.basename(req.file)}” was made for another Linux distribution"
        elif req.file:
            title = f"Install {os.path.basename(req.file)}"
        else:
            title = f"Install {', '.join(req.names) or 'software'}"
        page.pack_start(self.heading(title), False, False, 0)
        page.pack_start(self.label(EXPLANATION.format(
            tool=req.tool or KIND_WORDS.get(req.kind, "that"))), False, False, 0)
        grid = self.Gtk.Grid(column_spacing=12, row_spacing=4)
        rows = []
        if req.command:
            rows.append(("You typed", req.command))
        if req.file:
            rows.append(("Kind", KIND_TITLES.get(req.kind, "File")))
        for key, title in (("name", "Name"), ("version", "Version"),
                           ("description", "About"), ("homepage", "Website"),
                           ("license", "Licence")):
            if info.get(key):
                rows.append((title, str(info[key])))
        if info.get("programs"):
            progs = info["programs"]
            rows.append(("Programs inside", ", ".join(progs[:8]) + (" …" if len(progs) > 8 else "")))
        if req.file and os.path.isfile(req.file):
            rows.append(("Size", recipe_ui.size_text(req.file)))
        for i, (k, v) in enumerate(rows):
            grid.attach(self.label(k, dim=True), 0, i, 1, 1)
            grid.attach(self.label(v), 1, i, 1, 1)
        page.pack_start(grid, False, False, 0)

    def _enter_about(self) -> None:
        self.set_next("_Next")

    def _next_about(self) -> None:
        self.go("match")

    # ------------------------------------------------------------- 2 In TulsiOS

    def start_lookup(self) -> None:
        if self.hint["names"] or self.hint["programs"]:
            self.client.match(self.hint, 8, self._found, self._lookup_failed)
        else:
            self._found([])

    def _found(self, candidates: list) -> None:
        self.matches = candidates[:5]
        self.lookup_error = ""
        log("matches: " + ", ".join(
            (f"service {c['name']}" if c.get("kind") == "service" else c.get("attr", "?"))
            + f" ({c.get('reason', '')})" for c in self.matches))
        self._after_lookup()

    def _lookup_failed(self, error) -> None:
        log(f"Match failed: {error.message}")
        self.matches = []
        self.lookup_error = error.message
        self._after_lookup()

    def _after_lookup(self) -> None:
        current = self.stack.get_visible_child_name()
        # Nothing matched and a way to package it was remembered: go straight there.
        if not self.matches:
            choice = self.remembered_choice()
            if choice == "recipe":
                self.go("details")
                return
            if choice == "assistant":
                self.ask_assistant()
                return
        if current == "match":
            self.go("match", remember=False)
        elif self.matches and current == "about":
            # TulsiOS has it: show that straight away (Back still shows "What it is").
            # "What it is" stays first for downloads that need packaging.
            self.go("match")

    def remembered_choice(self) -> str:
        """The remembered way, if it can be used for this request."""
        default = recipe_ui.packaging_default()
        if default == "recipe" and self.get_plan().get("recipe"):
            return "recipe"
        if default == "assistant" and self.assistant_ready:
            return "assistant"
        return ""

    def _enter_match(self) -> None:
        page = self.clear("match")
        if self.matches is None:
            spinner = self.Gtk.Spinner()
            spinner.start()
            row = self.Gtk.Box(spacing=8)
            row.pack_start(spinner, False, False, 0)
            row.pack_start(self.label(f"Looking for “{self.what}” in TulsiOS…"), False, False, 0)
            page.pack_start(row, False, False, 0)
            self.set_next("_Next", sensitive=False)
            return
        can_package = bool(self.get_plan().get("recipe")) or self.assistant_installed
        if self.lookup_error:
            page.pack_start(self.label(f"Could not look in TulsiOS: {self.lookup_error}"),
                            False, False, 0)
        elif not self.matches:
            page.pack_start(self.heading(f"TulsiOS has nothing for “{self.what}” yet"),
                            False, False, 0)
            page.pack_start(self.label(
                "It can be packaged for TulsiOS: built and tried on this computer, and "
                "installed only after you say so." if can_package else
                "Nothing on this computer can package it either."), False, False, 0)
        else:
            page.pack_start(self.heading("TulsiOS has"), False, False, 0)
            for i, c in enumerate(self.matches):
                page.pack_start(self._match_row(c, i == 0), False, False, 0)
        if self.matches:
            self.set_next("None of These: _Package It", sensitive=can_package)
        else:
            self.set_next("_Next", sensitive=can_package)

    def _match_row(self, c: dict, first: bool):
        from .model import Package

        Gtk, esc = self.Gtk, self.esc
        line = Gtk.Box(spacing=8)
        why = re.sub(r"`([^`]*)`", "“\\1”", c.get("reason", ""))
        reason = f"\n<small><i>{esc(why)}</i></small>" if why else ""
        if c.get("kind") == "service":
            on = c.get("enabled")
            markup = f"<b>The {esc(c['name'])} service</b>{' (already on)' if on else ''}{reason}"
            label, action, sensitive = "_Turn On", (lambda n=c["name"]: self.finish("service", n)), not on
        else:
            p = Package.from_json(c)
            markup = (f"<b>{esc(p.title)}</b> {esc(p.version)}\n"
                      f"<small>{esc(p.description)}</small>{reason}")
            label = "Installed" if p.installed else "_Install"
            action, sensitive = (lambda a=p.attr: self.finish("install", a)), not p.installed
        line.pack_start(self.label(markup=markup), True, True, 0)
        button = Gtk.Button.new_with_mnemonic(label)
        button.set_sensitive(sensitive)
        button.set_valign(Gtk.Align.CENTER)
        button.connect("clicked", lambda _b: action())
        if first and sensitive:
            button.get_style_context().add_class("suggested-action")
        line.pack_end(button, False, False, 0)
        return line

    def finish(self, action: str, arg: str) -> None:
        """Hands the change to the Software Center (its confirmation, history and Undo)."""
        _software_center(action, arg)
        self.window.destroy()

    def _next_match(self) -> None:
        choice = self.remembered_choice() if not self.matches else ""
        if choice == "recipe":
            self.go("details")
        elif choice == "assistant":
            self.ask_assistant()
        else:
            self.go("how")

    # ------------------------------------------------------- 3 How to package it

    def _enter_how(self) -> None:
        Gtk = self.Gtk
        page = self.clear("how")
        plan = self.get_plan()
        page.pack_start(self.heading("How should TulsiOS package it?"), False, False, 0)
        self.use_recipe = Gtk.RadioButton.new_with_mnemonic(
            None, "Package it with a _recipe (no AI model needed)")
        # Alt shortcuts on this page: r(ecipe), A(ssistant), m(remember), N(ext), B(ack), C(ancel).
        self.use_assistant = Gtk.RadioButton.new_with_mnemonic_from_widget(
            self.use_recipe, "Ask the _Assistant (an AI agent)")
        recipe_note = (plan.get("title") + "." if plan.get("recipe") else
                       f"No recipe fits: {plan.get('whyNot') or 'TulsiOS cannot read this file.'}"
                       if self.req.file else "Recipes package downloaded files.")
        assistant_note = ("It can package almost anything, and asks you before installing." if
                          self.assistant_ready else
                          "It needs an AI model, and none is set up." if self.assistant_installed
                          else "The Assistant is not installed.")
        for radio, note, usable in ((self.use_recipe, recipe_note, bool(plan.get("recipe"))),
                                    (self.use_assistant, assistant_note, self.assistant_installed)):
            radio.set_sensitive(usable)
            page.pack_start(radio, False, False, 0)
            hint = self.label(note, dim=True)
            hint.set_margin_start(26)
            page.pack_start(hint, False, False, 0)
        default = recipe_ui.packaging_default()
        prefer_recipe = plan.get("recipe") and (default != "assistant" or not self.assistant_ready)
        (self.use_recipe if prefer_recipe else self.use_assistant).set_active(True)
        self.url_entry = Gtk.Entry(placeholder_text="Download page or file URL, for the Assistant (optional)")
        self.url_entry.set_text(self.req.url)
        if self.assistant_installed:
            page.pack_start(self.url_entry, False, False, 0)
        self.remember = Gtk.CheckButton.new_with_mnemonic(
            "Re_member my choice (change it in Starah's window)")
        if plan.get("recipe") and self.assistant_installed:
            page.pack_start(self.remember, False, False, 0)

        def update(*_args) -> None:
            recipe = self.use_recipe.get_active()
            self.set_next("_Next" if recipe else "As_k the Assistant",
                          sensitive=recipe or self.assistant_installed)

        self.use_recipe.connect("toggled", update)
        update()

    def _next_how(self) -> None:
        recipe = self.use_recipe.get_active()
        if self.remember.get_active():
            try:
                recipe_ui.save_packaging_default("recipe" if recipe else "assistant")
            except OSError as e:
                log(f"cannot save the choice: {e}")
        if recipe:
            self.go("details")
        else:
            self.ask_assistant()

    def ask_assistant(self) -> None:
        req = self.req
        store_path = file_hash = ""
        if req.file and req.kind != "binary" and os.path.isfile(req.file):
            try:
                store_path, file_hash = add_file_to_store(req.file)
            except (OSError, subprocess.SubprocessError) as e:
                log(f"could not add {req.file} to the store: {e}\n{getattr(e, 'stderr', '') or ''}")
                return
        url = self.url_entry.get_text().strip() if hasattr(self, "url_entry") else req.url
        prompt = assistant_prompt(req, url, store_path, file_hash)
        print(f"tulsi-adopt: asking the Assistant: {prompt}", flush=True)
        _activate("org.tulsi.Assistant", "/org/tulsi/Assistant", ["ocimum-assistant"], "ask", prompt)
        self.window.destroy()

    # ---------------------------------------------------------------- 4 Details

    def _enter_details(self) -> None:
        page = self.clear("details")
        plan = self.get_plan()
        page.pack_start(self.heading("A few details"), False, False, 0)
        # Alt shortcuts here: F(ree), P(roprietary), m(enu), K(eep), u (Build), B(ack), C(ancel).
        self.form = recipe_ui.QuestionsForm(
            plan, self.req.file, on_change=lambda: self.set_next("B_uild", self.form.valid()))
        page.pack_start(self.form.widget, False, False, 0)
        self.set_next("B_uild", self.form.valid())

    def _next_details(self) -> None:
        if not self.form.valid():
            return
        self.answers = self.form.answers()
        self.go("build")

    # ---------------------------------------------------------- 5 Build and try

    def _enter_build(self) -> None:
        page = self.clear("build")
        self.set_next("_Next", sensitive=False)
        command = recipe_ui.build_command(self.req.file, self.answers)
        self.build_view = recipe_ui.BuildView(page, command, self._built)

    def _built(self, outcome: dict) -> None:
        self.build_view = None
        self.outcome = outcome
        log(f"recipe finished: ok={outcome.get('ok')} error={outcome.get('error', '')!r}")
        self.go("install")

    # ---------------------------------------------------------------- 6 Install

    def _enter_install(self) -> None:
        Gtk, esc = self.Gtk, self.esc
        page = self.clear("install")
        o = self.outcome
        if o.get("ok"):
            page.pack_start(self.heading(f"{o['name']} {o.get('version', '')} is ready"), False, False, 0)
            lines = ["Programs: " + esc(", ".join(o.get("programs") or []))]
            tried = o.get("tried") or {}
            if tried.get("ok"):
                lines.append(f"{esc(tried.get('program', ''))} starts (tried in a sandbox).")
            for w in o.get("warnings") or []:
                lines.append(f"⚠ {esc(w)}")
            lines.append("Installing adds it to this computer's configuration, like any other "
                         "package; Undo in the Software Center removes it again.")
            page.pack_start(self.label(markup="\n".join(lines)), False, False, 0)
            show = Gtk.Expander(label="Show the package")
            code = Gtk.TextView(editable=False, monospace=True)
            code.get_buffer().set_text(o.get("expression", ""))
            scroll = Gtk.ScrolledWindow(min_content_height=180)
            scroll.add(code)
            show.add(scroll)
            page.pack_start(show, True, True, 0)
            self.set_next("_Install")
        else:
            page.pack_start(self.heading("The recipe could not finish"), False, False, 0)
            page.pack_start(self.label(o.get("error") or "The build could not be read."), False, False, 0)
            if o.get("logTail"):
                log_view = Gtk.Expander(label="Show the end of the build log")
                text = Gtk.TextView(editable=False, monospace=True)
                text.get_buffer().set_text(o["logTail"])
                scroll = Gtk.ScrolledWindow(min_content_height=160)
                scroll.add(text)
                log_view.add(scroll)
                page.pack_start(log_view, True, True, 0)
            edit = recipe_ui.edit_command(o)
            if edit:
                page.pack_start(self.label(
                    "You can also finish it yourself: the Nix Editor opens the recipe's draft "
                    "with this log, explains what you see, and builds and installs it from there.",
                    dim=True), False, False, 0)
                button = Gtk.Button.new_with_mnemonic("_Edit It Yourself")
                button.connect("clicked", lambda _b: self.edit_yourself(edit))
                row = Gtk.Box(spacing=8)
                row.pack_start(button, False, False, 0)
                page.pack_start(row, False, False, 0)
            if self.assistant_installed:
                page.pack_start(self.label(
                    "The Assistant can finish it: it gets the recipe's draft and this log."
                    + ("" if self.assistant_ready else " It needs an AI model, and none is set up."),
                    dim=True), False, False, 0)
                self.set_next("_Ask the Assistant to Finish It")
            else:
                self.set_next(None)
        self.cancel.set_label("_Close")

    def edit_yourself(self, command: list[str]) -> None:
        """Opens the draft in the Nix Editor, which builds and installs it from there.
        This window stays, so the Assistant can still be asked."""
        log("editing the draft: " + " ".join(command))
        # GLib reaps it when it exits, so no zombie stays behind while this window is open.
        self.GLib.spawn_async(command, flags=self.GLib.SpawnFlags.DEFAULT)

    def _next_install(self) -> None:
        o = self.outcome
        if o.get("ok"):
            ops = recipe_ui.local_ops(o, bool(o.get("unfree", self.answers.get("unfree"))))
            self.finish("apply-ops", json.dumps({"ops": ops, "label": f"Installing {o['name']}"}))
        else:
            prompt = recipe_ui.failure_prompt(self.req.file, self.get_plan(), o)
            print(f"tulsi-adopt: asking the Assistant: {prompt[:200]}", flush=True)
            _activate("org.tulsi.Assistant", "/org/tulsi/Assistant", ["ocimum-assistant"], "ask", prompt)
            self.window.destroy()

    # -------------------------------------------------------------------- run

    def run(self) -> int:
        self.go("about", remember=False)
        self.start_lookup()
        self.Gtk.main()
        return 0
