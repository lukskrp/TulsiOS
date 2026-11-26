"""The drivers block in configuration.nix (ADR 0029).

The Drivers app keeps its settings in one marked block, so it can read them back
and replace them without touching anything else the person wrote:

      # Drivers (from the Drivers app; change them there or with tulsi-drivers).
      tulsi.drivers.nvidia = { enable = true; branch = "production"; open = true; };
      tulsi.drivers.games32Bit = true;
      nixpkgs.config.allowUnfree = true;
      # End of drivers.

The `tulsi.drivers.*` options are defined by TulsiOS's drivers module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

BEGIN = "# Drivers (from the Drivers app; change them there or with tulsi-drivers)."
END = "# End of drivers."
INDENT = "  "

_BLOCK = re.compile(rf"^[ \t]*{re.escape(BEGIN)}\n(.*?)^[ \t]*{re.escape(END)}\n?", re.M | re.S)
_UNFREE = re.compile(r"^(\s*)nixpkgs\.config\.allowUnfree\s*=\s*(true|false)\s*;", re.M)


@dataclass(frozen=True)
class Nvidia:
    branch: str = "production"
    open: bool = True
    prime: str = "none"  # "none", "offload" or "sync"
    nvidia_bus: str = ""
    intel_bus: str = ""
    amdgpu_bus: str = ""


@dataclass(frozen=True)
class Settings:
    nvidia: Nvidia | None = None  # None: Nouveau (the default)
    amd_compute: bool = False
    amd_legacy: bool = False
    intel_va: str | None = None  # "media", "i965" or None
    intel_compute: bool = False
    games32: bool = False
    broadcom: bool = False
    printers: bool = False  # the manufacturers' unfree printer drivers (ADR 0033)
    unfree: bool = False  # the block allows unfree software

    @property
    def needs_unfree(self) -> bool:
        return self.nvidia is not None or self.broadcom or self.printers

    def to_json(self) -> dict:
        out = {k: getattr(self, k) for k in self.__dataclass_fields__ if k != "nvidia"}
        out["nvidia"] = None if self.nvidia is None else dict(self.nvidia.__dict__)
        return out


def _nix_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("${", "\\${") + '"'


def _b(v: bool) -> str:
    return "true" if v else "false"


def render(settings: Settings, unfree_elsewhere: bool = False) -> list[str]:
    """The block's lines (without indentation), or [] when there is nothing to say."""
    lines = []
    nv = settings.nvidia
    if nv is not None:
        parts = [f"enable = true;", f"branch = {_nix_str(nv.branch)};", f"open = {_b(nv.open)};"]
        if nv.prime != "none":
            prime = [f"mode = {_nix_str(nv.prime)};", f"nvidiaBusId = {_nix_str(nv.nvidia_bus)};"]
            if nv.intel_bus:
                prime.append(f"intelBusId = {_nix_str(nv.intel_bus)};")
            if nv.amdgpu_bus:
                prime.append(f"amdgpuBusId = {_nix_str(nv.amdgpu_bus)};")
            parts.append("prime = { " + " ".join(prime) + " };")
        lines.append("tulsi.drivers.nvidia = { " + " ".join(parts) + " };")
    if settings.amd_compute:
        lines.append("tulsi.drivers.amd.compute = true;")
    if settings.amd_legacy:
        lines.append("tulsi.drivers.amd.legacySupport = true;")
    if settings.intel_va:
        lines.append(f"tulsi.drivers.intel.videoAcceleration = {_nix_str(settings.intel_va)};")
    if settings.intel_compute:
        lines.append("tulsi.drivers.intel.compute = true;")
    if settings.games32:
        lines.append("tulsi.drivers.games32Bit = true;")
    if settings.broadcom:
        lines.append("tulsi.drivers.broadcomWifi.enable = true;")
    if settings.printers:
        lines.append("tulsi.printingScanning.unfreeDrivers = true;")
    # Unfree software stays allowed once allowed: by then the Software Center may
    # have installed unfree apps that would stop building without it.
    if (settings.unfree or settings.needs_unfree) and not unfree_elsewhere:
        lines.append("nixpkgs.config.allowUnfree = true;")
    return lines


