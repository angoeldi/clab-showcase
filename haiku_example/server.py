from __future__ import annotations

import json
import os
import re
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .domain import load_domain
from .graph import build_graph
from .persistence import make_checkpointer
from .tutorial import TutorialConfig, load_tutorial
from .users import BootstrapUser, RegisteredUserStore, UserSessionStore, load_bootstrap_users


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v is not None else default


DEFAULT_DOMAIN_PATH = "configs/examples/haiku_tutor/domain.yaml"
DEFAULT_TUTORIAL_PATH = "configs/examples/haiku_tutor/tutorial.yaml"
DEFAULT_USERS_PATH = "configs/examples/haiku_tutor/users.yaml"
DEFAULT_USERS_STATE_PATH = "./.clab/user_sessions.json"
DEFAULT_REGISTERED_USERS_STATE_PATH = "./.clab/registered_users.json"
DEFAULT_UI_TITLE = "Haiku Expert Chat"
DEFAULT_ASSISTANT_NAME = "Haiku Expert"
DEFAULT_AUTH_REALM = "haiku-example"
UI_DIR = Path(__file__).resolve().parent / "ui"
HTTP_BASIC = HTTPBasic(auto_error=False)


class ChatRequest(BaseModel):
    thread_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    thread_id: str
    message: str
    status: Dict[str, Any] = Field(default_factory=dict)


class SessionStartRequest(BaseModel):
    user_id: str | None = None
    new_thread: bool = False


class SessionStartResponse(BaseModel):
    user_id: str
    display_name: str
    profile: Dict[str, Any] = Field(default_factory=dict)
    thread_id: str
    resumed: bool
    auth_required: bool
    auth_mode: str = Field(default="bootstrap")
    status: Dict[str, Any] = Field(default_factory=dict)


class RegisterRequest(BaseModel):
    user_id: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)
    display_name: str = ""
    new_thread: bool = False


class LoginRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    new_thread: bool = False


class GuestRequest(BaseModel):
    guest_code: str | None = None
    new_thread: bool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with make_checkpointer() as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        users_path = _env("CLAB_USERS_PATH", DEFAULT_USERS_PATH) or DEFAULT_USERS_PATH
        users_state_path = _env("CLAB_USERS_STATE_PATH", DEFAULT_USERS_STATE_PATH) or DEFAULT_USERS_STATE_PATH
        registered_users_state_path = (
            _env("CLAB_REGISTERED_USERS_STATE_PATH", DEFAULT_REGISTERED_USERS_STATE_PATH)
            or DEFAULT_REGISTERED_USERS_STATE_PATH
        )

        if Path(users_path).exists():
            users = load_bootstrap_users(users_path)
        else:
            users = {}

        app.state.checkpointer = checkpointer
        app.state.graph = graph
        app.state.users_path = users_path
        app.state.bootstrap_users = users
        app.state.user_sessions = UserSessionStore(users_state_path)
        app.state.registered_users = RegisteredUserStore(registered_users_state_path)
        yield


app = FastAPI(title="haiku-example", version="0.1.0", lifespan=lifespan)

if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")


