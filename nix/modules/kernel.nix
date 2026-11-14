# TulsiOS boots the newest stable kernel (tulsipkgs' linuxPackages_latest, 7.3 on
# 2026-11-14), not the LTS default (6.18), for newer firmware and driver support. It
# follows tulsipkgs: when a new major turns stable, tulsi-sync moves linux_latest to it.
# A machine's own boot.kernelPackages still wins (mkDefault); pkgs.linuxPackages is LTS.
{ lib, pkgs, ... }:
{
  boot.kernelPackages = lib.mkDefault pkgs.linuxPackages_latest;
  # Redistributable linux-firmware blobs (GPU, Wi-Fi, Bluetooth) for those drivers.
  hardware.enableRedistributableFirmware = lib.mkDefault true;
}
