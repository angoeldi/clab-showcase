from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from .models import ActionPlan, AnalysisResult, BotMemory, Hypothesis, StatusState


def _dedupe(seq: List[str]) -> List[str]:
    seen = set()
    out = []
    for s in seq:
        k = s.strip()
        if not k:
            continue
        if k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def merge_memory(prev: BotMemory, analysis: AnalysisResult, action: ActionPlan, assistant_text: str) -> BotMemory:
    goal = analysis.goal or prev.goal
    constraints = _dedupe((prev.constraints or []) + (analysis.constraints or []))
    facts = _dedupe((prev.facts or []) + (analysis.facts or []))

    # Hypotheses: naive merge by text
    prev_h = {h.text: h for h in (prev.hypotheses or [])}
    for h in analysis.hypotheses or []:
        prev_h[h.text] = h
    hypotheses = list(prev_h.values())

    open_qs = _dedupe(list(analysis.open_questions or []))
    next_step = None
    if action.action == "PROBE":
        q = str(action.params.get("question") or "").strip()
        next_step = q or (open_qs[0] if open_qs else None)
    elif action.action == "SUMMARISE":
        next_step = "Confirm or adjust the status card; then pick one concrete next step."
    elif action.action == "SAFETY":
        next_step = "Follow the safety guidance above."
    else:
        next_step = "Proceed with the proposed action."

    return BotMemory(
        goal=goal,
        stage=analysis.stage,
        constraints=constraints,
        commitments=list(prev.commitments or []),
        facts=facts,
        hypotheses=hypotheses,
        signals=analysis.signals,
        open_questions=open_qs,
        next_step=next_step,
        last_updated_utc=datetime.now(timezone.utc).isoformat(),
    )


def render_user_card(memory: BotMemory) -> str:
    goal = memory.goal or "(not set)"
    stage = memory.stage or "(unknown)"
    constraints = memory.constraints[:4]
    open_qs = memory.open_questions[:3]

    lines = []
    lines.append("---")
    lines.append("**Status**")
    lines.append(f"- Goal: {goal}")
    lines.append(f"- Stage: {stage}")
    if constraints:
        lines.append(f"- Constraints: {', '.join(constraints)}")
    if memory.next_step:
        lines.append(f"- Next: {memory.next_step}")
    if open_qs:
        lines.append(f"- Open questions: {', '.join(open_qs)}")
    lines.append("- Commands: `update goal: ...`, `update constraints: ...`, `pause and summarise`")
    return "\n".join(lines).strip() + "\n"


def build_status(prev_status: Dict[str, Any] | None, analysis: AnalysisResult, action: ActionPlan, assistant_text: str) -> StatusState:
    prev_mem = None
    if prev_status and isinstance(prev_status.get("bot_memory"), dict):
        prev_mem = BotMemory.model_validate(prev_status["bot_memory"])
    elif prev_status and isinstance(prev_status.get("bot_memory"), BotMemory):
        prev_mem = prev_status["bot_memory"]
    else:
        prev_mem = BotMemory(last_updated_utc=datetime.now(timezone.utc).isoformat())

    mem = merge_memory(prev_mem, analysis, action, assistant_text)
    card = render_user_card(mem)
    return StatusState(user_card_md=card, bot_memory=mem)
