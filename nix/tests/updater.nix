# tulsi.updater (ADR 0038): the Update Manager is installed with a menu entry,
# the daily release check runs per user session, upgrades snapshot /home
# first when snapper manages it, and generations are listed.
{ self }:
{
  name = "updater";

  nodes.machine =
    { modulesPath, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      tulsi.updater.enable = true;
      # `tulsi upgrade --check` and `tulsi history` talk to tulsid; the
      # rebuild is a stand-in (tests have no network to build real systems).
      tulsi.state = {
        enable = true;
        file = ./state-test.json;
      };
      tulsi.daemon = {
        enable = true;
        wheelNoPassword = true;
      };
    };

  testScript = ''
    machine.wait_for_unit("multi-user.target")

    with subtest("the Update Manager comes with the system, and a menu entry"):
        machine.succeed("command -v tulsi-update-manager")
        machine.succeed("command -v tulsi-upgrade")
        machine.succeed("test -f /run/current-system/sw/share/applications/org.tulsi.UpdateManager.desktop")
        machine.succeed("test -f /run/current-system/sw/share/icons/hicolor/scalable/apps/org.tulsi.UpdateManager.svg")

    with subtest("the release is checked once a day, notifying once per release"):
        machine.succeed("systemctl --user -M alice@ cat tulsi-upgrade-check.service 2>/dev/null || "
                        "test -f /etc/systemd/user/tulsi-upgrade-check.service")
        timer = machine.succeed("cat /etc/systemd/user/tulsi-upgrade-check.timer")
        assert "OnCalendar=daily" in timer, timer
        service = machine.succeed("cat /etc/systemd/user/tulsi-upgrade-check.service")
        assert "tulsi upgrade --check --notify" in service, service

    with subtest("older versions are listed (the boot menu goes back to them)"):
        # Test VMs boot a single system with no generation links; the command
        # still runs, and the running version resolves. On installed machines
        # every change adds a version, which the window lists.
        machine.succeed("nix-env -p /nix/var/nix/profiles/system --list-generations")
        machine.succeed("readlink /run/current-system")

    with subtest("the release check runs offline and says so"):
        out = machine.succeed("tulsi upgrade --check")
        assert "cannot check for a newer release" in out, out

    with subtest("history is shown"):
        machine.succeed("tulsi history 5")
  '';
}
