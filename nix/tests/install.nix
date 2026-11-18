# Installing TulsiOS onto an empty disk, offline, the way Calamares does it:
# partition, then tulsi-install-system (system flake + nixos-install). Then the
# disk boots on its own (UEFI, systemd-boot), shows only the chosen desktop,
# logs in through the greeter, and its /etc/nixos flake evaluates to exactly the
# running system. Modelled on nixpkgs' nixos/tests/installer.nix.
{ self, desktop }:
let
  lib = self.inputs.nixpkgs.lib;
  password = "tulsi";
  # openssl passwd -6 -salt tulsitest tulsi
  passwordHash = "$6$tulsitest$hSDNyVECxMk8PT61eFiFl4gsk0dgTfjOV1/9mBo0S6nVIJD.pFbfmir74OxoAP2ooaRlBdWZZ5V4birKT7nrR1";

  # A TulsiOS install like the one the test makes, so its closure (the desktop,
  # the kernel, …) is in the installer's store and nixos-install only builds what
  # differs per machine.
  reference = lib.nixosSystem {
    modules = [
      self.nixosModules.default
      ../hosts/desktop
      (
        { modulesPath, ... }:
        {
          imports = [
            (modulesPath + "/profiles/qemu-guest.nix")
            (modulesPath + "/testing/test-instrumentation.nix")
          ];
          networking.hostName = "reference";
          tulsi.desktop.session = desktop;
          boot.loader.systemd-boot.enable = true;
          boot.loader.efi.canTouchEfiVariables = true;
          fileSystems."/" = {
            device = "/dev/disk/by-label/nixos";
            fsType = "ext4";
          };
          fileSystems."/boot" = {
            device = "/dev/disk/by-label/ESP";
            fsType = "vfat";
          };
          users.users.reference = {
            isNormalUser = true;
            extraGroups = [
              "networkmanager"
              "wheel"
            ];
          };
          system.stateVersion = lib.trivial.release;
        }
      )
    ];
  };

  sessionCheck =
    if desktop == "dwm" then
      ''target.wait_until_succeeds("pgrep -u alice -x dwm", timeout=300)''
    else
      ''target.wait_until_succeeds("pgrep -u alice -f cinnamon-session", timeout=300)'';
  otherDesktop = if desktop == "dwm" then "-cinnamon-[0-9]" else "-dwm-[0-9]";
