"""A Recipe's draft, edited by a person (ADR 0019).

A draft is a folder (`~/.local/share/tulsi/recipes/NAME/`) with the Recipe's
`package.nix` and `recipe.json` (its name, version, licence…). The editor builds it
with `tulsi recipe build-draft DIR`, turns the result into Software Center ops with
`tulsi recipe ops RESULT.json`, and hands those to the Software Center's `apply-ops`
action, so installing has the usual confirmation, history and Undo.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time


def tulsi() -> str:
    return shutil.which("tulsi") or "tulsi"


def recipes_dir() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "tulsi", "recipes")


def draft_info(directory: str) -> dict:
    try:
        with open(os.path.join(directory, "recipe.json"), encoding="utf-8") as f:
            info = json.load(f)
        return info if isinstance(info, dict) else {}
    except (OSError, ValueError):
        return {}


def is_draft(directory: str) -> bool:
    return os.path.isfile(os.path.join(directory, "package.nix")) and bool(draft_info(directory))


def draft_of(path: str) -> str:
    """The draft folder a package.nix belongs to, or ''."""
    directory = os.path.dirname(os.path.abspath(path))
    if os.path.basename(path) == "package.nix" and is_draft(directory):
        return directory
    return ""


def build_command(directory: str) -> list[str]:
    return [tulsi(), "recipe", "build-draft", directory]


def check_command(path: str) -> list[str]:
    return [tulsi(), "recipe", "check", path]


def ops_for(outcome: dict) -> list[dict]:
    """The ops installing a successful build (via `tulsi recipe ops`)."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(outcome, f)
        path = f.name
    try:
        out = subprocess.run([tulsi(), "recipe", "ops", path], check=True, capture_output=True,
                             text=True, timeout=60).stdout
        return json.loads(out)
    finally:
        os.unlink(path)


def apply_ops_argument(outcome: dict, ops: list[dict]) -> str:
    return json.dumps({"ops": ops, "label": f"Installing {outcome.get('name', '')}"})


TOKEN = re.compile(r"`([^`]+)`")


def locate(problem: str, text: str) -> tuple[int, int, int] | None:
    """Where in `text` a `tulsi recipe check` problem is: (line, column, length), all
    from 0, for the first occurrence of the code it quotes; None if it quotes none
    (the "must be a function" and size problems)."""
    m = TOKEN.search(problem)
    if not m or problem.startswith("the expression must be"):
        return None
    token = m.group(1)
    at = text.find(token)
    if at < 0:
        return None
    line = text.count("\n", 0, at)
    column = at - (text.rfind("\n", 0, at) + 1)
    return line, column, len(token)


def software_center(action: str, arg: str) -> None:
    """Activates a Software Center action, starting it if needed."""
    from gi.repository import Gio, GLib

    name, path = "org.tulsi.SoftwareCenter", "/org/tulsi/SoftwareCenter"
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def running() -> bool:
        reply = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                              "NameHasOwner", GLib.Variant("(s)", (name,)), None,
                              Gio.DBusCallFlags.NONE, 2000, None)
        return reply.unpack()[0]

    if not running():
        subprocess.Popen(["ocimum-software-center"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if running():
                break
            time.sleep(0.2)
    Gio.DBusActionGroup.get(bus, name, path).activate_action(action, GLib.Variant("s", arg))
    bus.flush_sync(None)
