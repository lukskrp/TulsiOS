# Installed TulsiOS machines: the host module the installer's system flake uses
# (ADR 0016). What differs per machine lives next to the flake in /etc/nixos:
#   configuration.nix          hostname, users, locale, keyboard, boot loader and
#                              tulsi.desktop.session, written by the installer
#   hardware-configuration.nix disks and kernel modules (nixos-generate-config)
#   tulsi/state.json           software chosen in the Software Center/Assistant
{ lib, ... }:

{
  nixpkgs.hostPlatform = lib.mkDefault "x86_64-linux";

  tulsi.desktop.session = lib.mkDefault "ocimum";
  ocimum.softwareCenter.enable = true;
  ocimum.assistant.enable = true;

  tulsi.state = {
    enable = true;
    # The system flake points this at ./tulsi/state.json.
    file = lib.mkDefault ../../../state/initial.json;
  };

  tulsi.daemon = {
    enable = true;
    bootstrap = {
      enable = true;
      hostModule = "nix/hosts/desktop";
    };
  };

  # Every locale, prebuilt: any language picked in the installer (or later) needs no
  # glibc locale build, so installing works offline.
  i18n.supportedLocales = lib.mkDefault [ "all" ];

  networking.networkmanager.enable = lib.mkDefault true;

  services.pipewire = {
    enable = lib.mkDefault true;
    alsa.enable = lib.mkDefault true;
    pulse.enable = lib.mkDefault true;
  };
  security.rtkit.enable = lib.mkDefault true;

  services.printing.enable = lib.mkDefault true;
  hardware.bluetooth.enable = lib.mkDefault true;
}