in
{
  name = "install-${desktop}";

  nodes = {
    # The live system that installs (stands in for the ISO).
    installer =
      { modulesPath, pkgs, ... }:
      {
        imports = [
          self.nixosModules.default
        ];
        # Not nixpkgs' installation-device/base profiles: they set nixpkgs.overlays
        # (test nodes share one read-only pkgs) and ZFS, which TulsiOS's 7.3 kernel lacks.
        environment.systemPackages = [
          pkgs.parted
          pkgs.dosfstools
          pkgs.e2fsprogs
        ];
        tulsi.installer = {
          enable = true;
          offlineSystems = [ reference.config.system.build.toplevel ];
          buildDependencies =
            import ../lib/install-closure.nix pkgs ++ import ../lib/offline-rebuild-inputs.nix reference;
        };
        nix.settings = {
          substituters = lib.mkForce [ ];
          hashed-mirrors = null;
          connect-timeout = 1;
        };
        hardware.enableAllFirmware = lib.mkForce false;

        # Boots from a small /dev/vdb; /dev/vda is the target disk, shared with `target`.
        virtualisation.emptyDiskImages = [ 1024 ];
        virtualisation.rootDevice = "/dev/vdb";
        virtualisation.fileSystems."/".autoFormat = true;
        virtualisation.diskImage = "./target.qcow2";
        virtualisation.diskSize = 24 * 1024;
        virtualisation.memorySize = 4096;
        virtualisation.cores = 4;
        virtualisation.useEFIBoot = true;
        # OVMFFull needs SMM (q35,smm=on), which nested KVM under Hyper-V/WSL2
        # cannot enter ("KVM: entry failed"); plain OVMF has no secure boot and no SMM.
        virtualisation.efi.OVMF = pkgs.OVMF;
      };

    # The installed disk, booted through its own boot loader.
    target =
      { pkgs, ... }:
      {
        virtualisation.useBootLoader = true;
        virtualisation.useEFIBoot = true;
        virtualisation.efi.OVMF = pkgs.OVMF;
        virtualisation.useDefaultFilesystems = false;
        virtualisation.efi.keepVariables = false;
        virtualisation.fileSystems."/" = {
          device = "/dev/disk/by-label/this-is-not-real-and-will-never-be-used";
          fsType = "ext4";
        };
        virtualisation.diskImage = "./target.qcow2";
        virtualisation.diskSize = 24 * 1024;
        virtualisation.memorySize = 4096;
        virtualisation.cores = 4;
      };
  };

  testScript = ''
    args = ("--root /mnt --desktop ${desktop} --hostname tulsi-box --user alice --full-name 'Alice Tester' "
            "--hashed-password '${passwordHash}' --timezone Europe/Stockholm --locale en_US.UTF-8 "
            "--keyboard-layout se --boot uefi")

    installer.start()
    installer.wait_for_unit("multi-user.target")
    installer.succeed("udevadm settle")

    with subtest("partition: EFI system partition and an ext4 root"):
        installer.succeed(
            "flock /dev/vda parted --script /dev/vda -- mklabel gpt"
            + " mkpart ESP fat32 1M 512MiB set 1 esp on"
            + " mkpart primary ext4 512MiB -1MiB",
            "udevadm settle",
            "mkfs.vfat -n ESP /dev/vda1",
            "mkfs.ext4 -L nixos /dev/vda2",
            "mkdir -p /mnt",
            "mount LABEL=nixos /mnt",
            "mkdir -p /mnt/boot",
            "mount LABEL=ESP /mnt/boot",
        )

    with subtest("tulsi-install-system writes the system flake"):
        installer.fail("tulsi-install-system --root /mnt --desktop gnome --user alice --write-only")
        installer.fail("tulsi-install-system --root /mnt --hostname 'bad host' --user alice --write-only")
        installer.succeed(f"tulsi-install-system {args} --write-only >&2")
        config = installer.succeed("cat /mnt/etc/nixos/configuration.nix")
        print(config)
        assert 'tulsi.desktop.session = "${desktop}";' in config, config
        assert 'networking.hostName = "tulsi-box";' in config, config
        flake = installer.succeed("cat /mnt/etc/nixos/flake.nix")
        assert 'inputs.tulsi.url = "path:/nix/store/' in flake, flake
        assert '"''${tulsi}/nix/hosts/desktop"' in flake, flake
        installer.succeed("grep -q firefox /mnt/etc/nixos/tulsi/state.json")
        installer.succeed("grep -q 'fileSystems.\"/\"' /mnt/etc/nixos/hardware-configuration.nix")
        # Let the test driver talk to the installed system, like nixpkgs' installer tests.
        installer.succeed(
            "sed -i 's|(modulesPath + \"/profiles/qemu-guest.nix\")|&"
            " (modulesPath + \"/testing/test-instrumentation.nix\")|' /mnt/etc/nixos/hardware-configuration.nix",
            "grep -q test-instrumentation /mnt/etc/nixos/hardware-configuration.nix",
        )

    with subtest("nixos-install, offline"):
        installer.succeed(f"tulsi-install-system {args} --keep-hardware-config >&2", timeout=3600)
        installer.succeed("test -e /mnt/boot/loader/loader.conf")
        installer.succeed("umount -R /mnt")
        installer.succeed("sync")
        installer.shutdown()

    # The same disk, booting on its own.
    target.state_dir = installer.state_dir
    target.start()
    target.wait_for_unit("multi-user.target")

    with subtest("the installed machine is the one we asked for"):
        assert target.succeed("hostname").strip() == "tulsi-box"
        assert target.succeed("readlink /etc/localtime").strip().endswith("Europe/Stockholm")
        target.succeed("nix-store -qR /run/current-system | grep -E -- '-${desktop}-[0-9]|-cinnamon-[0-9]'")
        target.fail("nix-store -qR /run/current-system | grep -E -- '${otherDesktop}'")

    with subtest("tulsid keeps /etc/nixos in git, and the flake rebuilds this very system"):
        target.wait_for_unit("tulsid.service")
        target.wait_until_succeeds("test -d /etc/nixos/.git")
        target.succeed("tulsi history >&2")
        built = target.succeed(
            "nix --extra-experimental-features 'nix-command flakes' eval --raw "
            "/etc/nixos#nixosConfigurations.tulsi-box.config.system.build.toplevel.outPath"
        ).strip()
        running = target.succeed("readlink -f /run/current-system").strip()
        assert built == running, f"{built} != {running}"

    with subtest("logs in through the greeter into ${desktop}"):
        target.wait_for_unit("greetd.service")
        target.wait_until_succeeds("pgrep -u greeter -f 'ocimum-greeter --config'", timeout=180)
        target.sleep(3)
        target.send_chars("alice\n")
        target.sleep(1)
        target.send_chars("${password}\n")
        ${sessionCheck}
        target.sleep(5)
        target.screenshot("installed_${desktop}")

    target.shutdown()
  '';
}
