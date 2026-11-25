"""tulsi-ai-check: which local language models this computer can run (ADR 0023).

Reads the hardware from /proc and /sys (and nvidia-smi when NVIDIA's driver is
installed), then says which *size classes* of model fit, where they would run
(graphics card, shared, processor) and roughly how fast. The example models come
from ai-models.json, which ages quickly; the size classes and the arithmetic do
not.

Rule of thumb: a model quantised to 4 bits (Q4, what Ollama downloads by
default) needs about 0.6 GB per billion parameters, plus about 1.5 GB for the
context and the runtime.

The result is saved to ~/.cache/tulsi/ai-check.json, which the Software
Center's AI Agents page shows.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from importlib import resources
from pathlib import Path

GB = 1000**3
GIB = 1024**3
GB_PER_BILLION = 0.6
OVERHEAD_GB = 1.5
# Of the RAM, what a model can have and leave the desktop usable.
RAM_SHARE = 0.7
# Of a graphics card's memory, what the model can have (the desktop uses some).
VRAM_SHARE = 0.9
# AMD reports an integrated GPU's carve-out as VRAM; real cards have more.
INTEGRATED_VRAM_MAX = 2 * GIB

VENDORS = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}
VENDOR_NAMES = {"nvidia": "NVIDIA", "amd": "AMD", "intel": "Intel", "other": "Other"}


@dataclass
class GPU:
    vendor: str
    name: str
    vram: int | None = None  # bytes, None when unknown
    integrated: bool = False


@dataclass
class Hardware:
    cpu: str = "Unknown processor"
    cores: int = 1
    threads: int = 1
    avx2: bool = False
    avx512: bool = False
    ram: int = 0
    disk_free: int | None = None
    gpus: list[GPU] = field(default_factory=list)

    @property
    def dedicated_gpu(self) -> GPU | None:
        cards = [g for g in self.gpus if not g.integrated and g.vram]
        return max(cards, key=lambda g: g.vram or 0, default=None)


@dataclass
class Fit:
    id: str
    label: str
    need_gb: float
    where: str  # "gpu", "split", "cpu" or "no"
    speed: str  # "fast", "usable", "slow" or ""
    good_for: str
    examples: list[str]


# ------------------------------------------------------------------ detection


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace").strip()
    except OSError:
        return ""


def _cpu(root: Path, hw: Hardware) -> None:
    text = _read(root / "proc/cpuinfo")
    threads, cores, flags = 0, set(), set()
    physical = core = ""
    for line in text.splitlines() + [""]:
        key, _, value = (part.strip() for part in line.partition(":"))
        if key == "processor":
            threads += 1
        elif key == "model name" and hw.cpu == "Unknown processor":
            hw.cpu = " ".join(value.split())
        elif key == "physical id":
            physical = value
        elif key == "core id":
            core = value
        elif key == "flags" and not flags:
            flags = set(value.split())
        elif not line.strip() and core:
            cores.add((physical, core))
            physical = core = ""
    hw.threads = max(threads, 1)
    hw.cores = len(cores) or hw.threads
    hw.avx2 = "avx2" in flags
    hw.avx512 = "avx512f" in flags


def _ram(root: Path, hw: Hardware) -> None:
    for line in _read(root / "proc/meminfo").splitlines():
        if line.startswith("MemTotal:"):
            hw.ram = int(line.split()[1]) * 1024
            return


def _nvidia_smi() -> list[tuple[str, int]]:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return []
    try:
        out = subprocess.run(
            [smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    cards = []
    for line in out.splitlines():
        name, _, mib = line.rpartition(",")
        if mib.strip().isdigit():
            cards.append((name.strip(), int(mib.strip()) * 1024 * 1024))
    return cards


def _gpus(root: Path, hw: Hardware, use_nvidia_smi: bool) -> None:
    drm = root / "sys/class/drm"
    nvidia = _nvidia_smi() if use_nvidia_smi else []
    seen = set()
    for card in sorted(drm.glob("card[0-9]*")) if drm.is_dir() else []:
        if "-" in card.name:  # card0-HDMI-A-1: a connector, not a card
            continue
        device = card / "device"
        address = os.path.realpath(device)
        if address in seen:
            continue
        seen.add(address)
        vendor = VENDORS.get(_read(device / "vendor"), "other")
        name = _read(device / "product_name") or f"{VENDOR_NAMES[vendor]} graphics"
        vram = _read(device / "mem_info_vram_total")
        gpu = GPU(vendor, name, int(vram) if vram.isdigit() else None)
        if vendor == "intel":
            gpu.integrated = True
            gpu.vram = None
        elif vendor == "amd" and gpu.vram is not None and gpu.vram < INTEGRATED_VRAM_MAX:
            gpu.integrated = True
        elif vendor == "nvidia" and nvidia:
            gpu.name, gpu.vram = nvidia.pop(0)
        hw.gpus.append(gpu)
    # nvidia-smi saw cards sysfs did not (or no sysfs at all).
    hw.gpus += [GPU("nvidia", name, vram) for name, vram in nvidia]


def detect(root: Path = Path("/"), *, use_nvidia_smi: bool = True) -> Hardware:
    hw = Hardware()
    _cpu(root, hw)
    _ram(root, hw)
    _gpus(root, hw, use_nvidia_smi)
    try:
        hw.disk_free = shutil.disk_usage(Path.home()).free
    except OSError:
        pass
    return hw


# -------------------------------------------------------------------- advice


def load_classes() -> tuple[str, list[dict]]:
    data = json.loads(resources.files(__package__).joinpath("ai-models.json").read_text())
    return data["as_of"], data["classes"]


def need_gb(params_b: float) -> float:
    return params_b * GB_PER_BILLION + OVERHEAD_GB


def fits(hw: Hardware, classes: list[dict]) -> list[Fit]:
    gpu = hw.dedicated_gpu
    gpu_budget = (gpu.vram or 0) * VRAM_SHARE / GB if gpu else 0.0
    ram_budget = hw.ram * RAM_SHARE / GB
    result = []
    for c in classes:
        need = need_gb(c["params_b"])
        if need <= gpu_budget:
            where, speed = "gpu", "fast"
        elif gpu and need <= gpu_budget + ram_budget:
            where, speed = "split", "usable" if need <= gpu_budget * 1.5 else "slow"
        elif need <= ram_budget:
            where = "cpu"
            if c["params_b"] <= 3:
                speed = "usable"
            elif c["params_b"] <= 8 and hw.avx2 and hw.threads >= 8:
                speed = "usable"
            else:
                speed = "slow"
        else:
            where, speed = "no", ""
        result.append(Fit(c["id"], c["label"], round(need, 1), where, speed,
                          c["good_for"], list(c["examples"])))
    return result


def runner(hw: Hardware) -> tuple[str, str]:
    """The Ollama package to install, and why."""
    gpu = hw.dedicated_gpu
    if gpu and gpu.vendor == "nvidia":
        return "ollama-cuda", "uses your NVIDIA card (needs NVIDIA's driver)"
    if gpu and gpu.vendor == "amd":
        return "ollama-rocm", "uses your AMD card through ROCm; if your card is not supported, try ollama-vulkan"
    if gpu:
        return "ollama-vulkan", "uses your graphics card through Vulkan"
    return "ollama", "runs on the processor"


def verdict(results: list[Fit]) -> str:
    """One line for the Software Center: the largest class that runs well."""
    good = [f for f in results if f.where != "no" and f.speed in ("fast", "usable")]
    if not good:
        some = [f for f in results if f.where != "no"]
        if not some:
            return "This computer has too little memory for local models; use a cloud agent."
        return f"Local models up to {some[-1].label} fit, but run slowly here."
    best = good[-1]
    place = {"gpu": "on the graphics card", "split": "on the graphics card and processor",
             "cpu": "on the processor"}[best.where]
    return f"Models up to {best.label} run {place}."


def report(hw: Hardware, results: list[Fit], as_of: str) -> dict:
    package, why = runner(hw)
    return {
        "hardware": asdict(hw),
        "fits": [asdict(f) for f in results],
        "runner": {"package": package, "why": why},
        "verdict": verdict(results),
        "examples_as_of": as_of,
    }


def cache_file() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "tulsi" / "ai-check.json"


def _last() -> dict:
    try:
        data = json.loads(cache_file().read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def last_verdict() -> str | None:
    """The last check's one-line result, if it has run on this account."""
    verdict = _last().get("verdict")
    return verdict if isinstance(verdict, str) else None


