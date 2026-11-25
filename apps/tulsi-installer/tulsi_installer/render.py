"""The files tulsi-install-system writes into <root>/etc/nixos. No I/O here.

  flake.nix                   the TulsiOS system flake (the template tulsid also uses)
  flake.lock                  pins it to the TulsiOS release the ISO carries
  configuration.nix           this machine's settings: hostname, users, locale,
                              keyboard, boot loader and the desktop
  hardware-configuration.nix  from nixos-generate-config, with fixes
  tulsi/state.json            the initial software (state/initial.json)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

DESKTOPS = ("ocimum", "sonic", "dwm")
BOOT_KINDS = ("uefi", "bios", "none")
HOST_MODULE = "nix/hosts/desktop"
DEFAULT_GROUPS = ("networkmanager", "wheel")


class InvalidChoice(ValueError):
    """An answer that cannot go into the configuration."""


@dataclass
class User:
    name: str
    full_name: str = ""
    # A crypt(3) hash for users.users.<name>.initialHashedPassword. Calamares sets
    # passwords itself after the install (its `users` job), so it passes none.
    hashed_password: str | None = None


@dataclass
class Choices:
    desktop: str
    hostname: str
    users: list[User]
    state_version: str
    boot: str = "uefi"
    # The disk GRUB is installed on (boot = "bios").
    bios_device: str | None = None
    timezone: str | None = None
    locale: str | None = None
    # LC_* overrides, e.g. {"LC_TIME": "sv_SE.UTF-8"}.
    extra_locale: dict[str, str] = field(default_factory=dict)
    keyboard_layout: str | None = None
    keyboard_variant: str | None = None
    console_keymap: str | None = None
    autologin: str | None = None
    # GRUB unlocks an encrypted /boot (or a root without a /boot partition) with
    # /boot/crypto_keyfile.bin; these LUKS mapper names get that key file.
    grub_crypt_mappers: list[str] = field(default_factory=list)
    # Encrypted swap, which nixos-generate-config does not see: mapper name -> UUID.
    luks_swap: dict[str, str] = field(default_factory=dict)
    root_is_btrfs: bool = False


_HOSTNAME = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_USERNAME = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_TIMEZONE = re.compile(r"^[A-Za-z0-9_+-]+(/[A-Za-z0-9_+-]+)*$")
_LOCALE = re.compile(r"^[A-Za-z0-9_.@-]+$")
_LC_NAME = re.compile(r"^LC_[A-Z]+$")
_XKB = re.compile(r"^[A-Za-z0-9_,()+-]*$")
_DEVICE = re.compile(r"^/dev/[A-Za-z0-9/_.:+-]+$")
_MAPPER = re.compile(r"^[A-Za-z0-9_.+-]+$")
_UUID = re.compile(r"^[A-Fa-f0-9-]+$")
_STATE_VERSION = re.compile(r"^[0-9]{2}\.[0-9]{2}$")


def _check(ok: bool, what: str, value: object) -> None:
    if not ok:
        raise InvalidChoice(f"invalid {what}: {value!r}")


def validate(c: Choices) -> None:
    """Raises InvalidChoice for anything that must not reach configuration.nix."""
    _check(c.desktop in DESKTOPS, "desktop (ocimum, sonic or dwm)", c.desktop)
    _check(bool(_HOSTNAME.fullmatch(c.hostname)), "hostname", c.hostname)
    _check(bool(c.users), "users (at least one)", c.users)
    for u in c.users:
        _check(bool(_USERNAME.fullmatch(u.name)) and u.name != "root", "user name", u.name)
        _check("\n" not in u.full_name, "full name", u.full_name)
    names = [u.name for u in c.users]
    _check(len(set(names)) == len(names), "users (duplicate names)", names)
    _check(bool(_STATE_VERSION.fullmatch(c.state_version)), "state version", c.state_version)
    _check(c.boot in BOOT_KINDS, "boot loader (uefi, bios or none)", c.boot)
    if c.boot == "bios":
        _check(c.bios_device is not None and bool(_DEVICE.fullmatch(c.bios_device)), "GRUB device", c.bios_device)
    if c.timezone is not None:
        _check(bool(_TIMEZONE.fullmatch(c.timezone)), "time zone", c.timezone)
    for loc in [c.locale, *c.extra_locale.values()]:
        if loc is not None:
            _check(bool(_LOCALE.fullmatch(loc)), "locale", loc)
    for name in c.extra_locale:
        _check(bool(_LC_NAME.fullmatch(name)), "locale category", name)
    for v in (c.keyboard_layout, c.keyboard_variant):
        if v is not None:
            _check(bool(_XKB.fullmatch(v)), "keyboard layout", v)
    if c.console_keymap is not None:
        _check(bool(_LOCALE.fullmatch(c.console_keymap)), "console keymap", c.console_keymap)
    if c.autologin is not None:
        _check(c.autologin in names, "autologin user (not one of the users)", c.autologin)
    for m in c.grub_crypt_mappers:
        _check(bool(_MAPPER.fullmatch(m)), "LUKS mapper name", m)
    for m, uuid in c.luks_swap.items():
        _check(bool(_MAPPER.fullmatch(m)) and bool(_UUID.fullmatch(uuid)), "encrypted swap", (m, uuid))
    if c.grub_crypt_mappers:
        _check(c.boot == "bios", "GRUB key file (only with boot = bios)", c.grub_crypt_mappers)


def nix_string(s: str) -> str:
    """A Nix string literal for any text."""
    escaped = (
        s.replace("\\", "\\\\").replace('"', '\\"').replace("${", "\\${").replace("\n", "\\n")
    )
    return f'"{escaped}"'


def flake_nix(template: str, tulsi_url: str, host: str) -> str:
    """Fills in data/system-flake.nix.in, as tulsid's bootstrap does. tulsi_url is
    the `tulsi` input: the release branch (github:…) or a local path:…."""
    out = (
        template.replace("@tulsiUrl@", tulsi_url)
        .replace("@host@", host)
        .replace("@hostModule@", HOST_MODULE)
    )
    if re.search(r"@[A-Za-z]+@", out):
        raise InvalidChoice("the system flake template has an unknown @placeholder@")
    return out


_GITHUB = re.compile(r"^github:([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/([A-Za-z0-9_./-]+)$")
_REV = re.compile(r"^[0-9a-f]{40}$")


def flake_lock(source_lock: dict, upstream: str, rev: str, nar_hash: str, last_modified: int) -> str:
    """The system flake's flake.lock, written by the installer instead of `nix flake
    lock`, so an install needs no network (ADR 0017).

    `tulsi` is locked to the TulsiOS source the ISO carries: upstream is the release
    branch (github:owner/repo/ref), rev and nar_hash those of the carried source. Nix
    finds a locked input with that narHash in the store and does not download it.
    TulsiOS's own inputs (tulsipkgs, Starah) are copied from source_lock, its
    flake.lock, so the lock is complete and nothing rewrites it during nixos-install.
    """
    m = _GITHUB.fullmatch(upstream)
    if not m:
        raise InvalidChoice(f"upstream must be github:owner/repo/branch, not {upstream!r}")
    if not _REV.fullmatch(rev):
        raise InvalidChoice(f"not a git revision: {rev!r}")
    if not nar_hash.startswith("sha256-"):
        raise InvalidChoice(f"not a narHash: {nar_hash!r}")
    owner, repo, ref = m.groups()

    def renamed(name: str) -> str:
        return f"tulsi-{name}"

    def inputs(own: dict) -> dict:
        # A string names a node; a list is a `follows` path from the root, which now
        # starts at `tulsi`.
        return {k: (["tulsi", *v] if isinstance(v, list) else renamed(v)) for k, v in own.items()}

    own_root = source_lock["root"]
    nodes: dict = {}
    for name, node in source_lock["nodes"].items():
        if name == own_root:
            continue
        node = dict(node)
        if "inputs" in node:
            node["inputs"] = inputs(node["inputs"])
        nodes[renamed(name)] = node
    nodes["tulsi"] = {
        "inputs": inputs(source_lock["nodes"][own_root].get("inputs", {})),
        "locked": {
            "lastModified": last_modified,
            "narHash": nar_hash,
            "owner": owner,
            "repo": repo,
            "rev": rev,
            "type": "github",
        },
        "original": {"owner": owner, "ref": ref, "repo": repo, "type": "github"},
    }
    nodes["root"] = {"inputs": {"tulsi": "tulsi"}}
    lock = {"nodes": nodes, "root": "root", "version": source_lock.get("version", 7)}
    return json.dumps(lock, indent=2, sort_keys=True) + "\n"


def configuration_nix(c: Choices) -> str:
    validate(c)
    s = nix_string
    out = [
        "# This machine's own NixOS settings, written by the TulsiOS installer.",
        "# Software chosen in the Software Center or the Assistant is kept in",
        "# ./tulsi/state.json instead. Change these settings with `tulsi config`, so",
        "# each edit is recorded and can be undone: `tulsi config show > FILE`, edit",
        "# FILE, then `tulsi config apply FILE --summary \"what changed\"`.",
        "{ config, lib, pkgs, ... }:",
        "",
        "{",
        f"  networking.hostName = {s(c.hostname)};",
        "",
        '  # The desktop: "ocimum" (Ocimum Desktop), "sonic" (SonicDE) or "dwm" (tiling).',
        f"  tulsi.desktop.session = {s(c.desktop)};",
        "",
    ]

    if c.boot == "uefi":
        out += [
            "  boot.loader.systemd-boot.enable = true;",
            "  boot.loader.efi.canTouchEfiVariables = true;",
        ]
    elif c.boot == "bios":
        out += [
            "  boot.loader.grub.enable = true;",
            f"  boot.loader.grub.device = {s(c.bios_device or '')};",
            "  boot.loader.grub.useOSProber = true;",
        ]
        if c.root_is_btrfs:
            # Provided UUIDs instead of blkid probing (btrfs subvolumes).
            out.append('  boot.loader.grub.fsIdentifier = "provided";')
    else:
        out.append("  boot.loader.grub.enable = false;")
    if c.grub_crypt_mappers:
        out += [
            "  boot.loader.grub.enableCryptodisk = true;",
            '  boot.initrd.secrets."/boot/crypto_keyfile.bin" = null;',
        ]
        for m in c.grub_crypt_mappers:
            out.append(f'  boot.initrd.luks.devices.{s(m)}.keyFile = "/boot/crypto_keyfile.bin";')
    for m, uuid in sorted(c.luks_swap.items()):
        out.append(f'  boot.initrd.luks.devices.{s(m)}.device = "/dev/disk/by-uuid/{uuid}";')
    out.append("")

    if c.timezone:
        out.append(f"  time.timeZone = {s(c.timezone)};")
    if c.locale:
        out.append(f"  i18n.defaultLocale = {s(c.locale)};")
    extra = {k: v for k, v in sorted(c.extra_locale.items()) if v != c.locale}
    if extra:
        out.append("  i18n.extraLocaleSettings = {")
        out += [f"    {k} = {s(v)};" for k, v in extra.items()]
        out.append("  };")
    if c.keyboard_layout:
        out.append(f"  services.xserver.xkb.layout = {s(c.keyboard_layout)};")
        out.append(f"  services.xserver.xkb.variant = {s(c.keyboard_variant or '')};")
    if c.console_keymap:
        out.append(f"  console.keyMap = {s(c.console_keymap)};")
    if out[-1] != "":
        out.append("")

    for u in c.users:
        groups = " ".join(s(g) for g in DEFAULT_GROUPS)
        out.append(f"  users.users.{s(u.name)} = {{")
        out.append("    isNormalUser = true;")
        if u.full_name:
            out.append(f"    description = {s(u.full_name)};")
        out.append(f"    extraGroups = [ {groups} ];")
        if u.hashed_password:
            out.append(f"    initialHashedPassword = {s(u.hashed_password)};")
        out.append("  };")
    if c.autologin:
        out.append(f"  tulsi.desktop.autoLoginUser = {s(c.autologin)};")
    out += [
        "",
        "  # The TulsiOS release this machine was installed with. Keep it as it is:",
        "  # it is not the version you run, and changing it can break saved data.",
        f"  system.stateVersion = {s(c.state_version)};",
        "}",
        "",
    ]
    return "\n".join(out)


