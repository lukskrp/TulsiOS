"""Imports the GTK modules so GObject registration errors fail the build."""

import importlib

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")


@pytest.mark.parametrize("module", ["window", "app", "settings"])
def test_module_imports(module):
    importlib.import_module(f"ocimum_assistant.{module}")


def test_settings_roundtrip(tmp_path):
    from ocimum_assistant.settings import Settings

    path = tmp_path / "s.json"
    assert Settings.load(path).model == "claude-opus-5-5"
    Settings(model="claude-haiku-5-5", effort="low").save(path)
    s = Settings.load(path)
    assert (s.model, s.effort) == ("claude-haiku-5-5", "low")
    path.write_text('{"model": "gpt-9", "effort": "extreme"}')
    s = Settings.load(path)
    assert (s.model, s.effort) == ("claude-opus-5-5", "medium")
