"""Running the desktop's own tools (gsettings, dconf, plasma-apply-*, xrdb).

Tests swap `runner` for a recorder, so what a switch would do can be checked
without a desktop.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Sequence

Runner = Callable[[Sequence[str]], str]


def system(argv: Sequence[str]) -> str:
    return subprocess.run(list(argv), check=True, capture_output=True, text=True).stdout


runner: Runner = system


def run(*argv: str) -> str:
    return runner(argv)


def have(tool: str) -> bool:
    return runner is not system or shutil.which(tool) is not None


def gvariant_str(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def gvariant_strv(items: Sequence[str]) -> str:
    return "[" + ", ".join(gvariant_str(i) for i in items) + "]"
