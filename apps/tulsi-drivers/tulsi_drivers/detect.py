"""What hardware this computer has, from /sys and /proc (ADR 0029).

Only what drivers depend on: graphics cards, Wi-Fi cards and the processor.
`detect(root)` reads below `root`, so tests use fake trees; `TULSI_DRIVERS_ROOT`
does the same for the apps (the Welcome window's VM test).
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

VENDORS = {"10de": "NVIDIA", "1002": "AMD", "8086": "Intel", "14e4": "Broadcom"}

PCI_IDS = [
    Path(p)
    for p in (
        os.environ.get("TULSI_PCI_IDS", ""),
        "/run/current-system/sw/share/hwdata/pci.ids",
        "/usr/share/hwdata/pci.ids",
    )
    if p
]


@dataclass
class Device:
    slot: str  # "0000:01:00.0"
    kind: str  # "gpu" or "wifi"
    vendor_id: str  # "10de"
    device_id: str  # "2684"
    vendor: str
    name: str
    driver: str | None  # the kernel driver bound to it now
    boot_vga: bool = False  # the GPU the firmware showed the boot screen on

    @property
    def bus_id(self) -> str:
        """The slot as X and NixOS write it: decimal, "PCI:1:0:0"."""
        _domain, bus, rest = self.slot.split(":")
        dev, fn = rest.split(".")
        return f"PCI:{int(bus, 16)}:{int(dev, 16)}:{int(fn, 16)}"


@dataclass
class CPU:
    vendor: str  # "Intel", "AMD" or what /proc/cpuinfo says
    model: str
    microcode: str | None  # the revision loaded now


@dataclass
class Hardware:
    devices: list[Device] = field(default_factory=list)
    cpu: CPU | None = None

    @property
    def gpus(self) -> list[Device]:
        return [d for d in self.devices if d.kind == "gpu"]

    @property
    def wifi(self) -> list[Device]:
        return [d for d in self.devices if d.kind == "wifi"]

    def to_json(self) -> dict:
        return {
            "devices": [asdict(d) | {"bus_id": d.bus_id} for d in self.devices],
            "cpu": asdict(self.cpu) if self.cpu else None,
        }


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _hex(value: str) -> str:
    return value.lower().removeprefix("0x").zfill(4)


def pci_names(vendor_id: str, device_id: str, ids_files: list[Path] | None = None) -> tuple[str, str]:
    """The vendor's and the device's names from hwdata's pci.ids."""
    vendor = VENDORS.get(vendor_id, f"Vendor {vendor_id}")
    name = ""
    for path in ids_files if ids_files is not None else PCI_IDS:
        try:
            with path.open(encoding="utf-8", errors="replace") as f:
                in_vendor = False
                for line in f:
                    if not line.strip() or line.startswith("#"):
                        continue
                    if not line[0].isspace():
                        if in_vendor:
                            break
                        if line[:4].lower() == vendor_id:
                            in_vendor = True
                            if vendor_id not in VENDORS:
                                vendor = line[4:].strip()
                    elif in_vendor and line.startswith("\t") and not line.startswith("\t\t"):
                        if line[1:5].lower() == device_id:
                            name = line[5:].strip()
                            break
        except OSError:
            continue
        break
    if not name:
        name = f"Device {device_id}"
    # "GA106 [GeForce RTX 3060 Lite Hash Rate]": the marketing name is the bracketed part.
    bracket = re.search(r"\[(.+)\]", name)
    if bracket:
        name = bracket.group(1)
    return vendor, name


def _kind(pci_class: str) -> str | None:
    cls = _hex(pci_class).zfill(6)
    if cls.startswith("03"):
        return "gpu"
    if cls.startswith("0280"):
        return "wifi"
    return None


def detect_devices(root: Path = Path("/"), ids_files: list[Path] | None = None) -> list[Device]:
    devices = []
    base = root / "sys/bus/pci/devices"
    try:
        entries = sorted(base.iterdir())
    except OSError:
        return devices
    for entry in entries:
        kind = _kind(_read(entry / "class"))
        if kind is None:
            continue
        vendor_id = _hex(_read(entry / "vendor"))
        device_id = _hex(_read(entry / "device"))
        vendor, name = pci_names(vendor_id, device_id, ids_files)
        driver_link = entry / "driver"
        driver = os.path.basename(os.readlink(driver_link)) if driver_link.is_symlink() else None
        devices.append(
            Device(
                slot=entry.name,
                kind=kind,
                vendor_id=vendor_id,
                device_id=device_id,
                vendor=vendor,
                name=name,
                driver=driver,
                boot_vga=_read(entry / "boot_vga") == "1",
            )
        )
    return devices


def detect_cpu(root: Path = Path("/")) -> CPU | None:
    info = _read(root / "proc/cpuinfo")
    if not info:
        return None
    fields: dict[str, str] = {}
    for line in info.splitlines():
        if not line.strip():
            break  # the first processor is enough
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    vendor = {"GenuineIntel": "Intel", "AuthenticAMD": "AMD"}.get(
        fields.get("vendor_id", ""), fields.get("vendor_id", "Unknown")
    )
    return CPU(
        vendor=vendor,
        model=fields.get("model name", "Unknown processor"),
        microcode=fields.get("microcode"),
    )


def detect(root: Path | None = None, ids_files: list[Path] | None = None) -> Hardware:
    if root is None:
        root = Path(os.environ.get("TULSI_DRIVERS_ROOT", "/"))
    return Hardware(devices=detect_devices(root, ids_files), cpu=detect_cpu(root))