def fix_btrfs_subvolumes(hardware: str) -> str:
    """nixos-generate-config writes mount points as btrfs subvolume names; Calamares'
    mount.conf creates subvolumes "home" and "nix" (root stays top-level, for GRUB).
    After calamares-nixos-extensions (MIT), whose pattern stops at the first `;` and
    so never reaches `options` in nixos-generate-config's output; this one stays
    inside the file system's `{ … }`."""
    for mount_point, subvol in (("/home", "home"), ("/nix", "nix")):
        pattern = r'(fileSystems\."{}"\s*=\s*\{{[^}}]*?"subvol=)[^"]*"'.format(re.escape(mount_point))
        hardware = re.sub(pattern, r'\g<1>{}"'.format(subvol), hardware)
    return hardware


_EXTRA_MODULES = re.compile(r"boot\.extraModulePackages = \[ (.*) \];")


def extra_module_packages(hardware: str) -> list[str]:
    """Out-of-tree kernel modules nixos-generate-config chose, e.g. ["broadcom_sta"]."""
    m = _EXTRA_MODULES.search(hardware)
    if not m:
        return []
    return [p.rsplit(".", 1)[-1] for p in m.group(1).split() if p]


def drop_extra_module_packages(hardware: str, names: list[str]) -> str:
    """Removes these (unfree) modules: TulsiOS does not allow unfree packages by default."""
    m = _EXTRA_MODULES.search(hardware)
    if not m or not names:
        return hardware
    keep = [p for p in m.group(1).split() if p and p.rsplit(".", 1)[-1] not in names]
    inner = " ".join(keep)
    return hardware[: m.start()] + f"boot.extraModulePackages = [ {inner}{' ' if inner else ''}];" + hardware[m.end():]


def console_keymap_for(layout: str, variant: str | None, kbd_model_map: str) -> str | None:
    """The console keymap matching an X layout, from systemd's kbd-model-map
    (columns: keymap, x11 layout, model, variant, options). None for "us"."""
    rows = [line.split() for line in kbd_model_map.splitlines() if line and not line.startswith("#")]
    same_layout = [r for r in rows if len(r) >= 4 and r[1] == layout]
    if not same_layout:
        return None
    keymap = same_layout[0][0]
    want = variant or "-"
    for r in same_layout:
        if want in r[3]:
            keymap = r[0]
            break
    return None if keymap == "us" else keymap
