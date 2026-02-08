# SETUP

This file contains the full technical setup and operational reference for this repo.

## Defaults

Default runtime target:
- App module: `haiku_example.server:app`
- Domain config: `configs/examples/haiku_tutor/domain.yaml`
- Tutorial config: `configs/examples/haiku_tutor/tutorial.yaml`
- Bootstrap users: `configs/examples/haiku_tutor/users.yaml`
- Model default (docker): `gpt-5-nano`

## Quick Start

### Local (default haiku app)

```bash
export OPENAI_API_KEY=...
export CLAB_APP_MODULE=haiku_example.server:app
export CLAB_DOMAIN_PATH=configs/examples/haiku_tutor/domain.yaml
export CLAB_TUTORIAL_PATH=configs/examples/haiku_tutor/tutorial.yaml
export CLAB_USERS_PATH=configs/examples/haiku_tutor/users.yaml
export CLAB_BASIC_AUTH_ENABLED=true
pip install -e ".[dev]"
uvicorn "$CLAB_APP_MODULE" --reload
```

Open:
- `http://127.0.0.1:8000/ui/`
- `http://127.0.0.1:8000/meta`

### Docker (default haiku app)

```bash
export OPENAI_API_KEY=...
docker compose up --build -d
```

Compose reads:
- `CLAB_APP_MODULE` (default `haiku_example.server:app`)
- `CLAB_DOMAIN_PATH`
- `CLAB_TUTORIAL_PATH`
- `CLAB_USERS_PATH`
- `CLAB_USERS_STATE_PATH`
- `CLAB_REGISTERED_USERS_STATE_PATH`
- `CLAB_BASIC_AUTH_ENABLED`
- `CLAB_MODEL`
- `CLAB_CHECKPOINTER`
- `CLAB_SQLITE_PATH`
- `CLAB_POSTGRES_URI`

## Run The MI Example App

### Local (MI app)

```bash
export OPENAI_API_KEY=...
export CLAB_APP_MODULE=mi_social_media_addiction_example.server:app
export CLAB_DOMAIN_PATH=configs/examples/mi-social-media-addiction/domain.yaml
export CLAB_TUTORIAL_PATH=configs/examples/mi-social-media-addiction/tutorial.yaml
export CLAB_USERS_PATH=configs/examples/mi-social-media-addiction/users.yaml
export CLAB_BASIC_AUTH_ENABLED=true
pip install -e ".[dev]"
uvicorn "$CLAB_APP_MODULE" --reload
```

### Docker (MI app)

```bash
export OPENAI_API_KEY=...
export CLAB_APP_MODULE=mi_social_media_addiction_example.server:app
export CLAB_DOMAIN_PATH=configs/examples/mi-social-media-addiction/domain.yaml
export CLAB_TUTORIAL_PATH=configs/examples/mi-social-media-addiction/tutorial.yaml
export CLAB_USERS_PATH=configs/examples/mi-social-media-addiction/users.yaml
docker compose up --build -d
```

Quick check:

```bash
curl -s http://127.0.0.1:8000/meta
```

Expected MI fields:
- `"title": "mi-social-media-addiction-example"`
- `"domain_path": "configs/examples/mi-social-media-addiction/domain.yaml"`

## Returning User Bootstrap Flow

Seeded bootstrap users live in `configs/examples/haiku_tutor/users.yaml`.

List bootstrap users:

```bash
curl -s http://127.0.0.1:8000/users/bootstrap
```

Start or resume a session (Basic auth enabled by default):

```bash
curl -s -u demo_haiku_student:demo-haiku-123 \
  -H 'content-type: application/json' \
  -d '{"new_thread":false}' \
  http://127.0.0.1:8000/session/start
```

Response includes:
- `thread_id`
- `resumed`
- `profile`
- `status`

## Registration, Login, And Default Guest

Navbar auth controls call:
- `POST /auth/login`
- `POST /auth/register`
- `POST /auth/guest`

