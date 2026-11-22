# TulsiOS's name where NixOS would show its own: /etc/os-release, /etc/issue,
# boot menu entries (and GRUB's theme) and the live ISO (ADR 0016). os-release keeps ID_LIKE=nixos;
# VERSION_ID stays NixOS's release, TULSIOS_VERSION is TulsiOS's (VERSION, ADR 0017).
{ lib, pkgs, ... }:
{
  # Systems that boot with GRUB (BIOS installs) show TulsiOS's boot menu, as the
  # live ISO does: the Tulsi Leaf wallpaper, cropped to the screen.
  boot.loader.grub.theme = lib.mkDefault (pkgs.callPackage ../packages/tulsios-grub-theme.nix { });

  system.nixos = {
    distroName = lib.mkDefault "TulsiOS";
    distroId = lib.mkDefault "tulsios";
    vendorName = lib.mkDefault "TulsiOS";
    vendorId = lib.mkDefault "tulsios";
    extraOSReleaseArgs = {
      HOME_URL = lib.mkDefault "https://github.com/lukskrp/TulsiOS";
      SUPPORT_URL = lib.mkDefault "https://github.com/lukskrp/TulsiOS";
      TULSIOS_VERSION = lib.fileContents ../../VERSION;
    };
  };
}
