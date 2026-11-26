# Ocimum Desktop: the tulsipkgs Cinnamon fork is what gets installed, the
# TulsiOS defaults (theme, wallpaper, menu icon, Assistant shortcut) apply, the
# session runs on XLibre with XLibre's drivers, and the session's wallpaper is
# painted by the OTK background daemon.
{ self }:
{
  name = "ocimum-desktop";

  nodes.machine =
    {
      config,
      modulesPath,
      pkgs,
      ...
    }:
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
      # So its launcher is asked for explicitly (the default follows the session app).
      ocimum.desktop.topRightLaunchers = [
        "${config.services.starah.session.package}/share/applications/org.starah.Session.desktop"
        "${config.ocimum.softwareCenter.package}/share/applications/org.tulsi.AIAgents.desktop"
      ];
      # Diagnostics for the wallpaper subtest; Starah's app for its launcher's icon.
      environment.systemPackages = [
        pkgs.xprop
        pkgs.jq
        pkgs.xdg-utils
        config.services.starah.session.package
      ];
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
        launchers = default("org.cinnamon", "panel-launchers")
        assert launchers == "['nemo.desktop', 'brave-origin.desktop', 'org.gnome.Terminal.desktop']", launchers
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
        # Starah's launcher, on the desktop at first login, trusted (executable)
        # and placed in the top-right corner.
        launcher = "/home/alice/Desktop/org.starah.Session.desktop"
        machine.wait_until_succeeds(f"test -x {launcher}")
        machine.succeed("grep -qx org.starah.Session.desktop /home/alice/.local/state/ocimum/desktop-launchers")
        position = su(f"gio info -a metadata::nemo-icon-position {launcher}")
        machine.log(position)
        found = re.search(r"nemo-icon-position: (\d+),(\d+)", position)
        assert found is not None, position
        x, y = int(found.group(1)), int(found.group(2))
        assert x > 512 and y < 100, (x, y)
        # The AI Agents shortcut (ADR 0023): one row below Starah's, opening the
        # Software Center's AI Agents page.
        ai = "/home/alice/Desktop/org.tulsi.AIAgents.desktop"
        machine.succeed(f"test -x {ai}")
        machine.succeed(f"grep -qx 'Exec=ocimum-software-center --page ai' {ai}")
        ai_position = su(f"gio info -a metadata::nemo-icon-position {ai}")
        ai_found = re.search(r"nemo-icon-position: (\d+),(\d+)", ai_position)
        assert ai_found is not None, ai_position
        assert abs(int(ai_found.group(1)) - x) < 50 and int(ai_found.group(2)) > y, ai_position
        monitor = su(f"gio info -a metadata::monitor {launcher}")
        assert "metadata::monitor: 0" in monitor, monitor
        machine.succeed("grep -A1 '^\\[desktop-monitor-0\\]' /home/alice/.config/nemo/desktop-metadata "
                        "| grep -qx 'nemo-icon-view-auto-layout=false'")
        # The default look: Tulsi Leaf wallpaper, the TulsiOS start button, the
        # panel's Show Desktop, launchers and Trash, desktop icons on the left.
        machine.sleep(10)
        machine.screenshot("desktop")

    with subtest("LocalSend comes with the desktop, and other devices can find it"):
        machine.succeed("command -v localsend_app")
        machine.succeed("test -n \"$(ls /run/current-system/sw/share/applications | grep -i localsend)\"")
        machine.succeed("{ iptables-save 2>/dev/null || true; nft list ruleset 2>/dev/null || true; } | grep -q 53317")

    with subtest("printers and scanners come with the desktop (Mint parity)"):
        machine.succeed("systemctl is-active cups.service")
        machine.succeed("systemctl is-active cups-browsed.service")
        # ipp-usb is on-demand (udev starts it with a USB printer), so present
        # but inactive in a VM without one.
        machine.succeed("systemctl cat ipp-usb.service")
        machine.succeed("command -v ipp-usb")
        machine.succeed("systemctl is-active avahi-daemon.service")
        machine.succeed("test -f /etc/sane-config/airscan.conf")
        machine.succeed("command -v simple-scan")
        machine.succeed("command -v system-config-printer")
        # Only free drivers by default: the manufacturers' are opt-in (ADR 0033).
        machine.fail("nix-store -qR /run/current-system | grep -q -- '-cnijfilter2-'")

    with subtest("Brave Origin comes with the desktop, in the panel and for web links"):
        # The launchers applet took the default into the user's own settings and
        # marked the old key used, so the list is now the user's to change.
        spices = "/home/alice/.config/cinnamon/spices/panel-launchers@cinnamon.org"
        machine.wait_until_succeeds(f"jq -e '.launcherList.value | index(\"brave-origin.desktop\")' {spices}/*.json",
                                    timeout=datetime.timedelta(seconds=60))
        assert su("gsettings get org.cinnamon panel-launchers").strip() == "['DEPRECATED']"
        # What the running panel shows, in order.
        machine.succeed(
            "cat > /tmp/launchers.js <<'EOF'\n"
            "imports.ui.appletManager.getRunningInstancesForUuid('panel-launchers@cinnamon.org')[0]"
            "._launchers.map(l => l.getId()).join(' ')\n"
            "EOF"
        )
        shown = su('gdbus call --session -d org.Cinnamon -o /org/Cinnamon -m org.Cinnamon.Eval "$(cat /tmp/launchers.js)"')
        machine.log(f"panel launchers: {shown}")
        assert "nemo.desktop brave-origin.desktop org.gnome.Terminal.desktop" in shown, shown
        assert su("xdg-mime query default x-scheme-handler/https").strip() == "brave-origin.desktop"
        version = su("brave-origin --version")
        assert "Brave" in version, version

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