Default behavior on page load:
- UI starts a guest session automatically.
- If no guest code is supplied, backend generates one.
- Guest code can come from query string (`GET`) and/or body (`POST`).
- If both are present, `POST` takes precedence.

API examples:

```bash
# Register
curl -s -H 'content-type: application/json' \
  -d '{"user_id":"new_writer","password":"writer-pass-123","display_name":"New Writer","new_thread":true}' \
  http://127.0.0.1:8000/auth/register

# Login
curl -s -H 'content-type: application/json' \
  -d '{"user_id":"new_writer","password":"writer-pass-123","new_thread":false}' \
  http://127.0.0.1:8000/auth/login

# Guest via GET
curl -s "http://127.0.0.1:8000/auth/guest?code=demo-guest"

# Guest via POST (wins over GET if both present)
curl -s -H 'content-type: application/json' \
  -d '{"guest_code":"from_post","new_thread":true}' \
  "http://127.0.0.1:8000/auth/guest?code=from_get"
```

## Create Another App From The Working Example

Clone full package + config set:

```bash
python scripts/create_app_from_example.py writing-coach
```

Creates:
- `writing_coach_example/`
- `configs/examples/writing-coach/`

Typical run:

```bash
export CLAB_APP_MODULE=writing_coach_example.server:app
export CLAB_DOMAIN_PATH=configs/examples/writing-coach/domain.yaml
export CLAB_TUTORIAL_PATH=configs/examples/writing-coach/tutorial.yaml
export CLAB_USERS_PATH=configs/examples/writing-coach/users.yaml
docker compose up --build -d
```

Options:

```bash
python scripts/create_app_from_example.py <app-id> \
  --source-package haiku_example \
  --source-config-dir configs/examples/haiku_tutor \
  --config-id <config-folder-name> \
  --force
```

Naming note:
- Package names normalize to `<slug>_example`.

## Prompt For Creating A New App

Domain-pack zip contract (what should be inside):
- Required: one domain config YAML (for example `domain_<app>.yaml`)
- Required: one tutorial config YAML (for example `tutorial_<app>.yaml`)
- Optional but recommended: one references/notes file (for example `references_<app>.md`)
- Optional: one bootstrap users YAML (for example `users_<app>.yaml`)

If `users_<app>.yaml` is not provided, keep the scaffolded users file and edit it manually.

### What must be in `domain.yaml`

Use this structure (minimum + recommended):

```yaml
runtime:
  model: "gpt-5-nano"        # recommended
  store_responses: true      # optional (default true)
  reasoning_effort:          # optional
    analyze: "low"           # supported keys: analyze, act, compose
    act: "low"               # use "act" (not "decide_action")
    compose: "medium"

stages:                      # recommended
  - id: "engage"
    label: "Engage"
    purpose: "..."

constructs:                  # recommended
  - id: "goal_clarity"       # keep: goal_clarity, motivation, risk
    label: "Goal clarity"
  - id: "motivation"
    label: "Motivation"
  - id: "risk"
    label: "Risk"

interventions:               # recommended
  - id: "PROBE"
    label: "Open question"
  - id: "SUMMARISE"
    label: "Summary"

action_policy:               # required for deterministic routing
  rules:
    - when:
        stage_in: ["engage"]         # optional
        risk_gte: 4                  # optional
        missing_any: ["goal"]        # optional; supported: goal, constraints
      then:
        action: "PROBE"
        params:
          question: "What do you want to change?"
    - when:
        default: true
      then:
        action: "SUMMARISE"
        params: {}
  llm_fallback:
    enabled: true
    allowed_actions: ["PROBE", "SUMMARISE", "SAFETY"]

writing_style:               # optional but strongly recommended
  tone: "empathetic, concise"
  formatting:
    include_status_card: true

safety:                      # optional but strongly recommended
  red_flags:
    - id: "self_harm"
      patterns: ["suicide", "kill myself", "self harm"]
  policies:
    crisis:
      do: ["Encourage immediate support."]
      dont: ["Do not provide harmful instructions."]
      resources: ["US/Canada: 988 Suicide & Crisis Lifeline."]
```

