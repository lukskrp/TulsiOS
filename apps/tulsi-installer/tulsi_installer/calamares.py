"""Calamares' answers (its global storage, dumped as JSON by the `tulsios` job
module) -> Choices. The same rules as calamares-nixos-extensions' `nixos` module."""

from __future__ import annotations

from typing import Any

from .render import Choices, User, console_keymap_for

LUKS = ("luks", "luks2")


def choices_from_globalstorage(gs: dict[str, Any], kbd_model_map: str, state_version: str) -> Choices:
    partitions: list[dict[str, Any]] = gs.get("partitions") or []
    firmware = gs.get("firmwareType")
    boot_device = (gs.get("bootLoader") or {}).get("installPath") or "nodev"
    if firmware == "efi":
        boot, bios_device = "uefi", None
    elif boot_device != "nodev":
        boot, bios_device = "bios", boot_device
    else:
        boot, bios_device = "none", None

    root = next((p for p in partitions if p.get("mountPoint") == "/"), {})
    boot_part = next((p for p in partitions if p.get("mountPoint") == "/boot"), None)
    root_encrypted = root.get("fsName") in LUKS
    claimed_luks = [
        p for p in partitions if p.get("claimed") is True and p.get("fsName") in LUKS and p.get("device")
    ]
    grub_crypt = boot == "bios" and (
        (boot_part is not None and boot_part.get("fsName") in LUKS)
        or (root_encrypted and boot_part is None)
    )

    users = []
    if gs.get("username"):
        users.append(User(gs["username"], gs.get("fullname") or ""))

    locale = None
    extra: dict[str, str] = {}
    conf = dict(gs.get("localeConf") or {})
    if conf.get("LANG"):
        locale = conf.pop("LANG").split("/")[0]
        extra = {k: v.split("/")[0] for k, v in conf.items() if k.startswith("LC_") and v}

    layout = gs.get("keyboardLayout")
    variant = gs.get("keyboardVariant")
    keymap = (gs.get("keyboardVConsoleKeymap") or "").strip() or None
    if layout and keymap is None:
        keymap = console_keymap_for(layout, variant, kbd_model_map)

    timezone = None
    if gs.get("locationRegion") and gs.get("locationZone"):
        timezone = f"{gs['locationRegion']}/{gs['locationZone']}"

    autologin = users[0].name if users and gs.get("autoLoginUser") else None

    return Choices(
        desktop=gs.get("packagechooser_packagechooser") or "ocimum",
        hostname=gs.get("hostname") or "tulsios",
        users=users,
        state_version=state_version,
        boot=boot,
        bios_device=bios_device,
        timezone=timezone,
        locale=locale,
        extra_locale=extra,
        keyboard_layout=layout,
        keyboard_variant=variant if layout else None,
        console_keymap=keymap,
        autologin=autologin,
        grub_crypt_mappers=[p["luksMapperName"] for p in claimed_luks] if grub_crypt else [],
        luks_swap={
            p["luksMapperName"]: p["uuid"] for p in claimed_luks if p.get("fs") == "linuxswap"
        },
        root_is_btrfs=root.get("fs") == "btrfs",
    )
