# ADR 0029: Drivers, and changes on trial until the next restart

Status: accepted (2026-11-25).

## Context

Linux Mint has a Driver Manager; TulsiOS had none.

- **An NVIDIA driver meant four lines through `tulsi config`** (the skill's table).
  Nothing helped the person choose the right series for their card, or set up a
  laptop's two GPUs.
- **A wrong driver can leave a black screen.** Nobody can click Undo then. Applying
  a driver while running (`nixos-rebuild switch`) also fails units, and tulsid then
  restores the file, so the change never took effect.
- **Nothing detected hardware.** Only the AI page's `ai_check` read
  `/sys/class/drm`.

The person asked for a graphical tool covering GPUs, Broadcom Wi-Fi and the CPU, with
unfree drivers turning on unfree software as a whole, a keep-or-revert check, and a
Drivers page in the Welcome window.

## Decision

**Settings: `tulsi.drivers`** (`nix/modules/drivers.nix`). The module turns a few
plain settings into NixOS's own options. Evaluation can't see the hardware, so the
app detects it and the module only follows the settings.

| Setting | What it sets |
| --- | --- |
| `nvidia.{enable,branch,open}` | `videoDrivers = [ "nvidia" ]`, `hardware.nvidia.{package,open,modesetting,powerManagement}`; the 470 series also accepts NVIDIA's licence (`nixpkgs.config.nvidia.acceptLicense`) |
| `nvidia.prime.{mode,nvidiaBusId,intelBusId,amdgpuBusId}` | PRIME offload (with `nvidia-offload`, fine-grained power management on the open modules, switcheroo-control) or sync |
| `amd.compute`, `amd.legacySupport` | `hardware.amdgpu.opencl`, `hardware.amdgpu.legacySupport` |
| `intel.videoAcceleration` (`media`/`i965`), `intel.compute` | intel-media-driver or intel-vaapi-driver (and `LIBVA_DRIVER_NAME`), intel-compute-runtime |
| `games32Bit` | `hardware.graphics.enable32Bit` |
| `broadcomWifi.enable` | broadcom-sta (`wl`), blacklisting b43/bcma/ssb/brcmsmac, allowed as insecure by name |

- **Assertions** say what's wrong in plain words: unfree software not allowed, a
  series that doesn't build with the kernel, PRIME without bus IDs.
- **`/etc/tulsi/drivers.json`** tells the app what this system can build: the
  kernel, each NVIDIA series' version, and whether it builds (nixpkgs' `broken`,
  plus `tulsi.drivers.brokenBranches`); also Broadcom and microcode.
- On kernel 7.3, the production (595), new-feature, 580, 535 and 470 series build;
  390 and 340 don't (nixpkgs marks them broken).

**The app and `tulsi-drivers`** (`apps/tulsi-drivers`, Python; GTK only in the
window).

- **Detection** reads `/sys/bus/pci/devices` (class 03 graphics, 0280 Wi-Fi, vendor,
  device, bound driver, `boot_vga`) and `/proc/cpuinfo`. Names come from hwdata's
  `pci.ids`.
- **NVIDIA's own list** of supported GPUs (`supported-gpus.json`, inside the 580
  driver) becomes `nvidia-gpus.json`: for each device id, the series and whether
  the open kernel modules support it. `scripts/update-nvidia-gpus.sh` regenerates
  it. The rules:
  - Turing and newer: production, with the open modules.
  - Maxwell to Volta: 580, proprietary.
  - Kepler: 470.
  - Older cards: Nouveau only.
  - A card newer than the list is treated as Turing or newer.
- **Laptops:** an NVIDIA card plus an Intel or AMD GPU that showed the boot screen
  gets "power saving" (offload, recommended) or "for everything" (sync).
- **AMD and Intel** keep their drivers. They get extras: video decoding
  (intel-media-driver from Broadwell, i965 before), compute, and amdgpu for GCN 1
  and 2 cards that use radeon.
