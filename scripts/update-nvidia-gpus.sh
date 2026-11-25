#!/usr/bin/env bash
# Regenerates apps/tulsi-drivers/tulsi_drivers/nvidia-gpus.json (ADR 0029) from
# NVIDIA's own list of supported GPUs, inside the legacy_580 driver (which lists
# every GPU, with the legacy branch for the old ones and "kernelopen" for those
# the open kernel modules support). Run it when tulsipkgs moves NVIDIA's branches.
set -euo pipefail
cd "$(dirname "$0")/.."
src=$(nix build --no-link --print-out-paths --impure --expr \
  "(builtins.getFlake (toString ./.)).nixosConfigurations.tulsi-vm.config.boot.kernelPackages.nvidiaPackages.legacy_580.src")
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
sh "$src" --extract-only --target "$work/x" >/dev/null
python3 - "$work/x/supported-gpus/supported-gpus.json" apps/tulsi-drivers/tulsi_drivers/nvidia-gpus.json "$(basename "$src")" <<'EOF'
import json, sys

chips = json.load(open(sys.argv[1]))["chips"]
gpus = {}
for chip in chips:
    devid = chip["devid"].lower().removeprefix("0x")
    legacy = chip.get("legacybranch")
    features = chip.get("features", [])
    if legacy is None:
        # Turing and newer have the open modules (and the GSP); NVIDIA's current
        # branches dropped the older ones, which stay on the 580 series.
        branch = "production" if "kernelopen" in features else "legacy_580"
    elif legacy == "470.xx":
        branch = "legacy_470"
    else:
        branch = "nouveau"  # 390 and older: no build for TulsiOS's kernel
    entry = gpus.setdefault(devid, {"name": chip["name"], "branch": branch,
                                    "open": "kernelopen" in features,
                                    "runtimepm": "runtimepm" in features})
    # A device id can be listed once per subsystem; any listing with the
    # feature counts.
    entry["open"] |= "kernelopen" in features
    entry["runtimepm"] |= "runtimepm" in features
out = {"source": sys.argv[3], "gpus": dict(sorted(gpus.items()))}
with open(sys.argv[2], "w") as f:
    json.dump(out, f, indent=0, separators=(",", ":"))
    f.write("\n")
print(f"{len(gpus)} GPUs from {sys.argv[3]}")
EOF
