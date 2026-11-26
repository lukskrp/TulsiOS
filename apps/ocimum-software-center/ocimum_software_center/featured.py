"""The Featured page's list (featured.json, ADR 0034), free of GTK for tests."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources


@dataclass
class App:
    attr: str
    name: str
    blurb: str


@dataclass
class Section:
    title: str
    intro: str
    apps: list[App] = field(default_factory=list)


def load(text: str | None = None) -> list[Section]:
    if text is None:
        text = resources.files(__package__).joinpath("featured.json").read_text()
    data = json.loads(text)
    return [
        Section(s["title"], s.get("intro", ""), [App(**a) for a in s["apps"]])
        for s in data["sections"]
    ]


def attrs(sections: list[Section]) -> list[str]:
    return [a.attr for s in sections for a in s.apps]
