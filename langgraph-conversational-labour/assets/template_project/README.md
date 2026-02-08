# clab-bot (Conversational Labour Bot scaffold)

A domain-general LangGraph chatbot template for "conversational labour":

user message -> domain-theory analysis -> action selection -> response -> status summaries.

## Quickstart (local)

```bash
export OPENAI_API_KEY=...
pip install -e ".[dev]"
uvicorn clab_bot.server:app --reload
```

Test:

```bash
curl -s http://127.0.0.1:8000/chat \
  -H 'content-type: application/json' \
  -d '{"thread_id":"demo","message":"I want to get better at writing."}'
```

## Docker

SQLite persistence (default):

```bash
export OPENAI_API_KEY=...
docker compose up --build
```

Postgres persistence:

```bash
export OPENAI_API_KEY=...
docker compose --profile postgres up --build
```

## Configure the bot

Edit:

- `configs/domain.yaml` (domain theory)
- `configs/tutorial.yaml` (intake tutorial)

Key env vars:

- `OPENAI_API_KEY` (required)
- `CLAB_MODEL` (default from domain.yaml)
- `CLAB_CHECKPOINTER` = `sqlite` | `postgres` | `memory`
- `CLAB_SQLITE_PATH` (default: `./.clab/checkpoints.sqlite3`)
- `CLAB_POSTGRES_URI` (required if postgres)

## Endpoints

- `POST /chat`
  - input: `{ "thread_id": "...", "message": "..." }`
  - output: `{ "thread_id": "...", "message": "assistant text", "status": {...} }`

- `POST /chat/stream`
  - streams Server-Sent Events (SSE) for the composed assistant message

- `GET /threads/{thread_id}/status`
  - returns the latest stored status summary (user card + bot memory)

## How state is persisted

The app compiles the LangGraph graph with a database-backed checkpointer.

- SQLite uses `AsyncSqliteSaver` (`langgraph-checkpoint-sqlite`)
- Postgres uses `AsyncPostgresSaver` (`langgraph-checkpoint-postgres`)
