# The dwm session (ADR 0016): logs in through greetd on XLibre, has a bar with a
# system tray, Super+A opens the Assistant, and what Cinnamon would otherwise
# provide runs: graphical-session.target (Starah's session helper), a polkit
# agent, notifications, the GTK theme. And no Cinnamon in the system.
{ self }:
{
  name = "dwm-session";

  nodes.machine =
    { modulesPath, pkgs, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      tulsi.desktop = {
        session = "dwm";
        autoLoginUser = "alice";
      };
      networking.networkmanager.enable = true;
      tulsi.state = {
        enable = true;
        file = ./state-test.json;
      };
      tulsi.daemon = {
        enable = true;
        packageIndex = ./index-test.json;
        rebuildCommand = [ "${pkgs.coreutils}/bin/true" ];
      };
      ocimum.assistant.enable = true;
      environment.systemPackages = [
        pkgs.xprop
        pkgs.libnotify
        # Succeeds when dwm's system tray window holds at least one icon.
        (pkgs.writeShellScriptBin "tray-has-icons" ''
          export PATH=${pkgs.xwininfo}/bin:${pkgs.xprop}/bin:${pkgs.gnugrep}/bin:${pkgs.gawk}/bin:$PATH
          for w in $(xwininfo -root -children | awk '$1 ~ /^0x/ {print $1}'); do
            if xprop -id "$w" _NET_SYSTEM_TRAY_ORIENTATION | grep -q ' = '; then
              xwininfo -id "$w" -children | grep -Eq '[1-9][0-9]* child' && exit 0
            fi
          done
          exit 1
        '')
      ];
      virtualisation.memorySize = 2048;
    };

  testScript = ''
    def su(command):
        env = ("XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus "
               "DISPLAY=:0 XAUTHORITY=/run/user/1000/ocimum-xauthority")
        return machine.succeed(f"su - alice -c '{env} {command}'")

    machine.wait_for_unit("greetd.service")

    with subtest("autologin starts dwm on XLibre, as the user"):
        machine.wait_until_succeeds("pgrep -u alice -x dwm", timeout=180)
        pid = machine.succeed("pgrep -o -u alice -x X || pgrep -o -u alice -x Xorg").strip()
        exe = machine.succeed(f"readlink /proc/{pid}/exe").strip()
        assert "-xlibre-xserver-" in exe, exe

    with subtest("the bar shows slstatus' text"):
        machine.wait_until_succeeds("pgrep -u alice -x slstatus")
        machine.wait_until_succeeds(
            "su - alice -c 'DISPLAY=:0 XAUTHORITY=/run/user/1000/ocimum-xauthority xprop -root WM_NAME' "
            "| grep -E '[0-9]{4}-[0-9]{2}-[0-9]{2}'"
        )

    with subtest("graphical-session.target: Starah, the polkit agent, nm-applet in the tray"):
        for unit in ["graphical-session.target", "starah-session.service", "tulsi-polkit-agent.service"]:
            machine.wait_until_succeeds(
                f"su - alice -c 'XDG_RUNTIME_DIR=/run/user/1000 systemctl --user is-active {unit}'",
                timeout=120,
            )
        machine.wait_until_succeeds("pgrep -u alice -f nm-applet", timeout=60)
        # nm-applet's icon is embedded in dwm's systray window (the patch's XEmbed tray).
        machine.wait_until_succeeds(
            "su - alice -c 'DISPLAY=:0 XAUTHORITY=/run/user/1000/ocimum-xauthority tray-has-icons'",
            timeout=60,
        )

    with subtest("notifications reach dunst"):
        su("notify-send TulsiOS hello")
        machine.wait_until_succeeds("pgrep -u alice -f bin/dunst")

    with subtest("Super+A opens the Assistant, Super+S the Software Center"):
        machine.sleep(2)
        machine.send_key("meta_l-a")
        machine.wait_until_succeeds("pgrep -u alice -f ocimum-assistant", timeout=60)
        machine.send_key("meta_l-s")
        machine.wait_until_succeeds("pgrep -u alice -f ocimum-software-center", timeout=60)
        machine.sleep(3)
        machine.screenshot("dwm_session")

    with subtest("GTK apps get the TulsiOS theme"):
        machine.succeed("grep -x gtk-theme-name=Mint-Y-Dark /etc/xdg/gtk-3.0/settings.ini")

    with subtest("no Cinnamon in the system"):
        machine.fail("nix-store -qR /run/current-system | grep -E -- '-cinnamon-[0-9]'")
        machine.fail("systemctl cat lightdm.service")
  '';
}
