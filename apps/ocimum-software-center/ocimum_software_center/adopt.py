"""tulsi-adopt: when someone installs software the imperative way, show the TulsiOS way.

Started by:
- the `apt`, `dnf`, `pacman`, … commands TulsiOS provides (`tulsi-adopt shim apt install vlc`);
- opening a downloaded .deb/.rpm/.AppImage/.tar.gz/.zip/.run (`tulsi-adopt --file PATH`);
- running a program built for another distribution, which NixOS cannot start
  (`tulsi-adopt --binary PATH`, from TulsiOS's ELF-loader stub).

It explains that TulsiOS installs software declaratively, offers matching packages
from the Software Center and, when there is none, asks the Assistant to package the
software (ADR 0013).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field

EXPLANATION = (
    "TulsiOS does not install software with {tool}. Software is installed declaratively: "
    "every program is recorded in the system's configuration, so it survives updates, "
    "can be undone, and is the same every time you rebuild."
)

SHIM_COMMANDS = ("apt", "apt-get", "dnf", "yum", "pacman", "zypper", "snap", "brew")

_INSTALL = {"install", "reinstall", "in", "add"}
_SEARCH = {"search", "se", "find"}
_REMOVE = {"remove", "erase", "purge", "uninstall", "rm", "autoremove"}

# Downloaded files tulsi-adopt is the handler for, by suffix.
FILE_KINDS = (
    (".deb", "deb"),
    (".rpm", "rpm"),
    (".appimage", "appimage"),
    (".tar.gz", "archive"),
    (".tgz", "archive"),
    (".tar.xz", "archive"),
    (".tar.bz2", "archive"),
    (".tar.zst", "archive"),
    (".zip", "archive"),
    (".run", "installer"),
    (".sh", "installer"),
)


@dataclass
class Request:
    """What the person tried to do."""

    action: str  # install | search | remove | other
    names: list[str] = field(default_factory=list)
    tool: str = ""
    command: str = ""
    file: str = ""
    kind: str = ""  # deb, rpm, appimage, archive, installer, binary


def _strip_version(name: str) -> str:
    """`foo=1.2`, `foo>=1`, `foo@2` -> `foo`."""
    return re.split(r"[<>=@:]", name, maxsplit=1)[0]


def parse_shim(tool: str, args: list[str]) -> Request:
    """Understands the common forms of other distributions' install commands."""
    command = " ".join([tool, *args])
    if tool == "pacman":
        flags = next((a for a in args if a.startswith("-") and not a.startswith("--")), "")
        names = [_strip_version(a) for a in args if not a.startswith("-")]
        if flags.startswith("-S"):
            action = "search" if "s" in flags[2:] else "install"
        elif flags.startswith("-R"):
            action = "remove"
        else:
            action = "other"
        return Request(action, names, tool, command)
    words = [a for a in args if not a.startswith("-")]
    if not words:
        return Request("other", [], tool, command)
    sub, rest = words[0], words[1:]
    if sub in _INSTALL:
        action = "install"
    elif sub in _SEARCH:
        action = "search"
    elif sub in _REMOVE:
        action = "remove"
    else:
        action = "other"
    names = [_strip_version(n) for n in rest]
    files = [n for n in rest if file_kind(n)]
    req = Request(action, [n for n in names if not file_kind(n)], tool, command)
    if files:
        req.file, req.kind = files[0], file_kind(files[0])
    return req


def file_kind(path: str) -> str:
    low = path.lower()
    for suffix, kind in FILE_KINDS:
        if low.endswith(suffix):
            return kind
    return ""


def name_from_file(path: str) -> str:
    """A package name guessed from a download's file name.

    `vlc_3.0.21-1_amd64.deb` -> vlc, `frob-1.0.tar.gz` -> frob,
    `Obsidian-1.6.7.AppImage` -> obsidian, `foo-bar-linux-x86_64.tar.xz` -> foo-bar.
    """
    base = os.path.basename(path)
    low = base.lower()
    for suffix, _ in FILE_KINDS:
        if low.endswith(suffix):
            base = base[: -len(suffix)]
            break
    # Cut at the first separator followed by a digit or a platform word.
    m = re.match(r"(.+?)(?:[-_.](?:v?\d|linux|x86|amd64|x64|aarch64|arm64|setup|installer)).*$",
                 base, re.IGNORECASE)
    name = m.group(1) if m else base
    name = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()
    return name or "software"


