"""tulsi-adopt: when someone installs software the imperative way, show the TulsiOS way.

Started by:
- the `apt`, `dnf`, `pacman`, … commands TulsiOS provides (`tulsi-adopt shim apt install vlc`),
  and `pip`, `npm -g`, `cargo`, `gem`, `go`, `flatpak` when they are asked to install;
- opening a downloaded .deb/.rpm/.AppImage/.tar.gz/.zip/.run/.flatpakref
  (`tulsi-adopt --file PATH`);
- running a program built for another distribution, which NixOS cannot start
  (`tulsi-adopt --binary PATH`, from TulsiOS's ELF-loader stub);
- a link to a browser extension's store page (`tulsi-adopt --url URL`).

It explains that TulsiOS installs software declaratively and finds what TulsiOS
has for it first (tulsid's `Match`: other systems' names, the programs inside a
download, ADR 0018). Only when nothing fits does it offer to have the Assistant
package the software (ADR 0013).
"""

from __future__ import annotations

import argparse
import json
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

# Other distributions' package managers: every use opens the TulsiOS way.
SHIM_COMMANDS = ("apt", "apt-get", "dnf", "yum", "pacman", "zypper", "snap", "brew")
# Language and app installers: only their install commands come here (nix/modules/adopt.nix
# passes everything else on to the real tool, when there is one).
LANGUAGE_COMMANDS = ("pip", "pip3", "pipx", "npm", "cargo", "gem", "go", "flatpak")

_INSTALL = {"install", "reinstall", "in", "add", "i"}
_SEARCH = {"search", "se", "find"}
_REMOVE = {"remove", "erase", "purge", "uninstall", "rm", "autoremove"}

# Options whose value is the next argument, so it is not a package name.
_VALUE_OPTIONS = {
    "-r", "--requirement", "-c", "--constraint", "-e", "--editable", "-i", "--index-url",
    "--extra-index-url", "-t", "--target", "--prefix", "--root", "--git", "--path",
    "--version", "--branch", "--tag", "--rev", "--features", "-F", "--registry",
    "--install-dir", "--bindir", "--arch",
}

# Downloaded files tulsi-adopt is the handler for, by suffix (when `tulsi inspect`
# cannot tell from the content).
FILE_KINDS = (
    (".deb", "deb"),
    (".rpm", "rpm"),
    (".appimage", "appimage"),
    (".flatpakref", "flatpakref"),
    (".tar.gz", "archive"),
    (".tgz", "archive"),
    (".tar.xz", "archive"),
    (".tar.bz2", "archive"),
    (".tar.zst", "archive"),
    (".zip", "archive"),
    (".run", "installer"),
    (".sh", "installer"),
)

KIND_WORDS = {
    "binary": "programs built for other distributions",
    "deb": ".deb files", "rpm": ".rpm files", "appimage": "AppImages",
    "archive": "downloaded archives", "installer": "installer scripts",
    "flatpakref": "Flatpak", "url": "download links",
}


@dataclass
class Request:
    """What the person tried to do."""

    action: str  # install | search | remove | other
    names: list[str] = field(default_factory=list)
    tool: str = ""
    command: str = ""
    file: str = ""
    kind: str = ""  # deb, rpm, appimage, archive, installer, binary, flatpakref
    url: str = ""


def _strip_version(name: str) -> str:
    """`foo=1.2`, `foo>=1`, `foo@2`, `requests[socks]` -> `foo`; keeps npm's `@scope/x`."""
    if name.startswith("@"):
        scope, _, rest = name[1:].partition("/")
        return "@" + scope + "/" + re.split(r"[<>=@:\[]", rest, maxsplit=1)[0] if rest else name
    return re.split(r"[<>=@:\[!~;]", name, maxsplit=1)[0]


def _words(args: list[str]) -> list[str]:
    """Arguments that are not options, skipping the values of options that take one."""
    words: list[str] = []
    skip = False
    for a in args:
        if skip:
            skip = False
        elif a.startswith("-"):
            skip = a in _VALUE_OPTIONS
        else:
            words.append(a)
    return words


def _go_name(path: str) -> str:
    """`github.com/x/tool/cmd/tool@latest` -> tool; `golang.org/x/tools/gopls@v0.1` -> gopls."""
    parts = [p for p in path.split("@", 1)[0].split("/") if p]
    while len(parts) > 1 and re.fullmatch(r"v\d+", parts[-1]):
        parts.pop()
    return parts[-1] if parts else path


def parse_shim(tool: str, args: list[str]) -> Request:
    """Understands the common forms of other systems' install commands."""
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
    words = _words(args)
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
    if tool == "npm" and action == "install" and not ({"-g", "--global"} & set(args)):
        action = "other"  # installing into a project, not the system
    files = [n for n in rest if file_kind(n)]
    rest = [n for n in rest if not file_kind(n)]
    if tool == "go":
        names = [_go_name(n) for n in rest]
    elif tool == "flatpak":
        # `flatpak install [remote] org.videolan.VLC`: application ids have dots.
        ids = [n for n in rest if "." in n]
        names = [i.rsplit(".", 1)[-1].lower() for i in ids]
    else:
        names = [_strip_version(n) for n in rest]
        if tool in LANGUAGE_COMMANDS:
            # Paths and URLs are not package names.
            names = [n for n in names if "://" not in n and not n.startswith((".", "/", "~"))]
    req = Request(action, [n for n in names if n], tool, command)
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


