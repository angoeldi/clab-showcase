from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List, Optional, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, StateGraph

from .domain import DomainConfig, load_domain
from .llm import json_schema_call, text_call
from .models import ActionPlan, AnalysisResult, BotMemory
from .policy import select_action
from .summaries import build_status
from .tutorial import apply_tutorial_command, load_tutorial, render_current_step, should_start_tutorial


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v is not None else default


def _emit_stream_event(payload: Dict[str, Any]) -> None:
    try:
        writer = get_stream_writer()
    except Exception:
        writer = None
    if writer is None:
        return
    try:
        writer(payload)
    except Exception:
        return


def _reasoning_stream_callback(node_name: str) -> Callable[[str, bool, int], None]:
    def _cb(text: str, is_partial: bool, summary_index: int) -> None:
        _emit_stream_event(
            {
                "type": "reasoning_generated_live" if is_partial else "reasoning_generated",
                "node": node_name,
                "message": str(text or ""),
                "summary_index": int(summary_index),
                "partial": bool(is_partial),
            }
        )

    return _cb


def _emit_reasoning_status(node_name: str, message: str, phase: str = "update") -> None:
    _emit_stream_event(
        {
            "type": "reasoning_status",
            "node": node_name,
            "message": str(message or ""),
            "phase": str(phase or "update"),
        }
    )


ANALYSIS_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "stage",
        "user_intent",
        "goal",
        "constraints",
        "facts",
        "hypotheses",
        "open_questions",
        "signals",
        "risk_flags",
        "safety_mode",
    ],
    "properties": {
        "stage": {"type": "string"},
        "user_intent": {"type": "string"},
        "goal": {"type": ["string", "null"]},
        "constraints": {"type": "array", "items": {"type": "string"}},
        "facts": {"type": "array", "items": {"type": "string"}},
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "confidence", "ask_confirmation", "confirmed"],
                "properties": {
                    "text": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                    "ask_confirmation": {"type": "boolean"},
                    "confirmed": {"type": ["boolean", "null"]},
                },
            },
        },
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "signals": {
            "type": "object",
            "additionalProperties": False,
            "required": ["goal_clarity", "motivation", "risk"],
            "properties": {
                "goal_clarity": {"type": "integer", "minimum": 0, "maximum": 5},
                "motivation": {"type": "integer", "minimum": 0, "maximum": 5},
                "risk": {"type": "integer", "minimum": 0, "maximum": 5},
            },
        },
        "risk_flags": {"type": "array", "items": {"type": "string"}},
        "safety_mode": {"type": ["string", "null"]},
    },
}

ACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action", "rationale", "params"],
    "properties": {
        "action": {"type": "string"},
        "rationale": {"type": "string"},
        "params": {"type": "object", "additionalProperties": True},
    },
}


class GraphState(TypedDict, total=False):
    # conversation
    messages: List[Dict[str, str]]  # [{role, text}]
    last_user_message: str
    assistant_message: str
    turn_index: int

    # tutorial
    tutorial: Dict[str, Any]
    mode: str

    # analysis + action + status
    analysis: Dict[str, Any]
    action_plan: Dict[str, Any]
    status: Dict[str, Any]
    generated_reasoning: List[str]

    # responses api chaining
    previous_response_id: str

    # safety
    red_flags: List[str]


def _init_state(state: GraphState) -> GraphState:
    state.setdefault("messages", [])
    state.setdefault("turn_index", 0)
    state.setdefault("tutorial", {"completed": False, "step_index": 0})
    state.setdefault("status", {})
    state.setdefault("generated_reasoning", [])
    state.setdefault("red_flags", [])
    return state


def _trim_messages(messages: List[Dict[str, str]], keep_last: int = 20) -> List[Dict[str, str]]:
    if len(messages) <= keep_last:
        return messages
    return messages[-keep_last:]


def _match_red_flags(domain: DomainConfig, user_text: str) -> List[str]:
    safety = domain.safety
    flags = []
    for rf in (safety.get("red_flags") or []):
        rid = str(rf.get("id", "")).strip()
        patterns = [str(p).lower() for p in (rf.get("patterns") or [])]
        if not rid or not patterns:
            continue
        u = user_text.lower()
        if any(p in u for p in patterns):
            flags.append(rid)
    return flags


