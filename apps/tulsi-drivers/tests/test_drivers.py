"""Detection, choices and the configuration.nix block, on fake /sys trees."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from tulsi_drivers import catalogue, config, detect
from tulsi_drivers.config import Nvidia, Settings

PCI_IDS = """\
# fake pci.ids
10de  NVIDIA Corporation
\t2684  AD102 [GeForce RTX 4090]
\t1c8d  GP107M [GeForce GTX 1050 Mobile]
\t1180  GK104 [GeForce GTX 680]
\t0a20  GT216 [GeForce GT 220]
\t25a2  GA107M [GeForce RTX 3050 Mobile]
\t\t1043 1e11  subsystem line
1002  Advanced Micro Devices, Inc. [AMD/ATI]
\t73bf  Navi 21 [Radeon RX 6800/6800 XT / 6900 XT]
\t6798  Tahiti XT [Radeon HD 7970]
14e4  Broadcom Inc. and subsidiaries
\t43a0  BCM4360 802.11ac Dual Band Wireless Network Adapter
\t43a3  BCM4350 802.11ac Wireless Network Adapter
8086  Intel Corporation
\t9a49  TigerLake-LP GT2 [Iris Xe Graphics]
\t0166  3rd Gen Core processor Graphics Controller
\t2725  Wi-Fi 6E(802.11ax) AX210/AX1675* 2x2 [Typhoon Peak]
"""

SYSTEM = {
    "kernel": "7.3.5",
    "nvidia": {
        "production": {"version": "595.112.07", "available": True},
        "new_feature": {"version": "615.78.08", "available": True},
        "legacy_580": {"version": "580.196.07", "available": True},
        "legacy_470": {
            "version": "470.256.02",
            "available": False,
            "reason": "NVIDIA's 470 X driver crashes with XLibre, TulsiOS's display server.",
        },
    },
    "broadcom": {"available": True},
    "microcode": True,
}


def make_root(tmp_path: Path, devices: list[tuple], cpu: str = "GenuineIntel") -> Path:
    root = tmp_path / "root"
    for slot, cls, vendor, device, driver, boot_vga in devices:
        d = root / "sys/bus/pci/devices" / slot
        d.mkdir(parents=True)
        (d / "class").write_text(cls + "\n")
        (d / "vendor").write_text(f"0x{vendor}\n")
        (d / "device").write_text(f"0x{device}\n")
        (d / "boot_vga").write_text("1\n" if boot_vga else "0\n")
        if driver:
            target = root / "sys/bus/pci/drivers" / driver
            target.mkdir(parents=True, exist_ok=True)
            os.symlink(target, d / "driver")
    (root / "proc").mkdir(parents=True, exist_ok=True)
    (root / "proc/cpuinfo").write_text(
        f"processor\t: 0\nvendor_id\t: {cpu}\nmodel name\t: Test CPU 9000\nmicrocode\t: 0x2c\n\nprocessor\t: 1\n"
    )
    return root


@pytest.fixture
def ids(tmp_path: Path) -> list[Path]:
    p = tmp_path / "pci.ids"
    p.write_text(PCI_IDS)
    return [p]


def hw_of(tmp_path, ids, devices, cpu="GenuineIntel"):
    return detect.detect(make_root(tmp_path, devices, cpu), ids)


DESKTOP_RTX = [("0000:01:00.0", "0x030000", "10de", "2684", "nouveau", True)]
LAPTOP_PASCAL = [
    ("0000:00:02.0", "0x030000", "8086", "9a49", "i915", True),
    ("0000:01:00.0", "0x030200", "10de", "1c8d", "nouveau", False),
    ("0000:00:14.3", "0x028000", "8086", "2725", "iwlwifi", False),
]
LAPTOP_AMPERE = [
    ("0000:00:02.0", "0x030000", "8086", "9a49", "i915", True),
    ("0000:2d:00.0", "0x030200", "10de", "25a2", "nouveau", False),
]
KEPLER = [("0000:01:00.0", "0x030000", "10de", "1180", "nouveau", True)]
TESLA = [("0000:01:00.0", "0x030000", "10de", "0a20", "nouveau", True)]
AMD = [("0000:03:00.0", "0x030000", "1002", "73bf", "amdgpu", True)]
AMD_OLD = [("0000:03:00.0", "0x030000", "1002", "6798", "radeon", True)]
BROADCOM_NO_DRIVER = [
    ("0000:00:02.0", "0x030000", "8086", "0166", "i915", True),
    ("0000:02:00.0", "0x028000", "14e4", "43a0", None, False),
]
BROADCOM_OPEN = [("0000:02:00.0", "0x028000", "14e4", "43a3", "brcmfmac", False)]


# ---------------------------------------------------------------- detection


def test_detect_reads_devices_names_and_drivers(tmp_path, ids):
    hw = hw_of(tmp_path, ids, LAPTOP_PASCAL)
    assert [d.kind for d in hw.devices] == ["gpu", "wifi", "gpu"]
    nvidia = next(d for d in hw.gpus if d.vendor_id == "10de")
    assert nvidia.name == "GeForce GTX 1050 Mobile"
    assert nvidia.vendor == "NVIDIA"
    assert nvidia.driver == "nouveau"
    assert not nvidia.boot_vga
    assert nvidia.bus_id == "PCI:1:0:0"
    assert hw.cpu.vendor == "Intel" and hw.cpu.microcode == "0x2c"


def test_bus_id_is_decimal(tmp_path, ids):
    hw = hw_of(tmp_path, ids, LAPTOP_AMPERE)
    assert next(d for d in hw.gpus if d.vendor_id == "10de").bus_id == "PCI:45:0:0"


def test_unknown_device_gets_a_name(tmp_path, ids):
    hw = hw_of(tmp_path, ids, [("0000:01:00.0", "0x030000", "10de", "ffff", None, True)])
    assert hw.gpus[0].name == "Device ffff"


# ---------------------------------------------------------------- choices


def choice(rows, ident):
    return next(c for r in rows for c in r.choices if c.id == ident)


def test_rtx_desktop_recommends_nvidia_open(tmp_path, ids):
    hw = hw_of(tmp_path, ids, DESKTOP_RTX)
    rows = catalogue.rows(hw, Settings(), SYSTEM)
    nv = choice(rows, "nvidia")
    assert nv.recommended and nv.available and nv.unfree
    assert nv.settings.nvidia == Nvidia(branch="production", open=True)
    assert "595.112.07" in nv.label
    assert choice(rows, "nouveau").selected
    assert catalogue.needs_attention(hw, Settings(), SYSTEM)


def test_pascal_laptop_recommends_580_proprietary_offload(tmp_path, ids):
    hw = hw_of(tmp_path, ids, LAPTOP_PASCAL)
    rec = catalogue.recommend(hw, Settings(), SYSTEM)
    assert rec.nvidia == Nvidia(
        branch="legacy_580", open=False, prime="offload", nvidia_bus="PCI:1:0:0", intel_bus="PCI:0:2:0"
    )
    # Intel's video decoding is recommended too; the Wi-Fi works as it is.
    assert rec.intel_va == "media"
    assert not rec.broadcom
    rows = catalogue.rows(hw, Settings(), SYSTEM)
    assert choice(rows, "nvidia-sync").settings.nvidia.prime == "sync"
    assert not any(c.id == "nvidia-new-feature" for r in rows for c in r.choices)


def test_kepler_branch_that_does_not_build_falls_back_to_nouveau(tmp_path, ids):
    hw = hw_of(tmp_path, ids, KEPLER)
    rows = catalogue.rows(hw, Settings(), SYSTEM)
    nv = choice(rows, "nvidia")
    assert not nv.available and "XLibre" in nv.reason
    assert choice(rows, "nouveau").recommended
    assert not catalogue.needs_attention(hw, Settings(), SYSTEM)


def test_too_old_card_has_only_nouveau(tmp_path, ids):
    rows = catalogue.rows(hw_of(tmp_path, ids, TESLA), Settings(), SYSTEM)
    assert not choice(rows, "nvidia").available
    assert choice(rows, "nouveau").recommended


def test_amd_has_extras_and_no_attention(tmp_path, ids):
    hw = hw_of(tmp_path, ids, AMD)
    rows = catalogue.rows(hw, Settings(), SYSTEM)
    assert [e.id for e in rows[0].extras] == ["amd-compute"]
    assert "works without changes" in rows[0].status
    assert not catalogue.needs_attention(hw, Settings(), SYSTEM)
    old = catalogue.rows(hw_of(tmp_path / "b", ids, AMD_OLD), Settings(), SYSTEM)
    assert "amd-legacy" in [e.id for e in old[0].extras]


def test_intel_va_driver_by_generation():
    assert catalogue.intel_va_driver("0166") == "i965"  # Ivy Bridge
    assert catalogue.intel_va_driver("9a49") == "media"  # Tiger Lake
    assert catalogue.intel_va_driver("1616") == "media"  # Broadwell


def test_broadcom_without_driver_recommends_wl(tmp_path, ids):
    hw = hw_of(tmp_path, ids, BROADCOM_NO_DRIVER)
    rec = catalogue.recommend(hw, Settings(), SYSTEM)
    assert rec.broadcom
    assert rec.intel_va == "i965"
    assert catalogue.needs_attention(hw, Settings(), SYSTEM)


def test_broadcom_with_open_driver_stays(tmp_path, ids):
    hw = hw_of(tmp_path, ids, BROADCOM_OPEN)
    rows = catalogue.rows(hw, Settings(), SYSTEM)
    assert rows[-1].kind == "cpu"
    wifi = next(r for r in rows if r.kind == "wifi")
    assert wifi.choices == []  # 43a3 isn't one of wl's cards
    assert not catalogue.recommend(hw, Settings(), SYSTEM).broadcom


def test_cpu_row_says_microcode(tmp_path, ids):
    rows = catalogue.rows(hw_of(tmp_path, ids, AMD, cpu="AuthenticAMD"), Settings(), SYSTEM)
    cpu = rows[-1]
    assert cpu.subtitle == "AMD processor"
    assert "every start" in cpu.status and "0x2c" in cpu.status


def test_nvidia_list_covers_known_cards():
    gpus = catalogue.nvidia_gpus()
    assert gpus["2684"]["branch"] == "production" and gpus["2684"]["open"]
    assert gpus["1c82"]["branch"] == "legacy_580" and not gpus["1c82"]["open"]
    assert gpus["1180"]["branch"] == "legacy_470"


# ---------------------------------------------------------------- the block

BASE = """{ config, lib, pkgs, ... }:
{
  services.printing.enable = true;
}
"""


def test_block_round_trip():
    s = Settings(
        nvidia=Nvidia(branch="legacy_580", open=False, prime="offload", nvidia_bus="PCI:1:0:0", intel_bus="PCI:0:2:0"),
        intel_va="media",
        games32=True,
    )
    text = config.with_settings(BASE, s)
    assert "services.printing.enable = true;" in text
    assert config.BEGIN in text and config.END in text
    assert "nixpkgs.config.allowUnfree = true;" in text
    assert text.rstrip().endswith("}")
    back = config.parse(text)
    assert back == replace(s, unfree=True)


def test_block_is_replaced_in_place_and_unfree_stays():
    first = config.with_settings(BASE, Settings(nvidia=Nvidia()))
    second = config.with_settings(first, Settings(unfree=True, games32=True))
    assert second.count(config.BEGIN) == 1
    assert "tulsi.drivers.nvidia" not in second
    assert "nixpkgs.config.allowUnfree = true;" in second
    assert config.parse(second).games32


def test_empty_settings_remove_the_block():
    text = config.with_settings(BASE, Settings(games32=True))
    assert config.with_settings(text, Settings()) == BASE


def test_unfree_elsewhere_is_reused_or_turned_on():
    on = BASE.replace("}\n", "  nixpkgs.config.allowUnfree = true;\n}\n")
    text = config.with_settings(on, Settings(nvidia=Nvidia()))
    assert text.count("allowUnfree") == 1
    off = BASE.replace("}\n", "  nixpkgs.config.allowUnfree = false;\n}\n")
    text = config.with_settings(off, Settings(nvidia=Nvidia()))
    assert text.count("allowUnfree") == 1 and "allowUnfree = true;" in text


def test_empty_config_gets_a_whole_file():
    text = config.with_settings("", Settings(games32=True))
    assert text.startswith("{ config, lib, pkgs, ... }:\n{\n")
    assert config.parse(text).games32


def test_strings_are_escaped():
    s = Settings(nvidia=Nvidia(branch='x"${y}'))
    assert '"x\\"\\${y}"' in config.with_settings(BASE, s)


def test_without_tulsi_nothing_crashes(monkeypatch, tmp_path):
    # A system without tulsid (or `tulsi` off the PATH): failures, not crashes.
    from tulsi_drivers import system

    monkeypatch.setenv("PATH", str(tmp_path))
    assert system.trial_status() == {"state": "none"}
    assert system.trial("keep")[0] is False
    with pytest.raises(RuntimeError):
        system.current_settings()
