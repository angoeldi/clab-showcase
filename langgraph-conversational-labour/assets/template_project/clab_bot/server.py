from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .domain import load_domain
from .graph import build_graph, ANALYSIS_SCHEMA
from .llm import json_schema_call, stream_events_call, text_call
from .models import ActionPlan, AnalysisResult, BotMemory
from .persistence import make_checkpointer
from .policy import select_action
from .summaries import build_status
from .tutorial import apply_tutorial_command, load_tutorial, render_current_step, should_start_tutorial


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v is not None else default


class ChatRequest(BaseModel):
    thread_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    thread_id: str
    message: str
    status: Dict[str, Any] = Field(default_factory=dict)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with make_checkpointer() as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        app.state.checkpointer = checkpointer
        app.state.graph = graph
        yield


app = FastAPI(title="clab-bot", version="0.1.0", lifespan=lifespan)


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    graph = app.state.graph
    config = {"configurable": {"thread_id": req.thread_id}}
    out = await graph.ainvoke({"last_user_message": req.message}, config=config)
    return ChatResponse(
        thread_id=req.thread_id,
        message=str(out.get("assistant_message") or ""),
        status=dict(out.get("status") or {}),
    )


@app.get("/threads/{thread_id}/status")
async def get_status(thread_id: str):
    graph = app.state.graph
    config = {"configurable": {"thread_id": thread_id}}
    snap = await graph.aget_state(config)
    values = getattr(snap, "values", None) or {}
    return JSONResponse({"thread_id": thread_id, "status": values.get("status") or {}})


