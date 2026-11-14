# The login screen: greetd + the Ocimum Greeter (OTK) on XLibre. No autologin:
# the test types the user name and password like a person would.
{ self }:
{
  name = "ocimum-greeter";

  nodes.machine =
    { modulesPath, pkgs, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      ocimum.desktop.enable = true;
      environment.systemPackages = [ pkgs.xwininfo ];
      virtualisation.memorySize = 2048;
    };

  testScript = ''
      def x_server(user):
          """The X server process of `user`: (pid, executable)."""
          pid = machine.succeed(f"pgrep -o -u {user} -x X || pgrep -o -u {user} -x Xorg").strip()
          return pid, machine.succeed(f"readlink /proc/{pid}/exe").strip()

      def cinnamon_running():
          machine.wait_until_succeeds(
              "su - alice -c 'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus "
              "gdbus call --session -d org.Cinnamon -o /org/Cinnamon -m org.Cinnamon.Eval Main.runState' "
              "| grep -q 'true,..2'",
              timeout=300,
          )

      machine.wait_for_unit("greetd.service")


      with subtest("no other display manager"):
          machine.fail("systemctl cat lightdm.service")
          machine.fail("systemctl cat sddm.service")
          machine.fail("systemctl cat gdm.service")

      with subtest("the greeter runs on XLibre as the unprivileged greeter user"):
          machine.wait_until_succeeds("pgrep -u greeter -f 'ocimum-greeter --config'", timeout=120)
          machine.wait_until_succeeds("pgrep -u greeter -x X || pgrep -u greeter -x Xorg")
          pid, exe = x_server("greeter")
          assert "-xlibre-xserver-" in exe, exe
          machine.fail("pgrep -u root -x X")
          machine.wait_until_succeeds("XAUTHORITY=/run/user/$(id -u greeter)/ocimum-xauthority DISPLAY=:0 "
                                      "xwininfo -root -tree | grep -q 'Ocimum Greeter'")
          machine.sleep(2)
          machine.screenshot("greeter")

      with subtest("a wrong password keeps the greeter and opens no session"):
          machine.send_chars("alice\n")
          machine.sleep(1)
          machine.send_chars("wrong-password\n")
          machine.wait_until_succeeds("journalctl -b | grep -q 'authentication failure.*user=alice'")
          machine.sleep(4)  # PAM's failure delay, then the greeter is ready again
          machine.succeed("pgrep -u greeter -f 'ocimum-greeter --config'")
          machine.fail("loginctl list-sessions --no-legend | grep -w alice")
          machine.screenshot("greeter_wrong_password")

      with subtest("the right password starts Ocimum on XLibre, as the user"):
          machine.send_chars("foobar\n")
          cinnamon_running()
          pid, exe = x_server("alice")
          assert "-xlibre-xserver-" in exe, exe
          machine.fail("pgrep -u greeter -f 'ocimum-greeter --config'")
          session_type = machine.succeed(
              "loginctl show-session $(loginctl list-sessions --no-legend | awk '$3 == \"alice\" {print $1}' | head -1) -p Type --value"
          ).strip()
          machine.log(f"alice's session type: {session_type}")
          machine.screenshot("desktop_after_login")

      with subtest("logging out brings the greeter back, which remembers the user"):
          # Log out with Cinnamon's own tool (Python + Gtk/XApp typelibs), without the
          # confirmation dialog.
          machine.succeed(
              "su - alice -c 'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus "
              "DISPLAY=:0 XAUTHORITY=/run/user/1000/ocimum-xauthority "
              "cinnamon-session-quit --logout --no-prompt'"
          )
          machine.wait_until_succeeds("pgrep -u greeter -f 'ocimum-greeter --config'", timeout=120)
          machine.succeed("grep -x alice /var/cache/ocimum-greeter/last-user")
          machine.wait_until_succeeds("XAUTHORITY=/run/user/$(id -u greeter)/ocimum-xauthority DISPLAY=:0 "
                                      "xwininfo -root -tree | grep -q 'Ocimum Greeter'")
          machine.screenshot("greeter_after_logout")
    '';
}
