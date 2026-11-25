"""tulsi-drivers: the Drivers app for terminals and agents (ADR 0029).

    tulsi-drivers list [--json]          devices, their drivers and the choices
    tulsi-drivers recommend [--check]    what TulsiOS recommends for this computer
    tulsi-drivers set CHOICE... [--off EXTRA...] [--accept-unfree] [--dry-run]
    tulsi-drivers status                 the drivers chosen, and a change on trial
    tulsi-drivers keep | undo            keep, or undo, a driver change after restarting

A change takes effect at the next restart. If that start fails (a black
screen), restart again: the driver before comes back by itself.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace

from . import catalogue, config, detect, system

UNFREE_NOTE = (
    "This driver is unfree. Choosing it turns on unfree software for the whole system\n"
    "(nixpkgs.config.allowUnfree = true): the Software Center can then install unfree\n"
    "apps too. NVIDIA's licence: https://www.nvidia.com/en-us/drivers/nvidia-license/"
)


def _current_or_default() -> config.Settings:
    """The chosen settings; for looking only, the defaults when tulsid can't say."""
    try:
        return system.current_settings()
    except RuntimeError as e:
        print(f"tulsi-drivers: can't read configuration.nix ({e}); showing the defaults", file=sys.stderr)
        return config.Settings()


def _rows(current: config.Settings) -> list[catalogue.Row]:
    return catalogue.rows(detect.detect(), current)


def cmd_list(args) -> int:
    current = _current_or_default()
    rows = _rows(current)
    if args.json:
        print(json.dumps({"settings": current.to_json(), "rows": [r.to_json() for r in rows]}, indent=2))
        return 0
    for row in rows:
        print(f"{row.title}  ({row.subtitle})")
        if row.status:
            print(f"  {row.status}")
        for c in row.choices:
            mark = "●" if c.selected else "○"
            tags = []
            if c.recommended:
                tags.append("recommended")
            if c.unfree:
                tags.append("unfree")
            tag = f" [{', '.join(tags)}]" if tags else ""
            line = f"  {mark} {c.id}: {c.label}{tag}"
            if not c.available:
                line += f" — not available: {c.reason}"
            print(line)
        for e in row.extras:
            mark = "[x]" if e.on else "[ ]"
            print(f"  {mark} {e.id}: {e.label}{' [recommended]' if e.recommended else ''}")
        print()
    return 0


def cmd_recommend(args) -> int:
    current = _current_or_default()
    hw = detect.detect()
    rec = catalogue.recommend(hw, current)
    attention = catalogue.needs_attention(hw, current)
    if args.check:
        return 10 if attention else 0
    if args.json:
        print(json.dumps({"settings": rec.to_json(), "change": config.changed(current, rec), "attention": attention}))
        return 0
    if not config.changed(current, rec):
        print("This computer has the recommended drivers.")
        return 0
    print(system.summary(current, rec).replace("Drivers: ", "Recommended: "))
    print("Apply with: tulsi-drivers set recommended")
    return 0


def _find(rows: list[catalogue.Row], ident: str):
    for row in rows:
        for c in row.choices:
            if c.id == ident:
                return row, c
        for e in row.extras:
            if e.id == ident:
                return row, e
    return None, None


def cmd_set(args) -> int:
    current = system.current_settings()
    hw = detect.detect()
    new = current
    if args.choices == ["recommended"]:
        new = catalogue.recommend(hw, current)
    else:
        for ident in args.choices + [f"-{x}" for x in args.off]:
            off = ident.startswith("-")
            ident = ident.lstrip("-")
            row, item = _find(catalogue.rows(hw, new), ident)
            if item is None:
                print(f"tulsi-drivers: no choice or extra called {ident!r} (see tulsi-drivers list)", file=sys.stderr)
                return 2
            if isinstance(item, catalogue.Choice):
                if off:
                    print(f"tulsi-drivers: {ident} is a choice; pick another one instead", file=sys.stderr)
                    return 2
                if not item.available:
                    print(f"tulsi-drivers: {item.label} isn't available: {item.reason}", file=sys.stderr)
                    return 1
                if row.kind == "gpu":
                    new = replace(new, nvidia=item.settings.nvidia)
                else:
                    new = replace(new, broadcom=item.settings.broadcom)
            else:
                # An extra is one setting, on or off.
                target = item.settings_off if off else item.settings_on
                fields = [
                    k
                    for k in target.__dataclass_fields__
                    if getattr(item.settings_on, k) != getattr(item.settings_off, k)
                ]
                new = replace(new, **{k: getattr(target, k) for k in fields})
    if not config.changed(current, new):
        print("Nothing to change.")
        return 0
    if new.needs_unfree and not (current.unfree or args.accept_unfree):
        print(UNFREE_NOTE, file=sys.stderr)
        print("Run again with --accept-unfree to accept.", file=sys.stderr)
        return 3
    print(system.summary(current, new))
    if args.dry_run:
        print(config.with_settings(system.read_config(), replace(new, unfree=new.unfree or current.unfree)))
        return 0
    ok, out = system.apply(new, at_restart=not args.now)
    if out:
        print(out)
    if ok and not args.now:
        print("The new drivers take effect when you restart. If the screen stays black,")
        print("restart again: the drivers before come back by themselves.")
    return 0 if ok else 1


def cmd_status(args) -> int:
    current = system.current_settings()
    trial = system.trial_status()
    if args.json:
        print(json.dumps({"settings": current.to_json(), "trial": trial}))
        return 0
    print(system.summary(config.Settings(unfree=current.unfree), current).replace("Drivers: ", "Chosen: "))
    state = trial.get("state", "none")
    if state == "pending":
        print("A driver change waits for a restart.")
    elif state == "testing":
        print("You restarted with a new driver: keep it with `tulsi-drivers keep`, or `tulsi-drivers undo`.")
    elif state == "reverted":
        print("The last driver change was undone because it wasn't kept after restarting.")
    return 0


def cmd_trial(action: str):
    def run(_args) -> int:
        ok, out = system.trial(action)
        if out:
            print(out)
        return 0 if ok else 1

    return run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tulsi-drivers", description="Drivers for this computer's hardware.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("list", help="devices, their drivers and the choices")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)
    p = sub.add_parser("recommend", help="what TulsiOS recommends")
    p.add_argument("--json", action="store_true")
    p.add_argument("--check", action="store_true", help="exit 10 if a device needs a driver")
    p.set_defaults(func=cmd_recommend)
    p = sub.add_parser("set", help="choose drivers (CHOICE ids from list, or 'recommended')")
    p.add_argument("choices", nargs="*")
    p.add_argument("--off", action="append", default=[], metavar="EXTRA", help="turn an extra off")
    p.add_argument("--accept-unfree", action="store_true", help="accept the driver's licence and unfree software")
    p.add_argument("--dry-run", action="store_true", help="show the new configuration.nix, change nothing")
    p.add_argument("--now", action="store_true", help=argparse.SUPPRESS)  # no restart (tests, extras)
    p.set_defaults(func=cmd_set)
    p = sub.add_parser("status", help="the drivers chosen, and a change on trial")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)
    sub.add_parser("keep", help="keep the driver change you restarted with").set_defaults(func=cmd_trial("keep"))
    sub.add_parser("undo", help="undo the driver change on trial").set_defaults(func=cmd_trial("undo"))
    args = parser.parse_args(argv)
    if args.command == "set" and not args.choices and not args.off:
        parser.error("set needs a CHOICE or --off EXTRA")
    try:
        return args.func(args)
    except RuntimeError as e:
        print(f"tulsi-drivers: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