def build_graph(*, domain_path: str | None = None, tutorial_path: str | None = None, checkpointer: object | None = None):
    domain_path = domain_path or (
        _env("CLAB_DOMAIN_PATH", "configs/examples/haiku_tutor/domain.yaml")
        or "configs/examples/haiku_tutor/domain.yaml"
    )
    tutorial_path = tutorial_path or (
        _env("CLAB_TUTORIAL_PATH", "configs/examples/haiku_tutor/tutorial.yaml")
        or "configs/examples/haiku_tutor/tutorial.yaml"
    )

    domain = load_domain(domain_path)
    tutorial_cfg = load_tutorial(tutorial_path)

    async def ingest(state: GraphState) -> GraphState:
        state = _init_state(state)
        state["generated_reasoning"] = []
        _emit_reasoning_status("ingest", "Message received.", "start")
        user_text = str(state.get("last_user_message") or "").strip()
        state["turn_index"] = int(state.get("turn_index", 0)) + 1
        if user_text:
            state["messages"] = _trim_messages(state["messages"] + [{"role": "user", "text": user_text}])

        # deterministic red-flag matching
        state["red_flags"] = _match_red_flags(domain, user_text)
        return state

    async def decide(state: GraphState) -> GraphState:
        state = _init_state(state)
        state["generated_reasoning"] = []
        _emit_reasoning_status("decide", "Choosing the best coaching path.", "start")
        user_text = str(state.get("last_user_message") or "")
        if should_start_tutorial(tutorial_cfg, state, user_text):
            state["mode"] = "tutorial"
        else:
            state["mode"] = "work"
        return state

    async def tutorial_node(state: GraphState) -> GraphState:
        state = _init_state(state)
        state["generated_reasoning"] = []
        _emit_reasoning_status("tutorial", "Showing a quick tutorial step.", "start")
        user_text = str(state.get("last_user_message") or "")
        state = apply_tutorial_command(state, user_text, tutorial_cfg.steps)
        tut = state.get("tutorial") or {}
        if tut.get("completed"):
            # After completion, fall through to normal processing on next turn.
            state["assistant_message"] = "Tutorial completed. Tell me your goal and constraints, and we begin."
            state["messages"] = _trim_messages(state["messages"] + [{"role": "assistant", "text": state["assistant_message"]}])
            return state

        state["assistant_message"] = render_current_step(state, tutorial_cfg.steps).strip()
        state["messages"] = _trim_messages(state["messages"] + [{"role": "assistant", "text": state["assistant_message"]}])
        return state

    async def analyze(state: GraphState) -> GraphState:
        state = _init_state(state)
        state["generated_reasoning"] = []
        _emit_reasoning_status("analyze", "Reviewing your draft and identifying improvements.", "start")

        # Load bot memory if present
        bot_mem = None
        if isinstance(state.get("status"), dict) and isinstance(state["status"].get("bot_memory"), dict):
            bot_mem = state["status"]["bot_memory"]
        else:
            bot_mem = {}

        safety = domain.safety
        safety_instruction = json.dumps(safety, ensure_ascii=False)

        instructions = (
            "You are an analysis engine for a domain-theory-driven conversational labour bot.\n"
            "Rules:\n"
            "- Extract facts ONLY if explicitly stated by the user.\n"
            "- Any inference must be emitted as a hypothesis (non-factive), with confidence and ask_confirmation.\n"
            "- If any red flags exist, include them in risk_flags and set safety_mode appropriately.\n"
            "- Output MUST be valid JSON matching the provided schema.\n"
            "\n"
            "Domain theory (YAML-derived):\n"
            f"- stages: {json.dumps(domain.stages, ensure_ascii=False)}\n"
            f"- constructs: {json.dumps(domain.constructs, ensure_ascii=False)}\n"
            f"- interventions: {json.dumps(domain.interventions, ensure_ascii=False)}\n"
            f"- safety: {safety_instruction}\n"
        )

        user_text = str(state.get("last_user_message") or "")
        red_flags = list(state.get("red_flags") or [])
        input_text = (
            "Bot memory (JSON):\n"
            f"{json.dumps(bot_mem, ensure_ascii=False)}\n\n"
            f"Red flags (deterministic match): {red_flags}\n\n"
            "User message:\n"
            f"{user_text}"
        )

        data, _, generated_reasoning = await json_schema_call(
            model=_env("CLAB_MODEL", domain.model) or domain.model,
            schema_name="AnalysisResult",
            schema=ANALYSIS_SCHEMA,
            instructions=instructions,
            input_text=input_text,
            reasoning_effort=domain.reasoning_effort("analyze", "low"),
            store=False,
            on_reasoning_update=_reasoning_stream_callback("analyze"),
        )
        analysis = AnalysisResult.model_validate(data)

        # If deterministic red flags found, override risk_flags union
        analysis.risk_flags = _dedupe_list(list(analysis.risk_flags or []) + red_flags)
        if analysis.risk_flags and not analysis.safety_mode:
            # pick a mode based on domain policy, if present
            # (simple default)
            analysis.safety_mode = "crisis"

        state["analysis"] = analysis.model_dump()
        state["generated_reasoning"] = generated_reasoning
        return state

    async def act(state: GraphState) -> GraphState:
        state = _init_state(state)
        state["generated_reasoning"] = []
        _emit_reasoning_status("act", "Selecting the most helpful feedback style.", "start")
        analysis = AnalysisResult.model_validate(state.get("analysis") or {})
        bot_mem = BotMemory.model_validate(
            (state.get("status") or {}).get("bot_memory") or {"last_updated_utc": "1970-01-01T00:00:00Z"}
        )
        plan, generated_reasoning = await select_action(
            domain,
            analysis,
            bot_mem,
            on_reasoning_update=_reasoning_stream_callback("act"),
        )

        # Hard override if safety mode is active
        if analysis.safety_mode:
            prior_action = str(plan.action or "").strip() or "unspecified"
            flags = [str(f).strip() for f in (analysis.risk_flags or []) if str(f).strip()]
            flag_text = ", ".join(flags[:3]) if flags else "risk indicators from analysis"
            plan = ActionPlan(
                action="SAFETY",
                rationale=(
                    "I overrode the previous plan"
                    f" (**{prior_action}**) and switched to **SAFETY** mode"
                    f" (`{analysis.safety_mode}`) because safety signals were detected ({flag_text})."
                ),
                params={"mode": analysis.safety_mode},
            )
            generated_reasoning = []

        state["action_plan"] = plan.model_dump()
        state["generated_reasoning"] = generated_reasoning
        return state

    async def compose(state: GraphState) -> GraphState:
        state = _init_state(state)
        state["generated_reasoning"] = []
        _emit_reasoning_status("compose", "Writing your feedback.", "start")
        analysis = AnalysisResult.model_validate(state.get("analysis") or {})
        plan = ActionPlan.model_validate(state.get("action_plan") or {})

        prev_status = state.get("status") if isinstance(state.get("status"), dict) else {}
        prev_resp_id = state.get("previous_response_id")

        # Safety policy instruction (if applicable)
        safety_text = ""
        if analysis.safety_mode:
            policy = (domain.safety.get("policies") or {}).get(analysis.safety_mode) or {}
            safety_text = f"\nSAFETY MODE: {analysis.safety_mode}\nPOLICY: {json.dumps(policy, ensure_ascii=False)}\n"

        style = domain.writing_style
        style_text = json.dumps(style, ensure_ascii=False)

        instructions = (
            "You are a domain-theory-driven conversational labour chatbot.\n"
            "Implement the selected action faithfully.\n"
            "Constraints:\n"
            "- Do not claim certainty beyond the user's statements.\n"
            "- Label hypotheses as hypotheses.\n"
            "- Ask at most one question at a time unless the action demands otherwise.\n"
            "- Keep the user on track toward the goal.\n"
            "- Keep internal reasoning private: do not mention analysis JSON, action plan JSON, status cards, "
            "or headers like 'Status', 'Hypotheses', or 'Open questions'.\n"
            "- The user-facing reply should read like a direct tutor response, not a diagnostic report.\n"
            f"- Writing style: {style_text}\n"
            + safety_text
        )

        user_text = str(state.get("last_user_message") or "")
        input_text = (
            "Context for this turn:\n"
            f"- User message: {user_text}\n"
            f"- Analysis (JSON): {json.dumps(analysis.model_dump(), ensure_ascii=False)}\n"
            f"- Action plan (JSON): {json.dumps(plan.model_dump(), ensure_ascii=False)}\n"
        )

        text, resp_id, generated_reasoning = await text_call(
            model=_env("CLAB_MODEL", domain.model) or domain.model,
            instructions=instructions,
            input_text=input_text,
            reasoning_effort=domain.reasoning_effort("compose", "medium"),
            previous_response_id=prev_resp_id,
            store=domain.store_responses,
            on_reasoning_update=_reasoning_stream_callback("compose"),
        )

        # Update status summaries (deterministic)
        status = build_status(prev_status, analysis, plan, text)
        final_text = text.strip()
        if bool(style.get("formatting", {}).get("include_status_card", True)):
            final_text = final_text + "\n\n" + status.user_card_md.strip()

        state["assistant_message"] = final_text
        state["status"] = status.model_dump()
        state["previous_response_id"] = resp_id
        state["generated_reasoning"] = generated_reasoning
        state["messages"] = _trim_messages(state["messages"] + [{"role": "assistant", "text": final_text}])
        return state

    async def finalize(state: GraphState) -> GraphState:
        # No-op node; exists to make the graph structure explicit.
        state = _init_state(state)
        state["generated_reasoning"] = []
        _emit_reasoning_status("finalize", "Final response ready.", "start")
        return state

    def router(state: GraphState) -> str:
        return str(state.get("mode") or "work")

    builder: StateGraph = StateGraph(GraphState)
    builder.add_node("ingest", ingest)
    builder.add_node("decide", decide)
    builder.add_node("tutorial", tutorial_node)
    builder.add_node("analyze", analyze)
    builder.add_node("act", act)
    builder.add_node("compose", compose)
    builder.add_node("finalize", finalize)

    builder.set_entry_point("ingest")
    builder.add_edge("ingest", "decide")
    builder.add_conditional_edges("decide", router, {"tutorial": "tutorial", "work": "analyze"})
    builder.add_edge("tutorial", "finalize")
    builder.add_edge("analyze", "act")
    builder.add_edge("act", "compose")
    builder.add_edge("compose", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer)


def _dedupe_list(xs: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in xs:
        x = str(x).strip()
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out
