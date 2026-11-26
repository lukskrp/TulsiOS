"""`ocimum-assistant --explain FILE` (ADR 0037): the file manager's "Explain with
Assistant". This runs as the person: it reads the file's text here and puts it in
the question. The agent never gets the file or its path on disk, only the text
shown in the chat.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

MAX_CHARS = 40_000
MAX_BYTES = 50_000_000
PDF = {".pdf"}
OFFICE = {".odt", ".ods", ".odp", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".rtf"}


class CannotExplain(Exception):
    """Why this file can't be explained, in words for the person."""


def _is_text(data: bytes) -> bool:
    if b"\0" in data[:8192]:
        return False
    try:
        data[:8192].decode("utf-8")
    except UnicodeDecodeError as e:
        # A multi-byte character cut at the 8 KiB boundary is still text.
        return e.start >= 8188
    return True


def _run(argv: list[str], timeout: int = 60) -> str:
    try:
        done = subprocess.run(argv, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise CannotExplain(f"Could not read the file's text: {e}") from e
    if done.returncode != 0:
        raise CannotExplain("Could not read the file's text: "
                            + done.stderr.decode(errors="replace").strip()[-300:])
    return done.stdout.decode("utf-8", errors="replace")


def extract(path: Path, which=None) -> str:
    """The file's text: plain text as it is, PDFs with pdftotext, office documents
    with LibreOffice when it is installed."""
    which = which or shutil.which
    if not path.is_file():
        raise CannotExplain(f"“{path.name}” is not a file.")
    if path.stat().st_size > MAX_BYTES:
        raise CannotExplain(f"“{path.name}” is too large to explain (over 50 MB).")
    suffix = path.suffix.lower()
    if suffix in PDF:
        if not which("pdftotext"):
            raise CannotExplain("Reading PDFs needs pdftotext (poppler-utils).")
        text = _run(["pdftotext", "-l", "40", "-layout", str(path), "-"])
    elif suffix in OFFICE:
        office = which("soffice") or which("libreoffice")
        if not office:
            raise CannotExplain(
                f"Reading “{path.name}” needs LibreOffice: install it from the Software Center.")
        text = _run([office, "--headless", "--cat", str(path)], timeout=120)
    else:
        with path.open("rb") as f:
            data = f.read(MAX_CHARS * 4)
        if not _is_text(data):
            raise CannotExplain(
                f"“{path.name}” isn't text, a PDF or an office document, so the Assistant "
                "can't read it.")
        text = data.decode("utf-8", errors="replace")
    if not text.strip():
        raise CannotExplain(f"“{path.name}” has no text to explain (a scanned PDF needs OCR first).")
    return text


def _fence(text: str) -> str:
    longest = run = 0
    for ch in text:
        run = run + 1 if ch == "`" else 0
        longest = max(longest, run)
    return "`" * max(3, longest + 1)


def prompt(name: str, text: str) -> str:
    truncated = len(text) > MAX_CHARS
    text = text[:MAX_CHARS]
    fence = _fence(text)
    note = (f" (only its first {MAX_CHARS:,} characters: the rest was left out)"
            if truncated else "")
    return (
        f"Explain this file to me in plain language: what it is, what it says or does, "
        f"and anything I should watch out for. Don't change anything. The file is "
        f"“{name}”; its text follows{note}.\n\n{fence}\n{text.rstrip()}\n{fence}"
    )


def question_for(path: Path, which=None) -> str:
    return prompt(path.name, extract(path, which))
