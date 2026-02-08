from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator, Dict, Optional, Tuple

from openai import AsyncOpenAI


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v is not None else default


_client: Optional[AsyncOpenAI] = None


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=_env("OPENAI_API_KEY"))
    return _client


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
) -> Tuple[Dict[str, Any], str]:
    """
    Call the Responses API with Structured Outputs (json_schema).

    Returns: (parsed_json, response_id)
    """
    resp = await client().responses.create(
        model=model,
        instructions=instructions,
        input=input_text,
        previous_response_id=previous_response_id,
        reasoning={"effort": reasoning_effort},
        store=store,
        text={
            "format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            }
        },
    )
    out = getattr(resp, "output_text", "") or ""
    try:
        return json.loads(out), resp.id
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
) -> Tuple[str, str]:
    """
    Call the Responses API for plain text.

    Returns: (text, response_id)
    """
    resp = await client().responses.create(
        model=model,
        instructions=instructions,
        input=input_text,
        previous_response_id=previous_response_id,
        reasoning={"effort": reasoning_effort},
        store=store,
    )
    out = getattr(resp, "output_text", "") or ""
    return out, resp.id


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
        reasoning={"effort": reasoning_effort},
        store=store,
        stream=True,
    )
    async for event in stream:
        yield event
