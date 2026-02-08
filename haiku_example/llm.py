from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple

from openai import AsyncOpenAI


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v is not None else default


_client: Optional[AsyncOpenAI] = None
ReasoningUpdateFn = Callable[[str, bool, int], None]


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=_env("OPENAI_API_KEY"))
    return _client


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _extract_reasoning_summaries(resp: Any) -> List[str]:
    """
    Best-effort extraction of model-generated reasoning summaries from
    Responses API output items.
    """
    out: List[str] = []
    seen = set()

    output_items = _as_list(_field(resp, "output", []))
    for item in output_items:
        if str(_field(item, "type", "")).strip().lower() != "reasoning":
            continue

        summaries = _as_list(_field(item, "summary", []))
        for summary in summaries:
            text = str(_field(summary, "text", "") or "").strip()
            if text and text not in seen:
                seen.add(text)
                out.append(text)

        # Fallback in case a client shape omits `summary` and exposes text in content.
        if not summaries:
            for content in _as_list(_field(item, "content", [])):
                text = str(_field(content, "text", "") or "").strip()
                if text and text not in seen:
                    seen.add(text)
                    out.append(text)

    return out


def _safe_call_reasoning_update(
    fn: Optional[ReasoningUpdateFn],
    text: str,
    is_partial: bool,
    summary_index: int,
) -> None:
    if fn is None:
        return
    message = str(text or "").strip()
    if not message:
        return
    try:
        fn(message, is_partial, int(summary_index))
    except Exception:
        # UI telemetry hooks must never break core model calls.
        return


async def _stream_response_call(
    *,
    model: str,
    instructions: str,
    input_text: str,
    reasoning_effort: str,
    previous_response_id: Optional[str],
    store: bool,
    text_format: Optional[Dict[str, Any]] = None,
    on_reasoning_update: Optional[ReasoningUpdateFn] = None,
) -> Tuple[str, str, List[str]]:
    req: Dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "input": input_text,
        "previous_response_id": previous_response_id,
        "reasoning": {"effort": reasoning_effort, "summary": "auto"},
        "store": store,
        "stream": True,
    }
    if text_format is not None:
        req["text"] = text_format

    stream = await client().responses.create(**req)

    out_chunks: List[str] = []
    response_id = ""
    summaries: Dict[int, str] = {}
    last_emit_ts: Dict[int, float] = {}
    last_emit_text: Dict[int, str] = {}

    async for event in stream:
        etype = str(_field(event, "type", "") or "")

        if etype == "response.created":
            resp = _field(event, "response")
            rid = str(_field(resp, "id", "") or "").strip()
            if rid:
                response_id = rid
            continue

        if etype == "response.reasoning_summary_text.delta":
            idx = int(_field(event, "summary_index", 0) or 0)
            delta = str(_field(event, "delta", "") or "")
            if delta:
                next_text = summaries.get(idx, "") + delta
                summaries[idx] = next_text

                candidate = next_text.strip()
                if candidate:
                    prev_text = str(last_emit_text.get(idx, ""))
                    if candidate != prev_text:
                        now = time.monotonic()
                        prev_ts = float(last_emit_ts.get(idx, 0.0))
                        grew = len(candidate) - len(prev_text)
                        should_emit = (not prev_text) or (grew >= 24) or (now - prev_ts >= 0.18)
                        if should_emit:
                            _safe_call_reasoning_update(on_reasoning_update, candidate, True, idx)
                            last_emit_ts[idx] = now
                            last_emit_text[idx] = candidate
            continue

        if etype == "response.reasoning_summary_text.done":
            idx = int(_field(event, "summary_index", 0) or 0)
            done_text = str(_field(event, "text", "") or "").strip()
            if done_text:
                summaries[idx] = done_text
            final_text = summaries.get(idx, "").strip()
            if final_text:
                _safe_call_reasoning_update(on_reasoning_update, final_text, False, idx)
                last_emit_ts[idx] = time.monotonic()
                last_emit_text[idx] = final_text
            continue

        if etype == "response.output_text.delta":
            delta = str(_field(event, "delta", "") or "")
            if delta:
                out_chunks.append(delta)
            continue

        if etype == "response.output_text.done":
            txt = str(_field(event, "text", "") or "")
            if txt and not out_chunks:
                out_chunks.append(txt)
            continue

        if etype == "response.done":
            resp = _field(event, "response")
            rid = str(_field(resp, "id", "") or "").strip()
            if rid:
                response_id = rid
            # Final fallback in case output_text only exists on response.done payload.
            if not out_chunks:
                final_out = str(_field(resp, "output_text", "") or "")
                if final_out:
                    out_chunks.append(final_out)
            continue

    output_text = "".join(out_chunks)
    ordered_reasoning = [summaries[k].strip() for k in sorted(summaries) if summaries.get(k, "").strip()]
    return output_text, response_id, ordered_reasoning


async def json_schema_call(
    *,
    model: str,
    schema_name: str,
    schema: Dict[str, Any],
    instructions: str,
    input_text: str,
    reasoning_effort: str = "low",
    previous_response_id: Optional[str] = None,
    store: bool = False,
    on_reasoning_update: Optional[ReasoningUpdateFn] = None,
) -> Tuple[Dict[str, Any], str, List[str]]:
    """
    Call the Responses API with Structured Outputs (json_schema).

    Returns: (parsed_json, response_id, reasoning_summaries)
    """
    out, resp_id, reasoning = await _stream_response_call(
        model=model,
        instructions=instructions,
        input_text=input_text,
        reasoning_effort=reasoning_effort,
        previous_response_id=previous_response_id,
        store=store,
        text_format={
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": True,
            }
        },
        on_reasoning_update=on_reasoning_update,
    )
    try:
        return json.loads(out), resp_id, reasoning
    except json.JSONDecodeError as e:
        raise RuntimeError(
            "Model returned non-JSON output under json_schema. "
            f"Output was: {out[:500]}"
        ) from e


async def text_call(
    *,
    model: str,
    instructions: str,
    input_text: str,
    reasoning_effort: str = "medium",
    previous_response_id: Optional[str] = None,
    store: bool = True,
    on_reasoning_update: Optional[ReasoningUpdateFn] = None,
) -> Tuple[str, str, List[str]]:
    """
    Call the Responses API for plain text.

    Returns: (text, response_id, reasoning_summaries)
    """
    out, resp_id, reasoning = await _stream_response_call(
        model=model,
        instructions=instructions,
        input_text=input_text,
        reasoning_effort=reasoning_effort,
        previous_response_id=previous_response_id,
        store=store,
        on_reasoning_update=on_reasoning_update,
    )
    return out, resp_id, reasoning


async def stream_events_call(
    *,
    model: str,
    instructions: str,
    input_text: str,
    reasoning_effort: str = "medium",
    previous_response_id: Optional[str] = None,
    store: bool = True,
) -> AsyncIterator[Any]:
    """
    Stream server-sent events from the Responses API.

    The caller must iterate once. Relevant event types include:
    - response.output_text.delta
    - response.output_text.done
    - response.done
    """
    stream = await client().responses.create(
        model=model,
        instructions=instructions,
        input=input_text,
        previous_response_id=previous_response_id,
        reasoning={"effort": reasoning_effort, "summary": "auto"},
        store=store,
        stream=True,
    )
    async for event in stream:
        yield event