Important policy syntax note:
- Rules must use `when` + `then`.
- Older shorthand rule shapes (without `when`/`then`) are ignored by this runtime.

### What must be in `tutorial.yaml`

For this repo's default UI-overlay onboarding:

```yaml
enabled: true
start_when:
  - ui_overlay
steps:
  - id: "runtime-panel"      # should match a UI `data-tutorial-id`
    title: "..."
    body_md: "..."
    cta: "Next"
```

Supported step fields:
- `id` (string)
- `title` (string)
- `body_md` (markdown text)
- `cta` (button label)

Optional chat-trigger mode is also supported by backend parser:
- `first_turn`
- `user_says` list of phrases

### What must be in `users.yaml`

```yaml
users:
  - id: demo_user
    password: demo-pass-123
    display_name: Demo User
    profile:
      role: "tester"
```

Rules:
- `id` and `password` are required for each bootstrap user.
- `display_name` and `profile` are optional.
- `id` is normalized to lowercase alphanumerics plus `_`, `-`, `.`.
- Duplicate normalized ids are invalid.
- File can be either:
  - a mapping with top-level `users: [...]` (recommended), or
  - a raw list of user objects.

### Mapping zip files into the app config folder

After cloning a new app, copy/rename files to:
- `configs/examples/<config-id>/domain.yaml`
- `configs/examples/<config-id>/tutorial.yaml`
- `configs/examples/<config-id>/users.yaml` (if provided)
- `configs/examples/<config-id>/references.md` (optional)

Prompt template:

```text
Build a new app in this repo using the same architecture as the existing app.
The domain pack zip is <ZIP_FILE>.
Use the existing skills and cloning flow (do not rebuild from scratch).
Create it in a new folder, adapt domain/tutorial/users as needed, and verify it runs in Docker.
Keep the current default app unchanged unless I ask otherwise.
```

## Smoke Checks

### In-container stream smoke test (default haiku app)

```bash
docker compose run --rm --build app python - <<'PY'
import json
from fastapi.testclient import TestClient
from haiku_example.server import app

with TestClient(app) as client:
    r = client.get("/meta")
    print("META", r.status_code, r.json().get("model"))
    with client.stream("POST", "/chat/stream", json={
        "thread_id": "smoke",
        "message": "Please critique this haiku: Winter moon glows / tiny birds softly singing / snow drifts in silence",
    }) as s:
        print("STREAM", s.status_code)
        for line in s.iter_lines():
            if line and line.startswith("data: "):
                payload = line[6:]
                print(payload[:180])
                if payload == "[DONE]":
                    break
PY
```

### Unit tests

```bash
pytest -q
```

## Endpoints

- `GET /` redirects to `/ui/`
- `GET /ui/` browser test harness
- `GET /meta` runtime metadata
- `GET /tutorial` tutorial overlay steps
- `GET /users/bootstrap` bootstrap user list
- `POST /session/start` bootstrap start/resume
- `POST /auth/register` register + start session
- `POST /auth/login` login + start/resume
- `GET /auth/guest` start/resume guest session
- `POST /auth/guest` start/resume guest session
- `POST /chat` non-stream response
- `POST /chat/stream` SSE stream
- `GET /threads/{thread_id}/status` persisted status

Reasoning event types from `/chat/stream`:
- `reasoning_generated_live`
- `reasoning_generated`
- `reasoning_deterministic`
- `reasoning_status`

## Repo Notes

- Core reference implementation: `haiku_example/`
- UI skill asset: `.agents/skills/add-fastapi-chat-ui/assets/simple-chat-ui/index.html`
- LangGraph scaffold skill: `.agents/skills/langgraph-conversational-labour/SKILL.md`