@app.middleware("http")
async def ui_cache_bust_middleware(request, call_next):
    response = await call_next(request)
    path = request.url.path or ""
    if path.startswith("/ui"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.get("/")
async def root():
    if UI_DIR.exists():
        return RedirectResponse(url="/ui/")
    return JSONResponse(_runtime_meta())


@app.get("/meta")
async def get_meta():
    return JSONResponse(_runtime_meta())


@app.get("/tutorial")
async def get_tutorial():
    cfg = _load_runtime_tutorial()
    return JSONResponse(
        {
            "enabled": cfg.enabled,
            "start_when": cfg.start_when,
            "steps": [
                {
                    "id": s.id,
                    "title": s.title,
                    "body_md": s.body_md,
                    "cta": s.cta,
                }
                for s in cfg.steps
            ],
        }
    )


@app.get("/users/bootstrap")
async def get_bootstrap_users():
    users = _bootstrap_users()
    return JSONResponse(
        {
            "auth_required": _basic_auth_enabled(),
            "registration_enabled": True,
            "users_path": getattr(app.state, "users_path", DEFAULT_USERS_PATH),
            "users": [
                {
                    "user_id": user.user_id,
                    "display_name": user.display_name,
                    "profile": dict(user.profile or {}),
                }
                for user in users.values()
            ],
        }
    )


@app.post("/auth/register", response_model=SessionStartResponse)
async def auth_register(req: RegisterRequest) -> SessionStartResponse:
    user_id = _normalize_user_id(req.user_id)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id is required.")
    if user_id in _bootstrap_users():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="user_id is reserved by bootstrap users.")

    reg_store: RegisteredUserStore = _registered_users()
    try:
        created = await reg_store.register(
            user_id,
            req.password,
            display_name=str(req.display_name or "").strip(),
            profile={},
        )
    except ValueError as exc:
        msg = str(exc)
        if "already exists" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    return await _start_session_for_identity(
        user_id=created.user_id,
        display_name=created.display_name or created.user_id,
        profile=dict(created.profile or {}),
        new_thread=bool(req.new_thread),
        auth_required=False,
        auth_mode="registered",
    )


@app.post("/auth/login", response_model=SessionStartResponse)
async def auth_login(req: LoginRequest) -> SessionStartResponse:
    user_id = _normalize_user_id(req.user_id)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id is required.")
    password = str(req.password or "")
    if not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password is required.")

    boot = _bootstrap_users().get(user_id)
    if boot is not None and secrets.compare_digest(password, boot.password):
        return await _start_session_for_identity(
            user_id=boot.user_id,
            display_name=boot.display_name or boot.user_id,
            profile=dict(boot.profile or {}),
            new_thread=bool(req.new_thread),
            auth_required=_basic_auth_enabled(),
            auth_mode="bootstrap",
        )

    reg_store: RegisteredUserStore = _registered_users()
    found = await reg_store.verify(user_id, password)
    if found is not None:
        return await _start_session_for_identity(
            user_id=found.user_id,
            display_name=found.display_name or found.user_id,
            profile=dict(found.profile or {}),
            new_thread=bool(req.new_thread),
            auth_required=False,
            auth_mode="registered",
        )

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user credentials.")


@app.get("/auth/guest", response_model=SessionStartResponse)
async def auth_guest_get(
    code: str | None = Query(default=None),
    new_thread: bool = Query(default=False),
) -> SessionStartResponse:
    guest_code = _resolve_guest_code(post_value=None, get_value=code)
    return await _start_guest_session(guest_code=guest_code, new_thread=bool(new_thread))


@app.post("/auth/guest", response_model=SessionStartResponse)
async def auth_guest_post(
    req: GuestRequest,
    code: str | None = Query(default=None),
    new_thread: bool | None = Query(default=None),
) -> SessionStartResponse:
    # POST body values win over query-string values when both are provided.
    effective_new_thread = req.new_thread if req.new_thread is not None else bool(new_thread)
    guest_code = _resolve_guest_code(post_value=req.guest_code, get_value=code)
    return await _start_guest_session(guest_code=guest_code, new_thread=bool(effective_new_thread))


