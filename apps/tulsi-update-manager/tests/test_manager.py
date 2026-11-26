"""Parsing for the Update Manager: release checks, generations, snapshots."""

from __future__ import annotations

from tulsi_update_manager import system


def test_parse_check_up_to_date():
    check = system.parse_check("TulsiOS 0.1.0 (abcdef123456)\nfollows github:lukskrp/TulsiOS/stable\nThis is the newest release.\n")
    assert check.current == "0.1.0"
    assert check.follows == "github:lukskrp/TulsiOS/stable"
    assert not check.available
    assert check.error == ""


def test_parse_check_available():
    check = system.parse_check("TulsiOS 0.1.0 (abcdef123456)\nTulsiOS 0.2.0 is available (123456abcdef): run `tulsi upgrade`\n")
    assert check.available
    assert check.available_version == "0.2.0"
    assert check.error == ""


def test_parse_check_offline():
    check = system.parse_check("TulsiOS 0.1.0 (abcdef123456)\ncannot check for a newer release: offline\n")
    assert not check.available
    assert check.error == "offline"
    assert check.current == "0.1.0"


def test_parse_check_empty():
    check = system.parse_check("")
    assert check.current == ""
    assert not check.available


def test_parse_generations():
    out = "  12   2026-11-20 10:00:00   \n  13   2026-11-25 09:00:00   (current)\n"
    generations = system.parse_generations(out)
    assert [(g.number, g.current) for g in generations] == [(12, False), (13, True)]
    assert generations[0].date == "2026-11-20 10:00:00"


def test_parse_generations_empty():
    assert system.parse_generations("") == []
    assert system.parse_generations("no generations\n") == []


def test_parse_snapshots():
    out = (
        " # | Type   | Pre # | Date                     | User | Cleanup  | Description    | Userdata\n"
        "---+--------+-------+--------------------------+------+----------+----------------+---------\n"
        "0  | single |       |                          | root |          | current        |         \n"
        "12 | single |       | Wed Nov 26 10:00:00 2026 | root | timeline | timeline       |         \n"
        "13 | pre    |       | Wed Nov 26 11:00:00 2026 | root | number   | before upgrade |         \n"
    )
    snapshots = system.parse_snapshots(out)
    assert [(s.number, s.description) for s in snapshots] == [(0, "current"), (12, "timeline"), (13, "before upgrade")]
    assert snapshots[1].date == "Wed Nov 26 10:00:00 2026"


def test_parse_snapshots_empty():
    assert system.parse_snapshots("") == []


def test_current_version_missing():
    assert system.current_version("/nonexistent-os-release") == "unknown"


def test_current_version_reads(tmp_path):
    release = tmp_path / "os-release"
    release.write_text('NAME="TulsiOS"\nTULSIOS_VERSION="0.3.1"\n')
    assert system.current_version(str(release)) == "0.3.1"


def test_upgrade_command_prefers_wrapper(monkeypatch):
    monkeypatch.setattr(system.shutil, "which", lambda name: "/run/current-system/sw/bin/tulsi-upgrade")
    assert system.upgrade_command() == ["tulsi-upgrade"]


def test_upgrade_command_falls_back(monkeypatch):
    monkeypatch.setattr(system.shutil, "which", lambda name: None)
    assert system.upgrade_command() == ["tulsi", "upgrade"]
