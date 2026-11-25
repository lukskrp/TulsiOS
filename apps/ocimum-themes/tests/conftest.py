import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STOCK = ROOT / "themes"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """Each test gets its own home, and the stock themes from the source tree."""
    for var, sub in (("XDG_CONFIG_HOME", "config"), ("XDG_STATE_HOME", "state"),
                     ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache")):
        monkeypatch.setenv(var, str(tmp_path / sub))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("TULSI_THEME_STOCK", str(STOCK))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "nothing"))
    return tmp_path


@pytest.fixture
def commands(monkeypatch):
    """Record the desktop tools a switch would run, instead of running them."""
    from tulsi_theme import run

    calls: list[tuple[str, ...]] = []

    def recorder(argv):
        calls.append(tuple(argv))
        if argv[:2] == ("gsettings", "list-schemas"):
            return "org.cinnamon.desktop.interface\norg.cinnamon.theme\norg.cinnamon.desktop.background\norg.x.apps.portal\n"
        return ""

    monkeypatch.setattr(run, "runner", recorder)
    return calls


def mint_available() -> bool:
    try:
        import sass  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("TULSI_THEME_MINT_SRC")) and bool(os.environ.get("TULSI_THEME_MINT_THEMES"))
