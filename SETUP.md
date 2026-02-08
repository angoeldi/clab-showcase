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

Prompt template:

```text
Build a new app in this repo using the same architecture as the existing app.
The domain pack zip is <ZIP_FILE>.
Use the existing skills and cloning flow (do not rebuild from scratch).
Create it in a new folder, adapt domain/tutorial/users as needed, and verify it runs in Docker.
Keep the current default app unchanged unless I ask otherwise.
```

MI example prompt:

```text
Build a new app in this repo using the same architecture as the existing app.
The domain pack zip is mi_social_media_addiction_domain_pack_2026-02-07_v2.zip.
Use the existing skills and cloning flow (do not rebuild from scratch).
Create it in a new folder, adapt domain/tutorial/users as needed, and verify it runs in Docker.
Keep the current default haiku app unchanged.
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
