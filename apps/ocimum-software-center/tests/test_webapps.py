import random

import pytest

from ocimum_software_center import webapps

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path


def which_brave(program):
    return "/run/current-system/sw/bin/brave-origin" if program == "brave-origin" else None


def test_suggestions_load_and_are_well_formed():
    items = webapps.suggestions()
    names = [s.name for s in items]
    assert "Claude" in names and len(names) == len(set(names))
    for s in items:
        assert s.url.startswith("https://") and s.blurb and s.category in webapps.CATEGORIES


def test_add_writes_a_web_app_manager_launcher(home):
    def get(url):
        if url == "https://claude.ai":
            return b'<html><head><link rel="apple-touch-icon" href="/apple.png"></head></html>'
        if url == "https://claude.ai/apple.png":
            return PNG
        raise OSError("not found")

    app = webapps.add("Claude", "claude.ai", which=which_brave, get=get)
    text = app.path.read_text()
    codename = app.path.stem.removeprefix("WebApp-")
    assert app.path.parent == home / "applications"
    assert codename.startswith("Claude") and codename[-4:].isdigit()
    assert 'Exec=brave-origin --app="https://claude.ai" ' in text
    assert f"--user-data-dir={home}/ice/profiles/{codename}" in text
    assert f"StartupWMClass=WebApp-{codename}" in text  # how Web App Manager finds it
    assert "X-WebApp-Browser=Brave Origin" in text and "X-WebApp-Isolated=true" in text
    icon = home / "ice/icons" / f"{codename}.png"
    assert icon.read_bytes() == PNG and f"Icon={icon}" in text

    # Listed, found by its site, and not added twice.
    assert [a.name for a in webapps.installed()] == ["Claude"]
    assert webapps.find("https://www.claude.ai/") is not None
    assert webapps.add("Claude", "https://claude.ai", which=which_brave, get=get).path == app.path

    # Removing takes its profile (logins) and icon too.
    (home / "ice/profiles" / codename).mkdir(parents=True)
    webapps.remove(app)
    assert not app.path.exists() and not icon.exists()
    assert not (home / "ice/profiles" / codename).exists()
    assert webapps.installed() == []


def test_no_icon_falls_back_and_no_browser_is_an_error(home):
    def offline(url):
        raise OSError("offline")

    app = webapps.add("Proton Mail", "https://mail.proton.me", "Network", which=which_brave, get=offline)
    assert "Icon=webapp-manager" in app.path.read_text()
    assert "Categories=GTK;Network;" in app.path.read_text()
    with pytest.raises(RuntimeError, match="Chromium-based"):
        webapps.add("Gemini", "https://gemini.google.com", which=lambda _p: None, get=offline)
    with pytest.raises(ValueError):
        webapps.add("X", "https://x.org", "Nonsense", which=which_brave, get=offline)


def test_icon_candidates_prefer_large_icons():
    html = ('<link rel="icon" href="/fav.ico"><link rel="shortcut icon" href="https://cdn.x/i.png">'
            "<link rel='apple-touch-icon' href='touch.png'>")
    assert webapps.icon_candidates(html, "https://x.org/app/") == [
        "https://x.org/app/touch.png",
        "https://cdn.x/i.png",
        "https://x.org/fav.ico",
        "https://x.org/favicon.ico",
    ]


def test_codenames_avoid_collisions():
    rng = random.Random(1)
    first = webapps.codename_for("You Tube!", set(), random.Random(1))
    assert first.startswith("YouTube") and len(first) == len("YouTube") + 4
    assert webapps.codename_for("You Tube!", {first}, rng) != first


def test_cli_lists_and_removes(home, capsys, monkeypatch):
    monkeypatch.setattr(webapps.shutil, "which", which_brave)
    monkeypatch.setattr(webapps, "_get", lambda url, limit=0: (_ for _ in ()).throw(OSError()))
    assert webapps.main(["add", "Docs", "https://docs.google.com", "--icon", "x-office-document"]) == 0
    capsys.readouterr()
    assert webapps.main(["list"]) == 0
    assert "Docs\thttps://docs.google.com" in capsys.readouterr().out
    assert webapps.main(["remove", "Docs"]) == 0
    assert webapps.main(["remove", "Docs"]) == 1
