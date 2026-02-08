from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

import yaml
from pydantic import BaseModel, ConfigDict, Field


class BootstrapUser(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    user_id: str = Field(..., alias="id", min_length=1)
    password: str = Field(..., min_length=1)
    display_name: str = Field(default="")
    profile: Dict[str, Any] = Field(default_factory=dict)


class BootstrapUsersConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    users: List[BootstrapUser] = Field(default_factory=list)


class RegisteredUser(BaseModel):
    user_id: str = Field(..., min_length=1)
    display_name: str = Field(default="")
    password_hash: str = Field(..., min_length=1)
    profile: Dict[str, Any] = Field(default_factory=dict)
    created_at_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RegisteredUsersConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    users: List[RegisteredUser] = Field(default_factory=list)


def _normalize_user_id(value: str) -> str:
    raw = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9_\-\.]+", "", raw)


def normalize_user_id(value: str) -> str:
    return _normalize_user_id(value)


def _hash_password(password: str, *, iterations: int = 210_000) -> str:
    if not password:
        raise ValueError("password is required")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    if not password or not encoded:
        return False
    try:
        algo, iterations_s, salt_hex, digest_hex = str(encoded).split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iterations_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def load_bootstrap_users(path: str | Path) -> Dict[str, BootstrapUser]:
    src = Path(path)
    if not src.exists():
        return {}

    data = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
    payload: Dict[str, Any]
    if isinstance(data, list):
        payload = {"users": data}
    elif isinstance(data, dict):
        payload = data
    else:
        raise ValueError(f"users config must be a mapping or list: {src}")

    cfg = BootstrapUsersConfig.model_validate(payload)
    users: Dict[str, BootstrapUser] = {}
    for entry in cfg.users:
        uid = _normalize_user_id(entry.user_id)
        if not uid:
            raise ValueError("bootstrap user id cannot be empty after normalization")
        if uid in users:
            raise ValueError(f"duplicate bootstrap user id: {uid}")
        users[uid] = BootstrapUser(
            user_id=uid,
            password=entry.password,
            display_name=str(entry.display_name or "").strip(),
            profile=dict(entry.profile or {}),
        )
    return users


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RegisteredUserStore:
    """
    Persistent local registry for user-created accounts.

    JSON shape:
    {
      "users": {
        "<user_id>": {
          "display_name": "...",
          "password_hash": "pbkdf2_sha256$...",
          "profile": {...},
          "created_at_utc": "..."
        }
      }
    }
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = asyncio.Lock()

    def _read_state(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"users": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"users": {}}
        if not isinstance(data, dict):
            return {"users": {}}
        users = data.get("users")
        if not isinstance(users, dict):
            users = {}
        return {"users": users}

    def _write_state(self, state: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    async def get(self, user_id: str) -> RegisteredUser | None:
        uid = _normalize_user_id(user_id)
        if not uid:
            return None
        async with self._lock:
            state = self._read_state()
            users = state.get("users") if isinstance(state, dict) else None
            data = users.get(uid) if isinstance(users, dict) else None
            if not isinstance(data, dict):
                return None
            return RegisteredUser(
                user_id=uid,
                display_name=str(data.get("display_name") or "").strip(),
                password_hash=str(data.get("password_hash") or ""),
                profile=dict(data.get("profile") or {}),
                created_at_utc=str(data.get("created_at_utc") or _utc_now()),
            )

    async def register(
        self,
        user_id: str,
        password: str,
        *,
        display_name: str = "",
        profile: Dict[str, Any] | None = None,
    ) -> RegisteredUser:
        uid = _normalize_user_id(user_id)
        if not uid:
            raise ValueError("user_id is required")
        if len(uid) < 3:
            raise ValueError("user_id must be at least 3 characters")
        if len(str(password or "")) < 6:
            raise ValueError("password must be at least 6 characters")

        async with self._lock:
            state = self._read_state()
            users = state.setdefault("users", {})
            if not isinstance(users, dict):
                users = {}
                state["users"] = users
            if uid in users:
                raise ValueError("user_id already exists")

            created_at = _utc_now()
            record = {
                "display_name": str(display_name or "").strip(),
                "password_hash": _hash_password(password),
                "profile": dict(profile or {}),
                "created_at_utc": created_at,
            }
            users[uid] = record
            self._write_state(state)
            return RegisteredUser(
                user_id=uid,
                display_name=record["display_name"],
                password_hash=record["password_hash"],
                profile=record["profile"],
                created_at_utc=created_at,
            )

    async def verify(self, user_id: str, password: str) -> RegisteredUser | None:
        uid = _normalize_user_id(user_id)
        if not uid:
            return None
        async with self._lock:
            state = self._read_state()
            users = state.get("users") if isinstance(state, dict) else None
            data = users.get(uid) if isinstance(users, dict) else None
            if not isinstance(data, dict):
                return None
            encoded = str(data.get("password_hash") or "")
            if not _verify_password(password, encoded):
                return None
            return RegisteredUser(
                user_id=uid,
                display_name=str(data.get("display_name") or "").strip(),
                password_hash=encoded,
                profile=dict(data.get("profile") or {}),
                created_at_utc=str(data.get("created_at_utc") or _utc_now()),
            )


class UserSessionStore:
    """
    Persistent local mapping of bootstrap user -> most recent thread id.

    JSON shape:
    {
      "users": {
        "<user_id>": {
          "thread_id": "...",
          "created_at_utc": "...",
          "last_seen_utc": "...",
          "starts": 3
        }
      }
    }
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = asyncio.Lock()

    def _read_state(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"users": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"users": {}}
        if not isinstance(data, dict):
            return {"users": {}}
        users = data.get("users")
        if not isinstance(users, dict):
            users = {}
        return {"users": users}

    def _write_state(self, state: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    async def get(self, user_id: str) -> Dict[str, Any] | None:
        uid = _normalize_user_id(user_id)
        if not uid:
            return None
        async with self._lock:
            state = self._read_state()
            users = state.get("users") if isinstance(state, dict) else None
            record = users.get(uid) if isinstance(users, dict) else None
            return dict(record) if isinstance(record, dict) else None

    async def start(
        self,
        user_id: str,
        *,
        new_thread: bool,
        thread_factory: Callable[[str], str],
    ) -> Tuple[Dict[str, Any], bool]:
        uid = _normalize_user_id(user_id)
        if not uid:
            raise ValueError("user_id is required")

        async with self._lock:
            state = self._read_state()
            users = state.setdefault("users", {})
            if not isinstance(users, dict):
                users = {}
                state["users"] = users

            now = _utc_now()
            current = users.get(uid) if isinstance(users.get(uid), dict) else {}

            previous_thread = str(current.get("thread_id") or "").strip()
            resumed = bool(previous_thread and not new_thread)
            thread_id = previous_thread if resumed else str(thread_factory(uid))

            starts_raw = current.get("starts", 0)
            try:
                starts = max(0, int(starts_raw))
            except Exception:
                starts = 0
            starts += 1

            record = {
                "thread_id": thread_id,
                "created_at_utc": str(current.get("created_at_utc") or now),
                "last_seen_utc": now,
                "starts": starts,
            }
            users[uid] = record
            self._write_state(state)
            return dict(record), resumed