def inspect_file(path: str) -> dict:
    """`tulsi inspect PATH`: {kind, name, version, description, homepage, provides,
    programs}; {} when it cannot be run."""
    tulsi = shutil.which("tulsi")
    if not tulsi or not os.path.isfile(path):
        return {}
    try:
        out = subprocess.run([tulsi, "inspect", path], check=True, capture_output=True,
                             text=True, timeout=120).stdout
        return json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        print(f"tulsi-adopt: cannot inspect {path}: {e}", file=sys.stderr, flush=True)
        return {}


def match_hint(req: Request, info: dict | None = None) -> dict:
    """The MatchHint for tulsid's `Match`."""
    info = info or {}
    names = list(req.names)
    if not names and info.get("name"):
        names.append(info["name"])
    if not names and req.file:
        names.append(name_from_file(req.file))
    programs = list(info.get("programs") or [])
    if req.kind == "binary" and req.file:
        programs.insert(0, os.path.basename(req.file))
    return {
        "names": names,
        "programs": programs,
        "provides": list(info.get("provides") or []),
        "tool": req.tool,
    }


def lookup(hint: dict, limit: int = 5) -> list[dict] | None:
    """tulsid's `Match`, synchronously (for terminals); None if it cannot be asked."""
    try:
        from gi.repository import Gio, GLib

        session = os.environ.get("TULSI_BUS") == "session"
        bus = Gio.bus_get_sync(Gio.BusType.SESSION if session else Gio.BusType.SYSTEM, None)
        reply = bus.call_sync("org.tulsi.Manager1", "/org/tulsi/Manager1",
                              "org.tulsi.Manager1", "Match",
                              GLib.Variant("(su)", (json.dumps(hint), limit)),
                              GLib.VariantType.new("(s)"), Gio.DBusCallFlags.NO_AUTO_START,
                              5000, None)
        return json.loads(reply.unpack()[0])
    except Exception:  # noqa: BLE001 - no bus, no tulsid, no gi: just no matches
        return None


def describe_candidate(c: dict) -> tuple[str, str]:
    """(the command that installs it, why it matches)."""
    if c.get("kind") == "service":
        return f"tulsi service enable {c['name']}", c.get("reason", "")
    return f"tulsi install {c['attr']}", c.get("reason", "")


def terminal_text(req: Request, candidates: list[dict] | None = None,
                  looked_up: bool = False) -> str:
    """What a shim prints. `candidates`: tulsid's matches; `looked_up`: whether
    asking tulsid was attempted (None candidates then means it could not be asked)."""
    tool = req.tool or "that command"
    lines = [EXPLANATION.format(tool=tool), ""]
    if req.action == "install" and req.names and candidates:
        lines.append("TulsiOS has:")
        width = max(len(describe_candidate(c)[0]) for c in candidates)
        for c in candidates:
            cmd, why = describe_candidate(c)
            lines.append(f"  {cmd:<{width}}   # {why}")
        lines.append("")
        lines.append("Or open the Software Center.")
    elif req.action == "install" and req.names:
        for n in req.names:
            lines.append(f"  tulsi search {n}      # find it")
            lines.append(f"  tulsi install {n}     # install it, if it exists under that name")
        lines.append("")
        if looked_up and candidates is None:
            lines.append("(The TulsiOS system service could not be asked for matches.)")
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


def _software_center(action: str, arg: str) -> None:
    _activate("org.tulsi.SoftwareCenter", "/org/tulsi/SoftwareCenter",
              ["ocimum-software-center"], action, arg)


def run_gui(req: Request) -> int:
    """The step-by-step window (wizard.py)."""
    from .wizard import Wizard

    return Wizard(req).run()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["shim"] and len(argv) >= 2:
        req = parse_shim(argv[1], argv[2:])
    else:
        parser = argparse.ArgumentParser(prog="tulsi-adopt", description=__doc__.split("\n")[0])
        parser.add_argument("--name", action="append", default=[])
        parser.add_argument("--file")
        parser.add_argument("--binary")
        parser.add_argument("--url")
        # Set by the shims when they open the window: what the person typed.
        parser.add_argument("--tool", default="")
        parser.add_argument("--command", default="")
        args = parser.parse_args(argv)
        if args.url:
            from .links import LinkError, parse_extension_link

            try:
                parse_extension_link(args.url)
            except LinkError:
                path = args.url.split("?", 1)[0].rstrip("/")
                req = Request("install", args.name or [name_from_file(path)], url=args.url,
                              kind="url")
            else:
                # A browser extension: the Software Center adds it (with confirmation).
                _software_center("add-extension", args.url)
                return 0
        elif args.binary:
            req = Request("install", [name_from_file(args.binary)], file=args.binary, kind="binary")
        elif args.file:
            req = Request("install", [], file=args.file, kind=file_kind(args.file) or "archive")
        else:
            req = Request("install", args.name)
        req.tool, req.command = args.tool, args.command
    graphical = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if argv[:1] == ["shim"]:
        wants_window = graphical and req.action == "install" and (req.names or req.file)
        if req.action == "install" and req.names:
            print(terminal_text(req, lookup(match_hint(req)), looked_up=True), file=sys.stderr)
        else:
            print(terminal_text(req), file=sys.stderr)
        if wants_window:
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
        print(terminal_text(req, lookup(match_hint(req)), looked_up=True), file=sys.stderr)
        return 1
    return run_gui(req)


if __name__ == "__main__":
    sys.exit(main())
