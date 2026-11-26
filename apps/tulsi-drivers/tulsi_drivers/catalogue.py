"""From hardware to driver choices, and which one to recommend (ADR 0029).

One `Row` per device: its driver choices (pick one) and extras (on or off).
Choosing changes `Settings`, which config.py writes as the drivers block.

What the system can build comes from /etc/tulsi/drivers.json, written by the
drivers module: the kernel, and for each NVIDIA series its version and whether
it builds with that kernel.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from importlib import resources
from pathlib import Path

from .config import Nvidia, Settings
from .detect import CPU, Device, Hardware

SYSTEM_FILE = Path(os.environ.get("TULSI_DRIVERS_SYSTEM", "/etc/tulsi/drivers.json"))

# Broadcom cards the STA ("wl") driver supports. The open drivers (b43,
# brcmsmac, brcmfmac) handle many of them too; wl is recommended only when no
# driver claimed the card.
BROADCOM_WL = {
    "4311", "4312", "4313", "4315", "4727", "4328", "4329", "432a", "432b", "432c",
    "432d", "0576", "4353", "4357", "4358", "4359", "4365", "4331", "43a0", "43b1",
}

BRANCH_LABELS = {
    "production": "NVIDIA's driver",
    "new_feature": "NVIDIA's driver, new feature series",
    "beta": "NVIDIA's driver, beta",
    "legacy_580": "NVIDIA's driver, 580 series (the last for this card)",
    "legacy_470": "NVIDIA's driver, 470 series (the last for this card)",
}


@dataclass
class Choice:
    id: str
    label: str
    detail: str
    settings: Settings  # the settings with this choice made
    available: bool = True
    reason: str = ""  # why it isn't available
    recommended: bool = False
    unfree: bool = False
    selected: bool = False


@dataclass
class Extra:
    id: str
    label: str
    detail: str
    on: bool
    settings_on: Settings
    settings_off: Settings
    recommended: bool = False


@dataclass
class Row:
    id: str
    kind: str  # "gpu", "wifi", "cpu", "graphics"
    title: str
    subtitle: str
    status: str  # what runs now
    choices: list[Choice] = field(default_factory=list)
    extras: list[Extra] = field(default_factory=list)

    def to_json(self) -> dict:
        def choice(c: Choice) -> dict:
            return {k: v for k, v in c.__dict__.items() if k != "settings"}

        def extra(e: Extra) -> dict:
            return {k: v for k, v in e.__dict__.items() if not k.startswith("settings")}

        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "subtitle": self.subtitle,
            "status": self.status,
            "choices": [choice(c) for c in self.choices],
            "extras": [extra(e) for e in self.extras],
        }


def load_system(path: Path = SYSTEM_FILE) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def nvidia_gpus() -> dict:
    data = resources.files("tulsi_drivers").joinpath("nvidia-gpus.json").read_text()
    return json.loads(data)["gpus"]


def _branch_info(system: dict, branch: str) -> tuple[bool, str, str]:
    """(available, version, why not) of an NVIDIA series on this system."""
    info = system.get("nvidia", {}).get(branch)
    if info is None:
        return True, "", ""
    reason = info.get("reason") or f"It doesn't build with Linux {_kernel(system)}."
    return bool(info.get("available", True)), info.get("version", ""), reason


def _kernel(system: dict) -> str:
    return system.get("kernel", "this kernel")


def intel_va_driver(device_id: str) -> str:
    """intel-media-driver for Broadwell (2014) and newer, i965 before."""
    n = int(device_id, 16)
    if n <= 0x0F33 or 0x2500 <= n <= 0x2FFF or n in (0xA001, 0xA002, 0xA011, 0xA012, 0x8108, 0x8109):
        return "i965"
    return "media"


def _status(device: Device) -> str:
    names = {
        "nvidia": "NVIDIA's driver",
        "nouveau": "Nouveau (open source)",
        "amdgpu": "amdgpu (open source)",
        "radeon": "radeon (open source)",
        "i915": "i915 (open source)",
        "xe": "xe (open source)",
        "wl": "Broadcom STA",
    }
    if device.driver is None:
        return "No driver"
    return "In use: " + names.get(device.driver, device.driver)


def _nvidia_row(gpu: Device, hw: Hardware, current: Settings, system: dict) -> Row:
    entry = nvidia_gpus().get(gpu.device_id)
    if entry is None:
        # Newer than the list: NVIDIA's current driver, open modules.
        entry = {"branch": "production", "open": True, "name": gpu.name}
    igpu = next((g for g in hw.gpus if g is not gpu and g.vendor_id in ("8086", "1002")), None)
    # A laptop: the integrated GPU drives the screen (it showed the boot screen).
    hybrid = igpu is not None and not gpu.boot_vga

    def nv(branch: str, open_: bool, prime: str) -> Nvidia:
        if prime == "none" or igpu is None:
            return Nvidia(branch=branch, open=open_)
        return Nvidia(
            branch=branch,
            open=open_,
            prime=prime,
            nvidia_bus=gpu.bus_id,
            intel_bus=igpu.bus_id if igpu.vendor_id == "8086" else "",
            amdgpu_bus=igpu.bus_id if igpu.vendor_id == "1002" else "",
        )

    choices = [
        Choice(
            id="nouveau",
            label="Nouveau (open source)",
            detail="Works without NVIDIA's software. Slower in games, no CUDA, and some cards can't change clock speeds.",
            settings=replace(current, nvidia=None),
            recommended=entry["branch"] == "nouveau",
        )
    ]
    branch = entry["branch"]
    if branch == "nouveau":
        choices.append(
            Choice(
                id="nvidia",
                label="NVIDIA's driver",
                detail="",
                settings=current,
                available=False,
                reason=f"NVIDIA's last driver for this card doesn't work with Linux {_kernel(system)}.",
                unfree=True,
            )
        )
    else:
        available, version, why = _branch_info(system, branch)
        modules = "open kernel modules" if entry["open"] else "proprietary kernel modules"
        label = BRANCH_LABELS[branch] + (f" {version}" if version else "")
        reason = "" if available else why
        if hybrid:
            choices += [
                Choice(
                    id="nvidia-offload",
                    label=label + ", power saving",
                    detail=(
                        f"The {igpu.vendor} graphics draw the desktop; the NVIDIA card runs the apps you "
                        "start with “Run with dedicated GPU” (or nvidia-offload). Best for battery. "
                        f"Uses {modules}."
                    ),
                    settings=replace(current, nvidia=nv(branch, entry["open"], "offload")),
                    available=available,
                    reason=reason,
                    recommended=available,
                    unfree=True,
                ),
                Choice(
                    id="nvidia-sync",
                    label=label + ", for everything",
                    detail="The NVIDIA card draws everything. Faster, uses more battery.",
                    settings=replace(current, nvidia=nv(branch, entry["open"], "sync")),
                    available=available,
                    reason=reason,
                    unfree=True,
                ),
            ]
        else:
            choices.append(
                Choice(
                    id="nvidia",
                    label=label,
                    detail=f"Full speed, CUDA and NVENC. Uses {modules}.",
                    settings=replace(current, nvidia=nv(branch, entry["open"], "none")),
                    available=available,
                    reason=reason,
                    recommended=available,
                    unfree=True,
                )
            )
        if branch == "production":
            nf_available, nf_version, nf_why = _branch_info(system, "new_feature")
            choices.append(
                Choice(
                    id="nvidia-new-feature",
                    label=BRANCH_LABELS["new_feature"] + (f" {nf_version}" if nf_version else ""),
                    detail="NVIDIA's newer series, with features before they reach the main one.",
                    settings=replace(
                        current, nvidia=nv("new_feature", True, "offload" if hybrid else "none")
                    ),
                    available=nf_available,
                    reason="" if nf_available else nf_why,
                    unfree=True,
                )
            )
        if not any(c.recommended for c in choices):
            choices[0].recommended = True

    for c in choices:
        c.selected = _same_nvidia(c, current)
    return Row(
        id=gpu.slot,
        kind="gpu",
        title=gpu.name,
        subtitle=f"{gpu.vendor} graphics · {gpu.slot}",
        status=_status(gpu),
        choices=choices,
    )


def _same_nvidia(choice: Choice, current: Settings) -> bool:
    a, b = choice.settings.nvidia, current.nvidia
    if a is None or b is None:
        return a is None and b is None and choice.id == "nouveau"
    return (a.branch, a.prime) == (b.branch, b.prime)


def _extra(id_: str, label: str, detail: str, current: Settings, field_: str, value, recommended=False) -> Extra:
    on = getattr(current, field_) == value
    off_value = None if not isinstance(value, bool) else False
    return Extra(
        id=id_,
        label=label,
        detail=detail,
        on=on,
        settings_on=replace(current, **{field_: value}),
        settings_off=replace(current, **{field_: off_value}),
        recommended=recommended,
    )


def _amd_row(gpu: Device, current: Settings) -> Row:
    extras = [
        _extra("amd-compute", "Compute (ROCm OpenCL)", "For apps that compute on the GPU, like Blender and Darktable.", current, "amd_compute", True)
    ]
    if gpu.driver == "radeon":
        extras.append(
            _extra(
                "amd-legacy",
                "Use amdgpu instead of radeon",
                "For Radeon HD 7000 to R9 290 cards (GCN 1 and 2): Vulkan and better speed. Older cards keep radeon.",
                current,
                "amd_legacy",
                True,
            )
        )
    return Row(
        id=gpu.slot,
        kind="gpu",
        title=gpu.name,
        subtitle=f"AMD graphics · {gpu.slot}",
        status=_status(gpu) + " — works without changes",
        extras=extras,
    )


def _intel_row(gpu: Device, current: Settings) -> Row:
    va = intel_va_driver(gpu.device_id)
    va_name = "intel-media-driver" if va == "media" else "intel-vaapi-driver"
    return Row(
        id=gpu.slot,
        kind="gpu",
        title=gpu.name,
        subtitle=f"Intel graphics · {gpu.slot}",
        status=_status(gpu) + " — works without changes",
        extras=[
            _extra(
                "intel-va",
                "Hardware video decoding",
                f"Smoother video that uses less battery ({va_name}).",
                current,
                "intel_va",
                va,
                recommended=True,
            ),
            _extra(
                "intel-compute",
                "Compute (OpenCL, Level Zero)",
                "For apps that compute on the GPU. Intel graphics from 2020 (Gen12) and newer.",
                current,
                "intel_compute",
                True,
            ),
        ],
    )


def _wifi_row(card: Device, current: Settings, system: dict) -> Row:
    row = Row(
        id=card.slot,
        kind="wifi",
        title=card.name,
        subtitle=f"{card.vendor} Wi-Fi · {card.slot}",
        status=_status(card),
    )
    if card.vendor_id != "14e4" or card.device_id not in BROADCOM_WL:
        row.status += "" if card.driver is None else " — works without changes"
        return row
    broadcom = system.get("broadcom", {})
    available = bool(broadcom.get("available", True))
    needs_wl = card.driver in (None, "wl")
    row.choices = [
        Choice(
            id="broadcom-open",
            label="Open-source driver",
            detail="b43, brcmsmac or brcmfmac, from Linux itself.",
            settings=replace(current, broadcom=False),
            recommended=not needs_wl,
            selected=not current.broadcom,
        ),
        Choice(
            id="broadcom-wl",
            label="Broadcom STA (wl)",
            detail=(
                "Broadcom's own driver. It is unfree, unmaintained and has known security problems "
                "(CVE-2019-9501, CVE-2019-9502); use it only if the open driver doesn't work."
            ),
            settings=replace(current, broadcom=True),
            available=available,
            reason="" if available else broadcom.get("reason", f"It doesn't build with Linux {_kernel(system)}."),
            recommended=needs_wl and available,
            unfree=True,
            selected=current.broadcom,
        ),
    ]
    return row


def _cpu_row(cpu: CPU, system: dict) -> Row:
    updates = system.get("microcode")
    if updates is None:
        status = f"Microcode revision {cpu.microcode}" if cpu.microcode else "Microcode: unknown"
    elif updates:
        status = "Microcode updates load at every start" + (f" (revision {cpu.microcode})" if cpu.microcode else "")
    else:
        status = "Microcode updates are off (hardware.cpu.*.updateMicrocode)"
    return Row(id="cpu", kind="cpu", title=cpu.model, subtitle=f"{cpu.vendor} processor", status=status)


def rows(hw: Hardware, current: Settings, system: dict | None = None) -> list[Row]:
    system = load_system() if system is None else system
    out: list[Row] = []
    for gpu in hw.gpus:
        if gpu.vendor_id == "10de":
            out.append(_nvidia_row(gpu, hw, current, system))
        elif gpu.vendor_id == "1002":
            out.append(_amd_row(gpu, current))
        elif gpu.vendor_id == "8086":
            out.append(_intel_row(gpu, current))
        else:
            out.append(Row(id=gpu.slot, kind="gpu", title=gpu.name, subtitle=f"{gpu.vendor} graphics · {gpu.slot}", status=_status(gpu)))
    if hw.gpus:
        out.append(
            Row(
                id="graphics",
                kind="graphics",
                title="Games",
                subtitle="All graphics cards",
                status="",
                extras=[
                    _extra(
                        "games32",
                        "32-bit graphics libraries",
                        "Steam and older games need them.",
                        current,
                        "games32",
                        True,
                    )
                ],
            )
        )
    for card in hw.wifi:
        out.append(_wifi_row(card, current, system))
    # Printers aren't detected here (USB and network ones come and go): the
    # manufacturers' drivers are one choice for all of them (ADR 0033).
    out.append(
        Row(
            id="printers",
            kind="printers",
            title="Printers",
            subtitle="Canon, Samsung and HP printers the free drivers don't run",
            status="Free drivers (most printers need nothing else)"
            if not current.printers
            else "The manufacturers' drivers are installed",
            extras=[
                _extra(
                    "printers",
                    "Printer drivers from Canon, Samsung and HP (not free software)",
                    "Only if your printer doesn't print with the free drivers: many Canon "
                    "PIXMA/MAXIFY, older Samsung lasers, some HP models.",
                    current,
                    "printers",
                    True,
                )
            ],
        )
    )
    if hw.cpu:
        out.append(_cpu_row(hw.cpu, system))
    return out


def recommend(hw: Hardware, current: Settings, system: dict | None = None) -> Settings:
    """The current settings with each device's recommended driver chosen.

    Only drivers are chosen here (NVIDIA, Broadcom, Intel video decoding);
    the other extras stay as they are.
    """
    settings = current
    for row in rows(hw, current, system):
        rec = next((c for c in row.choices if c.recommended and c.available), None)
        if rec is not None:
            if row.kind == "gpu":
                settings = replace(settings, nvidia=rec.settings.nvidia)
            elif row.kind == "wifi":
                settings = replace(settings, broadcom=rec.settings.broadcom)
        for extra in row.extras:
            if extra.recommended and not extra.on:
                settings = replace(settings, **_diff(extra.settings_on, current))
    return settings


def _diff(a: Settings, b: Settings) -> dict:
    return {k: getattr(a, k) for k in a.__dataclass_fields__ if getattr(a, k) != getattr(b, k)}


def needs_attention(hw: Hardware, current: Settings, system: dict | None = None) -> bool:
    """Whether a device needs a driver the system doesn't have yet: an NVIDIA card
    on Nouveau when NVIDIA's driver is recommended, or a Broadcom card without
    Wi-Fi. (The Welcome window shows its Drivers page then.)"""
    rec = recommend(hw, current, system)
    return (rec.nvidia is not None and current.nvidia is None) or (rec.broadcom and not current.broadcom)