def _attr(body: str, name: str) -> str | None:
    m = re.search(rf"\b{name}\s*=\s*(\"(?:[^\"\\]|\\.)*\"|true|false)\s*;", body)
    if not m:
        return None
    v = m.group(1)
    return v[1:-1] if v.startswith('"') else v


def parse(config: str) -> Settings:
    """The settings in configuration.nix's drivers block (defaults when there is none)."""
    m = _BLOCK.search(config)
    if not m:
        return Settings()
    body = m.group(1)
    nvidia = None
    nv = re.search(r"tulsi\.drivers\.nvidia\s*=\s*\{(.*)\}\s*;", body)
    if nv and _attr(nv.group(1), "enable") == "true":
        inner = nv.group(1)
        prime_m = re.search(r"prime\s*=\s*\{(.*?)\}", inner)
        prime = prime_m.group(1) if prime_m else ""
        outer = inner.replace(prime_m.group(0), "") if prime_m else inner
        nvidia = Nvidia(
            branch=_attr(outer, "branch") or "production",
            open=_attr(outer, "open") != "false",
            prime=_attr(prime, "mode") or "none",
            nvidia_bus=_attr(prime, "nvidiaBusId") or "",
            intel_bus=_attr(prime, "intelBusId") or "",
            amdgpu_bus=_attr(prime, "amdgpuBusId") or "",
        )
    va = re.search(r'tulsi\.drivers\.intel\.videoAcceleration\s*=\s*"(\w+)"', body)

    def on(path: str) -> bool:
        return re.search(rf"tulsi\.drivers\.{re.escape(path)}\s*=\s*true\s*;", body) is not None

    return Settings(
        nvidia=nvidia,
        amd_compute=on("amd.compute"),
        amd_legacy=on("amd.legacySupport"),
        intel_va=va.group(1) if va else None,
        intel_compute=on("intel.compute"),
        games32=on("games32Bit"),
        broadcom=on("broadcomWifi.enable"),
        printers=re.search(r"tulsi\.printingScanning\.unfreeDrivers\s*=\s*true\s*;", body) is not None,
        unfree=_UNFREE.search(body) is not None and _UNFREE.search(body).group(2) == "true",
    )


def with_settings(config: str, settings: Settings) -> str:
    """configuration.nix with the drivers block replaced (or added, or removed)."""
    without = _BLOCK.sub("", config)
    # Allowing unfree software elsewhere in the file: keep that line, true.
    unfree_elsewhere = False
    outside = _UNFREE.search(without)
    if outside:
        if settings.needs_unfree and outside.group(2) == "false":
            without = _UNFREE.sub(lambda m: m.group(1) + "nixpkgs.config.allowUnfree = true;", without, count=1)
            unfree_elsewhere = True
        else:
            unfree_elsewhere = outside.group(2) == "true"
    lines = render(settings, unfree_elsewhere)
    m = _BLOCK.search(config)
    if not lines:
        # Also the blank line that was put before the block.
        return _tidy(re.sub(r"\n[ \t]*\n(\s*\}\s*)$", r"\n\1", without))
    block = INDENT + BEGIN + "\n" + "".join(INDENT + line + "\n" for line in lines) + INDENT + END + "\n"
    if m:
        # Where it was.
        return config[: m.start()] + block + config[m.end() :]
    if not without.strip():
        return "{ config, lib, pkgs, ... }:\n{\n" + block + "}\n"
    end = without.rstrip().rfind("}")
    if end < 0:
        raise ValueError("configuration.nix has no closing brace")
    head = without[:end].rstrip("\n")
    return head + "\n\n" + block + without[end:].rstrip() + "\n"


def _tidy(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text)


def changed(old: Settings, new: Settings) -> bool:
    return replace(old, unfree=False) != replace(new, unfree=False)