@app.post("/session/start", response_model=SessionStartResponse)
async def session_start(
    req: SessionStartRequest,
    credentials: HTTPBasicCredentials | None = Depends(HTTP_BASIC),
) -> SessionStartResponse:
    users = _bootstrap_users()
    if not users:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No bootstrap users configured.")

    auth_required = _basic_auth_enabled()
    selected_user: BootstrapUser

    if auth_required:
        selected_user = _authenticate_basic_user(credentials, users)
        requested = _normalize_user_id(req.user_id or "")
        if requested and requested != selected_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_id must match Basic auth username.",
            )
    else:
        requested = _normalize_user_id(req.user_id or "")
        if not requested:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id is required.")
        selected_user = users.get(requested)
        if selected_user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bootstrap user not found.")

    return await _start_session_for_identity(
        user_id=selected_user.user_id,
        display_name=selected_user.display_name or selected_user.user_id,
        profile=dict(selected_user.profile or {}),
        new_thread=bool(req.new_thread),
        auth_required=auth_required,
        auth_mode="bootstrap",
    )


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


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    graph = app.state.graph
    config = {"configurable": {"thread_id": req.thread_id}}

    async def event_stream() -> AsyncIterator[bytes]:
        custom_generated_nodes: set[str] = set()
        try:
            async for chunk in graph.astream(
                {"last_user_message": req.message},
                config=config,
                stream_mode=["custom", "updates"],
            ):
                mode = "updates"
                payload = chunk
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    mode = str(chunk[0] or "")
                    payload = chunk[1]

                if mode == "custom":
                    custom = payload if isinstance(payload, dict) else {}
                    ctype = str(custom.get("type") or "")
                    node_name = str(custom.get("node") or "")
                    if ctype in {
                        "reasoning_generated_live",
                        "reasoning_generated",
                        "reasoning_deterministic",
                        "reasoning_status",
                    }:
                        if ctype.startswith("reasoning_generated") and node_name:
                            custom_generated_nodes.add(node_name)
                        yield _sse(custom)
                    continue

                update = payload if isinstance(payload, dict) else None
                if not isinstance(update, dict):
                    continue
                for node, node_update in update.items():
                    node_name = str(node)

                    if node_name not in custom_generated_nodes:
                        for item in _node_generated_reasoning(node_name, node_update):
                            kind = str(item.get("kind") or "generated")
                            message = str(item.get("message") or "")
                            event_type = "reasoning_deterministic" if kind == "deterministic" else "reasoning_generated"
                            yield _sse({"type": event_type, "node": node_name, "message": message})

                    status_message = _node_status_message(node_name, node_update)
                    if status_message:
                        yield _sse({"type": "reasoning_status", "node": node_name, "message": status_message})

            snap = await graph.aget_state(config)
            values = dict(getattr(snap, "values", None) or {})
            yield _sse({"type": "assistant", "message": str(values.get("assistant_message") or "")})
            yield _sse({"type": "status", "status": dict(values.get("status") or {})})
            yield b"data: [DONE]\n\n"
        except Exception as exc:
            yield _sse({"type": "error", "message": str(exc)})
            yield b"data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _runtime_meta() -> Dict[str, Any]:
    domain_path = _env("CLAB_DOMAIN_PATH", DEFAULT_DOMAIN_PATH) or DEFAULT_DOMAIN_PATH
    tutorial_path = _env("CLAB_TUTORIAL_PATH", DEFAULT_TUTORIAL_PATH) or DEFAULT_TUTORIAL_PATH
    users_path = _env("CLAB_USERS_PATH", DEFAULT_USERS_PATH) or DEFAULT_USERS_PATH
    model = _env("CLAB_MODEL")
    ui_title = _env("CLAB_UI_TITLE", DEFAULT_UI_TITLE) or DEFAULT_UI_TITLE
    assistant_name = _env("CLAB_ASSISTANT_NAME", DEFAULT_ASSISTANT_NAME) or DEFAULT_ASSISTANT_NAME

    if not model:
        try:
            model = load_domain(domain_path).model
        except Exception:
            model = ""

    tutorial_enabled = False
    try:
        tutorial_enabled = load_tutorial(tutorial_path).enabled
    except Exception:
        tutorial_enabled = False

    bootstrap_user_count = 0
    try:
        bootstrap_user_count = len(load_bootstrap_users(users_path))
    except Exception:
        bootstrap_user_count = 0

    return {
        "title": "haiku-example",
        "version": "0.1.0",
        "model": model,
        "checkpointer": _env("CLAB_CHECKPOINTER", "sqlite") or "sqlite",
        "domain_path": domain_path,
        "tutorial_path": tutorial_path,
        "tutorial_enabled": tutorial_enabled,
        "users_path": users_path,
        "bootstrap_user_count": bootstrap_user_count,
        "basic_auth_enabled": _basic_auth_enabled(),
        "registration_enabled": True,
        "guest_enabled": True,
        "ui_title": ui_title,
        "assistant_name": assistant_name,
    }


