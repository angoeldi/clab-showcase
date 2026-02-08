# Persistence guide (database-backed state)

This scaffold uses LangGraph **checkpointers** to persist state by `thread_id`.

A checkpointer stores a checkpoint at every super-step so that a thread can be resumed later.

## What is persisted

The persisted state includes (by default):

- message history (or a bounded window, if you configure trimming)
- latest analysis + action plan
- tutorial progress
- status summaries:
  - user-facing card
  - bot memory object
- last `previous_response_id` (Responses API chaining)

## Required: thread_id

Every `/chat` call must include a `thread_id`. The checkpointer uses it as the durable key.

## Options

### 1) SQLite (default)

Best for:
- local development
- single-instance deployments
- demos, prototypes, low traffic

Implementation:
- `langgraph-checkpoint-sqlite` (`AsyncSqliteSaver`) with `aiosqlite`

Env vars:
- `CLAB_CHECKPOINTER=sqlite`
- `CLAB_SQLITE_PATH=./.clab/checkpoints.sqlite3`

### 2) Postgres (recommended for production)

Best for:
- multiple instances
- concurrency
- operational visibility and backups

Implementation:
- `langgraph-checkpoint-postgres` (`AsyncPostgresSaver`)

Env vars:
- `CLAB_CHECKPOINTER=postgres`
- `CLAB_POSTGRES_URI=postgresql://user:pass@host:5432/dbname`

The template includes a `docker-compose.yml` profile to start Postgres.

## Security notes (SQLite)

If you accept untrusted metadata filter keys in checkpoint search operations, older versions have had SQL injection issues.
The template pins `langgraph-checkpoint-sqlite` to a patched 3.x version.

## Operational notes

- For SQLite in Docker, mount a volume for `/.clab/` so the DB survives container restarts.
- For Postgres, run the saver `.setup()` once (the template does this on startup).

## Troubleshooting

- If state does not persist:
  - verify `thread_id` is stable
  - verify `CLAB_SQLITE_PATH` points to a writable location
  - for Postgres: verify connection string and that the checkpoint tables exist
