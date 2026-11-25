"""Mint-Y, recoloured from a palette: the GTK 3 and Cinnamon themes of Ocimum.

This is how Linux Mint makes Mint-Y's colour variants (mint-themes'
generate-themes.py): copy the SASS sources, change the colours, and compile
with libsass. Mint swaps one accent hex; a palette sets every colour, so the
light/dark block of each _colors.scss is replaced by the palette's values for
its mode, and Mint's derived colours (lighten/mix/transparentize) follow.
The accent-coloured PNG assets (checkboxes, radios, switches) are rendered
again from assets.svg with the palette's accent, at Mint's own sizes.

Paths come from the package: $TULSI_THEME_MINT_SRC is the mint-themes source
tree, $TULSI_THEME_MINT_THEMES its built share/themes.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

from .palette import Palette, mix, readable_on

MINT_ACCENT = "#35a854"  # Mint-Y's green, as mint-themes' constants.py names it


class MintError(RuntimeError):
    pass


def mint_src() -> Path:
    p = Path(os.environ.get("TULSI_THEME_MINT_SRC", "")) / "src" / "Mint-Y"
    if not p.is_dir():
        raise MintError("Mint-Y's sources are missing (TULSI_THEME_MINT_SRC)")
    return p


def mint_built(dark: bool) -> Path:
    p = Path(os.environ.get("TULSI_THEME_MINT_THEMES", "")) / ("Mint-Y-Dark" if dark else "Mint-Y")
    if not p.is_dir():
        raise MintError("Mint-Y is missing (TULSI_THEME_MINT_THEMES)")
    return p


# --- the palette, as Mint-Y's SASS variables --------------------------------

def gtk_colours(p: Palette) -> dict[str, str]:
    """Values for gtk-3.0/sass/_colors.scss."""
    v = {
        "header_bg": p["dark_background"],
        "bg_color": p["background"],
        "text_color": p["foreground"],
        "fg_color": p["foreground"],
        "wm_title_unfocused": p["dark_foreground"],
        "accent_color": p["accent"],
        "selected_fg_color": readable_on(p["accent"]),
        "link_color": p["blue"],
        "link_visited_color": p["magenta"],
        "warning_color": p["orange"],
        "error_color": p["red"],
        "success_color": p["green"],
        "destructive_color": p["red"],
        "suggested_color": p["green"],
        "question_color": p["cyan"],
        "panel_bg": p["darker_background"],
        "panel_fg": p["foreground"],
        "xfce_panel_bg": p["background"],
        "terminal_bg": p["background"],
        "osd_bg_color": p["darker_background"],
    }
    if p.dark:
        v.update(base_color=p["lighter_background"], header_highlight=p["lighter_background"])
    else:
        # A light palette's tones all darken from `background`; views and
        # entries are lighter than it in Mint-Y, so mix it toward white.
        v.update(
            base_color=mix(p["background"], "#ffffff", 0.4),
            header_highlight=p["background"],
            header_border=p["darker_background"],
            separator_color=p["darker_background"],
        )
    return v


def cinnamon_colours(p: Palette) -> dict[str, str]:
    """Values for cinnamon/sass/_colors.scss (the panel, menus, OSDs)."""
    return {
        "accent_color": p["accent"],
        "bg_color": p["dark_background"],
        "text_color": p["foreground"],
        "fg_color": p["foreground"],
        "panel_fg": p["foreground"],
        "selected_fg_color": readable_on(p["accent"]),
        "warning_color": p["orange"],
        "error_color": p["red"],
        "destructive_color": p["red"],
        "osd_bg_color": p["darker_background"],
        "osd_fg_color": p["foreground"],
    }


# --- rewriting _colors.scss -------------------------------------------------

def _matching_brace(text: str, open_at: int) -> int:
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    raise MintError("unbalanced braces in _colors.scss")


def keep_variant(text: str, dark: bool) -> str:
    """Replace the first `@if $variant == 'light' {…} @else {…}` with one branch."""
    m = re.search(r"@if \$variant == 'light' \{", text)
    if not m:
        raise MintError("_colors.scss has no light/dark block")
    light_open = m.end() - 1
    light_close = _matching_brace(text, light_open)
    e = re.compile(r"\s*@else\s*\{").match(text, light_close + 1)
    if not e:
        raise MintError("_colors.scss's light block has no @else")
    dark_open = e.end() - 1
    dark_close = _matching_brace(text, dark_open)
    body = text[dark_open + 1 : dark_close] if dark else text[light_open + 1 : light_close]
    return text[: m.start()] + body + text[dark_close + 1 :]


def set_vars(text: str, values: dict[str, str]) -> str:
    """Set each `$name: …;` assignment to the palette's value."""
    for name, value in values.items():
        pattern = re.compile(r"^(\s*)\$" + re.escape(name) + r":[^;\n]*;", re.MULTILINE)
        text, n = pattern.subn(lambda m: f"{m.group(1)}${name}: {value};", text)
        if n == 0:
            raise MintError(f"_colors.scss has no ${name}")
    return text


def recolour_scss(colors_scss: Path, dark: bool, values: dict[str, str]) -> None:
    text = colors_scss.read_text()
    colors_scss.write_text(set_vars(keep_variant(text, dark), values))


