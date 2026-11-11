# The Software Center on X11 against a real tulsid (fake rebuild), with
# GTK3-O grafted system-wide. Screenshots land in the test's output.
{ self }:
{
  name = "software-center";

  nodes.machine =
    { pkgs, modulesPath, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/x11.nix")
        (modulesPath + "/../tests/common/user-account.nix")
      ];

      users.users.alice.extraGroups = [ "wheel" ];
      # The X11 test helper logs in as root by default; the app runs as alice.
      test-support.displayManager.auto.user = "alice";
      virtualisation.memorySize = 2048;

      tulsi.state = {
        enable = true;
        file = ./state-test.json;
      };
      tulsi.daemon = {
        enable = true;
        wheelNoPassword = true;
        packageIndex = ./index-test.json;
        rebuildCommand = [
          "${pkgs.writeShellScript "fake-rebuild" ''
            echo "building the system configuration..."
            sleep 2
            echo "activating the configuration..."
          ''}"
        ];
      };

      ocimum.softwareCenter.enable = true;
      ocimum.gtk3o.enable = true;

      environment.systemPackages = [
        pkgs.git
        pkgs.yad
        (pkgs.writeShellScriptBin "sc-action" ''
          # sc-action ACTION [ARG]: activate a Software Center Gtk.Application action
          if [ $# -ge 2 ]; then param="[<'$2'>]"; else param="[]"; fi
          exec ${pkgs.glib.bin}/bin/gdbus call --session --dest org.tulsi.SoftwareCenter \
            --object-path /org/tulsi/SoftwareCenter \
            --method org.gtk.Actions.Activate "$1" "$param" "{}"
        '')
      ];
    };

  testScript =
    { nodes, ... }:
    let
      gtk3o = nodes.machine.ocimum.gtk3o.package;
    in
    ''
      from datetime import timedelta

      env = ""

      def alice(cmd):
          return f"su - alice -c '{env} {cmd}'"

      def wait_window(title, seconds=120):
          # Retrying variant of wait_for_window: xwininfo fails (BadWindow) if a
          # window disappears while it walks the tree, which GTK does at startup.
          machine.wait_until_succeeds(
              alice("xwininfo -root -tree 2>/dev/null") + f" | grep -qF -- '{title}'",
              timeout=timedelta(seconds=seconds),
          )

      def gtk_libs(pid):
          out = machine.succeed(f"grep -o '/nix/store/[^ ]*/libgtk-3.so[^ ]*' /proc/{pid}/maps | sort -u")
          return sorted(set(line.split("/lib/")[0] for line in out.split()))

      machine.wait_for_x()
      machine.wait_for_unit("tulsid.service")

      # Take alice's session environment from her window manager, so the app
      # sees the same X authority and session bus as anything she starts.
      machine.wait_until_succeeds("pgrep -u alice -o icewm", timeout=timedelta(minutes=5))
      wm = machine.succeed("pgrep -u alice -o icewm").strip()
      session = dict(
          line.split("=", 1)
          for line in machine.succeed(f"tr '\\0' '\\n' < /proc/{wm}/environ").splitlines()
          if "=" in line
      )
      keep = ["DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"]
      env = " ".join(f"{k}={session[k]}" for k in keep if k in session)
      print(f"alice's session environment: {env}")

      with subtest("the app opens"):
          machine.succeed(alice("ocimum-software-center >/tmp/sc.log 2>&1 &"))
          try:
              wait_window("Software Center")
          finally:
              print(machine.execute("cat /tmp/sc.log; pgrep -a -u alice -f software-center")[1])
          machine.sleep(2)
          machine.screenshot("01-start")

      with subtest("GTK3-O is the only GTK in the app (system-wide graft)"):
          pid = machine.succeed("pgrep -u alice -f ocimum-software-center | head -1").strip()
          assert gtk_libs(pid) == ["${gtk3o}"], gtk_libs(pid)

      with subtest("a stock nixpkgs GTK 3 app (yad) also gets GTK3-O"):
          machine.succeed(alice("yad --title=graft-check --text=graft-check >/dev/null 2>&1 &"))
          wait_window("graft-check")
          zpid = machine.succeed("pgrep -u alice -n -f 'yad --title=graft-check'").strip()
          assert gtk_libs(zpid) == ["${gtk3o}"], gtk_libs(zpid)
          machine.succeed(f"kill {zpid}")

      with subtest("search finds packages from the index"):
          machine.succeed(alice("sc-action search cow"))
          machine.sleep(2)
          machine.screenshot("02-search")

      with subtest("installing goes through confirmation and tulsid"):
          machine.succeed(alice("sc-action install cowsay"))
          wait_window("Confirm Changes")
          machine.sleep(1)
          machine.screenshot("03-confirm")
          machine.send_key("ret")
          machine.wait_until_succeeds("grep -q cowsay /etc/nixos/tulsi/state.json", timeout=timedelta(seconds=60))
          machine.wait_until_succeeds(
              "git -C /etc/nixos log -1 --format=%s | grep -qx 'tulsi: install cowsay'", timeout=timedelta(seconds=60)
          )
          machine.sleep(2)
          machine.screenshot("04-installed")

      with subtest("undo from the app"):
          machine.succeed(alice("sc-action undo"))
          wait_window("Confirm Changes")
          machine.send_key("ret")
          machine.wait_until_succeeds("! grep -q cowsay /etc/nixos/tulsi/state.json", timeout=timedelta(seconds=60))
          machine.sleep(2)
          machine.screenshot("05-undone")

      with subtest("unknown and unfree packages are refused before any rebuild"):
          out = machine.fail(alice("tulsi install cowsy 2>&1"))
          assert "did you mean: cowsay" in out, out
          out = machine.fail(alice("tulsi install steam 2>&1"))
          assert "unfree" in out, out
          out = machine.succeed(alice("tulsi search cow"))
          assert "cowsay" in out, out

      machine.succeed("cat /tmp/sc.log >&2")
    '';
}
