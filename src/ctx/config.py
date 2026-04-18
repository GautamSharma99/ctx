from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "distiller": {
        "model": "claude-sonnet-4-6",
        "budget_tokens": 2000,
    },
    "targets": {
        "default": "chatgpt",
    },
    "framing": {
        "extra_rules": [],
        "tone": "direct",
    },
}


@dataclass
class Config:
    distiller_model: str = "claude-sonnet-4-6"
    budget_tokens: int = 2000
    default_target: str = "chatgpt"
    extra_rules: list[str] = field(default_factory=list)
    tone: str = "direct"

    @classmethod
    def load(cls, ctx_dir: Path) -> "Config":
        path = ctx_dir / "config.yaml"
        if not path.exists():
            return cls()
        raw = yaml.safe_load(path.read_text()) or {}
        distiller = raw.get("distiller", {})
        targets = raw.get("targets", {})
        framing = raw.get("framing", {})
        return cls(
            distiller_model=distiller.get("model", cls.distiller_model),
            budget_tokens=int(distiller.get("budget_tokens", cls.budget_tokens)),
            default_target=targets.get("default", cls.default_target),
            extra_rules=list(framing.get("extra_rules", []) or []),
            tone=framing.get("tone", cls.tone),
        )

    @staticmethod
    def write_default(ctx_dir: Path) -> Path:
        path = ctx_dir / "config.yaml"
        path.write_text(yaml.safe_dump(DEFAULT_CONFIG, sort_keys=False))
        return path

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
