# The ISO's live session (nix/hosts/iso/live.nix) in an ordinary VM, without
# building an ISO: Ocimum Desktop logs in as `nixos` and Calamares starts, as
# root through pkexec, showing TulsiOS's pages. Screenshots of each page.
{ self }:
{
  name = "live-session";

  nodes.machine =
    { lib, ... }:
    {
      imports = [
        self.nixosModules.default
        ../hosts/iso/live.nix
      ];
      # What the ISO gets from nixpkgs' installation-device and graphical-base
      # profiles (not imported here: they set nixpkgs.overlays and ISO-only options).
      users.users.nixos = {
        isNormalUser = true;
        extraGroups = [
          "wheel"
          "networkmanager"
          "video"
        ];
        initialHashedPassword = "";
      };
      security.polkit.extraConfig = ''
        polkit.addRule(function(action, subject) {
          if (subject.isInGroup("wheel")) {
            return polkit.Result.YES;
          }
        });
      '';
      hardware.enableAllFirmware = lib.mkForce false;
      virtualisation.memorySize = 4096;
      virtualisation.cores = 4;
      # A disk to install onto, for the welcome page's storage check (20 GB).
      virtualisation.emptyDiskImages = [ (24 * 1024) ];
      virtualisation.resolution = {
        x = 1280;
        y = 800;
      };
    };

  testScript = ''
    machine.start()
    machine.wait_for_unit("graphical.target", timeout=300)

    with subtest("Ocimum Desktop logs in as nixos"):
        machine.wait_until_succeeds("pgrep -u nixos -f cinnamon-session", timeout=300)
        machine.succeed("grep -qx 'ID=tulsios' /etc/os-release")
        # The greeter's launcher once replaced the session's PATH, which hid the
        # setuid wrappers ("pkexec must be setuid root").
        session_path = machine.succeed(
            "tr '\\0' '\\n' < /proc/$(pgrep -u nixos -o -f cinnamon-session)/environ | grep '^PATH='"
        )
        print(session_path)
        assert "/run/wrappers/bin" in session_path, session_path

    with subtest("Calamares starts at login, as root through pkexec"):
        print(machine.succeed("ls /run/current-system/sw/etc/xdg/autostart/"))
        print(machine.succeed("grep -h '^Exec' /run/current-system/sw/etc/xdg/autostart/calamares.desktop"))
        machine.wait_until_succeeds(
            "ps -u root -o args= | grep -v -e pkexec -e grep | grep -q calamares", timeout=300
        )
        print(machine.succeed("ps -eo user,pid,args | grep -i [c]alamares"))
        # The welcome page's checks (the internet one waits for its timeout, offline).
        # Clicking through the pages is the manual Hyper-V run's job (ADR 0016).
        machine.sleep(45)
        machine.screenshot("calamares_welcome")
        machine.succeed("ps -u root -o args= | grep -v -e pkexec -e grep | grep -q calamares")

    with subtest("the installer's logo is sharp: a 512 px PNG and the vector"):
        branding = machine.succeed(
            "ls -d /nix/store/*-calamares-tulsios-extensions-*/share/calamares/branding/tulsios | head -1"
        ).strip()
        machine.succeed(f"grep -q 'productLogo: *\"logo.png\"' {branding}/branding.desc")
        size = machine.succeed(f"od -An -tu1 -j16 -N8 {branding}/logo.png").split()
        width = int.from_bytes(bytes(map(int, size[0:4])), "big")
        assert width == 512, size
        machine.fail(f"grep -q 'data:image' {branding}/logo.svg")
  '';
}
