"""Imports every GTK module, so GObject type registration problems (such as a
custom signal clashing with an inherited one) fail the build, not the app."""

import importlib

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "3.0")


@pytest.mark.parametrize("module", ["client", "rows", "progress", "dialogs", "window", "app", "approve", "adopt"])
def test_module_imports(module):
    importlib.import_module(f"ocimum_software_center.{module}")


def test_client_has_every_call_the_window_makes():
    import re
    from pathlib import Path

    from ocimum_software_center.client import Client

    window = (Path(__file__).parent.parent / "ocimum_software_center" / "window.py").read_text()
    for name in set(re.findall(r"self\.client\.(\w+)\(", window)):
        assert hasattr(Client, name), name