def terminal_text(req: Request) -> str:
    tool = req.tool or "that command"
    lines = [EXPLANATION.format(tool=tool), ""]
    if req.action == "install" and req.names:
        for n in req.names:
            lines.append(f"  tulsi search {n}      # find it")
            lines.append(f"  tulsi install {n}     # install it, if it exists under that name")
        lines.append("")
        lines.append("Or open the Software Center. If TulsiOS does not have it yet, the "
                     "Assistant can package it for you.")
    elif req.action == "search" and req.names:
        lines.append(f"  tulsi search {' '.join(req.names)}")
    elif req.action == "remove" and req.names:
        lines.append(f"  tulsi remove {' '.join(req.names)}")
    else:
        lines.append("Use the Software Center, or `tulsi search` / `tulsi install`.")
    return "\n".join(lines)


def assistant_prompt(req: Request, url: str = "", store_path: str = "", file_hash: str = "") -> str:
    """The request handed to the Assistant when nothing in the Software Center fits."""
    what = req.names[0] if req.names else name_from_file(req.file or "software")
    parts = [f"Please package \"{what}\" for TulsiOS so it can be installed from the Software Center."]
    if req.command:
        parts.append(f"I tried to install it with: {req.command}")
    if req.file:
        parts.append(f"I have the file {os.path.basename(req.file)} ({req.kind}).")
    if store_path:
        parts.append(f"It is in the Nix store at {store_path} with hash {file_hash}; "
                     "use requireFile with that name and hash as the source.")
    if url:
        parts.append(f"It can be downloaded from {url}")
    return " ".join(parts)


def add_file_to_store(path: str) -> tuple[str, str]:
    """Puts a downloaded file into the Nix store; returns (store path, SRI hash)."""
    store = subprocess.run(["nix-store", "--add-fixed", "sha256", path],
                           check=True, capture_output=True, text=True, timeout=300).stdout.strip()
    sri = subprocess.run(["nix", "--extra-experimental-features", "nix-command",
                          "hash", "file", "--sri", "--type", "sha256", path],
                         check=True, capture_output=True, text=True, timeout=300).stdout.strip()
    return store, sri


# ----------------------------------------------------------------------------- GUI


