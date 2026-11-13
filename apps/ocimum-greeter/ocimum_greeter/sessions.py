"""The X sessions the greeter offers: `.desktop` files from the system's xsessions
directory (NixOS: services.displayManager.sessionData.desktops/share/xsessions)."""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Session:
    id: str  # file name without .desktop, as in services.displayManager.defaultSession
    name: str
    exec: str
    desktop_names: tuple[str, ...]

    def environment(self) -> list[str]:
        """Variables the session is started with, as greetd's "K=V" list."""
        env = ["XDG_SESSION_TYPE=x11", f"XDG_SESSION_DESKTOP={self.id}"]
        if self.desktop_names:
            env.append("XDG_CURRENT_DESKTOP=" + ":".join(self.desktop_names))
        return env


def read_session(path: Path) -> Session | None:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str  # keys are case-sensitive
    try:
        parser.read(path, encoding="utf-8")
        entry = parser["Desktop Entry"]
    except (configparser.Error, KeyError, UnicodeDecodeError):
        return None
    if entry.get("Hidden", "false").lower() == "true" or entry.get("NoDisplay", "false").lower() == "true":
        return None
    exec_line = entry.get("Exec", "").strip()
    if not exec_line:
        return None
    names = tuple(n for n in entry.get("DesktopNames", "").split(";") if n)
    session_id = path.name[: -len(".desktop")]
    return Session(session_id, entry.get("Name", session_id), exec_line, names)


def find_sessions(directory: str | Path, default: str | None = None) -> list[Session]:
    """All valid sessions in `directory`, sorted by name, with `default` first."""
    sessions = []
    for path in sorted(Path(directory).glob("*.desktop")):
        session = read_session(path)
        if session is not None:
            sessions.append(session)
    sessions.sort(key=lambda s: (s.id != default, s.name.lower()))
    return sessions
