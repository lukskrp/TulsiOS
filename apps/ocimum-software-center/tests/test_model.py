from ocimum_software_center.model import (
    JobTracker,
    Package,
    describe_change,
    history_title,
    normalize_query,
    ops_install,
    ops_remove,
    relative_time,
)


def test_package_titles():
    p = Package.from_json({"attr": "python3Packages.cowsay", "pname": "cowsay", "version": "6.1"})
    assert p.title == "cowsay"
    assert p.subtitle == "6.1 · python3Packages.cowsay"
    q = Package.from_json({"attr": "steam", "pname": "steam", "version": "1.0", "unfree": True})
    assert q.subtitle == "1.0 · unfree"
    assert Package(attr="x").title == "x"


def test_normalize_query():
    assert normalize_query("  media   player ") == "media player"
    assert normalize_query("a") is None
    assert normalize_query("   ") is None


def test_ops():
    assert ops_install("vlc") == [{"op": "addPackage", "name": "vlc"}]
    assert ops_remove("vlc") == [{"op": "removePackage", "name": "vlc"}]


def test_describe_change():
    assert describe_change("+ package vlc") == "Install vlc"
    assert describe_change("- package gimp") == "Remove gimp"
    assert describe_change("+ firefox extension uBlock0@raymondhill.net") == (
        "Add Firefox extension uBlock0@raymondhill.net"
    )
    assert describe_change("+ service docker enabled") == "Enable service docker"
    assert describe_change("- service docker unmanaged") == "Stop managing service docker"
    assert describe_change("something new") == "something new"


def test_history_title():
    assert history_title("tulsi: install cowsay, install sl") == "Install cowsay, install sl"
    assert history_title("tulsi: undo install cowsay") == "Undo: install cowsay"
    assert history_title("tulsi: initial state") == "Initial state"


def test_done_text():
    from ocimum_software_center.model import done_text

    assert done_text("Installing vlc") == "vlc was installed."
    assert done_text("Removing gimp") == "gimp was removed."
    assert done_text("Undoing “Install vlc”") == "The change was undone."
    assert done_text("Other") == "Done."


def test_relative_time():
    now = 1_000_000
    assert relative_time(now - 5, now) == "just now"
    assert relative_time(now - 60, now) == "1 minute ago"
    assert relative_time(now - 3 * 3600, now) == "3 hours ago"
    assert relative_time(now - 30 * 3600, now) == "yesterday"
    assert relative_time(now - 3 * 86400, now) == "3 days ago"


def test_job_tracker_normal_flow():
    t = JobTracker()
    t.begin("Installing vlc")
    assert t.busy
    assert t.started(7) == ([], None)
    assert t.progress(7, "building")
    assert not t.progress(8, "someone else's job")
    assert t.finished(7, True, "ok")
    assert not t.busy
    assert t.lines == ["building"]


def test_job_tracker_signals_before_reply():
    t = JobTracker()
    t.begin("Installing vlc")
    assert not t.progress(3, "early line")
    assert not t.finished(3, False, "boom")
    lines, result = t.started(3)
    assert lines == ["early line"]
    assert result == (False, "boom")
    assert not t.busy


def test_job_tracker_cancel():
    t = JobTracker()
    t.begin("x")
    t.cancel()
    assert not t.busy
