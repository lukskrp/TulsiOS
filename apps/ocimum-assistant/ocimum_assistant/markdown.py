"""A small Markdown subset -> Pango markup, for chat bubbles.

Handles what the assistant is asked to use: paragraphs, **bold**, *italic*,
`inline code`, fenced code blocks, headings and bullet/numbered lists.
Everything else is shown as plain (escaped) text.
"""

from __future__ import annotations

import re
from xml.sax.saxutils import escape

_INLINE = [
    (re.compile(r"\*\*([^*]+)\*\*"), r"<b>\1</b>"),
    (re.compile(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])"), r"<i>\1</i>"),
]


def _inline(text: str) -> str:
    # Escape first, then split on code spans so ** inside code stays literal.
    out = []
    for i, part in enumerate(re.split(r"(`[^`]+`)", escape(text))):
        if i % 2 == 1:
            out.append(f"<tt>{part[1:-1]}</tt>")
        else:
            for pattern, repl in _INLINE:
                part = pattern.sub(repl, part)
            out.append(part)
    return "".join(out)


def to_pango(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").strip("\n").split("\n")
    out: list[str] = []
    in_code = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            out.append(f"<tt>{escape(line)}</tt>")
            continue
        heading = re.match(r"^#{1,6}\s+(.*)$", line)
        bullet = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
        numbered = re.match(r"^(\s*)(\d+)[.)]\s+(.*)$", line)
        if heading:
            out.append(f"<b>{_inline(heading.group(1))}</b>")
        elif bullet:
            out.append(f"{bullet.group(1)}• {_inline(bullet.group(2))}")
        elif numbered:
            out.append(f"{numbered.group(1)}{numbered.group(2)}. {_inline(numbered.group(3))}")
        else:
            out.append(_inline(line))
    return "\n".join(out)
