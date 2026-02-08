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

## When to use

Use this skill when the user asks to build an agent that performs *conversational labour*:
coaching, tutoring, diagnostic intake, interviewing, structured facilitation, behaviour change, compliance interviews, etc.

## Output format expectations

Deliverables are code + docs, not prose. You should leave the repository in a runnable state with:

- `clab_bot/` Python package
- `configs/domain.yaml` domain theory template
- `configs/tutorial.yaml` intake tutorial steps
- `Dockerfile` and `docker-compose.yml`
- `README.md` with exact commands to run (local + docker)

## Repository scaffold workflow

1) Copy the template project into the current repo root (safe: does not overwrite existing files):

```bash
python .agents/skills/langgraph-conversational-labour/scripts/scaffold.py
```

2) Edit **domain theory** in `configs/domain.yaml`.
3) Edit **tutorial** in `configs/tutorial.yaml`.
4) Choose persistence via env vars:

- SQLite (default):
  - `CLAB_CHECKPOINTER=sqlite`
  - `CLAB_SQLITE_PATH=./.clab/checkpoints.sqlite3`
- Postgres:
  - `CLAB_CHECKPOINTER=postgres`
  - `CLAB_POSTGRES_URI=postgresql://...`

5) Run locally:

```bash
export OPENAI_API_KEY=...
pip install -e ".[dev]"
uvicorn clab_bot.server:app --reload
```

6) Or run via Docker:

```bash
export OPENAI_API_KEY=...
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

See: `references/intake_tutorial_guide.md`.

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
- `assets/template_project/`: runnable FastAPI + LangGraph project.
- `references/`: specs and guides.