# ---- Streaming endpoint (SSE) ----
#
# This endpoint streams ONLY the composed assistant message text.
# It also persists the final state by updating the graph state after streaming ends.
#
@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    graph = app.state.graph
    config = {"configurable": {"thread_id": req.thread_id}}
    snap = await graph.aget_state(config)
    state = dict(getattr(snap, "values", None) or {})

    domain_path = _env("CLAB_DOMAIN_PATH", "configs/domain.yaml") or "configs/domain.yaml"
    tutorial_path = _env("CLAB_TUTORIAL_PATH", "configs/tutorial.yaml") or "configs/tutorial.yaml"
    domain = load_domain(domain_path)
    tutorial_cfg = load_tutorial(tutorial_path)

    # Initialize minimal state
    state.setdefault("messages", [])
    state.setdefault("turn_index", 0)
    state.setdefault("tutorial", {"completed": False, "step_index": 0})
    state.setdefault("status", {})

    user_text = req.message.strip()
    state["turn_index"] = int(state["turn_index"]) + 1
    state["last_user_message"] = user_text
    state["messages"] = (state["messages"] + [{"role": "user", "text": user_text}])[-20:]

    # Tutorial handling: stream as a single event (short message)
    if should_start_tutorial(tutorial_cfg, state, user_text):
        state = apply_tutorial_command(state, user_text, tutorial_cfg.steps)
        tut = state.get("tutorial") or {}
        if tut.get("completed"):
            assistant_text = "Tutorial completed. Tell me your goal and constraints, and we begin."
        else:
            assistant_text = render_current_step(state, tutorial_cfg.steps).strip()

        state["assistant_message"] = assistant_text
        state["messages"] = (state["messages"] + [{"role": "assistant", "text": assistant_text}])[-20:]

        await graph.aupdate_state(config, values=state)

        async def one_shot() -> AsyncIterator[bytes]:
            yield f"data: {json.dumps({'delta': assistant_text})}\n\n".encode("utf-8")
            yield b"data: [DONE]\n\n"

        return StreamingResponse(one_shot(), media_type="text/event-stream")

    # Normal flow: analyze -> act -> stream compose -> persist
    # Bot memory
    bot_mem_dict = (state.get("status") or {}).get("bot_memory") or {}
    if not bot_mem_dict:
        bot_mem_dict = {"last_updated_utc": "1970-01-01T00:00:00Z"}
    bot_mem = BotMemory.model_validate(bot_mem_dict)

    # Analysis
    analysis_schema = ANALYSIS_SCHEMA
    instructions = (
        "You are an analysis engine for a domain-theory-driven conversational labour bot.\n"
        "Rules:\n"
        "- Extract facts ONLY if explicitly stated by the user.\n"
        "- Any inference must be emitted as a hypothesis (non-factive), with confidence and ask_confirmation.\n"
        "- Output MUST be valid JSON matching the provided schema.\n"
        "\n"
        "Domain theory (YAML-derived):\n"
        f"- stages: {json.dumps(domain.stages, ensure_ascii=False)}\n"
        f"- constructs: {json.dumps(domain.constructs, ensure_ascii=False)}\n"
        f"- interventions: {json.dumps(domain.interventions, ensure_ascii=False)}\n"
    )
    input_text = (
        "Bot memory (JSON):\n"
        f"{json.dumps(bot_mem.model_dump(), ensure_ascii=False)}\n\n"
        "User message:\n"
        f"{user_text}"
    )
    data, _ = await json_schema_call(
        model=_env("CLAB_MODEL", domain.model) or domain.model,
        schema_name="AnalysisResult",
        schema=analysis_schema,
        instructions=instructions,
        input_text=input_text,
        reasoning_effort=domain.reasoning_effort("analyze", "low"),
        store=False,
    )
    analysis = AnalysisResult.model_validate(data)
    state["analysis"] = analysis.model_dump()

    # Action selection (rule-first; LLM fallback)
    plan = await select_action(domain, analysis, bot_mem)
    if analysis.safety_mode:
        plan = ActionPlan(action="SAFETY", rationale="Safety mode active.", params={"mode": analysis.safety_mode})
    state["action_plan"] = plan.model_dump()

    # Compose prompt
    style_text = json.dumps(domain.writing_style, ensure_ascii=False)
    safety_text = ""
    if analysis.safety_mode:
        policy = (domain.safety.get("policies") or {}).get(analysis.safety_mode) or {}
        safety_text = f"\nSAFETY MODE: {analysis.safety_mode}\nPOLICY: {json.dumps(policy, ensure_ascii=False)}\n"

    instructions = (
        "You are a domain-theory-driven conversational labour chatbot.\n"
        "Implement the selected action faithfully.\n"
        "Constraints:\n"
        "- Do not claim certainty beyond the user's statements.\n"
        "- Label hypotheses as hypotheses.\n"
        "- Ask at most one question at a time unless the action demands otherwise.\n"
        "- Keep the user on track toward the goal.\n"
        f"- Writing style: {style_text}\n"
        + safety_text
    )
    input_text = (
        "Context for this turn:\n"
        f"- User message: {user_text}\n"
        f"- Analysis (JSON): {json.dumps(analysis.model_dump(), ensure_ascii=False)}\n"
        f"- Action plan (JSON): {json.dumps(plan.model_dump(), ensure_ascii=False)}\n"
    )

    prev_resp_id = state.get("previous_response_id")

    async def event_stream() -> AsyncIterator[bytes]:
        full_text = ""
        response_id: Optional[str] = None

        async for event in stream_events_call(
            model=_env("CLAB_MODEL", domain.model) or domain.model,
            instructions=instructions,
            input_text=input_text,
            reasoning_effort=domain.reasoning_effort("compose", "medium"),
            previous_response_id=prev_resp_id,
            store=domain.store_responses,
        ):
            etype = getattr(event, "type", "")
            if etype == "response.created":
                resp_obj = getattr(event, "response", None)
                response_id = getattr(resp_obj, "id", None) or response_id

            if etype == "response.output_text.delta":
                delta = getattr(event, "delta", "") or ""
                full_text += delta
                yield f"data: {json.dumps({'delta': delta})}\n\n".encode("utf-8")

            if etype == "response.done":
                resp_obj = getattr(event, "response", None)
                response_id = getattr(resp_obj, "id", None) or response_id

        # After streaming ends: compute summaries + persist
        status = build_status(state.get("status") or {}, analysis, plan, full_text)
        final_text = full_text.strip()
        if bool(domain.writing_style.get("formatting", {}).get("include_status_card", True)):
            final_text = final_text + "\n\n" + status.user_card_md.strip()

        state["assistant_message"] = final_text
        state["status"] = status.model_dump()
        if response_id:
            state["previous_response_id"] = response_id

        state["messages"] = (state["messages"] + [{"role": "assistant", "text": final_text}])[-20:]

        await graph.aupdate_state(config, values=state)

        # Stream the status card as a final delta (so clients see it even if they only render deltas)
        card_delta = "\n\n" + status.user_card_md.strip()
        yield f"data: {json.dumps({'delta': card_delta})}\n\n".encode("utf-8")
        yield b"data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