def _activate(bus_name: str, path: str, launch: list[str], action: str, arg: str) -> None:
    """Activates a Gtk.Application action, starting the application if needed."""
    from gi.repository import Gio, GLib

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def running() -> bool:
        reply = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
                              "org.freedesktop.DBus", "NameHasOwner",
                              GLib.Variant("(s)", (bus_name,)), None,
                              Gio.DBusCallFlags.NONE, 2000, None)
        return reply.unpack()[0]

    if not running():
        subprocess.Popen(launch, start_new_session=True, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        for _ in range(100):
            if running():
                break
            time.sleep(0.2)
    group = Gio.DBusActionGroup.get(bus, bus_name, path)
    group.activate_action(action, GLib.Variant("s", arg))
    # activate_action only queues the call; tulsi-adopt exits right after, so send it now.
    bus.flush_sync(None)


def run_gui(req: Request) -> int:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import GLib, Gtk

    from .client import Client
    from .model import Package

    client = Client()
    window = Gtk.Window(title="Install the TulsiOS Way")
    window.set_default_size(560, -1)
    window.set_position(Gtk.WindowPosition.CENTER)
    window.set_border_width(18)
    window.connect("destroy", Gtk.main_quit)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    window.add(box)

    what = req.names[0] if req.names else (name_from_file(req.file) if req.file else "")
    heading = Gtk.Label(xalign=0)
    if req.kind == "binary":
        title = f"“{os.path.basename(req.file)}” was made for another Linux distribution"
    elif req.file:
        title = f"Install {os.path.basename(req.file)}"
    else:
        title = f"Install {', '.join(req.names) or 'software'}"
    heading.set_markup(f"<big><b>{GLib.markup_escape_text(title)}</b></big>")
    heading.set_line_wrap(True)
    box.pack_start(heading, False, False, 0)
    explain = Gtk.Label(xalign=0, label=EXPLANATION.format(tool=req.tool or {
        "binary": "programs built for other distributions",
        "deb": ".deb files", "rpm": ".rpm files", "appimage": "AppImages",
        "archive": "downloaded archives", "installer": "installer scripts"}.get(req.kind, "that")))
    explain.set_line_wrap(True)
    explain.set_max_width_chars(70)
    box.pack_start(explain, False, False, 0)

    status = Gtk.Label(xalign=0, label=f"Looking for “{what}” in the Software Center…")
    status.set_line_wrap(True)
    box.pack_start(status, False, False, 0)
    matches = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.pack_start(matches, False, False, 0)

    url_row = Gtk.Box(spacing=6)
    url_entry = Gtk.Entry(placeholder_text="Download page or file URL (optional)")
    url_entry.set_hexpand(True)
    url_row.pack_start(url_entry, True, True, 0)

    buttons = Gtk.ButtonBox(layout_style=Gtk.ButtonBoxStyle.END, spacing=8)
    cancel = Gtk.Button.new_with_mnemonic("_Cancel")
    cancel.connect("clicked", lambda _b: window.destroy())
    ask = Gtk.Button.new_with_mnemonic("Ask the Assistant to _Package It")
    buttons.add(cancel)
    buttons.add(ask)
    box.pack_end(buttons, False, False, 0)

    def install(attr: str) -> None:
        _activate("org.tulsi.SoftwareCenter", "/org/tulsi/SoftwareCenter",
                  ["ocimum-software-center"], "install", attr)
        window.destroy()

    def ask_assistant(_button) -> None:
        store_path = file_hash = ""
        if req.file and req.kind != "binary" and os.path.isfile(req.file):
            try:
                store_path, file_hash = add_file_to_store(req.file)
            except (OSError, subprocess.SubprocessError) as e:
                detail = getattr(e, "stderr", "") or ""
                print(f"tulsi-adopt: could not add {req.file} to the store: {e}\n{detail}",
                      file=sys.stderr, flush=True)
                status.set_text(f"Could not hand the file to the Assistant: {e}")
                return
        prompt = assistant_prompt(req, url_entry.get_text().strip(), store_path, file_hash)
        print(f"tulsi-adopt: asking the Assistant: {prompt}", flush=True)
        _activate("org.tulsi.Assistant", "/org/tulsi/Assistant",
                  ["ocimum-assistant"], "ask", prompt)
        window.destroy()

    ask.connect("clicked", ask_assistant)

    def found(results: list) -> None:
        packages = [Package.from_json(r) for r in results][:5]
        if not packages:
            status.set_text(f"The Software Center has nothing called “{what}”. The Assistant "
                            "can package it for TulsiOS: it writes the package, builds and "
                            "tests it, and asks you before installing.")
            box.pack_start(url_row, False, False, 0)
            box.reorder_child(url_row, 4)
            ask.get_style_context().add_class("suggested-action")
            window.show_all()
            ask.grab_focus()
            return
        status.set_text("Found in the Software Center:")
        for p in packages:
            row = Gtk.Box(spacing=8)
            label = Gtk.Label(xalign=0)
            label.set_markup(f"<b>{GLib.markup_escape_text(p.title)}</b> {GLib.markup_escape_text(p.version)}\n"
                             f"<small>{GLib.markup_escape_text(p.description)}</small>")
            label.set_line_wrap(True)
            row.pack_start(label, True, True, 0)
            button = Gtk.Button.new_with_mnemonic("_Install" if p is packages[0] else "Install")
            button.connect("clicked", lambda _b, a=p.attr: install(a))
            if p is packages[0]:
                button.get_style_context().add_class("suggested-action")
            row.pack_end(button, False, False, 0)
            matches.pack_start(row, False, False, 0)
        ask.set_label("None of These: Ask the Assistant to _Package It")
        window.show_all()

    window.show_all()
    if what:
        client.search(what, 20, lambda results: found(results),
                      lambda _e: found([]))
    else:
        found([])
    Gtk.main()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["shim"] and len(argv) >= 2:
        req = parse_shim(argv[1], argv[2:])
    else:
        parser = argparse.ArgumentParser(prog="tulsi-adopt", description=__doc__.split("\n")[0])
        parser.add_argument("--name", action="append", default=[])
        parser.add_argument("--file")
        parser.add_argument("--binary")
        # Set by the shims when they open the window: what the person typed.
        parser.add_argument("--tool", default="")
        parser.add_argument("--command", default="")
        args = parser.parse_args(argv)
        if args.binary:
            req = Request("install", [name_from_file(args.binary)], file=args.binary, kind="binary")
        elif args.file:
            req = Request("install", [], file=args.file, kind=file_kind(args.file) or "archive")
        else:
            req = Request("install", args.name)
        req.tool, req.command = args.tool, args.command
    graphical = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if argv[:1] == ["shim"]:
        print(terminal_text(req), file=sys.stderr)
        if graphical and req.action == "install" and (req.names or req.file):
            # The window opens beside the terminal; the command still fails so that
            # scripts notice.
            subprocess.Popen([shutil.which("tulsi-adopt") or sys.argv[0],
                              "--tool", req.tool, "--command", req.command,
                              *(["--file", req.file] if req.file else []),
                              *[x for n in req.names for x in ("--name", n)]],
                             start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, env=os.environ.copy())
        return 1
    if not graphical:
        print(terminal_text(req), file=sys.stderr)
        return 1
    return run_gui(req)


if __name__ == "__main__":
    sys.exit(main())
