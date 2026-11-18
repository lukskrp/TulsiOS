"""tulsi-install-system: writes the TulsiOS system flake into <root>/etc/nixos and
runs nixos-install. The disks must already be partitioned and mounted at <root>.

  tulsi-install-system --root /mnt --desktop dwm --hostname box --user alice
  tulsi-install-system --root /mnt --calamares globalstorage.json --progress-json

The paths of the TulsiOS source, the flake template and the initial state are
built in (TULSI_SOURCE, TULSI_FLAKE_TEMPLATE, TULSI_INITIAL_STATE).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from . import render
from .calamares import choices_from_globalstorage
from .render import Choices, InvalidChoice, User

KBD_MODEL_MAP = "/run/current-system/sw/share/systemd/kbd-model-map"


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="tulsi-install-system", description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True, help="mounted root of the new system, e.g. /mnt")
    p.add_argument("--calamares", metavar="JSON", help="Calamares' global storage, dumped as JSON")
    p.add_argument("--desktop", choices=render.DESKTOPS, default="ocimum")
    p.add_argument("--hostname", default="tulsios")
    p.add_argument("--user", action="append", default=[], metavar="NAME", help="a user (repeatable)")
    p.add_argument("--full-name", default="", help="full name of the first user")
    p.add_argument("--hashed-password", help="crypt(3) hash for the first user's password")
    p.add_argument("--boot", choices=render.BOOT_KINDS, default="uefi")
    p.add_argument("--bios-device", help="disk for GRUB, with --boot bios")
    p.add_argument("--timezone")
    p.add_argument("--locale")
    p.add_argument("--keyboard-layout")
    p.add_argument("--keyboard-variant")
    p.add_argument("--console-keymap")
    p.add_argument("--autologin", metavar="USER")
    p.add_argument("--write-only", action="store_true", help="write /etc/nixos, do not run nixos-install")
    p.add_argument(
        "--keep-hardware-config",
        action="store_true",
        help="keep an existing hardware-configuration.nix (e.g. one you edited after --write-only)",
    )
    p.add_argument("--progress-json", action="store_true", help="nix's internal-json log on stdout")
    p.add_argument("--source", default=os.environ.get("TULSI_SOURCE"))
    p.add_argument("--template", default=os.environ.get("TULSI_FLAKE_TEMPLATE"))
    p.add_argument("--initial-state", default=os.environ.get("TULSI_INITIAL_STATE"))
    p.add_argument("--state-version", default=os.environ.get("TULSI_STATE_VERSION"))
    return p.parse_args(argv)


def choices_from_args(a: argparse.Namespace) -> Choices:
    if a.calamares:
        gs = json.loads(Path(a.calamares).read_text())
        try:
            kbd = Path(KBD_MODEL_MAP).read_text()
        except OSError:
            kbd = ""
        return choices_from_globalstorage(gs, kbd, a.state_version)
    users = [User(name) for name in a.user]
    if users:
        users[0].full_name = a.full_name
        users[0].hashed_password = a.hashed_password
    return Choices(
        desktop=a.desktop,
        hostname=a.hostname,
        users=users,
        state_version=a.state_version,
        boot=a.boot,
        bios_device=a.bios_device,
        timezone=a.timezone,
        locale=a.locale,
        keyboard_layout=a.keyboard_layout,
        keyboard_variant=a.keyboard_variant,
        console_keymap=a.console_keymap,
        autologin=a.autologin,
    )


def unfree_kernel_modules(source: str, names: list[str]) -> list[str]:
    """Which of these kernel module packages are unfree in TulsiOS's nixpkgs."""
    expr = (
        f'let pkgs = import (builtins.getFlake "path:{source}").inputs.nixpkgs '
        '{ system = builtins.currentSystem; }; kp = pkgs.linuxPackages_latest; in '
        f"builtins.filter (n: (kp.${{n}}.meta.unfree or false)) (builtins.fromJSON ''{json.dumps(names)}'')"
    )
    try:
        out = subprocess.run(
            ["nix", "--extra-experimental-features", "nix-command flakes", "eval", "--impure", "--json", "--expr", expr],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        return json.loads(out)
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"tulsi-install-system: cannot check kernel modules {names}: {e}", file=sys.stderr)
        return []


def hardware_configuration(root: str, source: str, root_is_btrfs: bool) -> str:
    hw = subprocess.run(
        ["nixos-generate-config", "--root", root, "--show-hardware-config"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if root_is_btrfs:
        hw = render.fix_btrfs_subvolumes(hw)
    extra = render.extra_module_packages(hw)
    if extra:
        hw = render.drop_extra_module_packages(hw, unfree_kernel_modules(source, extra))
    return hw


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    path.write_text(text)
    path.chmod(0o644)


def install(a: argparse.Namespace) -> int:
    for what in ("source", "template", "initial_state", "state_version"):
        if not getattr(a, what):
            print(f"tulsi-install-system: --{what.replace('_', '-')} is not set", file=sys.stderr)
            return 2
    try:
        choices = choices_from_args(a)
        config = render.configuration_nix(choices)
        flake = render.flake_nix(Path(a.template).read_text(), a.source, choices.hostname)
    except InvalidChoice as e:
        print(f"tulsi-install-system: {e}", file=sys.stderr)
        return 2

    etc = Path(a.root) / "etc/nixos"
    write(etc / "flake.nix", flake)
    write(etc / "configuration.nix", config)
    hardware = etc / "hardware-configuration.nix"
    if not (a.keep_hardware_config and hardware.exists()):
        write(hardware, hardware_configuration(a.root, a.source, choices.root_is_btrfs))
    state = etc / "tulsi/state.json"
    if not state.exists():
        write(state, Path(a.initial_state).read_text())
    print(f"tulsi-install-system: wrote {etc} ({choices.desktop}, host {choices.hostname})", file=sys.stderr)
    if a.write_only:
        return 0

    cmd = [
        "nixos-install",
        "--root", a.root,
        "--flake", f"{etc}#{choices.hostname}",
        "--no-root-passwd",
        "--no-channel-copy",
        # Calamares mounts the root under /tmp; Nix wants a build directory
        # without world-writable parents.
        "--option", "build-dir", "/nix/var/nix/builds",
    ]
    if a.progress_json:
        cmd += ["--log-format", "internal-json"]
    os.makedirs("/nix/var/nix/builds", exist_ok=True)
    return subprocess.run(cmd, stdin=subprocess.DEVNULL).returncode


def main(argv: list[str] | None = None) -> None:
    sys.exit(install(parse_args(sys.argv[1:] if argv is None else argv)))


if __name__ == "__main__":
    main()
