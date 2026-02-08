---
name: langgraph-conversational-labour
description: >
  Scaffold a LangGraph-based "conversational labour" chatbot: user-message intake -> domain-theory analysis -> action selection -> response composition -> user tracking.
  Includes an intake tutorial flow, DB-backed persistence (SQLite/Postgres via LangGraph checkpointers), Docker, and per-turn + resumable status summaries.
triggers:
  - "langgraph chatbot"
  - "coaching bot"
  - "tutor bot"
  - "diagnostic interview bot"
  - "journalistic interview bot"
  - "domain theory driven agent"
  - "conversational labour"
---

# LangGraph Conversational Labour Scaffold (Domain-general)

## What this skill does

When invoked, you will scaffold a runnable LangGraph application that:

1) **Ingests user messages** (threaded by `thread_id`).
2) **Analyzes** each message using a *declared domain theory* (as data in YAML).
3) **Selects an action** (rule-first; LLM fallback) that enacts the domain theory.
4) **Composes the bot message** implementing that action while keeping the user on track.
5) **Persists state** in a database-backed checkpointer (SQLite by default; Postgres supported).
6) **Provides status summaries**:
   - **User-facing status card** appended to the bot message (configurable).
   - **Bot-facing memory object** injected at the start of each new session/turn.

It also includes an **intake tutorial** ("how this system works") as a short, visual, stepwise tour.
Default expectation: tutorial is a **UI overlay walkthrough** (spotlight/callout style), not a chat-turn gate, unless the user explicitly asks for in-chat tutorial turns.

## When to use

Use this skill when the user asks to build an agent that performs *conversational labour*:
coaching, tutoring, diagnostic intake, interviewing, structured facilitation, behaviour change, compliance interviews, etc.

## Output format expectations

Deliverables are code + docs, not prose. You should leave the repository in a runnable state with:

- `clab_bot/` Python package
- `configs/domain.yaml` domain theory template
- `configs/tutorial.yaml` intake tutorial steps
- `configs/users.yaml` bootstrap user profiles (for return-user testing)
- auth/session API support for:
  registration/login and guest default sessions (`/auth/register`, `/auth/login`, `/auth/guest`)
- `Dockerfile` and `docker-compose.yml`
- `README.md` with exact commands to run (local + docker)

## Repository scaffold workflow

1) Copy the template project into the current repo root (safe: does not overwrite existing files):

```bash
python .agents/skills/langgraph-conversational-labour/scripts/scaffold.py
```

If the repo already has a working app implementation and the user wants "same architecture, new domain/app", prefer cloning that working app instead of regenerating from template:

```bash
python scripts/create_app_from_example.py <app-id>
```

If the repo does not have that helper script yet, use the skill-bundled one:

```bash
python .agents/skills/langgraph-conversational-labour/scripts/create_app_from_example.py <app-id>
```

2) Edit **domain theory** in `configs/domain.yaml`.
3) Edit **tutorial** in `configs/tutorial.yaml`.
4) Edit **bootstrap users** in `configs/users.yaml` (include at least one test user id/password/profile).
5) Choose persistence via env vars:

- SQLite (default):
  - `CLAB_CHECKPOINTER=sqlite`
  - `CLAB_SQLITE_PATH=./.clab/checkpoints.sqlite3`
- Postgres:
  - `CLAB_CHECKPOINTER=postgres`
  - `CLAB_POSTGRES_URI=postgresql://...`

6) Run locally:

```bash
export OPENAI_API_KEY=...
export CLAB_APP_MODULE=clab_bot.server:app
export CLAB_USERS_PATH=configs/users.yaml
pip install -e ".[dev]"
uvicorn "$CLAB_APP_MODULE" --reload
```

7) Or run via Docker:

```bash
export OPENAI_API_KEY=...
export CLAB_APP_MODULE=clab_bot.server:app
export CLAB_USERS_PATH=configs/users.yaml
docker compose up --build
```

## Domain theory contract (must stay explicit)

The bot must never "improvise a theory" silently. The domain theory is declarative and must be edited by the developer:

- stages/phases
- constructs/signals to track
- interventions/actions (with constraints + style)
- rule policy for action selection
- safety/risk policies

See: `references/domain_theory_spec.md`.

## Intake tutorial contract

The tutorial must be a **short cycle** of visually distinct steps that explains:

- the bot's cycle (sensemaking -> action -> reflection)
- what the user can expect
- how the user can correct the bot
- how summaries work and how to resume

Implementation preference:
- Attach steps to visible UI elements via stable ids (e.g. `data-tutorial-id`).
- Support `Back`/`Next`/`Finish` and `Don't show again`.
- Avoid consuming user chat turns for tutorial unless explicitly requested.

See: `references/intake_tutorial_guide.md`.

## Streaming contract

If a streaming endpoint is provided (`/chat/stream`), it must run on the LangGraph execution path (not a duplicate manual pipeline) and may emit:

- per-node reasoning updates (e.g. ingest/analyze/act/compose/finalize),
- final assistant message,
- final status payload.

## Persistence contract

The app must persist graph state by thread ID using LangGraph checkpointers.

- SQLite is required.
- Postgres support is included (docker-compose profile + code path).

See: `references/persistence_guide.md`.

## Status summaries contract

Every turn should update:

- `status.user_card_md` (user-facing)
- `status.bot_memory` (machine-parseable)

These are used for continuity and to reduce prompt bloat.

See: `references/summaries_guide.md`.

## Guardrails (domain-general)

- No medical/legal/policing instruction beyond safe, non-actionable guidance unless the domain theory explicitly allows it and a qualified professional has reviewed prompts and rules.
- Non-factive reasoning must be labelled as hypothesis; do not present conjecture as fact.
- The system must ask for missing critical info instead of hallucinating.

## Files in this skill

- `scripts/scaffold.py`: copies `assets/template_project/` into the current repo.
- `scripts/create_app_from_example.py`: clones a working app package/config into a new app with updated default config paths.
- `assets/template_project/`: runnable FastAPI + LangGraph project.
- `references/`: specs and guides.
