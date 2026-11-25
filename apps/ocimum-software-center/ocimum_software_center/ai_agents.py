"""The AI Agents page's list (ai-agents.json, ADR 0023), free of GTK for tests."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources

KINDS = ("cloud-cli", "cloud-ide", "local-runner")


@dataclass
class Agent:
    attr: str
    name: str
    kind: str
    vendor: str
    homepage: str
    needs: str
    blurb: str
    variants: dict[str, str] = field(default_factory=dict)


@dataclass
class Section:
    kind: str
    title: str
    intro: str
    agents: list[Agent] = field(default_factory=list)


def load(text: str | None = None) -> list[Section]:
    if text is None:
        text = resources.files(__package__).joinpath("ai-agents.json").read_text()
    data = json.loads(text)
    sections = {s["kind"]: Section(s["kind"], s["title"], s["intro"]) for s in data["sections"]}
    for entry in data["agents"]:
        agent = Agent(**entry)
        if agent.kind not in sections:
            raise ValueError(f"{agent.attr}: unknown kind {agent.kind!r}")
        sections[agent.kind].agents.append(agent)
    return [sections[k] for k in KINDS if k in sections]


def attrs(sections: list[Section]) -> list[str]:
    """Every package the page can install, variants included."""
    out = []
    for section in sections:
        for agent in section.agents:
            out.append(agent.attr)
            out += agent.variants.values()
    return out
