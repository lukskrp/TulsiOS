"""The conversions behind the file manager's quick actions (ADR 0037), free of GTK
for tests. Each writes a new file beside the original and never overwrites one:
"photo.jpg" resized becomes "photo (resized).jpg", or "photo (resized 2).jpg" when
that exists.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class ToolError(Exception):
    pass


@dataclass
class Job:
    source: list[Path]
    output: Path
    argv: list[str]


def output_for(source: Path, ext: str, label: str = "", exists=Path.exists) -> Path:
    """SOURCE's folder and name, with LABEL in brackets and extension EXT (".jpg"),
    numbered until it is a name nobody uses."""
    stem = source.stem
    base = f"{stem} ({label})" if label else stem
    candidate = source.with_name(base + ext)
    n = 2
    while exists(candidate) or candidate == source:
        tag = f"{label} {n}" if label else str(n)
        candidate = source.with_name(f"{stem} ({tag}){ext}")
        n += 1
    return candidate


def _program(name: str, which=None) -> str:
    found = (which or shutil.which)(name)
    if not found:
        raise ToolError(f"{name} is not installed.")
    return found


def resize(source: Path, width: int | None = None, percent: int | None = None,
           which=None, exists=Path.exists) -> Job:
    """Smaller copies only: an image already narrower keeps its size."""
    if (width is None) == (percent is None):
        raise ToolError("Give a width or a percentage.")
    geometry = f"{width}x>" if width else f"{percent}%"
    if width is not None and width < 1 or percent is not None and not 1 <= percent <= 100:
        raise ToolError("The size must be positive (and at most 100%).")
    out = output_for(source, source.suffix.lower() or ".png", "resized", exists)
    return Job([source], out, [_program("magick", which), str(source), "-auto-orient",
                               "-resize", geometry, str(out)])


IMAGE_FORMATS = {"jpg": ".jpg", "png": ".png", "webp": ".webp"}


def convert_image(source: Path, fmt: str, which=None, exists=Path.exists) -> Job:
    ext = IMAGE_FORMATS.get(fmt)
    if ext is None:
        raise ToolError(f"Unknown image format {fmt!r}.")
    out = output_for(source, ext, "", exists)
    # JPEG has no transparency: flatten onto white.
    flatten = ["-background", "white", "-flatten"] if ext == ".jpg" else []
    return Job([source], out, [_program("magick", which), str(source), "-auto-orient",
                               *flatten, str(out)])


def images_to_pdf(sources: list[Path], which=None, exists=Path.exists) -> Job:
    if not sources:
        raise ToolError("No images given.")
    out = output_for(sources[0], ".pdf", "", exists)
    return Job(list(sources), out, [_program("magick", which), *map(str, sources),
                                    "-auto-orient", str(out)])


def to_mp3(source: Path, which=None, exists=Path.exists) -> Job:
    out = output_for(source, ".mp3", "", exists)
    return Job([source], out, [_program("ffmpeg", which), "-hide_banner", "-nostdin", "-n",
                               "-i", str(source), "-vn", "-codec:a", "libmp3lame",
                               "-q:a", "2", str(out)])


def document_to_pdf(source: Path, which=None, exists=Path.exists) -> Job:
    which = which or shutil.which
    office = which("soffice") or which("libreoffice")
    if not office:
        raise ToolError("Converting documents needs LibreOffice: install it from the "
                        "Software Center.")
    out = output_for(source, ".pdf", "", exists)
    # LibreOffice names its output itself (NAME.pdf) in --outdir: convert into a
    # private folder, then move it to the free name.
    return Job([source], out, [office, "--headless", "--convert-to", "pdf",
                               "--outdir", "{tmpdir}", str(source)])


def run(job: Job) -> Path:
    """Runs JOB and returns the new file. Nothing is left behind on failure."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="tulsi-file-tools-") as tmp:
        argv = [a.replace("{tmpdir}", tmp) for a in job.argv]
        done = subprocess.run(argv, capture_output=True, text=True)
        if "{tmpdir}" in job.argv:
            made = Path(tmp) / (job.source[0].stem + ".pdf")
            if done.returncode == 0 and made.exists() and not job.output.exists():
                shutil.move(str(made), job.output)
        if done.returncode != 0 or not job.output.exists():
            if job.output.exists() and done.returncode != 0:
                job.output.unlink()
            detail = (done.stderr or done.stdout).strip().splitlines()
            raise ToolError(detail[-1] if detail else "the conversion failed")
    return job.output
