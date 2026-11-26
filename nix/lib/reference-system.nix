# A TulsiOS install as the installer writes it, on hardware nobody knows yet. The
# live ISO keeps its closure (tulsi.installer.offlineSystems) and, through
# nix/lib/offline-rebuild-inputs.nix, what rebuilding its per-machine parts needs,
# so installing needs no network (ADR 0016).
#
#   desktop  "ocimum" | "dwm" | "sonic" (SonicDE is not on the ISO: nix/lib/sonic-cache.nix)
#   boot     "uefi" (systemd-boot) | "bios" (GRUB), as tulsi-install-system writes them
#
# A real machine's hardware-configuration.nix and Calamares' answers can switch on
# more than a plain install has. Those are on here, so the store already holds
# what the installed initrd and boot loader are built from: every disk controller
# module, both CPU vendors' microcode, the file systems Calamares offers, LUKS, and
# the Hyper-V guest support nixos-generate-config enables in Hyper-V VMs.
#   testing  also the NixOS test driver's backdoor, as the installed system in
#            checks.install-iso-references has it
{
  self,
  desktop,
  boot,
  testing ? false,
}:
self.inputs.nixpkgs.lib.nixosSystem {
  modules = [
    self.nixosModules.default
    ../hosts/desktop
    (
      { lib, modulesPath, ... }:
      {
        imports = [
          (modulesPath + "/installer/scan/not-detected.nix")
          (modulesPath + "/profiles/qemu-guest.nix")
        ]
        ++ lib.optional testing (modulesPath + "/testing/test-instrumentation.nix");

        networking.hostName = "reference";
        tulsi.desktop.session = desktop;

        hardware.enableAllHardware = true;
        hardware.cpu.intel.updateMicrocode = true;
        hardware.cpu.amd.updateMicrocode = true;
        virtualisation.hypervGuest.enable = true;

        boot.supportedFilesystems = [
          "ext4"
          "btrfs"
          "xfs"
          "f2fs"
          "vfat"
        ];
        boot.initrd.supportedFilesystems = [
          "ext4"
          "btrfs"
          "xfs"
          "f2fs"
          "vfat"
        ];
        boot.initrd.luks.devices.reference.device =
          "/dev/disk/by-uuid/00000000-0000-0000-0000-000000000000";

        boot.loader =
          if boot == "uefi" then
            {
              systemd-boot.enable = true;
              efi.canTouchEfiVariables = true;
            }
          else
            {
              grub = {
                enable = true;
                device = "/dev/sda";
                useOSProber = true;
              };
            };

        fileSystems."/" = {
          device = "/dev/disk/by-label/nixos";
          fsType = "ext4";
        };
        fileSystems."/boot" = lib.mkIf (boot == "uefi") {
          device = "/dev/disk/by-label/ESP";
          fsType = "vfat";
        };

        users.users.reference = {
          isNormalUser = true;
          extraGroups = [
            "networkmanager"
            "wheel"
            "lp"
            "scanner"
          ];
        };
        system.stateVersion = lib.trivial.release;
      }
    )
  ];
}
