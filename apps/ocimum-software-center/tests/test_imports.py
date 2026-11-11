"""Imports every GTK module, so GObject type registration problems (such as a
custom signal clashing with an inherited one) fail the build, not the app."""

import importlib

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")


@pytest.mark.parametrize("module", ["client", "rows", "progress", "dialogs", "window", "app", "approve"])
def test_module_imports(module):
    importlib.import_module(f"ocimum_software_center.{module}")
