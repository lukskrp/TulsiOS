"""User settings: model and effort in ~/.config, the API key in the keyring."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .providers import DEFAULT_EFFORT, DEFAULT_MODEL, EFFORTS, MODELS

KEY_LABEL = "Anthropic API key (Ocimum Assistant)"


def _config_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "ocimum-assistant" / "settings.json"


@dataclass
class Settings:
    model: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or _config_file()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        s = cls()
        if data.get("model") in MODELS:
            s.model = data["model"]
        if data.get("effort") in EFFORTS:
            s.effort = data["effort"]
        return s

    def save(self, path: Path | None = None) -> None:
        path = path or _config_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")


class Keyring:
    """The API key in the Secret Service (GNOME Keyring under Cinnamon).

    All methods degrade to "no key" when no keyring is available; the SDK then
    falls back to ANTHROPIC_API_KEY or an `ant auth login` profile.
    """

    def __init__(self):
        try:
            import gi

            gi.require_version("Secret", "1")
            from gi.repository import Secret

            self.Secret = Secret
            self.schema = Secret.Schema.new(
                "org.tulsi.Assistant",
                Secret.SchemaFlags.NONE,
                {"service": Secret.SchemaAttributeType.STRING},
            )
        except (ImportError, ValueError):
            self.Secret = None

    @property
    def available(self) -> bool:
        return self.Secret is not None

    def get(self) -> str | None:
        if not self.Secret:
            return None
        try:
            return self.Secret.password_lookup_sync(self.schema, {"service": "anthropic"}, None)
        except Exception:  # noqa: BLE001 - no keyring daemon, locked, ...
            return None

    def set(self, key: str) -> bool:
        if not self.Secret:
            return False
        try:
            return self.Secret.password_store_sync(
                self.schema, {"service": "anthropic"}, self.Secret.COLLECTION_DEFAULT, KEY_LABEL, key, None
            )
        except Exception:  # noqa: BLE001
            return False

    def clear(self) -> None:
        if self.Secret:
            try:
                self.Secret.password_clear_sync(self.schema, {"service": "anthropic"}, None)
            except Exception:  # noqa: BLE001
                pass
