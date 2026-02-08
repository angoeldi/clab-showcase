from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml


@dataclass(frozen=True)
class DomainConfig:
    raw: Dict[str, Any]

    @property
    def model(self) -> str:
        return str(self.raw.get("runtime", {}).get("model", "gpt-5.2"))

    def reasoning_effort(self, phase: str, default: str = "low") -> str:
        eff = self.raw.get("runtime", {}).get("reasoning_effort", {})
        return str(eff.get(phase, default))

    @property
    def store_responses(self) -> bool:
        return bool(self.raw.get("runtime", {}).get("store_responses", True))

    @property
    def writing_style(self) -> Dict[str, Any]:
        return dict(self.raw.get("writing_style", {}) or {})

    @property
    def action_policy(self) -> Dict[str, Any]:
        return dict(self.raw.get("action_policy", {}) or {})

    @property
    def safety(self) -> Dict[str, Any]:
        return dict(self.raw.get("safety", {}) or {})

    @property
    def stages(self) -> list[dict[str, Any]]:
        return list(self.raw.get("stages", []) or [])

    @property
    def interventions(self) -> list[dict[str, Any]]:
        return list(self.raw.get("interventions", []) or [])

    @property
    def constructs(self) -> list[dict[str, Any]]:
        return list(self.raw.get("constructs", []) or [])


def load_yaml(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def load_domain(domain_path: str | Path) -> DomainConfig:
    return DomainConfig(raw=load_yaml(domain_path))
