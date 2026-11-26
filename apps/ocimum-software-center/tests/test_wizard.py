from html import escape

from ocimum_software_center.wizard import STEPS, step_bar_markup


def test_six_steps_in_order():
    assert [name for name, _ in STEPS] == ["about", "match", "how", "details", "build", "install"]


def test_windows_programs_open_with_bottles_or_install_it():
    from ocimum_software_center.adopt import file_kind, name_from_file, windows_action
    from ocimum_software_center.wizard import KIND_TITLES

    assert file_kind("/home/a/Downloads/Setup.EXE") == "windows"
    assert file_kind("tool.msi") == "windows"
    assert name_from_file("Notepad++-8.7-Installer.x64.exe") == "notepad"
    assert KIND_TITLES["windows"] == "Windows program"
    assert windows_action("/tmp/a.exe", "/bin/bottles") == ("open", ["/bin/bottles", "/tmp/a.exe"])
    assert windows_action("/tmp/a.exe", None) == ("install", "bottles")


def test_the_step_bar_marks_where_you_are():
    bar = step_bar_markup("details", escape)
    assert "<b>4 Details</b>" in bar
    # Steps done are dimmer than steps to come.
    assert "<span alpha='55%'>1 What it is</span>" in bar
    assert "<span alpha='75%'>6 Install</span>" in bar
    assert bar.count("›") == 5
