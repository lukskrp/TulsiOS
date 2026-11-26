# Development VM (QEMU):
#   nix build .#nixosConfigurations.tulsi-vm.config.system.build.vm
#   ./result/bin/run-tulsi-vm-vm
# Login: tulsi / tulsi. The VM can rebuild itself: try `tulsi install cowsay`.
# scripts/vm-e2e.sh drives it headless over SSH.
{ lib, modulesPath, ... }:

{
  # Imported directly (not via vmVariant) so the configuration the VM
  # rebuilds from /etc/nixos is the very one it is running.
  imports = [ (modulesPath + "/virtualisation/qemu-vm.nix") ];

  nixpkgs.hostPlatform = "x86_64-linux";
  networking.hostName = "tulsi-vm";
  networking.networkmanager.enable = true;
  time.timeZone = "UTC";

  virtualisation = {
    memorySize = 6144;
    cores = 4;
    diskSize = 16384;
    # Keep store writes from in-VM rebuilds on disk instead of in RAM.
    writableStoreUseTmpfs = false;
  };

  ocimum.desktop = {
    enable = true;
    autoLoginUser = "tulsi";
  };
  # GTK3-O is grafted system-wide by default with ocimum.desktop (ocimum.gtk3o).
  ocimum.softwareCenter.enable = true;
  ocimum.assistant.enable = true;

  tulsi.state = {
    enable = true;
    file = lib.mkDefault ../../../state/example.json;
  };

  tulsi.daemon = {
    enable = true;
    wheelNoPassword = true; # dev convenience
    bootstrap = {
      enable = true;
      hostModule = "nix/hosts/vm";
    };
    # The VM has no boot loader: activate without creating a boot entry.
    rebuildCommand = [
      "nixos-rebuild"
      "test"
      "--flake"
      "/etc/nixos#tulsi-vm"
    ];
  };

  users.users.tulsi = {
    isNormalUser = true;
    initialPassword = "tulsi";
    extraGroups = [
      "wheel"
      "networkmanager"
      "lp"
      "scanner"
    ];
  };

  # Dev only: scripts/vm-e2e.sh forwards this to 127.0.0.1 on the host.
  services.openssh = {
    enable = true;
    settings.PasswordAuthentication = true;
  };

  system.stateVersion = "26.05";
}
