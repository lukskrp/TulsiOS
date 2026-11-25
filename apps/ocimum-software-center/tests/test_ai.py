from pathlib import Path

from ocimum_software_center import ai_agents, ai_check

GiB = 1024**3


def make_root(tmp: Path, *, ram_gib: int, threads: int = 8, avx2: bool = True,
              cards: list[tuple[str, str, int | None]] = ()) -> Path:
    """A fake / with /proc/cpuinfo, /proc/meminfo and /sys/class/drm cards
    given as (vendor id, product name, VRAM bytes)."""
    proc = tmp / "proc"
    proc.mkdir(parents=True)
    flags = "fpu sse sse2" + (" avx avx2" if avx2 else "")
    blocks = [
        f"processor\t: {i}\nmodel name\t: Test CPU 9000\nphysical id\t: 0\n"
        f"core id\t\t: {i // 2}\nflags\t\t: {flags}\n"
        for i in range(threads)
    ]
    (proc / "cpuinfo").write_text("\n".join(blocks) + "\n")
    (proc / "meminfo").write_text(f"MemTotal:       {ram_gib * 1024 * 1024} kB\nMemFree: 1 kB\n")
    drm = tmp / "sys/class/drm"
    drm.mkdir(parents=True)
    for i, (vendor, name, vram) in enumerate(cards):
        device = tmp / f"sys/devices/pci0000:00/0000:0{i}:00.0"
        device.mkdir(parents=True)
        (device / "vendor").write_text(vendor + "\n")
        if name:
            (device / "product_name").write_text(name + "\n")
        if vram is not None:
            (device / "mem_info_vram_total").write_text(f"{vram}\n")
        (drm / f"card{i}").mkdir()
        (drm / f"card{i}" / "device").symlink_to(device)
        (drm / f"card{i}-HDMI-A-1").mkdir()  # a connector: ignored
    return tmp


def check(root: Path):
    hw = ai_check.detect(root, use_nvidia_smi=False)
    _, classes = ai_check.load_classes()
    return hw, {f.id: f for f in ai_check.fits(hw, classes)}


def test_cpu_only_laptop(tmp_path):
    hw, fit = check(make_root(tmp_path, ram_gib=8, threads=8))
    assert hw.cpu == "Test CPU 9000"
    assert (hw.cores, hw.threads, hw.avx2) == (4, 8, True)
    assert hw.gpus == []
    assert fit["tiny"].where == "cpu" and fit["tiny"].speed == "usable"
    assert fit["small"].where == "cpu"
    assert fit["medium"].where == "no"
    assert ai_check.runner(hw)[0] == "ollama"


def test_amd_card_vram_from_sysfs(tmp_path):
    hw, fit = check(make_root(tmp_path, ram_gib=32,
                              cards=[("0x1002", "AMD Radeon RX 7800 XT", 16 * GiB)]))
    [gpu] = hw.gpus
    assert gpu.vendor == "amd" and not gpu.integrated and gpu.vram == 16 * GiB
    assert fit["medium"].where == "gpu" and fit["medium"].speed == "fast"
    assert fit["large"].where == "split"
    assert ai_check.runner(hw)[0] == "ollama-rocm"


def test_amd_apu_counts_as_integrated(tmp_path):
    hw, fit = check(make_root(tmp_path, ram_gib=16, cards=[("0x1002", "", 512 * 1024 * 1024)]))
    assert hw.gpus[0].integrated
    assert hw.dedicated_gpu is None
    assert fit["small"].where == "cpu"


def test_nvidia_card_from_nvidia_smi(tmp_path, monkeypatch):
    root = make_root(tmp_path, ram_gib=32, cards=[("0x10de", "", None), ("0x8086", "", None)])
    monkeypatch.setattr(ai_check, "_nvidia_smi", lambda: [("NVIDIA GeForce RTX 4070", 12 * GiB)])
    hw = ai_check.detect(root, use_nvidia_smi=True)
    _, classes = ai_check.load_classes()
    fit = {f.id: f for f in ai_check.fits(hw, classes)}
    assert [g.vendor for g in hw.gpus] == ["nvidia", "intel"]
    assert hw.dedicated_gpu.name == "NVIDIA GeForce RTX 4070"
    assert fit["medium"].where == "gpu"
    assert fit["huge"].where == "no" or fit["huge"].speed == "slow"
    assert ai_check.runner(hw)[0] == "ollama-cuda"
    assert "graphics card" in ai_check.verdict(list(fit.values()))


def test_tiny_machine_verdict(tmp_path):
    _, fit = check(make_root(tmp_path, ram_gib=2, threads=2, avx2=False))
    assert all(f.where == "no" for f in fit.values())
    assert "cloud agent" in ai_check.verdict(list(fit.values()))
    text = ai_check.render(ai_check.detect(tmp_path, use_nvidia_smi=False),
                           list(fit.values()), "2026-11", colour=False)
    assert "ollama" not in text and "cloud agent" in text


def test_render_and_cache(tmp_path, monkeypatch, capsys):
    root = make_root(tmp_path / "root", ram_gib=16)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    assert ai_check.main(["--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "Your hardware" in out and "What fits" in out and "ollama run" in out
    assert "\033[" not in out  # not a terminal: no colour
    assert ai_check.last_verdict() is not None


def test_agent_list():
    sections = ai_agents.load()
    assert [s.kind for s in sections] == ["cloud-cli", "cloud-ide", "local-runner"]
    attrs = ai_agents.attrs(sections)
    assert len(attrs) == len(set(attrs))
    for name in ("opencode", "claude-code", "codex", "antigravity-cli", "ollama", "llama-cpp"):
        assert name in attrs
    for section in sections:
        for agent in section.agents:
            assert agent.name and agent.blurb and agent.homepage.startswith("https://")
