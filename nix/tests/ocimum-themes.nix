# Themes on Ocimum (ADR 0021): a palette becomes the session's GTK and Cinnamon
# theme, icons, terminal colours and background at once, with no rebuild; the
# Themes app opens; undo goes back to the theme before, then to Ocimum's own look.
{ self }:
{
  name = "ocimum-themes";

  nodes.machine =
    { pkgs, modulesPath, ... }:
    {
      imports = [
        self.nixosModules.default
        (modulesPath + "/../tests/common/user-account.nix")
      ];
      ocimum.desktop.enable = true;
      ocimum.desktop.autoLoginUser = "alice";
      services.starah.session.enable = false;
      environment.systemPackages = [ pkgs.xdotool ];
      virtualisation.memorySize = 2048;
    };

  testScript = ''
    import datetime
    import re

    ENV = ("DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus DISPLAY=:0 "
           "XDG_CURRENT_DESKTOP=X-Cinnamon")

    def su(command, check=True):
        run = machine.succeed if check else machine.execute
        return run(f"su - alice -c '{ENV} {command}'")

    def get(schema, key):
        return su(f"gsettings get {schema} {key}").strip().strip("'")

    def panel_pixel():
        path = machine.shared_dir / "screen.ppm"
        machine.send_monitor_command(f"screendump {path}")
        data = path.read_bytes()
        header = re.match(rb"P6\s+(\d+)\s+(\d+)\s+\d+\s", data)
        assert header is not None, "screendump is not a binary PPM"
        width, height = int(header.group(1)), int(header.group(2))
        # The bottom panel, right of the window list, clear of the tray.
        x, y = width * 3 // 5, height - 6
        rgb = tuple(data[header.end() + (y * width + x) * 3:][:3])
        machine.log(f"panel pixel at {x},{y}: {rgb}")
        return rgb

    machine.wait_for_unit("multi-user.target")
    machine.wait_for_x()
    machine.wait_until_succeeds(
        f"su - alice -c '{ENV} gdbus call --session -d org.Cinnamon -o /org/Cinnamon "
        "-m org.Cinnamon.Eval Main.runState' | grep -q 'true,..2'",
        timeout=datetime.timedelta(minutes=5),
    )
    machine.sleep(5)

    with subtest("the stock palettes are there, with credits"):
        listed = su("tulsi-theme list")
        machine.log(listed)
        for slug in ["tulsi-leaf", "catppuccin-latte", "nord", "tokyo-night"]:
            assert slug in listed, (slug, listed)
        machine.succeed("test -f /run/current-system/sw/share/tulsi/themes/nord/CREDITS.md")
        dark_panel = panel_pixel()
        assert sum(dark_panel) < 3 * 90, dark_panel  # Mint-Y-Dark's panel

    with subtest("a light palette switches the session at once"):
        su("tulsi-theme set catppuccin-latte")
        value = get("org.cinnamon.desktop.interface", "gtk-theme")
        assert value == "Tulsi-catppuccin-latte", value
        value = get("org.cinnamon.theme", "name")
        assert value == "Tulsi-catppuccin-latte", value
        value = get("org.cinnamon.desktop.interface", "icon-theme")
        assert value == "Mint-Y-Blue", value
        value = get("org.x.apps.portal", "color-scheme")
        assert value == "prefer-light", value
        # Ocimum's background daemon moves picture-uri into its per-monitor list.
        uris = get("org.cinnamon.desktop.background", "picture-uri-list")
        assert "/tulsios-leaf.png'" in uris, f"picture-uri-list is {uris!r}"
        theme = "/home/alice/.local/share/themes/Tulsi-catppuccin-latte"
        machine.succeed(f"grep -qi '#1e66f5' {theme}/gtk-3.0/gtk.css")
        machine.succeed(f"grep -qi '#1e66f5' {theme}/cinnamon/cinnamon.css")
        machine.succeed(f"test -s {theme}/gtk-3.0/assets/checkbox-checked.png")
        # Cinnamon finds the generated theme and loads it: the panel turns light.
        machine.wait_until_succeeds(
            "journalctl -b | grep -q 'loading user theme: "
            "/home/alice/.local/share/themes/Tulsi-catppuccin-latte/cinnamon/cinnamon.css'",
            timeout=datetime.timedelta(seconds=30),
        )
        machine.sleep(3)
        light_panel = panel_pixel()
        assert sum(light_panel) > 3 * 170, light_panel
        # GNOME Terminal's default profile is the palette's.
        profile = su("dconf read /org/gnome/terminal/legacy/profiles:/default").strip()
        assert profile == "'6f3f5d1e-7a1c-4b8e-9d2f-71c5a1e0b0a1'", profile
        palette = su(f"dconf read /org/gnome/terminal/legacy/profiles:/:{profile.strip(chr(39))}/palette")
        assert "'#eff1f5'" in palette and "'#d20f39'" in palette, palette
        machine.screenshot("catppuccin-latte")

    with subtest("the Themes app opens"):
        # The session's X authority, from a session program's environment.
        xauth = machine.succeed(
            "tr '\\0' '\\n' < /proc/$(pgrep -u alice -o -f bin/.*nemo-desktop)/environ "
            "| sed -n 's/^XAUTHORITY=//p'"
        ).strip()
        machine.log(f"XAUTHORITY={xauth!r}")
        x = f"XAUTHORITY={xauth} " if xauth else ""
        su(f"{x}ocimum-themes >/tmp/themes.log 2>&1 &")
        machine.sleep(10)
        machine.log(machine.execute("cat /tmp/themes.log; pgrep -af ocimum-themes")[1])
        machine.wait_until_succeeds(
            f"su - alice -c '{ENV} {x}xdotool search --name \"^Themes$\"'",
            timeout=datetime.timedelta(seconds=60),
        )
        machine.sleep(3)
        machine.fail("grep -q Traceback /tmp/themes.log")
        machine.screenshot("themes-app")
        su("pkill -f ocimum-themes", check=False)

    with subtest("undo goes back, then to Ocimum's own look"):
        su("tulsi-theme set nord")
        value = get("org.cinnamon.theme", "name")
        assert value == "Tulsi-nord", value
        assert "back to Catppuccin Latte" in su("tulsi-theme undo")
        value = get("org.cinnamon.theme", "name")
        assert value == "Tulsi-catppuccin-latte", value
        assert "own look" in su("tulsi-theme undo")
        value = get("org.cinnamon.theme", "name")
        assert value == "Mint-Y-Dark", value
        value = get("org.cinnamon.desktop.interface", "gtk-theme")
        assert value == "Mint-Y-Dark", value
        profile = su("dconf read /org/gnome/terminal/legacy/profiles:/default").strip()
        assert "6f3f5d1e" not in profile, profile
        machine.sleep(3)
        assert sum(panel_pixel()) < 3 * 90
  '';
}
