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
    import re

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

    with subtest("Super+Shift+A shows the AI Agents page (ADR 0023)"):
        # The running Software Center switches page; tulsi-terminal picks st here.
        machine.send_key("meta_l-shift-a")
        machine.sleep(3)
        machine.screenshot("dwm_ai_agents")
        su("tulsi-terminal --hold -- tulsi-ai-check >/dev/null 2>&1 &")
        machine.wait_until_succeeds("pgrep -u alice -x st", timeout=30)
        machine.wait_until_succeeds("test -s /home/alice/.cache/tulsi/ai-check.json", timeout=30)
        machine.sleep(2)
        machine.screenshot("dwm_ai_check")
        machine.succeed("pkill -u alice -x st")

    with subtest("GTK apps get the TulsiOS theme"):
        machine.succeed("grep -x gtk-theme-name=Mint-Y-Dark /etc/xdg/gtk-3.0/settings.ini")

    def bar_pixel():
        # The selected tag ("1") at the bar's left edge: SchemeSel's background,
        # below the occupied-tag square dwm draws in the corner, left of the "1".
        path = machine.shared_dir / "screen.ppm"
        machine.send_monitor_command(f"screendump {path}")
        data = path.read_bytes()
        header = re.match(rb"P6\s+(\d+)\s+(\d+)\s+\d+\s", data)
        assert header is not None, "screendump is not a binary PPM"
        width = int(header.group(1))
        x, y = 1, 14
        rgb = tuple(data[header.end() + (y * width + x) * 3:][:3])
        machine.log(f"bar pixel: {rgb}")
        return rgb

    def close_to(rgb, want):
        return all(abs(a - b) <= 10 for a, b in zip(rgb, want))

    with subtest("a theme recolours dwm at once, and undo restores it (ADR 0021)"):
        desktop = machine.succeed(
            "tr '\\0' '\\n' < /proc/$(pgrep -u alice -o -x dwm)/environ | sed -n 's/^XDG_CURRENT_DESKTOP=//p'"
        ).strip()
        machine.log(f"dwm session XDG_CURRENT_DESKTOP={desktop!r}")
        dwm_pid = machine.succeed("pgrep -u alice -o -x dwm").strip()
        assert close_to(bar_pixel(), (0x3f, 0x8a, 0x4f)), "the leaf green before"
        su(f"XDG_CURRENT_DESKTOP={desktop} tulsi-theme set catppuccin-latte")
        machine.sleep(2)
        assert close_to(bar_pixel(), (0x1e, 0x66, 0xf5)), "Catppuccin Latte's blue accent"
        # The same dwm, not a restarted one.
        assert machine.succeed("pgrep -u alice -o -x dwm").strip() == dwm_pid
        resources = su("xrdb -query")
        assert "dwm.selbgcolor:\t#1e66f5" in resources, resources
        machine.succeed("grep -x gtk-theme-name=Tulsi-catppuccin-latte /home/alice/.config/gtk-3.0/settings.ini")
        machine.succeed("test -s /home/alice/.config/tulsi/theme.wallpaper")
        # A terminal opened now has the palette's background (st's colour patch):
        # alone on tag 2, it fills the screen below the bar.
        machine.send_key("meta_l-2")
        machine.sleep(1)
        machine.send_key("meta_l-shift-ret")
        machine.wait_until_succeeds("pgrep -u alice -x st", timeout=30)
        machine.sleep(2)
        path = machine.shared_dir / "screen.ppm"
        machine.send_monitor_command(f"screendump {path}")
        data = path.read_bytes()
        header = re.match(rb"P6\s+(\d+)\s+(\d+)\s+\d+\s", data)
        assert header is not None
        width, height = int(header.group(1)), int(header.group(2))
        x, y = width * 3 // 4, height * 3 // 4
        terminal = tuple(data[header.end() + (y * width + x) * 3:][:3])
        machine.log(f"terminal pixel: {terminal}")
        machine.screenshot("dwm_catppuccin_latte")
        assert close_to(terminal, (0xef, 0xf1, 0xf5)), "Catppuccin Latte's background in st"
        machine.succeed("pkill -u alice -x st")
        machine.send_key("meta_l-1")
        machine.sleep(1)
        assert "own look" in su(f"XDG_CURRENT_DESKTOP={desktop} tulsi-theme undo")
        machine.sleep(2)
        assert close_to(bar_pixel(), (0x3f, 0x8a, 0x4f)), "the leaf green again"
        machine.fail("grep -q gtk-theme-name /home/alice/.config/gtk-3.0/settings.ini")
        assert machine.succeed("pgrep -u alice -o -x dwm").strip() == dwm_pid

    with subtest("LocalSend is here too"):
        machine.succeed("command -v localsend_app")

    with subtest("no Cinnamon in the system"):
        machine.fail("nix-store -qR /run/current-system | grep -E -- '-cinnamon-[0-9]'")
        machine.fail("systemctl cat lightdm.service")
  '';
}
