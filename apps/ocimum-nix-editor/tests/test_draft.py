import json

from ocimum_nix_editor import draft
from ocimum_nix_editor.text import indent_snippet, is_dark_theme, typed_prefix

TEXT = """{ stdenv }:
stdenv.mkDerivation {
  src = ./secret;
  x = builtins.readFile "/etc/shadow";
}
"""


def test_problems_are_placed_on_the_code_they_quote():
    assert draft.locate(
        "path literals such as `./secret` are not allowed; fetch sources with a hashed "
        "fetcher (fetchurl, fetchzip, fetchFromGitHub)", TEXT) == (2, 8, 8)
    assert draft.locate("`builtins.readFile` is not allowed in a local package", TEXT) == (3, 6, 17)
    assert draft.locate("the expression must be a function of its dependencies, e.g. "
                        "`{ stdenv, fetchurl }: stdenv.mkDerivation { … }`", TEXT) is None
    assert draft.locate("the expression is too large", TEXT) is None


def test_drafts_are_folders_with_recipe_json(tmp_path, monkeypatch):
    d = tmp_path / "frob"
    d.mkdir()
    (d / "package.nix").write_text("{ }: { }")
    assert not draft.is_draft(str(d))
    assert draft.draft_of(str(d / "package.nix")) == ""
    (d / "recipe.json").write_text(json.dumps({"name": "frob"}))
    assert draft.is_draft(str(d))
    assert draft.draft_of(str(d / "package.nix")) == str(d)
    assert draft.draft_info(str(d)) == {"name": "frob"}
    (tmp_path / "other.nix").write_text("{ }")
    assert draft.draft_of(str(tmp_path / "other.nix")) == ""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert draft.recipes_dir() == str(tmp_path / "tulsi" / "recipes")


def test_commands(monkeypatch):
    monkeypatch.setattr(draft.shutil, "which", lambda name: f"/bin/{name}")
    assert draft.build_command("/d") == ["/bin/tulsi", "recipe", "build-draft", "/d"]
    assert draft.check_command("/d/package.nix") == ["/bin/tulsi", "recipe", "check", "/d/package.nix"]
    arg = json.loads(draft.apply_ops_argument({"name": "frob"}, [{"op": "addLocalPackage"}]))
    assert arg == {"ops": [{"op": "addLocalPackage"}], "label": "Installing frob"}


def test_completion_text():
    assert typed_prefix("  buildInputs = [ pkgs.hel") == "hel"
    assert typed_prefix("  pkgs.") == ""
    assert typed_prefix("helix-g") == "helix-g"
    assert indent_snippet("a {\n  b;\n}", "  ") == "a {\n    b;\n  }"


def test_dark_themes_are_recognised_by_their_background():
    assert is_dark_theme((0.18, 0.18, 0.18), "Mint-Y")          # the colour decides
    assert not is_dark_theme((0.94, 0.94, 0.94), "Mint-Y-Dark")
    assert is_dark_theme(None, "Mint-Y-Dark-Aqua")
    assert is_dark_theme(None, "Adwaita", prefer_dark=True)
    assert not is_dark_theme(None, "Mint-Y")
