from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml


@dataclass(frozen=True)
class TutorialStep:
    id: str
    title: str
    body_md: str
    cta: str


@dataclass(frozen=True)
class TutorialConfig:
    enabled: bool
    start_when: list[dict[str, Any]]
    steps: list[TutorialStep]


def load_tutorial(path: str | Path) -> TutorialConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    steps = [
        TutorialStep(
            id=str(s.get("id", "")),
            title=str(s.get("title", "")),
            body_md=str(s.get("body_md", "")),
            cta=str(s.get("cta", "")),
        )
        for s in (raw.get("steps", []) or [])
    ]
    return TutorialConfig(
        enabled=bool(raw.get("enabled", True)),
        start_when=list(raw.get("start_when", []) or []),
        steps=steps,
    )


def should_start_tutorial(cfg: TutorialConfig, state: Dict[str, Any], user_text: str) -> bool:
    if not cfg.enabled:
        return False
    tut = state.get("tutorial") or {}
    if tut.get("completed"):
        return False
    turn = int(state.get("turn_index", 0))
    triggers = cfg.start_when or [{"first_turn": True}]
    user_lower = user_text.strip().lower()

    for t in triggers:
        if t == "first_turn" or (isinstance(t, dict) and t.get("first_turn")):
            if turn <= 1:
                return True
        if isinstance(t, dict) and "user_says" in t:
            phrases = [str(p).lower() for p in (t.get("user_says") or [])]
            if any(p in user_lower for p in phrases):
                return True
    return False


def apply_tutorial_command(state: Dict[str, Any], user_text: str, steps: List[TutorialStep]) -> Dict[str, Any]:
    """Update tutorial progress based on the user's command."""
    tut = dict(state.get("tutorial") or {})
    if tut.get("completed"):
        return state

    cmd = user_text.strip().lower()
    idx = int(tut.get("step_index", 0))

    if cmd == "skip":
        tut["completed"] = True
        tut["step_index"] = idx
        state["tutorial"] = tut
        return state

    if cmd == "back":
        tut["step_index"] = max(0, idx - 1)
        state["tutorial"] = tut
        return state

    if cmd == "next":
        tut["step_index"] = min(len(steps), idx + 1)
        if tut["step_index"] >= len(steps):
            tut["completed"] = True
        state["tutorial"] = tut
        return state

    # No-op for other inputs (keep current index)
    state["tutorial"] = tut
    return state


def render_current_step(state: Dict[str, Any], steps: List[TutorialStep]) -> str:
    tut = state.get("tutorial") or {}
    idx = int(tut.get("step_index", 0))
    idx = max(0, min(idx, max(0, len(steps) - 1)))

    if not steps:
        return "Tutorial is enabled but no steps were configured."

    step = steps[idx]
    n = len(steps)
    header = f"### Tutorial ({idx + 1}/{n}): {step.title}\n"
    body = step.body_md.strip() + "\n"
    footer = f"\n*{step.cta.strip()}*\n"
    return header + "\n" + body + "\n" + footer
