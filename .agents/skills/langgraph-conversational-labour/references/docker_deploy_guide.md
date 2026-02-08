# Docker guide (local and production-ish)

The template includes:

- `Dockerfile` for the FastAPI + LangGraph app
- `docker-compose.yml` with:
  - an app service
  - an optional Postgres service (profile)

## SQLite mode (default)

Persistence uses a SQLite file mounted as a volume:

- `/.clab/checkpoints.sqlite3`

Commands:

```bash
export OPENAI_API_KEY=...
docker compose up --build
```

## Postgres mode

Commands:

```bash
export OPENAI_API_KEY=...
docker compose --profile postgres up --build
```

This starts:
- `db` (Postgres)
- `app` (FastAPI) with `CLAB_CHECKPOINTER=postgres`

## Notes

- In production, terminate TLS in front of the app (reverse proxy).
- If you need horizontal scaling, prefer Postgres.
- Treat `OPENAI_API_KEY` as secret. Use Docker secrets or your orchestrator's secret manager.