def _compile(scss: Path, css: Path) -> None:
    import sass  # libsass, as Mint builds with (pysassc)

    css.write_text(sass.compile(filename=str(scss), output_style="expanded"))


# --- assets ------------------------------------------------------------------

def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def render_assets(src_gtk3: Path, built_assets: Path, accent: str, out: Path) -> None:
    """Mint's assets.svg with the accent swapped, rendered at Mint's PNG sizes."""
    svg = re.sub(MINT_ACCENT, accent, (src_gtk3 / "assets.svg").read_text(), flags=re.IGNORECASE)
    out.mkdir(parents=True, exist_ok=True)
    rsvg = os.environ.get("TULSI_THEME_RSVG", "rsvg-convert")
    with tempfile.TemporaryDirectory() as tmp:
        svg_path = Path(tmp) / "assets.svg"
        svg_path.write_text(svg)
        for asset in (src_gtk3 / "assets.txt").read_text().split():
            for suffix in ("", "@2"):
                ref = built_assets / f"{asset}{suffix}.png"
                if not ref.exists():
                    continue
                w, h = png_size(ref)
                subprocess.run(
                    [rsvg, "-i", asset, "-w", str(w), "-h", str(h), "-o", str(out / ref.name), str(svg_path)],
                    check=True,
                    capture_output=True,
                )
    # Anything Mint ships that assets.svg doesn't draw, as it is.
    for ref in built_assets.iterdir():
        if not (out / ref.name).exists():
            shutil.copyfile(ref, out / ref.name)


def recolour_svgs(directory: Path, accent: str) -> None:
    for f in directory.rglob("*.svg"):
        text = f.read_text(errors="surrogateescape")
        new = re.sub(MINT_ACCENT, accent, text, flags=re.IGNORECASE)
        if new != text:
            f.write_text(new, errors="surrogateescape")


def copy_tree(src: Path, dest: Path) -> None:
    """copytree, made writable: Mint's files come read-only from the Nix store."""
    shutil.copytree(src, dest, copy_function=shutil.copyfile)
    for d, _dirs, files in os.walk(dest):
        os.chmod(d, 0o755)
        for f in files:
            os.chmod(os.path.join(d, f), 0o644)


# --- the whole theme ---------------------------------------------------------

def fingerprint(p: Palette) -> str:
    data = p.mode + "".join(f"{k}={v}" for k, v in sorted(p.colours.items()))
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def _assets_cache(accent: str, dark: bool) -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "tulsi-theme" / "assets" / f"{accent.lstrip('#')}-{'dark' if dark else 'light'}"


def generate(p: Palette, name: str, dest_dir: Path) -> Path:
    """Write the GTK 3 + Cinnamon theme `name` for palette `p` into dest_dir.

    Nothing is done when that theme already holds this palette.
    """
    dest = dest_dir / name
    stamp = fingerprint(p)
    if (dest / ".tulsi-palette").is_file() and (dest / ".tulsi-palette").read_text().strip() == stamp:
        return dest

    src, built = mint_src(), mint_built(p.dark)
    dest_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f".{name}-", dir=dest_dir))
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)

            # GTK 3
            sass_dir = tmp / "gtk-3.0" / "sass"
            copy_tree(src / "gtk-3.0" / "sass", sass_dir)
            recolour_scss(sass_dir / "_colors.scss", p.dark, gtk_colours(p))
            gtk3 = work / "gtk-3.0"
            gtk3.mkdir(parents=True)
            # A dark theme's gtk.css is the dark build, as Mint-Y-Dark's is.
            _compile(sass_dir / ("gtk-dark.scss" if p.dark else "gtk.scss"), gtk3 / "gtk.css")
            _compile(sass_dir / "gtk-dark.scss", gtk3 / "gtk-dark.css")

            cache = _assets_cache(p["accent"], p.dark)
            if not cache.is_dir():
                render_assets(src / "gtk-3.0", built / "gtk-3.0" / "assets", p["accent"], cache)
            copy_tree(cache, gtk3 / "assets")

            # Cinnamon
            cin_sass = tmp / "cinnamon" / "sass"
            copy_tree(src / "cinnamon" / "sass", cin_sass)
            recolour_scss(cin_sass / "_colors.scss", p.dark, cinnamon_colours(p))
            cinnamon = work / "cinnamon"
            copy_tree(built / "cinnamon", cinnamon)
            for stale in cinnamon.glob("*.css"):
                stale.unlink()
            recolour_svgs(cinnamon, p["accent"])
            entry = cin_sass / ("cinnamon-dark.scss" if p.dark else "cinnamon.scss")
            _compile(entry, cinnamon / "cinnamon.css")

        (work / "index.theme").write_text(
            "[Desktop Entry]\nType=X-GNOME-Metatheme\n"
            f"Name={name}\nComment=TulsiOS theme generated from a palette (tulsi-theme)\n\n"
            f"[X-GNOME-Metatheme]\nGtkTheme={name}\nMetacityTheme=Mint-Y\n"
        )
        (work / ".tulsi-palette").write_text(stamp + "\n")

        old = None
        if dest.exists():
            old = dest.with_name(f".{name}-old")
            shutil.rmtree(old, ignore_errors=True)
            dest.rename(old)
        work.rename(dest)
        if old:
            shutil.rmtree(old, ignore_errors=True)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    return dest
