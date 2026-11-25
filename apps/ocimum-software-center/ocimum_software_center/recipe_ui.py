"""Recipes in tulsi-adopt (ADR 0018): package a download from a tested template,
without a model, when TulsiOS has nothing for it.

`tulsi recipe plan FILE` says which recipe fits and suggests answers; the person
confirms a few of them; `tulsi recipe build FILE …` builds and tries the package
(its log is shown as it runs); the Software Center installs it as a local package,
with its usual confirmation and Undo. When a recipe cannot help, or fails, the
Assistant can take over, given what the recipe learned.

Which of the two to use when nothing matches is remembered in
~/.config/tulsi/packaging.json ({"whenNoPackage": "ask" | "recipe" | "assistant"}),
which Starah's window also sets.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading

CHOICES = ("ask", "recipe", "assistant")
MAX_LOG_LINES = 2000


def packaging_file() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "tulsi", "packaging.json")


def packaging_default() -> str:
    """What to do when TulsiOS has no package: ask, recipe or assistant."""
    try:
        with open(packaging_file(), encoding="utf-8") as f:
            choice = json.load(f).get("whenNoPackage", "ask")
    except (OSError, ValueError, AttributeError):
        return "ask"
    return choice if choice in CHOICES else "ask"


def save_packaging_default(choice: str) -> None:
    if choice not in CHOICES:
        raise ValueError(choice)
    path = packaging_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data: dict = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        pass
    data["whenNoPackage"] = choice
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def keep_sources_default() -> bool:
    """Keep downloads that local packages are built from (the last choice; on at first)."""
    try:
        with open(packaging_file(), encoding="utf-8") as f:
            return bool(json.load(f).get("keepSources", True))
    except (OSError, ValueError, AttributeError):
        return True


def save_keep_sources_default(keep: bool) -> None:
    path = packaging_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data: dict = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        pass
    data["keepSources"] = bool(keep)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def size_text(path: str) -> str:
    try:
        size = os.path.getsize(path)
    except OSError:
        return ""
    for unit in ("bytes", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "bytes" else f"{size:.1f} {unit}"
        size /= 1024
    return ""


def _keyring_has_key() -> bool:
    try:
        import gi

        gi.require_version("Secret", "1")
        from gi.repository import Secret

        schema = Secret.Schema.new("org.tulsi.Assistant", Secret.SchemaFlags.NONE,
                                   {"service": Secret.SchemaAttributeType.STRING})
        return bool(Secret.password_lookup_sync(schema, {"service": "anthropic"}, None))
    except Exception:  # noqa: BLE001 - no keyring, locked, no typelib
        return False


def assistant_state() -> tuple[bool, bool]:
    """(the Assistant is installed, it has a model to work with)."""
    installed = shutil.which("ocimum-assistant") is not None
    if not installed:
        return False, False
    ready = bool(os.environ.get("OCIMUM_ASSISTANT_PROVIDER") or os.environ.get("ANTHROPIC_API_KEY")
                 or _keyring_has_key())
    return True, ready


def recipe_plan(path: str) -> dict:
    """`tulsi recipe plan PATH`; {} when it cannot be run."""
    tulsi = shutil.which("tulsi")
    if not tulsi or not path or not os.path.isfile(path):
        return {}
    try:
        out = subprocess.run([tulsi, "recipe", "plan", path], check=True, capture_output=True,
                             text=True, timeout=120).stdout
        return json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        print(f"tulsi-adopt: no recipe plan for {path}: {e}", file=sys.stderr, flush=True)
        return {}


def build_command(path: str, answers: dict) -> list[str]:
    cmd = [shutil.which("tulsi") or "tulsi", "recipe", "build", path,
           "--name", answers["name"], "--version", answers["version"] or "0"]
    if answers.get("program"):
        cmd += ["--program", answers["program"]]
    if answers.get("description"):
        cmd += ["--description", answers["description"]]
    cmd.append("--unfree" if answers.get("unfree") else "--free")
    cmd.append("--menu" if answers.get("menu") else "--no-menu")
    cmd.append("--keep-source" if answers.get("keep_source", True) else "--no-keep-source")
    return cmd


def local_ops(outcome: dict, unfree: bool) -> list[dict]:
    """The tulsid ops that install a built recipe as a local package."""
    ops = []
    if unfree:
        # A person accepts the licence of software made on this computer (ADR 0012).
        ops.append({"op": "acceptLicense", "name": outcome["name"]})
    ops.append({
        "op": "addLocalPackage",
        "name": outcome["name"],
        "expression": outcome["expression"],
        "version": outcome.get("version", ""),
        "description": outcome.get("description", ""),
        "origin": outcome.get("origin", ""),
        "keepSource": bool(outcome.get("keepSource", True)),
    })
    return ops


def edit_command(outcome: dict) -> list[str]:
    """Opens a failed recipe's draft in the Nix Editor (ADR 0019); [] without one."""
    draft = outcome.get("draft") or ""
    editor = shutil.which("ocimum-nix-editor")
    if not editor or not draft or not os.path.isfile(draft):
        return []
    return [editor, "--draft", os.path.dirname(draft)]


