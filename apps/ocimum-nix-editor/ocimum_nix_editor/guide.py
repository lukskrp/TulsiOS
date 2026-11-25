"""The Nix guide beside the editor (ADR 0019): short entries written for TulsiOS.

Entries live in `guide/*.md`. Each starts with a `# Title` line, then header lines:

    id: let-in                       (stable name links use; required)
    keys: let, in                    (words in code that show this entry)
    see: with, rec                   (related entries, by id)

then Markdown: paragraphs, `## Heading`, `- ` bullets, `code`, **bold**, links to
other entries as [[id]] or [[id|text]], and fenced blocks. The first ```nix block
is the entry's example ("Insert Example"); a ```nix snippet block is also offered
by completion when one of the entry's keys is typed.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

GUIDE_DIR = os.path.join(os.path.dirname(__file__), "guide")
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_'\-]*(?:\.[A-Za-z_][A-Za-z0-9_'\-]*)*")


@dataclass
class Entry:
    id: str
    title: str
    keys: list[str] = field(default_factory=list)
    see: list[str] = field(default_factory=list)
    body: str = ""
    example: str = ""
    snippet: str = ""
    topic: str = ""


def parse(text: str, topic: str = "") -> list[Entry]:
    entries: list[Entry] = []
    current: Entry | None = None
    lines: list[str] = []
    in_header = False
    in_fence = False

    def close() -> None:
        if current is None:
            return
        current.body = "\n".join(lines).strip("\n")
        for info, code in fences(current.body):
            if info == "nix snippet" and not current.snippet:
                current.snippet = code
            if info.startswith("nix") and not current.example:
                current.example = code
        entries.append(current)

    for line in text.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("# ") and not line.startswith("```"):
            close()
            current = Entry(id="", title=line[2:].strip(), topic=topic)
            lines = []
            in_header = True
            continue
        if current is None:
            continue
        if in_header:
            m = re.match(r"^(id|keys|see):\s*(.*)$", line)
            if m:
                name, value = m.groups()
                if name == "id":
                    current.id = value.strip()
                else:
                    setattr(current, name, [v.strip().strip('"') for v in value.split(",") if v.strip()])
                continue
            in_header = False
            if not line.strip():
                continue
        lines.append(line)
    close()
    for e in entries:
        if not e.id:
            raise ValueError(f"guide entry {e.title!r} has no id")
    return entries


def fences(body: str) -> list[tuple[str, str]]:
    """[(info, code)] for each fenced block."""
    out = []
    info = None
    code: list[str] = []
    for line in body.splitlines():
        if line.startswith("```"):
            if info is None:
                info = line[3:].strip()
                code = []
            else:
                out.append((info, "\n".join(code)))
                info = None
        elif info is not None:
            code.append(line)
    return out


class Guide:
    def __init__(self, entries: list[Entry]):
        self.entries = entries
        self.by_id = {e.id: e for e in entries}
        if len(self.by_id) != len(entries):
            raise ValueError("two guide entries share an id")
        self.by_key: dict[str, Entry] = {}
        for e in entries:
            for k in e.keys:
                self.by_key.setdefault(k, e)

    @classmethod
    def load(cls, directory: str = GUIDE_DIR) -> "Guide":
        entries: list[Entry] = []
        for name in sorted(os.listdir(directory)):
            if name.endswith(".md"):
                with open(os.path.join(directory, name), encoding="utf-8") as f:
                    entries += parse(f.read(), topic=name[:-3].split("-", 1)[-1])
        return cls(entries)

    def lookup(self, word: str, prefixes: bool = True) -> Entry | None:
        """The entry for a word in code: the whole dotted name (`stdenv.mkDerivation`),
        then shorter endings (`mkDerivation`), then (with `prefixes`) shorter
        beginnings (`lib.licenses` for `lib.licenses.mit`, `pkgs` for `pkgs.zlib`)."""
        if not word:
            return None
        if word in self.by_key:
            return self.by_key[word]
        parts = word.split(".")
        for i in range(1, len(parts)):
            suffix = ".".join(parts[i:])
            if suffix in self.by_key:
                return self.by_key[suffix]
        if prefixes:
            for i in range(len(parts) - 1, 0, -1):
                prefix = ".".join(parts[:i])
                if prefix in self.by_key:
                    return self.by_key[prefix]
        return None

    def search(self, text: str, limit: int = 50) -> list[Entry]:
        """Entries matching `text`: title and keys first, then the text."""
        t = text.strip().lower()
        if not t:
            return list(self.entries)
        scored = []
        for i, e in enumerate(self.entries):
            if any(k.lower() == t for k in e.keys) or e.title.lower() == t:
                score = 0
            elif t in e.title.lower() or any(t in k.lower() for k in e.keys):
                score = 1
            elif t in e.body.lower():
                score = 2
            else:
                continue
            scored.append((score, i, e))
        return [e for _s, _i, e in sorted(scored)][:limit]

    def snippets(self, prefix: str) -> list[tuple[str, Entry]]:
        """[(key, entry)] whose snippet completion offers for a typed prefix."""
        if len(prefix) < 2:
            return []
        return [(k, e) for e in self.entries if e.snippet for k in e.keys
                if k.startswith(prefix) and k != prefix]

    def broken_links(self) -> list[str]:
        bad = []
        for e in self.entries:
            for target in e.see + [link for link, _t in links(e.body)]:
                if target not in self.by_id:
                    bad.append(f"{e.id} → {target}")
        return bad


def word_at(line: str, column: int) -> str:
    """The (dotted) name around `column` in `line`, or ''."""
    for m in WORD.finditer(line):
        if m.start() <= column <= m.end():
            return m.group(0).rstrip(".")
    return ""


# ------------------------------------------------------------------ rendering

LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
INLINE = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*|\[\[[^\]]+\]\])")


def links(body: str) -> list[tuple[str, str]]:
    return [(m.group(1).strip(), (m.group(2) or m.group(1)).strip()) for m in LINK.finditer(body)]


def inline(text: str, base: tuple[str, ...] = ()) -> list[tuple[str, tuple[str, ...], str]]:
    out = []
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            out.append((part[1:-1], base + ("code",), ""))
        elif part.startswith("**") and part.endswith("**") and len(part) > 3:
            out.append((part[2:-2], base + ("bold",), ""))
        elif LINK.fullmatch(part):
            m = LINK.fullmatch(part)
            out.append(((m.group(2) or m.group(1)).strip(), base + ("link",), m.group(1).strip()))
        else:
            out.append((part, base, ""))
    return out


def spans(entry: Entry, titles: dict[str, str] | None = None) -> list[tuple[str, tuple[str, ...], str]]:
    """The entry as (text, tags, link target) runs, for a Gtk.TextBuffer; `titles`
    names the entries "See also" links to."""
    titles = titles or {}
    out: list[tuple[str, tuple[str, ...], str]] = [(entry.title + "\n", ("title",), "")]
    paragraph: list[str] = []
    fence: list[str] | None = None

    def flush() -> None:
        if paragraph:
            out.extend(inline(" ".join(paragraph)))
            out.append(("\n\n", (), ""))
            paragraph.clear()

    for line in entry.body.splitlines():
        if line.startswith("```"):
            if fence is None:
                flush()
                fence = []
            else:
                out.append(("\n".join(fence) + "\n", ("codeblock",), ""))
                out.append(("\n", (), ""))
                fence = None
            continue
        if fence is not None:
            fence.append(line)
        elif line.startswith("## "):
            flush()
            out.append((line[3:].strip() + "\n", ("heading",), ""))
        elif line.startswith("- "):
            flush()
            out.append(("• ", ("bullet",), ""))
            out.extend(inline(line[2:].strip(), ("bullet",)))
            out.append(("\n", (), ""))
        elif not line.strip():
            flush()
            if out and out[-1][0] == "\n" and out[-1][1] == ():
                out[-1] = ("\n\n", (), "")
        else:
            paragraph.append(line.strip())
    flush()
    if entry.see:
        out.append(("See also: ", ("dim",), ""))
        for i, target in enumerate(entry.see):
            if i:
                out.append((", ", ("dim",), ""))
            out.append((titles.get(target, target), ("link",), target))
        out.append(("\n", (), ""))
    return out
