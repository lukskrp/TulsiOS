"""Installing a theme from a git repository, as `omarchy theme install` does.

Only data is kept: colors.toml, images, and text (licence, README, credits).
Anything else in the repo (scripts, *.lua, per-app configs) is dropped, so a
theme can never run code. The source URL is kept beside it, and its licence is
shown before the theme is used.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import palette, store

TEXT_NAMES = re.compile(r"^(LICEN[CS]E|COPYING|CREDITS|AUTHORS|README)(\.(md|txt|rst))?$", re.IGNORECASE)
IMAGE = re.compile(r"\.(png|jpe?g|webp)$", re.IGNORECASE)
MAX_FILE = 25 * 1024 * 1024


class InstallError(RuntimeError):
    pass


def slug_from_url(url: str) -> str:
    name = url.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    name = re.sub(r"\.git$", "", name).lower()
    name = re.sub(r"^(omarchy|tulsi(os)?)-", "", name)
    name = re.sub(r"-theme$", "", name)
    name = re.sub(r"[^a-z0-9-]+", "-", name).strip("-")
    if not name:
        raise InstallError(f"can't name a theme after {url!r}")
    return name


def check_url(url: str) -> None:
    # Refuse git options and transport helpers ("ext::", "-u…"), as Omarchy does.
    if url.startswith("-") or "::" in url or not re.match(r"^(https://|git@[\w.-]+:)", url):
        raise InstallError("only https:// or git@host: repository URLs can be installed")


def keep(rel: Path) -> bool:
    parts = rel.parts
    if any(part.startswith(".") for part in parts):
        return False
    if len(parts) == 1:
        return rel.name == "colors.toml" or bool(TEXT_NAMES.match(rel.name)) or rel.name in ("preview.png",)
    return parts[0] == "backgrounds" and len(parts) == 2 and bool(IMAGE.search(rel.name))


def copy_data(src: Path, dest: Path) -> list[str]:
    """Copy what `keep` allows; return what was dropped."""
    dropped = []
    for f in sorted(src.rglob("*")):
        rel = f.relative_to(src)
        if rel.parts[0] == ".git" or f.is_dir():
            continue
        if f.is_symlink() or not keep(rel) or f.stat().st_size > MAX_FILE:
            dropped.append(str(rel))
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, target)  # contents only: no modes, nothing executable
    return dropped


def install(url: str, slug: str | None = None) -> tuple[store.Theme, list[str]]:
    check_url(url)
    slug = slug or slug_from_url(url)
    dest = store.user_themes_dir() / slug
    if dest.exists():
        raise InstallError(f"a theme called {slug!r} is already installed (tulsi-theme remove {slug})")
    with tempfile.TemporaryDirectory() as tmp:
        clone = Path(tmp) / "repo"
        r = subprocess.run(
            ["git", "clone", "--depth", "1", "--", url, str(clone)],
            capture_output=True,
            text=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if r.returncode != 0:
            raise InstallError(f"git clone failed: {r.stderr.strip()}")
        if not (clone / "colors.toml").is_file():
            raise InstallError("that repository has no colors.toml, so it isn't a theme")
        palette.load(clone / "colors.toml")  # refuse a broken palette before keeping anything
        staged = Path(tmp) / slug
        staged.mkdir()
        dropped = copy_data(clone, staged)
        (staged / ".source").write_text(url + "\n")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged), dest)
    return store.get(slug), dropped


def remove(slug: str) -> None:
    dest = store.user_themes_dir() / slug
    if not dest.is_dir():
        raise InstallError(f"{slug!r} is not a theme you installed (stock themes can't be removed)")
    shutil.rmtree(dest)


def licence_text(theme: store.Theme) -> str | None:
    for f in sorted(theme.path.iterdir()):
        if TEXT_NAMES.match(f.name) and f.name.upper().startswith(("LICEN", "COPYING")):
            return f.read_text(errors="replace")
    return None