def last_runner() -> str | None:
    """The Ollama package the last check recommended (ollama-cuda, …)."""
    runner = _last().get("runner")
    return runner.get("package") if isinstance(runner, dict) else None


# -------------------------------------------------------------------- output


def _gb(n: int | None) -> str:
    return "unknown" if n is None else f"{n / GIB:.1f} GB"


class _Style:
    def __init__(self, on: bool):
        self.on = on

    def __call__(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.on else text


def render(hw: Hardware, results: list[Fit], as_of: str, colour: bool) -> str:
    s = _Style(colour)
    out = [s("1", "TulsiOS: which AI models can this computer run?"), ""]
    out.append(s("1;32", "Your hardware"))
    cpu = f"{hw.cpu}, {hw.cores} cores / {hw.threads} threads"
    simd = [n for n, ok in (("AVX2", hw.avx2), ("AVX-512", hw.avx512)) if ok]
    out.append(f"  Processor  {cpu}" + (f" ({', '.join(simd)})" if simd else ""))
    out.append(f"  Memory     {_gb(hw.ram)}")
    if not hw.gpus:
        out.append("  Graphics   none found")
    for g in hw.gpus:
        if g.integrated:
            kind = "integrated, shares the memory"
        elif g.vram:
            kind = f"{_gb(g.vram)} of its own memory"
        else:
            kind = "its memory is unknown, so it is not counted"
        out.append(f"  Graphics   {g.name} ({kind})")
    out.append(f"  Disk free  {_gb(hw.disk_free)} in your home folder")
    out.append("")

    out.append(s("1;32", "What fits") + s("2", f"   (4-bit models; examples as of {as_of})"))
    marks = {"gpu": s("32", "✔ graphics card"), "split": s("33", "✔ card + processor"),
             "cpu": s("33", "✔ processor"), "no": s("31", "✘ too big")}
    for f in results:
        speed = f" — {f.speed}" if f.speed else ""
        out.append(f"  {f.label:<11} ~{f.need_gb:>5.1f} GB  {marks[f.where]}{speed}")
        if f.where != "no":
            out.append(s("2", f"              {f.good_for}; e.g. {', '.join(f.examples)}"))
    out.append("")
    out.append(s("1", verdict(results)))
    biggest = next((f for f in reversed(results) if f.where != "no"), None)
    if biggest and hw.disk_free is not None and hw.disk_free / GB < biggest.need_gb * 1.2:
        out.append(s("31", f"Your disk has little room: a {biggest.label} model takes about "
                           f"{biggest.need_gb:.0f} GB."))
    out.append("")

    package, why = runner(hw)
    out.append(s("1;32", "How to start"))
    if biggest is None:
        out.append("  Use a cloud agent: the Software Center's AI Agents page lists them")
        out.append("  (ocimum-software-center --page ai). They need an account, not hardware.")
        return "\n".join(out)
    out.append(f"  1. Install {s('1', package)} ({why}) or llama.cpp,")
    out.append("     from the Software Center's AI Agents page: ocimum-software-center --page ai")
    out.append("  2. Start it:  ollama serve        (leave it running)")
    # The largest model that runs well, else the smallest that runs at all.
    good = [f for f in results if f.where != "no" and f.speed in ("fast", "usable")]
    runs = [f for f in results if f.where != "no"]
    example = (good[-1] if good else runs[0] if runs else None)
    example = example.examples[0] if example else "qwen3:1.7b"
    out.append(f"  3. Try one:   ollama run {example}")
    out.append("  Agents such as OpenCode, Aider, Goose and Crush can use it as their model.")
    out.append("")
    out.append(s("2", "These are rough pointers: new models appear every month, and the same size"))
    out.append(s("2", "keeps getting smarter. Cloud agents need none of this hardware."))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tulsi-ai-check", description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    parser.add_argument("--root", default="/", help=argparse.SUPPRESS)  # tests
    args = parser.parse_args(argv)

    root = Path(args.root)
    hw = detect(root, use_nvidia_smi=root == Path("/"))
    as_of, classes = load_classes()
    results = fits(hw, classes)
    data = report(hw, results, as_of)
    try:
        cache_file().parent.mkdir(parents=True, exist_ok=True)
        cache_file().write_text(json.dumps(data, indent=2) + "\n")
    except OSError:
        pass
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        colour = sys.stdout.isatty() and "NO_COLOR" not in os.environ
        print(render(hw, results, as_of, colour))
    return 0


if __name__ == "__main__":
    sys.exit(main())