def failure_prompt(file: str, plan: dict, outcome: dict) -> str:
    """What the Assistant gets when a recipe failed: the draft and the build log."""
    parts = [
        f"Please package \"{outcome.get('name') or plan.get('name')}\" for TulsiOS from "
        f"{os.path.basename(file)}.",
        f"TulsiOS's recipe \"{plan.get('title', '')}\" could not finish: {outcome.get('error', '')}",
    ]
    if outcome.get("draft"):
        parts.append(f"Its draft is {outcome['draft']}:\n{outcome.get('expression', '')}")
    if outcome.get("logTail"):
        parts.append(f"The end of the build log:\n{outcome['logTail']}")
    return "\n\n".join(parts)


# ----------------------------------------------------------------------------- GUI


class QuestionsForm:
    """The few questions a recipe needs, as a page: `widget`, `valid()`, `answers()`;
    `on_change` is called whenever validity may have changed."""

    def __init__(self, plan: dict, file: str = "", on_change=None):
        from gi.repository import Gtk

        self.on_change = on_change or (lambda: None)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.widget = box
        intro = Gtk.Label(xalign=0, wrap=True, max_width_chars=70)
        intro.set_text(f"{plan.get('title', 'Recipe')}. TulsiOS builds a package from it on "
                       "this computer and tries it; nothing is installed until you say so.")
        box.pack_start(intro, False, False, 0)

        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        box.pack_start(grid, False, False, 0)

        def add(row: int, label: str, widget) -> None:
            grid.attach(Gtk.Label(label=label, xalign=1), 0, row, 1, 1)
            widget.set_hexpand(True)
            grid.attach(widget, 1, row, 1, 1)

        self.name = Gtk.Entry(text=plan.get("name", ""), activates_default=True)
        add(0, "Name", self.name)
        self.version = Gtk.Entry(text=plan.get("version", "0"), activates_default=True)
        add(1, "Version", self.version)
        self.programs = plan.get("programs") or []
        self.program = Gtk.ComboBoxText()
        for p in self.programs:
            self.program.append(p, p)
        if self.programs:
            self.program.set_active_id(plan.get("program") or self.programs[0])
            add(2, "Main program", self.program)

        licence = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.free = Gtk.RadioButton.new_with_mnemonic(None, "_Free software (open source)")
        self.unfree = Gtk.RadioButton.new_with_mnemonic_from_widget(
            self.free, "_Proprietary: I accept its licence")
        self.unknown = Gtk.RadioButton.new_from_widget(self.free)  # nothing chosen yet
        licence.pack_start(self.free, False, False, 0)
        licence.pack_start(self.unfree, False, False, 0)
        {"free": self.free, "unfree": self.unfree}.get(
            plan.get("license", ""), self.unknown).set_active(True)
        if plan.get("licenseText"):
            note = Gtk.Label(xalign=0, wrap=True)
            note.set_text(f"It says: {plan['licenseText']}")
            note.get_style_context().add_class("dim-label")
            licence.pack_start(note, False, False, 0)
        add(3, "Licence", licence)

        self.menu = Gtk.CheckButton.new_with_mnemonic("Add it to the applications _menu")
        self.menu.set_active(bool(plan.get("menu")))
        grid.attach(self.menu, 1, 4, 1, 1)
        size = size_text(file)
        self.keep = Gtk.CheckButton.new_with_mnemonic(
            "_Keep the downloaded file" + (f" ({size})" if size else "")
            + ", so this package can always be rebuilt")
        self.keep.set_tooltip_text(
            "TulsiOS cannot download this file again by itself. Kept, it stays on this "
            "computer as part of the system; otherwise a cleanup may remove it, and a later "
            "upgrade would then need the file again.")
        self.keep.set_active(keep_sources_default())
        grid.attach(self.keep, 1, 5, 1, 1)

        self.name.connect("changed", lambda _w: self.on_change())
        for w in (self.free, self.unfree):
            w.connect("toggled", lambda _w: self.on_change())

    def valid(self) -> bool:
        return bool(self.name.get_text().strip()) and not self.unknown.get_active()

    def answers(self) -> dict:
        """The answers; remembers the keep-the-download choice for next time."""
        keep = self.keep.get_active()
        if keep != keep_sources_default():
            try:
                save_keep_sources_default(keep)
            except OSError:
                pass
        return {
            "keep_source": keep,
            "name": self.name.get_text().strip(),
            "version": self.version.get_text().strip() or "0",
            "program": (self.program.get_active_id() or "") if self.programs else "",
            "unfree": self.unfree.get_active(),
            "menu": self.menu.get_active(),
        }


