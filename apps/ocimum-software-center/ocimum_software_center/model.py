"""View-model logic for the Software Center.

Deliberately free of GTK and D-Bus so it can be unit tested anywhere.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

MIN_QUERY_LENGTH = 2
MAX_RESULTS = 200
MAX_LOG_LINES = 2000


@dataclass
class Package:
    attr: str
    pname: str = ""
    version: str = ""
    description: str = ""
    unfree: bool = False
    installed: bool = False
    # Unfree agents on tulsid's allow-list: the licence to accept before installing.
    license_name: str = ""
    license_url: str = ""
    license_accepted: bool = False
    # Made on this computer (a local package), and where it came from.
    local: bool = False
    origin: str = ""

    @classmethod
    def from_json(cls, data: dict) -> "Package":
        return cls(
            attr=data["attr"],
            pname=data.get("pname") or "",
            version=data.get("version") or "",
            description=data.get("description") or "",
            unfree=bool(data.get("unfree")),
            installed=bool(data.get("installed")),
            license_name=(data.get("license") or {}).get("name", ""),
            license_url=(data.get("license") or {}).get("url", ""),
            license_accepted=bool(data.get("license_accepted")),
            local=bool(data.get("local")),
            origin=data.get("origin") or "",
        )

    @property
    def needs_license(self) -> bool:
        """An allow-listed unfree package whose licence nobody accepted yet."""
        return bool(self.license_name) and not self.license_accepted

    @property
    def title(self) -> str:
        return self.pname or self.attr

    @property
    def subtitle(self) -> str:
        """Version, plus the attribute when it differs from the name."""
        parts = []
        if self.version:
            parts.append(self.version)
        if self.attr != self.title:
            parts.append(self.attr)
        if self.unfree:
            parts.append("unfree")
        if self.local:
            parts.append("made on this computer")
        return " · ".join(parts)


def normalize_query(text: str) -> str | None:
    """Collapses whitespace; returns None when the query is too short to search."""
    query = " ".join(text.split())
    return query if len(query) >= MIN_QUERY_LENGTH else None


def ops_install(attr: str, accept_license: bool = False) -> list[dict]:
    ops = [{"op": "addPackage", "name": attr}]
    if accept_license:
        ops.insert(0, {"op": "acceptLicense", "name": attr})
    return ops


def ops_remove(attr: str) -> list[dict]:
    return [{"op": "removePackage", "name": attr}]


def ops_remove_extension(browser: str, ext_id: str) -> list[dict]:
    return [{"op": "removeExtension", "browser": browser, "id": ext_id}]


BROWSER_TITLES = {"firefox": "Firefox", "chromium": "Chromium, Chrome and Brave"}


def extensions_of(state: dict) -> list[tuple[str, str]]:
    """(browser, id) pairs from a state.json dict, Firefox first."""
    exts = state.get("browserExtensions") or {}
    return [(b, i) for b in ("firefox", "chromium") for i in sorted(exts.get(b) or [])]


_CHANGE_WORDS = {
    ("+", "licence accepted:"): "Accept the licence of",
    ("+", "package"): "Install",
    ("-", "package"): "Remove",
    ("+", "firefox extension"): "Add Firefox extension",
    ("-", "firefox extension"): "Remove Firefox extension",
    ("+", "chromium extension"): "Add Chromium extension",
    ("-", "chromium extension"): "Remove Chromium extension",
}


def describe_change(line: str) -> str:
    """Turns a tulsid plan line ("+ package vlc") into a sentence ("Install vlc")."""
    sign, _, rest = line.partition(" ")
    for (want_sign, kind), verb in _CHANGE_WORDS.items():
        if sign == want_sign and rest.startswith(kind + " "):
            return f"{verb} {rest[len(kind) + 1:]}"
    if sign in "+-" and rest.startswith("service "):
        name, _, what = rest[len("service "):].partition(" ")
        verb = {"enabled": "Enable", "disabled": "Disable"}.get(what, "Stop managing")
        return f"{verb} service {name}"
    return line


def history_title(summary: str) -> str:
    """'tulsi: undo install cowsay' -> 'Undo: install cowsay'."""
    text = summary.removeprefix("tulsi: ")
    if text.startswith("undo "):
        return "Undo: " + text[len("undo "):]
    return text[:1].upper() + text[1:]


def history_by(by: str) -> str:
    """Who made a change: 'starah-assistant' -> 'by the Assistant', 'alice' -> 'by alice'."""
    if not by:
        return ""
    if by == "starah-assistant":
        return "by the Assistant"
    if by.startswith("starah-"):
        return f"by agent {by.removeprefix('starah-')}"
    if by == "root":
        return "by the system"
    return f"by {by}"


def done_text(label: str) -> str:
    """'Installing vlc' -> 'vlc was installed.'"""
    verb, _, rest = label.partition(" ")
    past = {"Installing": "installed", "Removing": "removed"}.get(verb)
    if past and rest:
        return f"{rest} was {past}."
    if verb == "Undoing":
        return "The change was undone."
    if verb == "Upgrading":
        return "TulsiOS was upgraded. Restart the computer to finish."
    return "Done."


def upgrade_status(info: dict) -> tuple[str, str, bool]:
    """The Updates page for a CheckUpgrade reply: (title, detail, can upgrade)."""
    current = info.get("currentVersion") or "unknown"
    if not info.get("following"):
        return (
            f"TulsiOS {current}",
            "This system uses a local copy of TulsiOS, so there are no releases to "
            "upgrade to.",
            False,
        )
    if info.get("error"):
        return (
            f"TulsiOS {current}",
            "Could not check for a newer release. Check the network connection and try "
            f"again.\n({info['error']})",
            False,
        )
    if info.get("available"):
        new = info.get("availableVersion") or "a newer version"
        if new == current:
            detail = f"A newer build of TulsiOS {current} is available, with fixes."
        else:
            detail = f"TulsiOS {new} is available. You have {current}."
        return (
            f"TulsiOS {new} is available",
            detail + " Your apps, files and settings stay as they are, and you can "
            "undo the upgrade in History.",
            True,
        )
    return (f"TulsiOS {current}", "This is the newest release.", False)


def relative_time(timestamp: int, now: float | None = None) -> str:
    now = time.time() if now is None else now
    seconds = max(0, int(now - timestamp))
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    return time.strftime("%Y-%m-%d", time.localtime(timestamp))


@dataclass
class JobTracker:
    """Follows the one change this window started.

    tulsid may emit Progress/Finished for a job before the Apply reply that
    carries its id arrives, so signals are buffered while a start is pending.
    """

    job: int | None = None
    label: str = ""
    pending: bool = False
    lines: list[str] = field(default_factory=list)
    _early_lines: dict[int, list[str]] = field(default_factory=dict)
    _early_finish: dict[int, tuple[bool, str]] = field(default_factory=dict)

    @property
    def busy(self) -> bool:
        return self.pending or self.job is not None

    def begin(self, label: str) -> None:
        """A request was sent; the job id is not known yet."""
        self.pending = True
        self.label = label
        self.lines = []
        self._early_lines.clear()
        self._early_finish.clear()

    def cancel(self) -> None:
        """The request failed before a job started."""
        self.pending = False
        self.job = None

    def started(self, job: int) -> tuple[list[str], tuple[bool, str] | None]:
        """Records the job id; returns buffered lines and a buffered result."""
        self.pending = False
        self.job = job
        early = self._early_lines.pop(job, [])
        self._remember(early)
        result = self._early_finish.pop(job, None)
        if result is not None:
            self.job = None
        return early, result

    def progress(self, job: int, line: str) -> bool:
        """True if the line belongs to our job and should be shown now."""
        if self.job == job:
            self._remember([line])
            return True
        if self.pending:
            self._early_lines.setdefault(job, []).append(line)
        return False

    def finished(self, job: int, success: bool, message: str) -> bool:
        """True if our job just finished."""
        if self.job == job:
            self.job = None
            return True
        if self.pending:
            self._early_finish[job] = (success, message)
        return False

    def _remember(self, lines: list[str]) -> None:
        self.lines.extend(lines)
        del self.lines[:-MAX_LOG_LINES]
