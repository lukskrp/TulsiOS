"""What a switch tells each desktop, checked without a desktop."""

from tulsi_theme import apply, kde, ocimum, store, terminal, xres


def test_terminal_palette_order():
    p = store.get("tokyo-night").palette
    colours = terminal.ansi(p)
    assert len(colours) == 16
    assert colours[0] == p["background"] and colours[7] == p["foreground"]
    assert colours[8] == p["muted"] and colours[15] == p["bright_foreground"]


def test_terminal_profile_keeps_users_profiles(commands, monkeypatch):
    from tulsi_theme import run

    def recorder(argv):
        commands.append(tuple(argv))
        if argv[-1].endswith("profiles:/list"):
            return "['aaaa-user']\n"
        return ""

    monkeypatch.setattr(run, "runner", recorder)
    terminal.apply(store.get("nord").palette, "Nord")
    writes = {c[2]: c[3] for c in commands if c[:2] == ("dconf", "write")}
    assert writes[terminal.BASE + "list"] == f"['aaaa-user', '{terminal.PROFILE}']"
    assert writes[terminal.BASE + "default"] == f"'{terminal.PROFILE}'"
    assert writes[f"{terminal.BASE}:{terminal.PROFILE}/use-theme-colors"] == "false"


def test_ocimum_settings():
    t = store.get("catppuccin-latte")
    bg = store.get("nord").path / "colors.toml"  # any file stands in for a background
    settings = {(s, k): v for s, k, v in ocimum.gsettings(t.palette, t.generated_name, bg)}
    assert settings[("org.cinnamon.desktop.interface", "gtk-theme")] == "Tulsi-catppuccin-latte"
    assert settings[("org.cinnamon.theme", "name")] == "Tulsi-catppuccin-latte"
    assert settings[("org.x.apps.portal", "color-scheme")] == "prefer-light"
    assert settings[("org.cinnamon.desktop.background", "picture-uri")].startswith("file:///")


def test_icon_theme_follows_accent_hue():
    assert ocimum.icon_theme("#1e66f5") == "Mint-Y-Blue"
    assert ocimum.icon_theme("#3f8a4f") == "Mint-Y"
    assert ocimum.icon_theme("#e82127") == "Mint-Y-Red"
    assert ocimum.icon_theme("#dcd7ba") == "Mint-Y-Sand"  # Kanagawa's pale, warm accent
    assert ocimum.icon_theme("#9d9d9d") == "Mint-Y-Grey"


def test_kde_scheme():
    p = store.get("gruvbox").palette
    text = kde.scheme(p, "Tulsi-gruvbox")
    assert "ColorScheme=Tulsi-gruvbox" in text
    for group in ("Window", "View", "Button", "Selection", "Tooltip", "Header", "Complementary"):
        assert f"[Colors:{group}]" in text and f"[Colors:{group}][Inactive]" in text
    assert "BackgroundNormal=40,40,40" in text  # gruvbox's background, #282828


def test_xresources():
    p = store.get("nord").palette
    text = xres.resources(p)
    assert f"dwm.selbgcolor: {p['accent']}" in text
    assert f"*.color15: {p['bright_foreground']}" in text


def test_xresources_reset_keeps_other_resources(monkeypatch):
    from tulsi_theme import run

    calls = []
    loaded = {}

    def recorder(argv):
        calls.append(tuple(argv))
        if argv[:2] == ("xrdb", "-query"):
            return "Xft.dpi:\t96\ndwm.selbgcolor:\t#81a1c1\n*.color0:\t#2e3440\n"
        if argv[:2] == ("xrdb", "-load"):
            from pathlib import Path

            loaded["text"] = Path(argv[2]).read_text()
        return ""

    monkeypatch.setattr(run, "runner", recorder)
    # The person's own GTK setting stays; ours come and go.
    xres.gtk_settings_file().parent.mkdir(parents=True)
    xres.gtk_settings_file().write_text("[Settings]\ngtk-font-name=Sans 11\n")
    bg = store.get("nord").path / "colors.toml"  # stands in for an image
    xres.apply(store.get("nord").palette, bg, gtk_theme="Tulsi-nord", icon_theme="Mint-Y-Blue")
    assert not any(c[0] == "pkill" for c in calls), "dwm is never signalled"
    assert ("xrdb", "-merge", str(xres.resources_file())) in calls
    ini = xres.gtk_settings_file().read_text()
    assert "gtk-theme-name=Tulsi-nord" in ini and "gtk-font-name=Sans 11" in ini
    assert xres.wallpaper_file().read_text().strip() == str(bg.resolve())

    xres.reset()
    lines = loaded["text"].splitlines()
    assert "Xft.dpi:\t96" in lines
    assert "*.color0:\t#2e3440" not in lines  # the palette's own resource is gone
    assert "dwm.selbgcolor:\t#3f8a4f" in lines  # dwm's leaf green is back
    assert not xres.resources_file().exists() and not xres.wallpaper_file().exists()
    ini = xres.gtk_settings_file().read_text()
    assert "gtk-theme-name" not in ini and "gtk-font-name=Sans 11" in ini


def test_switch_records_and_undoes(commands, monkeypatch, tmp_path):
    from tulsi_theme import mint

    monkeypatch.setattr(mint, "generate", lambda p, name, d: d / name)
    apply.switch(store.get("nord"), which="ocimum")
    apply.switch(store.get("kanagawa"), which="ocimum")
    assert store.current() == ("kanagawa", 0)
    assert ("gsettings", "set", "org.cinnamon.theme", "name", "Tulsi-kanagawa") in commands
    assert apply.undo() == "nord"
    assert store.current() == ("nord", 0)
    commands.clear()
    monkeypatch.setenv("TULSI_THEME_DESKTOP", "X-Cinnamon")
    assert apply.undo() == "default"
    assert ("gsettings", "reset", "org.cinnamon.theme", "name") in commands
    assert ("dconf", "reset", "-f", f"{terminal.BASE}:{terminal.PROFILE}/") in commands


def test_desktop_detection(monkeypatch):
    for value, expected in (("X-Cinnamon", "ocimum"), ("KDE", "sonic"), ("dwm", "dwm"), ("", "")):
        monkeypatch.setenv("XDG_CURRENT_DESKTOP", value)
        monkeypatch.delenv("TULSI_THEME_DESKTOP", raising=False)
        assert apply.desktop() == expected
