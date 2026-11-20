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


def test_extensions():
    from ocimum_software_center.model import extensions_of, ops_remove_extension

    state = {"browserExtensions": {"chromium": ["b" * 32], "firefox": ["z@x", "a@x"]}}
    assert extensions_of(state) == [("firefox", "a@x"), ("firefox", "z@x"), ("chromium", "b" * 32)]
    assert extensions_of({}) == []
    assert ops_remove_extension("firefox", "a@x") == [
        {"op": "removeExtension", "browser": "firefox", "id": "a@x"}
    ]


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


def test_history_by():
    from ocimum_software_center.model import history_by

    assert history_by("") == ""
    assert history_by("starah-assistant") == "by the Assistant"
    assert history_by("starah-helper") == "by agent helper"
    assert history_by("root") == "by the system"
    assert history_by("alice") == "by alice"


def test_done_text():
    from ocimum_software_center.model import done_text

    assert done_text("Installing vlc") == "vlc was installed."
    assert done_text("Removing gimp") == "gimp was removed."
    assert done_text("Undoing “Install vlc”") == "The change was undone."
    assert done_text("Upgrading TulsiOS to 0.2.0").startswith("TulsiOS was upgraded.")
    assert done_text("Other") == "Done."


def test_upgrade_status():
    from ocimum_software_center.model import upgrade_status

    base = {"following": "github:lukskrp/TulsiOS/stable", "currentVersion": "0.1.0", "error": ""}
    title, detail, can = upgrade_status({**base, "available": True, "availableVersion": "0.2.0"})
    assert (title, can) == ("TulsiOS 0.2.0 is available", True)
    assert "You have 0.1.0" in detail and "undo" in detail
    # Same VERSION, newer commit: fixes on the release branch.
    _, detail, can = upgrade_status({**base, "available": True, "availableVersion": "0.1.0"})
    assert can and "newer build" in detail
    assert upgrade_status({**base, "available": False}) == (
        "TulsiOS 0.1.0",
        "This is the newest release.",
        False,
    )
    _, detail, can = upgrade_status({**base, "error": "cannot reach github"})
    assert not can and "network" in detail
    _, detail, can = upgrade_status({"following": "", "currentVersion": "0.1.0"})
    assert not can and "local copy" in detail


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


def test_allow_listed_unfree_agent_needs_its_licence_accepted():
    from ocimum_software_center.model import describe_change, ops_install

    p = Package.from_json({"attr": "claude-code", "pname": "claude-code", "version": "2.1",
                           "unfree": True,
                           "license": {"name": "Unfree", "url": "https://example.com/terms"}})
    assert p.needs_license and p.license_url == "https://example.com/terms"
    assert ops_install("claude-code", accept_license=True) == [
        {"op": "acceptLicense", "name": "claude-code"},
        {"op": "addPackage", "name": "claude-code"},
    ]
    assert describe_change("+ licence accepted: claude-code") == "Accept the licence of claude-code"
    accepted = Package.from_json({"attr": "claude-code", "unfree": True, "license_accepted": True,
                                  "license": {"name": "Unfree"}})
    assert not accepted.needs_license
    assert not Package.from_json({"attr": "steam", "unfree": True}).needs_license
