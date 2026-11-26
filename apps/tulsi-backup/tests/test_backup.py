"""Backup manifests, listings, and rsync calls, with rsync faked out."""

from __future__ import annotations

import json
import subprocess

import pytest

from tulsi_backup import cli, system


@pytest.fixture()
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "docs").mkdir(parents=True)
    (home / "docs" / "note.txt").write_text("hello")
    (home / ".cache" / "junk").mkdir(parents=True)
    (home / ".cache" / "junk" / "big").write_text("skip me")
    monkeypatch.setattr(system.socket, "gethostname", lambda: "box")
    return home


def fake_rsync(record, returncode=0):
    def run(*cmd, **kwargs):
        record.append(cmd)
        return subprocess.CompletedProcess(list(cmd), returncode, "", "")
    return run


def test_backup_writes_manifest_and_skips_cache(tmp_path, home, monkeypatch):
    record = []
    monkeypatch.setattr(system, "_run", fake_rsync(record))
    monkeypatch.setattr(system, "current_version", lambda *a: "0.1.0")
    monkeypatch.setattr(system, "software_list", lambda *a: ["firefox"])
    ok, message = system.backup(str(home), str(tmp_path / "usb"))
    assert ok, message
    dest = system.Path(message)
    manifest = system.Manifest.from_json((dest / system.MANIFEST).read_text())
    assert (manifest.hostname, manifest.tulsios_version, manifest.packages) == ("box", "0.1.0", ["firefox"])
    cmd = record[0]
    assert cmd[:3] == ("rsync", "-a", "--delete")
    assert "--exclude=.cache" in cmd
    assert str(home) + "/" in cmd and "home/" in cmd[-1]


def test_backup_missing_home(tmp_path):
    ok, message = system.backup(str(tmp_path / "nobody"), str(tmp_path / "usb"))
    assert not ok and "not a folder" in message


def test_backup_no_rsync(tmp_path, home, monkeypatch):
    monkeypatch.setattr(system.shutil, "which", lambda name: None)
    ok, message = system.backup(str(home), str(tmp_path / "usb"))
    assert not ok and "rsync" in message


def test_manifest_round_trip():
    manifest = system.Manifest(1, "2026-11-27T00:00:00Z", "box", "0.1.0", ["firefox", 7])
    back = system.Manifest.from_json(manifest.to_json())
    assert (back.hostname, back.tulsios_version, back.packages) == ("box", "0.1.0", ["firefox"])


def test_list_backups_newest_first(tmp_path):
    for day in ("20240101T000000Z", "20240201T000000Z"):
        dated = tmp_path / "box" / day
        (dated / "home").mkdir(parents=True)
        (dated / "manifest.json").write_text(json.dumps({
            "version": 1, "date": day, "hostname": "box",
            "tulsios_version": "0.1.0", "packages": [],
        }))
    (tmp_path / "box" / "notes.txt").write_text("not a backup")
    backups = system.list_backups(tmp_path)
    assert [p.name for p, _ in backups] == ["20240201T000000Z", "20240101T000000Z"]


def test_list_backups_missing_target(tmp_path):
    assert system.list_backups(tmp_path / "nothing") == []


def test_restore_merges_without_delete(tmp_path, monkeypatch):
    record = []
    monkeypatch.setattr(system, "_run", fake_rsync(record))
    src = tmp_path / "usb" / "box" / "day"
    (src / "home").mkdir(parents=True)
    home = tmp_path / "home"
    home.mkdir()
    ok, _ = system.restore(str(src), str(home))
    assert ok
    assert record[0][:2] == ("rsync", "-a")
    assert "--delete" not in record[0]


def test_restore_missing_backup(tmp_path):
    ok, message = system.restore(str(tmp_path / "nothing"), str(tmp_path))
    assert not ok and "not a backup" in message


def test_cli_backup_and_list(tmp_path, home, monkeypatch, capsys):
    record = []
    monkeypatch.setattr(system, "_run", fake_rsync(record))
    monkeypatch.setattr(system, "current_version", lambda *a: "0.1.0")
    monkeypatch.setattr(system, "software_list", lambda *a: [])
    assert cli.main(["backup", str(tmp_path / "usb"), "--home", str(home)]) == 0
    assert cli.main(["list", str(tmp_path / "usb")]) == 0
    assert "box" in capsys.readouterr().out


def test_cli_restore_reports_software(tmp_path, home, monkeypatch, capsys):
    record = []
    monkeypatch.setattr(system, "_run", fake_rsync(record))
    src = tmp_path / "usb" / "box" / "day"
    (src / "home").mkdir(parents=True)
    (src / "manifest.json").write_text(json.dumps({
        "version": 1, "date": "d", "hostname": "box",
        "tulsios_version": "0.1.0", "packages": ["firefox"],
    }))
    assert cli.main(["restore", str(src), "--home", str(home)]) == 0
    assert "firefox" in capsys.readouterr().out
