import subprocess

import pytest

from conftest import STOCK
from tulsi_theme import install, store


def make_repo(path, files):
    path.mkdir()
    for name, content in files.items():
        f = path / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(content if isinstance(content, bytes) else content.encode())
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "theme"], cwd=path, check=True)


def test_slug_from_url():
    assert install.slug_from_url("https://github.com/someone/omarchy-tea-house-theme.git") == "tea-house"
    assert install.slug_from_url("git@github.com:someone/Midnight") == "midnight"


def test_refuses_git_tricks():
    for url in ("ext::sh -c touch% /tmp/x", "--upload-pack=x", "file:///etc", "/local/path"):
        with pytest.raises(install.InstallError):
            install.check_url(url)


def test_keeps_only_data(tmp_path, monkeypatch):
    repo = tmp_path / "omarchy-sample-theme"
    make_repo(repo, {
        "colors.toml": (STOCK / "nord" / "colors.toml").read_text(),
        "LICENSE": "MIT License\n\nCopyright (c) someone",
        "backgrounds/1-sea.png": b"\x89PNG fake",
        "neovim.lua": "os.execute('rm -rf ~')",
        "hyprland.lua": "-- code",
        "install.sh": "#!/bin/sh\necho hi",
        "backgrounds/evil.sh": "#!/bin/sh",
    })
    # Clone the local repo as if it were https (check_url itself is tested above).
    monkeypatch.setattr(install, "check_url", lambda url: None)
    theme, dropped = install.install(str(repo))
    assert theme.slug == "sample" and not theme.stock
    kept = sorted(str(p.relative_to(theme.path)) for p in theme.path.rglob("*") if p.is_file())
    assert kept == [".source", "LICENSE", "backgrounds/1-sea.png", "colors.toml"]
    assert set(dropped) >= {"neovim.lua", "hyprland.lua", "install.sh", "backgrounds/evil.sh"}
    assert "MIT" in install.licence_text(theme)
    assert not any(p.stat().st_mode & 0o111 for p in theme.path.rglob("*") if p.is_file())
    install.remove("sample")
    assert "sample" not in store.themes()


def test_refuses_a_repo_without_a_palette(tmp_path, monkeypatch):
    repo = tmp_path / "not-a-theme"
    make_repo(repo, {"README.md": "hello"})
    monkeypatch.setattr(install, "check_url", lambda url: None)
    with pytest.raises(install.InstallError, match="no colors.toml"):
        install.install(str(repo))


def test_stock_themes_cannot_be_removed():
    with pytest.raises(install.InstallError):
        install.remove("nord")