- **Broadcom:** wl is recommended only when no open driver claimed the card.
- **The CPU's row** shows its microcode status.
- **The settings** live in a marked block of `configuration.nix`. It is written
  through `tulsi config`, so it is recorded, needs the person's password
  (`tulsi.*` lines are `org.tulsi.configure`) and can be undone. Unfree software,
  once allowed, stays allowed: by then the Software Center may have installed
  unfree apps.
- **Unfree:** choosing NVIDIA or Broadcom shows the licence and says that it turns
  on unfree software for the whole system (`nixpkgs.config.allowUnfree = true`).
  `tulsi-drivers set` needs `--accept-unfree`.
- **The Welcome window** gets a Drivers page when `tulsi-drivers recommend --check`
  finds a device that needs a driver: an NVIDIA card on Nouveau, or a Broadcom card
  without Wi-Fi.

**Changes on trial (tulsid).** `ApplyConfigTrial` (`tulsi config apply …
--at-restart`) builds the change for the next start with `nixos-rebuild boot`, then
commits it and records `/var/lib/tulsi/trial.json`.

- **systemd-boot (UEFI):**
  - The system before stays the default (`bootctl set-default`), and the new one
    starts once (`set-oneshot`). A black screen, then any restart, lands on the
    system before.
  - When tulsid starts in a boot that isn't the new system, it undoes the change
    (a revert, built for the next start) and leaves a notice.
- **GRUB (BIOS):** there is no one-shot. A change started with but not kept within
  `tulsi.daemon.trialTimeout` (10 minutes) is undone, so the restart after brings
  back the system before.
- **Keep:** `KeepTrial` (`tulsi trial keep`, `tulsi-drivers keep`, the login
  prompt) clears the boot loader's override.
  - It is a new polkit action, `org.tulsi.trial`, allowed for the person at the
    computer without a password.
  - Agent accounts can't keep: only the person can see whether it works.
- **Undo:** `UndoTrial` reverts before or after the restart.
- **While a change is on trial,** other changes wait (tulsid says to restart, or
  to keep or undo it first). A later rebuild would otherwise make a newer default
  that the trial's boot override ignores.

**Agents.** The skill sends agents to `tulsi-drivers` instead of
`hardware.nvidia.*`. tulsi-mcp has a read-only `list_drivers`.

## Consequences

- People pick drivers the way they would on Mint. A wrong pick costs a restart or
  two, not a reinstall.
- **NVIDIA with XLibre is verified only as far as a VM can go.** The modules build,
  and XLibre loads NVIDIA's X driver (`checks.drivers-nvidia`). Driving a real card
  needs real hardware: a desktop card, and a laptop with offload. Do that before
  release.
- Unfree, once on, stays on: switching back to Nouveau doesn't turn it off.
- The GRUB time limit means a person who walks away from a working new driver gets
  the old one back. The login prompt says so.
- `nvidia-gpus.json` ages with NVIDIA's releases. Cards newer than the list get
  the current driver, which is right for new cards.

## Verification

- `tulsi-drivers` package: 19 unit tests on fake `/sys` trees. They cover an RTX
  desktop, a Pascal laptop with Intel (580, offload, bus ids), Kepler on a kernel
  where 470 doesn't build, a card too old for any NVIDIA driver, AMD and old AMD, a
  BCM4360 without a driver, a Broadcom card on brcmfmac, the CPU row, and the
  `configuration.nix` block (insert, replace in place, remove, `allowUnfree` already
  there, an empty file, escaping).
- `checks.drivers-trial`, two VMs with real boot loaders:
  - **systemd-boot:** the one-shot and default entries are set. Other changes wait.
    The new system starts once. Restarting without keeping it starts the old one,
    and the change is undone in git with a notice. Kept, the new system stays the
    default.
  - **GRUB:** not kept within the (shortened) limit, the change is undone, and the
    next start is the old system.
- `checks.drivers-nvidia`: NVIDIA's open kernel modules for TulsiOS's kernel, and
  XLibre loading `nvidia_drv.so` without refusing its ABI.
- tulsid's trial logic has unit tests: same boot, started with it, went back, and
  generation numbers.
