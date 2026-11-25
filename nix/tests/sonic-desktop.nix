# SonicDE (ADR 0020): the desktop the installer offers beside Ocimum and dwm. The
# Ocimum Greeter logs into the SonicDE X11 session on XLibre; sonic-win and the
# Plasma shell run with TulsiOS's look-and-feel (pinned apps, wallpaper, start
# button), Super+A opens the Assistant, and Sonic's apps start. KDE apps on the
# machine come from Sonic's package set. Screenshots land in the output.
{ self }:
{
  name = "sonic-desktop";

  # The module overlays kdePackages with sonicPackages (KDE apps on Sonic's
  # frameworks), so this node evaluates its own pkgs.
  node.pkgsReadOnly = false;

  nodes.machine =
    {
      config,
      pkgs,
      modulesPath,
      ...
    }:
    {
      # kdePackages is sonicPackages on this machine: KDE apps get Sonic's frameworks.
      assertions = [
        {
          assertion =
            pkgs.kdePackages.kcoreaddons.outPath == config.sonic.desktop.packages.kcoreaddons.outPath;
          message = "On SonicDE, kdePackages must be Sonic's package set.";
        }
      ];
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      tulsi.desktop = {
        session = "sonic";
        autoLoginUser = "alice";
      };
      ocimum.softwareCenter.enable = true;
      ocimum.assistant.enable = true;
      tulsi.daemon.enable = true;
      # Starah's first-login window would cover the desktop; it has its own test.
      services.starah.session.enable = false;
      virtualisation.memorySize = 4096;
      environment.systemPackages = [ pkgs.xdotool ];
    };

  testScript =
    { nodes, ... }:
    let
      sonic = nodes.machine.sonic.desktop.packages;
    in
    ''
      from datetime import timedelta

      def su(command):
          env = "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus DISPLAY=:0"
          return machine.succeed(f"su - alice -c '{env} {command}'")

      def session_log():
          machine.execute("ps -u alice -o pid,args | cut -c1-200 >&2")
          machine.execute("journalctl -b --no-pager -o cat | grep -iE 'kwin|plasma|ksmserver|sonic|kded|startplasma|qt\\.|error' | tail -80 >&2")
          machine.execute("tail -n 60 /home/alice/.xsession-errors /home/alice/.local/share/sddm/xorg-session.log >&2")
          machine.screenshot("sonic-session-failed")

      def wait_process(pattern):
          # Wrapped Qt programs run as .name-wrapped: match their command lines.
          try:
              machine.wait_until_succeeds(f"pgrep -u alice -f '{pattern}'", timeout=timedelta(minutes=3))
          except BaseException:
              session_log()
              raise

      machine.wait_for_unit("multi-user.target")

      with subtest("the Ocimum Greeter logs into SonicDE, on XLibre"):
          machine.wait_for_x()
          # SonicDE's names: sonic-win (its X11 KWin) and sonicshell (the Plasma shell).
          wait_process("bin/sonic-win")
          wait_process("bin/sonicshell")
          version = machine.succeed("X -version 2>&1")
          assert "XLibre X Server" in version, version
          # sonic-win is Sonic's KWin (X11), not KDE's.
          machine.succeed("readlink -f /proc/$(pgrep -u alice -of 'bin/sonic-win')/exe | grep -q '${sonic.kwin}'")
          # The session's environment, as the shell got it (a fresh su shell has none).
          desktop = machine.succeed("tr '\\0' '\\n' < /proc/$(pgrep -u alice -of 'bin/sonicshell')/environ | grep '^XDG_CURRENT_DESKTOP='")
          assert "SonicDE" in desktop or "KDE" in desktop, desktop

      with subtest("TulsiOS's look-and-feel: the pinned apps, start button and wallpaper"):
          lnf = su("kreadconfig6 --file kdeglobals --group KDE --key LookAndFeelPackage").strip()
          assert lnf == "org.tulsios.sonic.desktop", lnf
          machine.succeed(
              "cat > /tmp/launchers.js <<'EOF'\n"
              "var out = [];\n"
              "panels().forEach(function (p) { p.widgets().forEach(function (w) {\n"
              "  if (w.type === 'org.kde.plasma.taskmanager' || w.type === 'org.kde.plasma.icontasks') {\n"
              "    w.currentConfigGroup = ['General']; out.push(w.readConfig('launchers')); }\n"
              "  if (w.type === 'org.kde.plasma.kickoff') { w.currentConfigGroup = ['General']; out.push('icon=' + w.readConfig('icon')); }\n"
              "}); });\n"
              "print(out.join(' | '));\n"
              "EOF"
          )
          # Sonic's shell scripting: org.sonicde.sonicshell at /SonicShell (KDE's /PlasmaShell).
          machine.succeed(
              "cat > /tmp/panel.sh <<'EOF'\n"
              "qdbus org.sonicde.sonicshell /SonicShell evaluateScript \"$(cat /tmp/launchers.js)\" 2>/tmp/panel.err && exit 0\n"
              "cat /tmp/panel.err >&2; qdbus org.sonicde.sonicshell /SonicShell >&2; exit 1\n"
              "EOF\n"
              "chmod 755 /tmp/panel.sh"
          )
          machine.wait_until_succeeds("su - alice -c 'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus /tmp/panel.sh' | grep -q org.tulsi.SoftwareCenter.desktop",
                                      timeout=timedelta(minutes=2))
          shown = su("/tmp/panel.sh")
          machine.log(f"panel: {shown}")
          for want in ["preferred://browser", "org.kde.konsole.desktop", "org.tulsi.SoftwareCenter.desktop",
                       "org.tulsi.Assistant.desktop", "org.tulsi.AIAgents.desktop", "icon=tulsi-start"]:
              assert want in shown, (want, shown)
          assert su("xdg-mime query default x-scheme-handler/https").strip() == "brave-origin.desktop"
          machine.sleep(5)
          machine.screenshot("sonic-desktop")

      with subtest("Super+A opens the Assistant"):
          # The shortcut is X-KDE-Shortcuts in the Assistant's .desktop file.
          machine.wait_until_succeeds("su - alice -c 'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus qdbus org.kde.kglobalaccel' | grep -q org_tulsi_Assistant",
                                      timeout=timedelta(seconds=60))
          machine.send_key("meta_l-a")
          machine.wait_until_succeeds("pgrep -u alice -f ocimum-assistant", timeout=timedelta(seconds=60))
          machine.sleep(2)
          machine.screenshot("sonic-assistant")
          machine.execute("pkill -u alice -f ocimum-assistant")

      with subtest("Sonic's apps start: Ecco, Sonic Terminal, System Monitor, Screenies"):
          # Start each app in the session's environment (display, X authority, D-Bus), as the shell has it.
          machine.succeed(
              "cat > /tmp/in-session <<'EOF'\n"
              "#!/bin/sh\n"
              "eval \"$(tr '\\0' '\\n' < /proc/$(pgrep -u alice -of bin/sonicshell)/environ | sed -n 's/^\\([A-Z_][A-Z0-9_]*\\)=\\(.*\\)$/export \\1='\"'\"'\\2'\"'\"'/p')\"\n"
              "exec \"$@\"\n"
              "EOF\n"
              "chmod 755 /tmp/in-session"
          )
          # Screenies is Spectacle, renamed: its program is sonic-screenies.
          apps = ["dolphin", "konsole", "plasma-systemmonitor", "sonic-screenies"]
          for app in apps:
              machine.succeed(f"su - alice -c '/tmp/in-session {app} >/tmp/{app}.log 2>&1 &'")
              # Started by name: the command line begins with it (or its store path).
              machine.wait_until_succeeds(f"pgrep -u alice -f '^[^ ]*{app}'", timeout=timedelta(seconds=90))
          machine.sleep(10)
          # Still running once their windows are up.
          for app in apps:
              machine.succeed(f"pgrep -u alice -f '^[^ ]*{app}'")
          machine.screenshot("sonic-apps")

    '';
}
