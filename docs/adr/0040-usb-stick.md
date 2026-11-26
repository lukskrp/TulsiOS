# ADR 0040: tulsistick — USB sticks, Tulsi's own

Status: accepted (2026-11-27).

## Context

Mint writes ISOs and formats sticks with two small tools (Image Writer,
Formatter) that only ever offer removable drives. TulsiOS had nothing:
writing the ISO meant `dd` from a wiki line, formatting meant gparted or the
terminal, and nothing stopped a typo from naming the system disk.

Bottles/Lutris cover Windows programs through another agent; sticks had no
owner, so this is TulsiOS's own app in its own repository
(github:lukskrp/tulsistick), packaged here like Starah is separate from the
distro that ships it.

## Decision

**`tulsi.usbStick`** (`nix/modules/usb-stick.nix`): on with any TulsiOS
desktop, off on the live installer. Installs the Stick Writer and
`tulsi-stick`.

- **Only removable USB drives are listed** (`lsblk` removable/USB, whole
  disks); anything mounted as / or /boot can never appear, and writing or
  formatting a mounted drive refuses with "unmount it first".
- **Writing** copies with dd and reads the stick back for a SHA-256 check —
  a bad write says so instead of a mysteriously unbootable stick. Progress
  follows the bytes written.
- **Formatting** wipes the partition table and makes one fresh partition:
  FAT32 (everywhere), exFAT (big files, everywhere), NTFS (Windows), ext4
  (Linux), with a short label.
- **Confirming names the drive:** writing and formatting ask for the device
  name typed out (`/dev/sdb`), not just OK. Terminals get the same guards
  (`tulsi-stick list|write|format`).

## Consequences

- Installing TulsiOS on a new machine, and handing files to friends, stops
  needing the terminal — while the terminal keeps the identical tool.
- The app is developed outside TulsiOS (own repo, own tests); TulsiOS pins a
  revision with a hash, so a stick release is reproducible like everything
  else. Bumping it is one rev+hash change.
- Formatting still needs its tools on PATH (wrapped in): parted, dosfstools,
  exfatprogs, ntfs3g, e2fsprogs — no firmware, no licences.

## Verification

- tulsistick repo: 14 unit tests (only USB/removable disks listed, system
  disk hidden even when USB, bad JSON, mounts, write-to-file with
  verification, mounted/self-write refusal, format tool order and p1 naming,
  label validation, CLI list/write/format).
- `checks.usb-stick`: app, CLI and menu entry present; listing with no USB
  drive says to plug one in; writing a 10 MB image to a file "drive"
  verifies and matches byte for byte.
