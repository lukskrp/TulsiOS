# ADR 0036: `tulsi-webapp` adds a site as a menu app in its own Brave Origin window
# and profile, in the format Mint's Web App Manager reads, and Web App Manager
# starts and lists it. A screenshot lands in the test's output.
{ self }:
{
  name = "webapps";

  nodes.machine =
    { pkgs, modulesPath, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/x11.nix")
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      test-support.displayManager.auto.user = "alice";
      virtualisation.memorySize = 2048;
      # The utilities (Web App Manager) and tulsi-webapp, without the whole desktop.
      tulsi.utilities.enable = true;
      environment.systemPackages = [
        (pkgs.callPackage ../packages/ocimum-software-center.nix { })
        pkgs.brave-origin
        pkgs.xdotool
      ];
    };

  testScript = ''
    from datetime import timedelta

    machine.wait_for_x()

    def alice(cmd):
        return machine.succeed(f"su - alice -c '{cmd}'")

    with subtest("tulsi-webapp writes a Web App Manager launcher (offline: generic icon)"):
        path = alice("tulsi-webapp add Claude https://claude.ai").strip()
        assert "/home/alice/.local/share/applications/WebApp-Claude" in path, path
        entry = alice(f"cat {path}")
        assert 'Exec=brave-origin --app="https://claude.ai" --class=WebApp-Claude' in entry, entry
        assert "--user-data-dir=/home/alice/.local/share/ice/profiles/Claude" in entry, entry
        assert "X-WebApp-Browser=Brave Origin" in entry, entry
        assert "Claude\thttps://claude.ai" in alice("tulsi-webapp list")
        # Added once only.
        assert alice("tulsi-webapp add Claude claude.ai").strip() == path

    with subtest("Web App Manager starts, finds Brave Origin and lists the app"):
        # alice's X authority and session bus, from her window manager.
        machine.wait_until_succeeds("pgrep -u alice -o icewm", timeout=timedelta(seconds=300))
        wm = machine.succeed("pgrep -u alice -o icewm").strip()
        session = dict(
            line.split("=", 1)
            for line in machine.succeed(f"tr '\\0' '\\n' < /proc/{wm}/environ").splitlines()
            if "=" in line
        )
        env = " ".join(f"{k}={session[k]}" for k in ["DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS"] if k in session)
        alice(f"{env} webapp-manager >/tmp/wam.log 2>&1 &")
        machine.wait_until_succeeds(
            f"su - alice -c '{env} xwininfo -root -tree 2>/dev/null' | grep -qF 'Web Apps'", timeout=timedelta(seconds=120)
        )
        machine.sleep(3)
        machine.screenshot("webapp-manager")
        machine.fail("grep -q Traceback /tmp/wam.log")
        machine.fail("grep -q 'No supported browsers' /tmp/wam.log")

    with subtest("removing takes the launcher and its profile"):
        alice("mkdir -p .local/share/ice/profiles/$(basename " + path + " .desktop | cut -d- -f2)")
        alice("tulsi-webapp remove Claude")
        machine.fail(f"test -e {path}")
        assert alice("tulsi-webapp list").strip() == ""
  '';
}
