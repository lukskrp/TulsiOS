import json

import pytest

from ocimum_software_center import recipe_ui


def test_the_remembered_choice(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert recipe_ui.packaging_default() == "ask"
    recipe_ui.save_packaging_default("recipe")
    assert recipe_ui.packaging_default() == "recipe"
    data = json.loads((tmp_path / "tulsi" / "packaging.json").read_text())
    assert data == {"whenNoPackage": "recipe"}
    # Other settings in the file are kept; unknown values read as "ask".
    (tmp_path / "tulsi" / "packaging.json").write_text('{"other": 1, "whenNoPackage": "x"}')
    assert recipe_ui.packaging_default() == "ask"
    recipe_ui.save_packaging_default("assistant")
    assert json.loads((tmp_path / "tulsi" / "packaging.json").read_text()) == {
        "other": 1, "whenNoPackage": "assistant"}
    with pytest.raises(ValueError):
        recipe_ui.save_packaging_default("model")


def test_keeping_downloads_is_remembered(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert recipe_ui.keep_sources_default() is True
    recipe_ui.save_keep_sources_default(False)
    recipe_ui.save_packaging_default("recipe")
    assert recipe_ui.keep_sources_default() is False
    assert recipe_ui.packaging_default() == "recipe"
    f = tmp_path / "x.bin"
    f.write_bytes(b"\0" * 3 * 1024 * 1024)
    assert recipe_ui.size_text(str(f)) == "3.0 MB"
    answers = {"name": "frob", "version": "1", "keep_source": False}
    assert recipe_ui.build_command("x", answers)[-1] == "--no-keep-source"
    ops = recipe_ui.local_ops({"name": "frob", "expression": "e", "keepSource": False}, False)
    assert ops[0]["keepSource"] is False


def test_assistant_without_a_model(monkeypatch):
    monkeypatch.setattr(recipe_ui.shutil, "which", lambda name: "/bin/" + name)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OCIMUM_ASSISTANT_PROVIDER", raising=False)
    monkeypatch.setattr(recipe_ui, "_keyring_has_key", lambda: False)
    assert recipe_ui.assistant_state() == (True, False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert recipe_ui.assistant_state() == (True, True)
    monkeypatch.setattr(recipe_ui.shutil, "which", lambda name: None)
    assert recipe_ui.assistant_state() == (False, False)


def test_build_command_and_ops():
    answers = {"name": "frob", "version": "1.0", "program": "frob", "unfree": True,
               "menu": False}
    cmd = recipe_ui.build_command("/home/a/frob.tar.gz", answers)
    assert cmd[1:] == ["recipe", "build", "/home/a/frob.tar.gz", "--name", "frob",
                       "--version", "1.0", "--program", "frob", "--unfree", "--no-menu",
                       "--keep-source"]
    outcome = {"name": "frob", "version": "1.0", "description": "d", "expression": "{ }: x",
               "origin": "recipe:archive frob.tar.gz"}
    ops = recipe_ui.local_ops(outcome, unfree=True)
    assert ops[0] == {"op": "acceptLicense", "name": "frob"}
    assert ops[1]["op"] == "addLocalPackage" and ops[1]["expression"] == "{ }: x"
    assert recipe_ui.local_ops(outcome, unfree=False)[0]["op"] == "addLocalPackage"


def test_a_failed_recipe_hands_its_draft_to_the_assistant():
    prompt = recipe_ui.failure_prompt(
        "/home/a/frob.tar.gz", {"name": "frob", "title": "Source code built with CMake"},
        {"name": "frob", "error": "The build needs Qt6, which the recipe does not know.",
         "draft": "/home/a/.local/share/tulsi/recipes/frob/package.nix",
         "expression": "{ stdenv }: stdenv.mkDerivation { }", "logTail": "CMake Error"})
    assert "frob.tar.gz" in prompt and "Qt6" in prompt
    assert "stdenv.mkDerivation" in prompt and "CMake Error" in prompt


def test_a_failed_recipe_can_be_edited_in_the_nix_editor(tmp_path, monkeypatch):
    draft = tmp_path / "frob" / "package.nix"
    draft.parent.mkdir()
    draft.write_text("{ stdenv }: stdenv.mkDerivation { }")
    monkeypatch.setattr(recipe_ui.shutil, "which",
                        lambda name: "/run/current-system/sw/bin/" + name)
    assert recipe_ui.edit_command({"draft": str(draft)}) == [
        "/run/current-system/sw/bin/ocimum-nix-editor", "--draft", str(draft.parent)]
    assert recipe_ui.edit_command({"draft": str(tmp_path / "gone" / "package.nix")}) == []
    assert recipe_ui.edit_command({}) == []
    monkeypatch.setattr(recipe_ui.shutil, "which", lambda name: None)
    assert recipe_ui.edit_command({"draft": str(draft)}) == []
