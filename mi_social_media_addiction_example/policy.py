from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import ValidationError

from .domain import DomainConfig
from .llm import json_schema_call
from .models import ActionPlan, AnalysisResult, BotMemory


def _quoted_list(items: List[str]) -> str:
    vals = [str(x).strip() for x in items if str(x).strip()]
    if not vals:
        return ""
    return ", ".join(f"`{v}`" for v in vals)


def _deterministic_rule_reasoning(
    rule_when: Dict[str, Any],
    rule_then: Dict[str, Any],
    analysis: AnalysisResult,
    memory: BotMemory,
) -> str:
    action = str(rule_then.get("action", "SUMMARISE") or "SUMMARISE")
    parts: List[str] = []

    stage_in = rule_when.get("stage_in")
    if stage_in is not None:
        allowed = [str(s) for s in list(stage_in)]
        if allowed:
            parts.append(f"stage `{analysis.stage}` matches allowed stages {_quoted_list(allowed)}")

    risk_gte = rule_when.get("risk_gte")
    if risk_gte is not None:
        threshold = int(risk_gte)
        parts.append(f"risk score {analysis.signals.risk}/5 meets threshold >= {threshold}")

    missing_any = rule_when.get("missing_any")
    if missing_any is not None:
        requested = [str(f) for f in list(missing_any)]
        missing = [f for f in requested if _missing(f, analysis, memory)]
        if missing:
            parts.append(f"missing info detected: {_quoted_list(missing)}")
        elif requested:
            parts.append(f"required info check passed for {_quoted_list(requested)}")

    if rule_when.get("default") is True:
        parts.append("no earlier rule matched, so the default domain rule applies")

    if not parts:
        parts.append("a domain action rule matched this turn")

    params = dict(rule_then.get("params") or {})
    param_keys = [str(k) for k in params.keys()]
    param_note = ""
    if param_keys:
        param_note = f" Key settings: {_quoted_list(param_keys[:3])}."

    return f"I selected **{action}** using deterministic policy logic because " + "; ".join(parts) + "." + param_note


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


async def select_action(
    domain: DomainConfig,
    analysis: AnalysisResult,
    memory: BotMemory,
    on_reasoning_update: Optional[Callable[[str, bool, int], None]] = None,
) -> Tuple[ActionPlan, List[str]]:
    policy = domain.action_policy
    rules = list((policy.get("rules") or []))

    # 1) Deterministic rules
    for r in rules:
        when = dict(r.get("when") or {})
        then = dict(r.get("then") or {})
        if not when or not then:
            continue
        if _match_rule(when, analysis, memory):
            explanation = _deterministic_rule_reasoning(when, then, analysis, memory)
            plan = ActionPlan(
                action=str(then.get("action", "SUMMARISE")),
                rationale=explanation,
                params=dict(then.get("params") or {}),
            )
            return plan, []

    # 2) LLM fallback
    fb = dict((policy.get("llm_fallback") or {}))
    if not bool(fb.get("enabled", False)):
        return (
            ActionPlan(
                action="SUMMARISE",
                rationale="No rule matched and LLM fallback is disabled, so I used the safe default action **SUMMARISE**.",
                params={},
            ),
            [],
        )

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
    data, _, generated_reasoning = await json_schema_call(
        model=domain.model,
        schema_name="ActionPlan",
        schema=schema,
        instructions=instructions,
        input_text=input_text,
        reasoning_effort=domain.reasoning_effort("act", "low"),
        store=False,
        on_reasoning_update=on_reasoning_update,
    )
    try:
        plan = ActionPlan.model_validate(data)
    except ValidationError:
        plan = ActionPlan(action="SUMMARISE", rationale="Validation failed; default.", params={})
        generated_reasoning = list(generated_reasoning or []) + [
            "The model output did not validate cleanly, so I fell back to **SUMMARISE** for a safe default."
        ]

    if plan.action not in allowed:
        original = plan.action
        plan.action = allowed[0]
        plan.rationale = f"Adjusted to allowed action {plan.action}."
        generated_reasoning = list(generated_reasoning or []) + [
            f"Action **{original}** was not allowed by policy, so I switched to **{plan.action}**."
        ]
    return plan, generated_reasoning
