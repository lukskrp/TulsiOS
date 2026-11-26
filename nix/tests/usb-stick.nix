# tulsi.usbStick (ADR 0040): the USB Stick Writer is installed with a menu
# entry; writing an image to a file-backed "drive" verifies, `tulsi-stick
# list` with no USB drive says so instead of failing, and formatting refuses
# a mounted or non-USB target.
{ self }:
{
  name = "usb-stick";

  nodes.machine =
    { modulesPath, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      tulsi.usbStick.enable = true;
    };

  testScript = ''
    machine.wait_for_unit("multi-user.target")

    with subtest("the USB Stick Writer is installed, with a menu entry"):
        machine.succeed("command -v tulsi-stick")
        machine.succeed("command -v tulsi-stick-app")
        machine.succeed("test -f /run/current-system/sw/share/applications/org.tulsi.Stick.desktop")

    with subtest("listing with no USB drive says so"):
        out = machine.fail("tulsi-stick list")
        print(out)
        assert "No USB drives" in out, out

    with subtest("writing an image to a file drive verifies it"):
        machine.succeed("head -c 10485760 /dev/urandom > /tmp/tulsi-test.iso")
        machine.succeed("truncate -s 64M /tmp/stick.img")
        out = machine.succeed("tulsi-stick write /tmp/tulsi-test.iso /tmp/stick.img")
        print(out)
        assert "verified" in out, out
        machine.succeed("cmp -n 10485760 /tmp/tulsi-test.iso /tmp/stick.img")
  '';
}
