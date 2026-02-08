from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from .domain import DomainConfig
from .llm import json_schema_call
from .models import ActionPlan, AnalysisResult, BotMemory


def _missing(field: str, analysis: AnalysisResult, memory: BotMemory) -> bool:
    if field == "goal":
        return not (analysis.goal or memory.goal)
    if field == "constraints":
        return not (analysis.constraints or memory.constraints)
    # Unknown field: treat as missing to force explicit handling.
    return True


def _match_rule(rule_when: Dict[str, Any], analysis: AnalysisResult, memory: BotMemory) -> bool:
    if rule_when.get("default") is True:
        return True

    stage_in = rule_when.get("stage_in")
    if stage_in is not None and analysis.stage not in list(stage_in):
        return False

    risk_gte = rule_when.get("risk_gte")
    if risk_gte is not None and analysis.signals.risk < int(risk_gte):
        return False

    missing_any = rule_when.get("missing_any")
    if missing_any is not None:
        fields = list(missing_any)
        if not any(_missing(f, analysis, memory) for f in fields):
            return False

    return True


async def select_action(domain: DomainConfig, analysis: AnalysisResult, memory: BotMemory) -> ActionPlan:
    policy = domain.action_policy
    rules = list((policy.get("rules") or []))

    # 1) Deterministic rules
    for r in rules:
        when = dict(r.get("when") or {})
        then = dict(r.get("then") or {})
        if not when or not then:
            continue
        if _match_rule(when, analysis, memory):
            return ActionPlan(
                action=str(then.get("action", "SUMMARISE")),
                rationale="Matched domain action_policy rule.",
                params=dict(then.get("params") or {}),
            )

    # 2) LLM fallback
    fb = dict((policy.get("llm_fallback") or {}))
    if not bool(fb.get("enabled", False)):
        return ActionPlan(action="SUMMARISE", rationale="Fallback default.", params={})

    allowed = list(fb.get("allowed_actions") or [])
    disallowed = set(str(x) for x in (fb.get("disallowed_actions") or []))

    allowed = [a for a in allowed if a not in disallowed] or ["SUMMARISE"]

    schema = ActionPlan.model_json_schema()
    instructions = (
        "Select a single action from the allowed list that best implements the domain theory. "
        "Return JSON matching the schema. "
        f"Allowed actions: {allowed}."
    )
    input_text = (
        "Context:\n"
        f"- stage: {analysis.stage}\n"
        f"- goal: {analysis.goal or memory.goal}\n"
        f"- constraints: {analysis.constraints or memory.constraints}\n"
        f"- risk: {analysis.signals.risk}\n"
        f"- open_questions: {analysis.open_questions}\n"
    )
    data, _ = await json_schema_call(
        model=domain.model,
        schema_name="ActionPlan",
        schema=schema,
        instructions=instructions,
        input_text=input_text,
        reasoning_effort=domain.reasoning_effort("act", "low"),
        store=False,
    )
    try:
        plan = ActionPlan.model_validate(data)
    except ValidationError:
        plan = ActionPlan(action="SUMMARISE", rationale="Validation failed; default.", params={})

    if plan.action not in allowed:
        plan.action = allowed[0]
        plan.rationale = f"Adjusted to allowed action {plan.action}."
    return plan
