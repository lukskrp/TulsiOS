# Development VM:
#   nix build .#nixosConfigurations.tulsi-vm.config.system.build.vm
#   ./result/bin/run-tulsi-vm-vm
{ lib, ... }:

{
  nixpkgs.hostPlatform = "x86_64-linux";
  networking.hostName = "tulsi-vm";
  networking.networkmanager.enable = true;
  time.timeZone = "UTC";

  ocimum.desktop = {
    enable = true;
    autoLoginUser = "tulsi";
  };

  tulsi.state = {
    enable = true;
    file = ../../../state/example.json;
  };

  users.users.tulsi = {
    isNormalUser = true;
    initialPassword = "tulsi";
    extraGroups = [
      "wheel"
      "networkmanager"
    ];
  };

  nix.settings.experimental-features = [
    "nix-command"
    "flakes"
  ];

  # Placeholders so the configuration also evaluates as a real system;
  # the VM variant (system.build.vm) overrides disks itself.
  boot.loader.grub.device = lib.mkDefault "nodev";
  fileSystems."/" = lib.mkDefault {
    device = "/dev/disk/by-label/nixos";
    fsType = "ext4";
  };

  virtualisation.vmVariant.virtualisation = {
    memorySize = 4096;
    cores = 4;
    diskSize = 8192;
  };

  system.stateVersion = "26.05";
}