def _load_runtime_tutorial() -> TutorialConfig:
    tutorial_path = _env("CLAB_TUTORIAL_PATH", DEFAULT_TUTORIAL_PATH) or DEFAULT_TUTORIAL_PATH
    return load_tutorial(tutorial_path)


def _basic_auth_enabled() -> bool:
    raw = (_env("CLAB_BASIC_AUTH_ENABLED", "true") or "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _normalize_user_id(value: str) -> str:
    raw = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9_\-\.]+", "", raw)


def _new_thread_for_user(user_id: str) -> str:
    normalized = _normalize_user_id(user_id) or "user"
    return f"{normalized}-{int(time.time() * 1000)}-{secrets.token_hex(2)}"


def _bootstrap_users() -> Dict[str, BootstrapUser]:
    users = getattr(app.state, "bootstrap_users", {})
    return users if isinstance(users, dict) else {}


def _registered_users() -> RegisteredUserStore:
    return app.state.registered_users


def _auth_header_value() -> str:
    realm = (_env("CLAB_AUTH_REALM", DEFAULT_AUTH_REALM) or DEFAULT_AUTH_REALM).replace('"', "")
    return f'Basic realm="{realm}"'


def _authenticate_basic_user(
    credentials: HTTPBasicCredentials | None,
    users: Dict[str, BootstrapUser],
) -> BootstrapUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Basic auth credentials.",
            headers={"WWW-Authenticate": _auth_header_value()},
        )

    username = _normalize_user_id(credentials.username or "")
    password = str(credentials.password or "")
    user = users.get(username)
    if user is None or not secrets.compare_digest(password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user credentials.",
            headers={"WWW-Authenticate": _auth_header_value()},
        )
    return user


async def _thread_status_for(thread_id: str) -> Dict[str, Any]:
    if not thread_id:
        return {}
    graph = app.state.graph
    config = {"configurable": {"thread_id": thread_id}}
    snap = await graph.aget_state(config)
    values = getattr(snap, "values", None) or {}
    return dict(values.get("status") or {})


async def _start_session_for_identity(
    *,
    user_id: str,
    display_name: str,
    profile: Dict[str, Any],
    new_thread: bool,
    auth_required: bool,
    auth_mode: str,
) -> SessionStartResponse:
    store: UserSessionStore = app.state.user_sessions
    record, resumed = await store.start(
        user_id,
        new_thread=bool(new_thread),
        thread_factory=_new_thread_for_user,
    )
    thread_id = str(record.get("thread_id") or "")
    thread_status = await _thread_status_for(thread_id)
    return SessionStartResponse(
        user_id=user_id,
        display_name=display_name or user_id,
        profile=dict(profile or {}),
        thread_id=thread_id,
        resumed=resumed,
        auth_required=bool(auth_required),
        auth_mode=str(auth_mode or "bootstrap"),
        status=thread_status,
    )


def _resolve_guest_code(*, post_value: str | None, get_value: str | None) -> str:
    raw = str(post_value or "").strip() or str(get_value or "").strip()
    if not raw:
        raw = uuid.uuid4().hex[:12]
    normalized = re.sub(r"[^a-z0-9_\-]+", "", raw.lower())
    if not normalized:
        normalized = uuid.uuid4().hex[:12]
    return normalized[:32]


async def _start_guest_session(*, guest_code: str, new_thread: bool) -> SessionStartResponse:
    guest = _resolve_guest_code(post_value=guest_code, get_value=None)
    user_id = f"guest_{guest}"
    return await _start_session_for_identity(
        user_id=user_id,
        display_name=f"Guest {guest[:8]}",
        profile={"guest": True, "guest_code": guest},
        new_thread=bool(new_thread),
        auth_required=False,
        auth_mode="guest",
    )


def _node_generated_reasoning(_node: str, node_update: Any) -> list[Dict[str, str]]:
    data = node_update if isinstance(node_update, dict) else {}
    values = data.get("generated_reasoning")
    if not isinstance(values, list):
        values = []

    out: list[Dict[str, str]] = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append({"kind": "generated", "message": text})
    if out:
        return out
    return [{"kind": "deterministic", "message": msg} for msg in _node_deterministic_reasoning(_node, data)]


