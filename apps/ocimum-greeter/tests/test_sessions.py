import json

from ocimum_greeter.config import Config
from ocimum_greeter.sessions import find_sessions


def write(directory, name, text):
    (directory / f"{name}.desktop").write_text(text, encoding="utf-8")


def test_sessions_are_read_and_the_default_comes_first(tmp_path):
    write(tmp_path, "cinnamon", "[Desktop Entry]\nName=Ocimum Desktop\nExec=cinnamon-session-cinnamon\nDesktopNames=X-Cinnamon\n")
    write(tmp_path, "aaa-wm", "[Desktop Entry]\nName=A Window Manager\nExec=/nix/store/x/xsession\n")
    write(tmp_path, "hidden", "[Desktop Entry]\nName=Hidden\nExec=x\nHidden=true\n")
    write(tmp_path, "noexec", "[Desktop Entry]\nName=Broken\n")
    write(tmp_path, "garbage", "not a desktop file")

    sessions = find_sessions(tmp_path, default="cinnamon")
    assert [s.id for s in sessions] == ["cinnamon", "aaa-wm"]
    cinnamon = sessions[0]
    assert cinnamon.name == "Ocimum Desktop"
    assert cinnamon.environment() == [
        "XDG_SESSION_TYPE=x11",
        "XDG_SESSION_DESKTOP=cinnamon",
        "XDG_CURRENT_DESKTOP=X-Cinnamon",
    ]
    assert sessions[1].environment() == ["XDG_SESSION_TYPE=x11", "XDG_SESSION_DESKTOP=aaa-wm"]


def test_config_and_last_user(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"sessions_dir": "/s", "launcher": "/l", "state_dir": str(state), "unknown": 1}),
        encoding="utf-8",
    )
    config = Config.load(path)
    assert config.sessions_dir == "/s" and config.launcher == "/l"
    assert config.last_user() is None
    config.remember_user("alice")
    assert config.last_user() == "alice"
