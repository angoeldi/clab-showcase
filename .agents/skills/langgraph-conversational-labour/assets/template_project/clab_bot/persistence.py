from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

import aiosqlite
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# Optional Postgres support (installed via extras: `pip install -e ".[postgres]"`)
try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # type: ignore
except Exception:  # pragma: no cover
    AsyncPostgresSaver = None  # type: ignore


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v is not None else default


@asynccontextmanager
async def make_checkpointer() -> AsyncIterator[object]:
    """
    Create an async checkpointer based on environment variables.

    - CLAB_CHECKPOINTER: sqlite|postgres|memory (default: sqlite)
    - CLAB_SQLITE_PATH: path to sqlite file (default: ./.clab/checkpoints.sqlite3)
    - CLAB_POSTGRES_URI: postgres connection string (required for postgres)
    """
    mode = (_env("CLAB_CHECKPOINTER", "sqlite") or "sqlite").strip().lower()

    if mode == "memory":
        # InMemorySaver supports async usage in LangGraph's API.
        saver = InMemorySaver()
        yield saver
        return

    if mode == "postgres":
        if AsyncPostgresSaver is None:
            raise RuntimeError(
                "Postgres mode requires extras: pip install -e '.[postgres]'"
            )
        uri = _env("CLAB_POSTGRES_URI")
        if not uri:
            raise RuntimeError("CLAB_POSTGRES_URI is required when CLAB_CHECKPOINTER=postgres")

        async with AsyncPostgresSaver.from_conn_string(uri) as saver:
            # Run table creation the first time.
            await saver.setup()
            yield saver
        return

    # Default: sqlite
    sqlite_path = Path(_env("CLAB_SQLITE_PATH", "./.clab/checkpoints.sqlite3") or "./.clab/checkpoints.sqlite3")
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(str(sqlite_path)) as conn:
        saver = AsyncSqliteSaver(conn)
        await saver.setup()
        yield saver
