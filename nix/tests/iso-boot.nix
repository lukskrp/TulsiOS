# The live ISO itself boots, on UEFI and on BIOS, into the live session with
# Calamares. What the ISO installs is checked without an ISO, faster:
# checks.live-session (the session, Calamares' pages) and
# checks.install-iso-references (an offline install with the ISO's references).
{ self, pkgs }:
let
  # The release ISO plus the test driver's backdoor; faster compression than the
  # release's, same contents otherwise.
  isoConfig =
    (self.nixosConfigurations.tulsi-iso.extendModules {
      modules = [
        (
          { modulesPath, ... }:
          {
            imports = [ (modulesPath + "/testing/test-instrumentation.nix") ];
            isoImage.squashfsCompression = "zstd -Xcompression-level 3";
          }
        )
      ];
    }).config;
  iso = "${isoConfig.system.build.isoImage}/iso/${isoConfig.image.fileName}";

  qemu-common = import "${pkgs.path}/nixos/lib/qemu-common.nix" { inherit (pkgs) lib stdenv; };
  qemu = qemu-common.qemuBinary pkgs.qemu_test;
in
{
  name = "iso-boot";
  nodes = { };

  testScript = ''
    import time

    # Plain OVMF: OVMFFull needs SMM, which nested KVM under Hyper-V/WSL2 can't enter.
    pc = "${qemu} -m 4096 -smp 4 -nic none -cdrom ${iso}"
    firmware = {
        "uefi": " -drive if=pflash,format=raw,unit=0,readonly=on,file=${pkgs.OVMF.firmware}"
                " -drive if=pflash,format=raw,unit=1,readonly=on,file=${pkgs.OVMF.variables}",
        "bios": "",
    }

    for boot in ["uefi", "bios"]:
        live = create_machine(pc + firmware[boot], name=f"live_{boot}")
        # VMs from create_machine are not stopped by the driver when a test fails.
        try:
            with subtest(f"{boot}: boots into the live session with Calamares"):
                live.start()
                if boot == "uefi":
                    # The boot menu: TulsiOS's GRUB theme, the wallpaper cropped to
                    # the screen. A key stops GRUB's countdown (10 s); Enter then
                    # boots the default entry. (time.sleep: the machine's own sleep
                    # runs in the guest, which has no shell before it has booted.)
                    time.sleep(4)
                    live.send_key("up")
                    time.sleep(2)
                    live.screenshot("grub_uefi")
                    live.send_key("ret")
                live.wait_for_unit("multi-user.target", timeout=600)
                live.succeed("grep -qx 'ID=tulsios' /etc/os-release")
                live.succeed("test -e /run/current-system/sw/bin/tulsi-install-system")
                live.wait_until_succeeds("pgrep -u nixos -f cinnamon-session", timeout=300)
                live.wait_until_succeeds(
                    "ps -u root -o args= | grep -v -e pkexec -e grep | grep -q calamares", timeout=300
                )
                live.sleep(15)
                live.screenshot(f"live_{boot}")
        finally:
            live.crash()
  '';
}