def _node_deterministic_reasoning(node: str, data: Dict[str, Any]) -> list[str]:
    if node == "ingest":
        flags = [str(f).strip() for f in (data.get("red_flags") or []) if str(f).strip()]
        if flags:
            return [
                "I captured your message and ran keyword safety checks; potential safety matches found: "
                + ", ".join(flags[:3])
                + "."
            ]
        return ["I captured your message and ran keyword safety checks; no safety matches were detected."]

    if node == "decide":
        mode = str(data.get("mode") or "work").strip().lower()
        turn = int(data.get("turn_index", 0) or 0)
        if mode == "tutorial":
            return [f"I selected tutorial mode for turn {turn} because tutorial triggers are currently active."]
        return [f"I selected coaching mode for turn {turn} because tutorial triggers did not match this message."]

    if node == "tutorial":
        tut = data.get("tutorial") if isinstance(data.get("tutorial"), dict) else {}
        if tut.get("completed"):
            return ["I marked the tutorial as complete based on your command and will continue in coaching mode."]
        step_index = int(tut.get("step_index", 0) or 0) + 1
        return [f"I kept tutorial mode active and prepared step {step_index}."]

    if node == "analyze":
        analysis = data.get("analysis") if isinstance(data.get("analysis"), dict) else {}
        stage = str(analysis.get("stage") or "").strip() or "unspecified"
        signals = analysis.get("signals") if isinstance(analysis.get("signals"), dict) else {}
        risk = int(signals.get("risk", 0) or 0)
        return [f"I analyzed your draft as stage **{stage}** and estimated risk at {risk}/5 for this turn."]

    if node == "act":
        plan = data.get("action_plan") if isinstance(data.get("action_plan"), dict) else {}
        action = str(plan.get("action") or "").strip() or "SUMMARISE"
        rationale = str(plan.get("rationale") or "").strip()
        if rationale:
            return [rationale]
        params = plan.get("params") if isinstance(plan.get("params"), dict) else {}
        keys = [str(k).strip() for k in params.keys() if str(k).strip()]
        extra = ""
        if keys:
            extra += " Settings used: " + ", ".join(keys[:3]) + "."
        return [f"I selected **{action}** for this turn.{extra}"]

    if node == "compose":
        plan = data.get("action_plan") if isinstance(data.get("action_plan"), dict) else {}
        action = str(plan.get("action") or "").strip() or "current plan"
        return [f"I drafted your reply according to the **{action}** plan and current context."]

    if node == "finalize":
        return ["I finalized the turn by storing the drafted response and updated status for the next message."]

    return []


def _node_status_message(node: str, node_update: Any) -> str | None:
    data = node_update if isinstance(node_update, dict) else {}

    if node == "ingest":
        return "Input captured."

    if node == "decide":
        mode = str(data.get("mode") or "work").strip().lower()
        if mode == "tutorial":
            return "Tutorial path selected."
        return "Coaching path selected."

    if node == "tutorial":
        tut = data.get("tutorial") if isinstance(data.get("tutorial"), dict) else {}
        if tut.get("completed"):
            return "Tutorial complete."
        step_index = int(tut.get("step_index", 0)) + 1
        return f"Tutorial step {step_index} shown."

    if node == "analyze":
        analysis = data.get("analysis") if isinstance(data.get("analysis"), dict) else {}
        stage = str(analysis.get("stage") or "").strip()
        if stage:
            return f"Draft review complete ({stage})."
        return "Draft review complete."

    if node == "act":
        plan = data.get("action_plan") if isinstance(data.get("action_plan"), dict) else {}
        action = str(plan.get("action") or "").strip()
        if action:
            return f"Feedback plan selected ({action})."
        return "Feedback plan selected."

    if node == "compose":
        return "Feedback drafted."

    if node == "finalize":
        return "Response ready."

    return None


def _sse(payload: Dict[str, Any]) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
