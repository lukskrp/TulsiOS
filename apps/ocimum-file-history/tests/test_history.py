import os
import time
from pathlib import Path

import pytest

from ocimum_file_history import cli, history, welcome


def snapshot(root: Path, n: int, date: str, files: dict[str, str]) -> None:
    d = root / ".snapshots" / str(n)
    (d / "snapshot").mkdir(parents=True)
    (d / "info.xml").write_text(
        f"<?xml version=\"1.0\"?>\n<snapshot><type>single</type><num>{n}</num>"
        f"<date>{date}</date><description>timeline</description></snapshot>\n")
    for rel, text in files.items():
        p = d / "snapshot" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        # A file unchanged between snapshots keeps its time.
        stamp = 1_700_000_000 + hash(text) % 1000
        os.utime(p, (stamp, stamp))


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("TULSI_HOME_ROOT", str(tmp_path))
    monkeypatch.setenv("TULSI_SNAPSHOTS", str(tmp_path / ".snapshots"))
    snapshot(tmp_path, 1, "2026-11-20 10:00:00", {"alice/notes.txt": "v1", "alice/dir/a": "a"})
    snapshot(tmp_path, 2, "2026-11-21 10:00:00", {"alice/notes.txt": "v1", "alice/dir/a": "a"})
    snapshot(tmp_path, 3, "2026-11-22 10:00:00", {"alice/notes.txt": "v2"})
    (tmp_path / "alice").mkdir()
    (tmp_path / "alice" / "notes.txt").write_text("v3")
    return tmp_path


def test_snapshots_newest_first(home):
    assert [s.number for s in history.snapshots()] == [3, 2, 1]
    assert history.snapshots()[0].description == "timeline"


def test_versions_are_distinct(home):
    found = history.versions(home / "alice" / "notes.txt")
    # v2 (in 3), then v1 (in 2 and 1: listed once, at the newest).
    assert [v.snapshot.number for v in found] == [3, 2]
    assert [v.path.read_text() for v in found] == ["v2", "v1"]


def test_outside_home_is_refused(home, tmp_path_factory):
    with pytest.raises(ValueError):
        history.versions(tmp_path_factory.mktemp("elsewhere") / "x")
    with pytest.raises(ValueError):
        history.versions(home / ".snapshots" / "1")


def test_restore_trashes_what_is_there(home, monkeypatch):
    trashed = []
    monkeypatch.setattr(history, "trash", lambda p: (trashed.append(p.read_text()), p.unlink()))
    target = home / "alice" / "notes.txt"
    v1 = history.versions(target)[1]
    assert history.restore(target, v1) == target
    assert target.read_text() == "v1" and trashed == ["v3"]


def test_restore_as_copy_keeps_the_file(home):
    target = home / "alice" / "notes.txt"
    copy = history.restore(target, history.versions(target)[0], as_copy=True)
    assert target.read_text() == "v3"
    assert copy.read_text() == "v2" and copy.name.startswith("notes (from ") and copy.suffix == ".txt"


def test_deleted_folder_comes_back(home, capsys):
    folder = home / "alice" / "dir"
    assert cli.main(["restore", str(folder), "--from", "1"]) == 0
    assert (folder / "a").read_text() == "a"


def test_cli_without_snapshots_explains(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TULSI_SNAPSHOTS", str(tmp_path / "none"))
    assert cli.main(["snapshots"]) == 1
    assert "no history yet" in capsys.readouterr().err


def test_free_space_keeps_the_newest(home, monkeypatch):
    calls = []
    monkeypatch.setattr(history.subprocess, "run", lambda cmd, check: calls.append(cmd))
    numbers, _ = history.free_space(1, wait=0)
    assert numbers == [2, 1]
    assert calls == [["snapper", "-c", "home", "delete", "2", "1"]]
    assert history.free_space(5, wait=0) == ([], 0)


def test_welcome_adds_the_setting():
    base = "{ config, lib, pkgs, ... }:\n{\n  networking.hostName = \"x\";\n}\n"
    new = welcome.with_setting(base)
    assert new.rstrip().endswith("tulsi.homeSnapshots.enable = true;\n}")
    assert "networking.hostName" in new
    # Changing it again replaces the line.
    off = welcome.with_setting(new, False)
    assert off.count("tulsi.homeSnapshots.enable") == 1 and "= false;" in off
    assert "tulsi.homeSnapshots.enable = true;" in welcome.with_setting("")


def test_welcome_shows_once_and_not_in_vms(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.delenv("TULSI_WELCOME_FORCE", raising=False)
    monkeypatch.setattr(welcome, "is_virtual", lambda: False)
    assert welcome.should_show(True)
    welcome.mark_shown()
    assert not welcome.should_show(True)
    assert welcome.should_show(False)  # opened from the menu
    (tmp_path / "tulsi" / "welcome-shown").unlink()
    monkeypatch.setattr(welcome, "is_virtual", lambda: True)
    assert not welcome.should_show(True)


def test_fs_type(tmp_path):
    mounts = tmp_path / "mounts"
    mounts.write_text("/dev/vda1 / ext4 rw 0 0\n/dev/vda2 /home btrfs rw,subvol=/home 0 0\n")
    assert welcome.fs_type("/home", str(mounts)) == "btrfs"
    assert welcome.fs_type("/home/alice", str(mounts)) == "btrfs"
    assert welcome.fs_type("/etc", str(mounts)) == "ext4"
    assert time.time() > 0
