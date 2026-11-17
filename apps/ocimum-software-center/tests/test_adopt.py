from ocimum_software_center.adopt import (
    assistant_prompt,
    file_kind,
    name_from_file,
    parse_shim,
    terminal_text,
    Request,
)


def test_apt_install_with_flags_and_versions():
    r = parse_shim("apt", ["install", "-y", "vlc", "gimp=2.10", "--no-install-recommends"])
    assert (r.action, r.names, r.tool) == ("install", ["vlc", "gimp"], "apt")
    assert r.command == "apt install -y vlc gimp=2.10 --no-install-recommends"


def test_other_distributions():
    assert parse_shim("dnf", ["install", "htop"]).names == ["htop"]
    assert parse_shim("yum", ["-y", "install", "htop"]).action == "install"
    assert parse_shim("zypper", ["in", "htop"]).action == "install"
    assert parse_shim("brew", ["install", "wget@1"]).names == ["wget"]
    assert parse_shim("snap", ["install", "spotify"]).names == ["spotify"]
    assert parse_shim("apt-get", ["purge", "x"]).action == "remove"
    assert parse_shim("apt", ["search", "cow"]).action == "search"
    assert parse_shim("apt", ["update"]).action == "other"


def test_pacman_flags():
    assert parse_shim("pacman", ["-S", "firefox"]).action == "install"
    assert parse_shim("pacman", ["-Syu", "firefox"]).action == "install"
    assert parse_shim("pacman", ["-Ss", "fire"]).action == "search"
    assert parse_shim("pacman", ["-Rns", "firefox"]).action == "remove"


def test_installing_a_downloaded_deb_with_apt():
    r = parse_shim("apt", ["install", "./Downloads/code_1.95_amd64.deb"])
    assert r.file == "./Downloads/code_1.95_amd64.deb" and r.kind == "deb" and r.names == []


def test_file_kinds_and_names():
    assert file_kind("x.AppImage") == "appimage"
    assert file_kind("x.tar.xz") == "archive"
    assert file_kind("notes.txt") == ""
    assert name_from_file("/home/a/Downloads/vlc_3.0.21-1_amd64.deb") == "vlc"
    assert name_from_file("frob-1.0.tar.gz") == "frob"
    assert name_from_file("Obsidian-1.6.7.AppImage") == "obsidian"
    assert name_from_file("foo-bar-linux-x86_64.tar.xz") == "foo-bar"
    assert name_from_file("installer.run") == "installer"


def test_terminal_text_points_to_the_tulsios_way():
    text = terminal_text(parse_shim("apt", ["install", "vlc"]))
    assert "does not install software with apt" in text
    assert "tulsi install vlc" in text


def test_shim_hands_the_command_to_the_window(monkeypatch, capsys):
    """The shim opens the window in a new process; the tool and command must reach it."""
    import subprocess

    import ocimum_software_center.adopt as adopt

    launched = []
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **_kw: launched.append(cmd))
    assert adopt.main(["shim", "apt", "install", "-y", "hello"]) == 1
    (cmd,) = launched
    seen = []
    monkeypatch.setattr(adopt, "run_gui", lambda req: seen.append(req) or 0)
    assert adopt.main(cmd[1:]) == 0
    (req,) = seen
    assert (req.tool, req.command, req.names) == ("apt", "apt install -y hello", ["hello"])
    assert "I tried to install it with: apt install -y hello" in assistant_prompt(req)


def test_assistant_prompt_carries_the_file_in_the_store():
    req = Request("install", [], tool="", file="/home/a/frob-1.0.tar.gz", kind="archive")
    prompt = assistant_prompt(req, store_path="/nix/store/abc-frob-1.0.tar.gz",
                              file_hash="sha256-xyz")
    assert '"frob"' in prompt and "requireFile" in prompt and "sha256-xyz" in prompt
