# Ocimum Desktop: the tulsipkgs Cinnamon fork is what gets installed, the
# TulsiOS defaults (theme, wallpaper, menu icon, Assistant shortcut) apply, the
# session runs on XLibre with XLibre's drivers, and the session's wallpaper is
# painted by the OTK background daemon.
{ self }:
{
  name = "ocimum-desktop";

  nodes.machine =
    { modulesPath, pkgs, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      ocimum.desktop.enable = true;
      ocimum.desktop.autoLoginUser = "alice";
      # Starah's first-login window would cover the sampled desktop pixel; it has
      # its own test (starah-setup).
      services.starah.session.enable = false;
      # Diagnostics for the wallpaper subtest.
      environment.systemPackages = [ pkgs.xprop ];
      virtualisation.memorySize = 2048;
    };

  testScript = ''
      import datetime
      import re

      def su(command):
          env = "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus DISPLAY=:0"
          return machine.succeed(f"su - alice -c '{env} {command}'")

      def desktop_pixel():
          # QEMU's screendump writes a binary PPM (P6) on the host. Sample the
          # empty desktop: right of the icons, halfway up, clear of the panel.
          path = machine.shared_dir / "screen.ppm"
          machine.send_monitor_command(f"screendump {path}")
          data = path.read_bytes()
          header = re.match(rb"P6\s+(\d+)\s+(\d+)\s+\d+\s", data)
          assert header is not None, "screendump is not a binary PPM"
          width, height = int(header.group(1)), int(header.group(2))
          x, y = width * 3 // 4, height // 2
          offset = header.end() + (y * width + x) * 3
          rgb = tuple(data[offset:offset + 3])
          machine.log(f"desktop pixel at {x},{y} of {width}x{height}: {rgb}")
          return rgb

      def close_to(rgb, want):
          return all(abs(a - b) <= 8 for a, b in zip(rgb, want))

      machine.wait_for_unit("multi-user.target")

      with subtest("the installed desktop is the Ocimum fork"):
          names = machine.succeed("grep -h '^Name=' /run/current-system/sw/share/xsessions/*.desktop || "
                                  "grep -rh '^Name=' /nix/store/*-cinnamon-*-ocimum*/share/xsessions/")
          assert "Ocimum Desktop" in names, names
          share = "/run/current-system/sw/share"
          for icon in ["ocimum-symbolic", "tulsi-start", "tulsi-start-white"]:
              machine.succeed(f"ls {share}/icons/hicolor/scalable/apps/{icon}.svg")
          for icon in ["tulsi-start", "tulsi-start-white"]:
              # True vectors, not a bitmap wrapped in an SVG (which blurs when drawn large).
              machine.fail(f"grep -q 'data:image' {share}/icons/hicolor/scalable/apps/{icon}.svg")
          machine.succeed(f"ls {share}/backgrounds/ocimum/tulsios-leaf.png")
          # System Settings → Backgrounds lists it, by a path that exists.
          listed = machine.succeed(f"grep -o '<filename>[^<]*' {share}/cinnamon-background-properties/ocimum.xml")
          machine.succeed(f"test -f {listed.strip().removeprefix('<filename>')}")

      with subtest("TulsiOS defaults are the compiled gsettings defaults"):
          # The Cinnamon module exports the compiled overrides for the session.
          schemas = machine.succeed("bash -lc 'echo $NIX_GSETTINGS_OVERRIDES_DIR'").strip()
          machine.succeed(f"test -f {schemas}/gschemas.compiled")
          def default(schema, key):
              return machine.succeed(
                  f"GSETTINGS_SCHEMA_DIR={schemas} GSETTINGS_BACKEND=memory gsettings get {schema} {key}"
              ).strip()
          icon = default("org.cinnamon", "app-menu-icon-name")
          assert icon == "'tulsi-start'", icon
          theme = default("org.cinnamon.desktop.interface", "gtk-theme")
          assert theme == "'Mint-Y-Dark'", theme
          uri = default("org.cinnamon.desktop.background", "picture-uri")
          assert uri.endswith("/share/backgrounds/ocimum/tulsios-leaf.png'"), uri
          machine.succeed(f"test -f {uri.strip(chr(39)).removeprefix('file://')}")
          applets = default("org.cinnamon", "enabled-applets")
          for uuid in ["menu", "show-desktop", "panel-launchers", "grouped-window-list", "trash", "calendar"]:
              assert f":{uuid}@cinnamon.org'" in applets, (uuid, applets)
          for key in ["show-desktop-icons", "computer-icon-visible", "home-icon-visible",
                      "trash-icon-visible", "volumes-visible"]:
              assert default("org.nemo.desktop", key) == "true", key

      with subtest("Super+A opens the Assistant"):
          read = lambda key: machine.succeed(f"su - alice -c 'dconf read {key}'").strip()
          base = "/org/cinnamon/desktop/keybindings/custom-keybindings/custom0/"
          assert read("/org/cinnamon/desktop/keybindings/custom-list") == "['custom0']"
          assert read(base + "command") == "'ocimum-assistant'"
          assert read(base + "binding") == "['<Super>a']"

      with subtest("the Cinnamon session starts"):
          machine.wait_for_x()
          machine.wait_until_succeeds(
              "su - alice -c 'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus "
              "gdbus call --session -d org.Cinnamon -o /org/Cinnamon -m org.Cinnamon.Eval Main.runState' "
              "| grep -q 'true,..2'"
          )
          # The session sees the TulsiOS panel (Cinnamon appends an instance id to
          # each entry once it has loaded them), and the desktop icons are drawn.
          applets = su("gsettings get org.cinnamon enabled-applets")
          for uuid in ["show-desktop", "panel-launchers", "trash"]:
              assert f":{uuid}@cinnamon.org:" in applets, (uuid, applets)
          machine.wait_until_succeeds("pgrep -u alice -f bin/.*nemo-desktop")
          # The default look: Tulsi Leaf wallpaper, the TulsiOS start button, the
          # panel's Show Desktop, launchers and Trash, desktop icons on the left.
          machine.sleep(10)
          machine.screenshot("desktop")

      with subtest("the display server is XLibre, with XLibre's drivers"):
          version = machine.succeed("X -version 2>&1")
          assert "XLibre X Server" in version, version
          pid = machine.succeed("pgrep -o -x X || pgrep -o -x Xorg").strip()
          exe = machine.succeed(f"readlink /proc/{pid}/exe").strip()
          assert "-xlibre-xserver-" in exe, exe
          maps = machine.succeed(f"cat /proc/{pid}/maps")
          drivers = sorted(set(re.findall(r"/nix/store/[a-z0-9]{32}-([^/]+)/lib/xorg/modules/(\S+_drv\.so)", maps)))
          machine.log(f"X drivers: {drivers}")
          # modesetting is built into the server; input goes through XLibre's
          # libinput fork, from its per-ABI module directory.
          assert any(p.startswith("xlibre-xserver-") and m.endswith("/modesetting_drv.so") for p, m in drivers), drivers
          assert any(p.startswith("xf86-input-libinput-") and m == "xlibre-25/input/libinput_drv.so" for p, m in drivers), drivers

      with subtest("the background daemon runs on OTK, not GTK 4"):
          machine.wait_until_succeeds("pgrep -f libexec/cinnamon-background-daemon")
          pid = machine.succeed("pgrep -f libexec/cinnamon-background-daemon | head -1").strip()
          maps = machine.succeed(f"cat /proc/{pid}/maps")
          assert "libotk-3.so" in maps, "daemon does not use OTK"
          assert "libgtk-4.so" not in maps, "daemon still loads GTK 4"

      with subtest("the daemon paints the configured wallpaper colour, and follows changes"):
          # A plain colour, so a pixel on the empty desktop shows exactly what was
          # painted. Since Cinnamon 6.8 the daemon reads picture-uri-list (one entry
          # per monitor; without a connector it applies to all).
          for colour, rgb in [("#3366cc", (0x33, 0x66, 0xcc)), ("#cc6633", (0xcc, 0x66, 0x33))]:
              entry = ('[{"picture-uri": <"">, "picture-options": <"none">, '
                       f'"primary-color": <"{colour}">, "color-shading-type": <"solid">}}]')
              machine.succeed(
                  "cat > /tmp/set-background.sh <<'EOF'\n"
                  f"gsettings set org.cinnamon.desktop.background picture-uri-list '{entry}'\n"
                  "EOF"
              )
              su("sh /tmp/set-background.sh")
              try:
                  retry(lambda _: close_to(desktop_pixel(), rgb), timeout=datetime.timedelta(seconds=60))
              finally:
                  machine.screenshot(f"wallpaper_{colour[1:]}")
                  machine.execute("su - alice -c 'DISPLAY=:0 xprop -root _XROOTPMAP_ID ESETROOT_PMAP_ID' >&2")
                  machine.execute("journalctl -b --no-pager | grep -i -E 'background|bg-' | tail -30 >&2")
    '';
}
