# Starah on the Ocimum Desktop: the first-login setup window, the admin password,
# an agent's request answered in the Agent Request window, and the login summary.
{ self }:
{
  name = "starah-setup";

  nodes.machine =
    { modulesPath, pkgs, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      ocimum.desktop.enable = true;
      ocimum.desktop.autoLoginUser = "alice";
      ocimum.assistant.enable = true;
      tulsi.daemon.enable = true;
      users.users.alice.extraGroups = [ "wheel" ];
      environment.systemPackages = [
        pkgs.xwininfo
        pkgs.xdotool
      ];
      # Clicks the bottom-right button of the window titled $1 (Save / Approve).
      # A click needs no keyboard focus, which Muffin may refuse to tools like xdotool.
      environment.etc."starah-test/click".source = pkgs.writeShellScript "click" ''
        id=$(${pkgs.xdotool}/bin/xdotool search --sync --name "^$1$" | head -1)
        eval "$(${pkgs.xdotool}/bin/xdotool getwindowgeometry --shell "$id")"
        ${pkgs.xdotool}/bin/xdotool mousemove --window "$id" $((WIDTH - 70)) $((HEIGHT - 36)) click 1
      '';
      virtualisation.memorySize = 2048;
    };

  testScript = ''
      X = "DISPLAY=:0 XAUTHORITY=/run/user/1000/ocimum-xauthority"

      def window(title, timeout=180):
          machine.wait_until_succeeds(
              f"su - alice -c '{X} xwininfo -root -tree' | grep -qF '\"{title}\"'", timeout=timeout
          )

      def focus(title):
          machine.succeed(f"su - alice -c '{X} xdotool search --sync --name \"^{title}$\" windowactivate --sync'")

      def cinnamon_running():
          machine.wait_until_succeeds(
              "su - alice -c 'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus "
              "gdbus call --session -d org.Cinnamon -o /org/Cinnamon -m org.Cinnamon.Eval Main.runState' "
              "| grep -q 'true,..2'",
              timeout=300,
          )

      def no_window(title):
          machine.wait_until_fails(f"su - alice -c '{X} xwininfo -root -tree' | grep -qF '\"{title}\"'")

      machine.wait_for_unit("starahd.service")

      with subtest("first login opens Starah Setup"):
          window("Starah Setup")
          cinnamon_running()
          status = machine.succeed("starah status")
          assert "Configured: no" in status and "assistant" in status, status
          machine.sleep(3)
          machine.screenshot("starah_setup")

      with subtest("saving the levels asks for the admin password"):
          # Cinnamon's polkit dialog is up once polkit's helper unit waits for the password.
          helper = "systemctl list-units --no-legend 'polkit-agent-helper@*' | grep -q polkit-agent-helper"
          for attempt in range(3):
              machine.succeed(f"su - alice -c '{X} /etc/starah-test/click \"Starah Setup\"'")
              if machine.execute(f"timeout 20 sh -c 'until {helper}; do sleep 1; done'")[0] == 0:
                  break
          machine.succeed(helper)
          machine.sleep(3)
          machine.screenshot("starah_setup_password")
          machine.send_chars("foobar\n")
          try:
              machine.wait_until_succeeds("starah status | grep -q 'Configured: yes'", timeout=60)
          except Exception:
              machine.log(machine.execute(
                  "journalctl -b --no-pager | grep -iE 'polkit|starah|authenticat|pam_unix' | tail -40"
              )[1])
              raise
          no_window("Starah Setup")
          machine.succeed("journalctl -b -u starahd | grep '\"event\":\"set-policy\"' | grep -q '\"by\":\"alice\"'")
      with subtest("an agent's request appears and the human approves it"):
          machine.succeed(
              "(starah run --agent assistant -- starah ask org.tulsi.apply 'install cowsay' '+ package cowsay';"
              " echo $? > /tmp/ask.rc) > /tmp/ask.log 2>&1 &"
          )
          window("Agent Request", timeout=60)
          focus("Agent Request")
          machine.sleep(2)
          machine.screenshot("starah_request")
          machine.fail("test -e /tmp/ask.rc")
          machine.succeed(f"su - alice -c '{X} /etc/starah-test/click \"Agent Request\"'")
          machine.wait_until_succeeds("grep -qx 0 /tmp/ask.rc", timeout=60)
          no_window("Agent Request")

      with subtest("later logins show the summary"):
          machine.succeed("su - alice -c 'XDG_RUNTIME_DIR=/run/user/1000 systemctl --user restart starah-session'")
          window("Agent Privileges", timeout=60)
          machine.sleep(2)
          machine.screenshot("starah_summary")
  '';
}
