# The TulsiOS live ISO (Phase 7, ADR 0016)

    nix build .#iso
    # result/iso/tulsios-0.1.0-x86_64-linux.iso, about 3–4 GB

A hybrid ISO: the same file boots from a DVD, or from a USB stick on BIOS and UEFI
machines. Write it to a stick with `dd` (Linux) or Etcher/Rufus in DD mode (Windows):

    sudo dd if=tulsios-0.1.0-x86_64-linux.iso of=/dev/sdX bs=4M conv=fsync status=progress

It is not signed for Secure Boot; turn Secure Boot off (in Hyper-V: Gen 2 VM, Security →
untick "Enable Secure Boot").

## What is in it

- `default.nix`: the image (nixpkgs' graphical installer base, names, boot menu artwork,
  Plymouth logo, no ZFS) and what installing needs offline;
- `live.nix`: the live session, Ocimum Desktop logged in as `nixos`, Calamares started at
  login. Tested on its own by `checks.live-session`;
- `references.nix`: the reference installs (Ocimum + systemd-boot, dwm + GRUB, see
  `nix/lib/reference-system.nix`) whose closures, and what rebuilding their per-machine
  parts needs (`nix/lib/offline-rebuild-inputs.nix`, `nix/lib/install-closure.nix`), are
  in the ISO's store. Tested by `checks.install-iso-references`.

`checks.iso-boot` boots the ISO itself on UEFI and BIOS.