class BuildView:
    """Runs `tulsi recipe build` and shows its log; calls `on_done(outcome)` in the
    main loop ({} if the result could not be read)."""

    def __init__(self, box, command: list[str], on_done):
        from gi.repository import Gtk

        self.on_done = on_done
        self.spinner = Gtk.Spinner()
        self.status = Gtk.Label(xalign=0, label="Building the package…", wrap=True)
        top = Gtk.Box(spacing=8)
        top.pack_start(self.spinner, False, False, 0)
        top.pack_start(self.status, True, True, 0)
        box.pack_start(top, False, False, 0)
        self.buffer = Gtk.TextBuffer()
        view = Gtk.TextView(buffer=self.buffer, editable=False, monospace=True,
                            wrap_mode=Gtk.WrapMode.CHAR)
        self.view = view
        scroll = Gtk.ScrolledWindow(min_content_height=220)
        scroll.add(view)
        box.pack_start(scroll, True, True, 0)
        box.show_all()
        self.spinner.start()
        print("tulsi-adopt: recipe: " + " ".join(command), file=sys.stderr, flush=True)
        self.proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
        self._stdout: list[str] = []
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        self._stdout.append(self.proc.stdout.read())

    def _read_stderr(self) -> None:
        from gi.repository import GLib

        for line in self.proc.stderr:
            GLib.idle_add(self._append, line)
        self.proc.wait()
        GLib.idle_add(self._finish)

    def _append(self, line: str) -> bool:
        if line.startswith("tulsi-recipe: "):
            self.status.set_text(line.removeprefix("tulsi-recipe: ").strip().capitalize() + "…")
        end = self.buffer.get_end_iter()
        self.buffer.insert(end, line)
        if self.buffer.get_line_count() > MAX_LOG_LINES:
            start = self.buffer.get_start_iter()
            cut = self.buffer.get_iter_at_line(self.buffer.get_line_count() - MAX_LOG_LINES)
            self.buffer.delete(start, cut)
        self.view.scroll_to_iter(self.buffer.get_end_iter(), 0, False, 0, 1)
        return False

    def _finish(self) -> bool:
        # stdout is read by its own thread; wait for it briefly.
        for _ in range(50):
            if self._stdout:
                break
            threading.Event().wait(0.05)
        self.spinner.stop()
        try:
            outcome = json.loads("".join(self._stdout))
        except ValueError:
            outcome = {}
        self.on_done(outcome)
        return False

    def cancel(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
