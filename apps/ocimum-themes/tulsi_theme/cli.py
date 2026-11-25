"""tulsi-theme: switch the desktop's colours and background from a palette (ADR 0021)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import apply, install, look, palette, store


def cmd_list(args) -> int:
    current, _ = store.current()
    themes = store.themes()
    if args.json:
        print(json.dumps([
            {"slug": t.slug, "name": t.name, "mode": t.palette.mode, "stock": t.stock,
             "backgrounds": len(t.backgrounds), "current": t.slug == current}
            for t in themes.values()
        ], indent=2))
        return 0
    for t in themes.values():
        mark = "*" if t.slug == current else " "
        origin = "" if t.stock else "  (yours)"
        print(f"{mark} {t.slug:<20} {t.palette.mode:<5} {len(t.backgrounds)} backgrounds{origin}")
    return 0


def cmd_current(args) -> int:
    slug, background = store.current()
    print(slug if not args.json else json.dumps({"theme": slug, "background": background}))
    return 0


def cmd_set(args) -> int:
    theme = store.get(args.theme)
    dest = apply.switch(theme, args.background)
    print(f"{theme.name} is on ({dest})")
    return 0


def cmd_undo(args) -> int:
    slug = apply.undo()
    if slug is None:
        print("nothing to undo", file=sys.stderr)
        return 1
    print("back to the desktop's own look" if slug == "default" else f"back to {store.title(slug)}")
    return 0


def cmd_install(args) -> int:
    theme, dropped = install.install(args.url, args.name)
    print(f"installed {theme.name} from {args.url}")
    if dropped:
        print("left out (only colours, images and text are kept): " + ", ".join(dropped))
    licence = install.licence_text(theme)
    print("licence:" if licence else "this repository has no licence file; check its README before sharing it.")
    if licence:
        print("  " + "\n  ".join(licence.strip().splitlines()[:12]))
    return 0


def cmd_remove(args) -> int:
    install.remove(args.theme)
    print(f"removed {args.theme}")
    return 0


def cmd_look(args) -> int:
    path = Path(args.theme)
    if path.is_dir():
        theme = store.Theme(path.name, path, stock=False, palette=palette.load(path / "colors.toml"))
    else:
        theme = store.get(args.theme)
    out = Path(args.output or f"/tmp/tulsi-theme-look-{theme.slug}.png")
    look.draw(theme, out)
    print(out)
    issues = look.problems(theme)
    for issue in issues:
        print(f"problem: {issue}")
    return 1 if issues else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tulsi-theme", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("list", help="themes you can switch to")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_list)
    s = sub.add_parser("current", help="the theme that is on")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_current)
    s = sub.add_parser("set", help="switch to a theme")
    s.add_argument("theme")
    s.add_argument("--background", type=int, default=0, help="which of its backgrounds (0 = first)")
    s.set_defaults(func=cmd_set)
    s = sub.add_parser("undo", help="go back to the theme before")
    s.set_defaults(func=cmd_undo)
    s = sub.add_parser("install", help="install a theme from a git repository (Omarchy themes work)")
    s.add_argument("url")
    s.add_argument("--name", help="slug to install it as")
    s.set_defaults(func=cmd_install)
    s = sub.add_parser("remove", help="remove a theme you installed")
    s.add_argument("theme")
    s.set_defaults(func=cmd_remove)
    s = sub.add_parser("look", help="draw a theme (slug or directory) to a PNG and list problems")
    s.add_argument("theme")
    s.add_argument("-o", "--output")
    s.set_defaults(func=cmd_look)
    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except (LookupError, palette.PaletteError, install.InstallError) as e:
        print(f"tulsi-theme: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
