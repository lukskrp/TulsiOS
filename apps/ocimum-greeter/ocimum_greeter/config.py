"""The greeter's configuration: a JSON file written by the NixOS module
(nix/modules/ocimum-greeter.nix), passed with --config."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    sessions_dir: str
    launcher: str
    default_session: str | None = None
    wallpaper: str | None = None
    # Remembers the last user who logged in (a directory the greeter user owns).
    state_dir: str | None = None
    title: str = "TulsiOS"

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    # --- last user

    def last_user(self) -> str | None:
        if not self.state_dir:
            return None
        try:
            name = (Path(self.state_dir) / "last-user").read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return name or None

    def remember_user(self, name: str) -> None:
        if not self.state_dir:
            return
        try:
            (Path(self.state_dir) / "last-user").write_text(name + "\n", encoding="utf-8")
        except OSError:
            pass  # not worth failing a login over
