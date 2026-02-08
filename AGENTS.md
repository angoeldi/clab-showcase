# AGENTS

## Repo Defaults

- Default app module: `haiku_example.server:app`
- Default domain: `configs/examples/haiku_tutor/domain.yaml`
- Default tutorial: `configs/examples/haiku_tutor/tutorial.yaml`
- Default bootstrap users: `configs/examples/haiku_tutor/users.yaml`
- Default UI auth mode on load: guest session (`POST /auth/guest`)
- Default docker model: `gpt-5-nano`

## Fast Path For New Apps

When the request is "same app architecture, new domain", do not respec from scratch.
Clone the working reference app and adapt:

```bash
python scripts/create_app_from_example.py <app-id>
```

Then run with:

```bash
export CLAB_APP_MODULE=<app_package>.server:app
export CLAB_DOMAIN_PATH=configs/examples/<config-id>/domain.yaml
export CLAB_TUTORIAL_PATH=configs/examples/<config-id>/tutorial.yaml
export CLAB_USERS_PATH=configs/examples/<config-id>/users.yaml
docker compose up --build -d
```

Use `--force` on the clone script only when explicitly replacing an existing target package/config.

## Docker Testing In This Environment

Use this flow first to avoid dead time:

1. Run Docker commands from repo root:
`/home/gold/projects/clab`

2. Prefer in-container tests over host curl:
- Host `curl http://localhost:8000/...` can fail in this sandbox even when app logs look healthy.
- Use `docker compose run --rm app ...` with Python `TestClient` or in-container HTTP calls.

3. Canonical smoke test command (stream + event types):

```bash
docker compose run --rm --build app python - <<'PY'
import json
from fastapi.testclient import TestClient
from haiku_example.server import app

thread_id = "smoke-stream"
with TestClient(app) as client:
    print("META", client.get("/meta").status_code, client.get("/meta").json().get("model"))
    with client.stream("POST", "/chat/stream", json={
        "thread_id": thread_id,
        "message": "Please critique this haiku draft: Winter moonlight glows / tiny birds softly sing / snow falls quietly",
    }) as resp:
        print("STREAM_STATUS", resp.status_code)
        types = []
        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                types.append("[DONE]")
                break
            data = json.loads(payload)
            types.append(data.get("type"))
        print("EVENT_TYPES", types)
PY
```

Typical graph-stream event types:
- `reasoning_generated_live`
- `reasoning_generated`
- `reasoning_deterministic` (when rule-based logic is used)
- `reasoning_status`
- `assistant`
- `status`
- `[DONE]`

Bootstrap user/session smoke check:

```bash
docker compose run --rm app python - <<'PY'
import base64
from fastapi.testclient import TestClient
from haiku_example.server import app

auth = base64.b64encode(b"demo_haiku_student:demo-haiku-123").decode("ascii")
headers = {"Authorization": f"Basic {auth}"}
with TestClient(app) as client:
    users = client.get("/users/bootstrap")
    print("USERS", users.status_code, [u["user_id"] for u in users.json().get("users", [])])
    s1 = client.post("/session/start", headers=headers, json={})
    s2 = client.post("/session/start", headers=headers, json={})
    print("START1", s1.status_code, s1.json().get("thread_id"), s1.json().get("resumed"))
    print("START2", s2.status_code, s2.json().get("thread_id"), s2.json().get("resumed"))
PY
```

Registration/login/guest smoke check:

```bash
docker compose run --rm app python - <<'PY'
from fastapi.testclient import TestClient
from haiku_example.server import app

with TestClient(app) as client:
    reg = client.post("/auth/register", json={"user_id":"new_writer","password":"writer-pass-123","display_name":"New Writer","new_thread":True})
    print("REGISTER", reg.status_code, reg.json().get("auth_mode"), reg.json().get("thread_id"))
    login = client.post("/auth/login", json={"user_id":"new_writer","password":"writer-pass-123"})
    print("LOGIN", login.status_code, login.json().get("auth_mode"), login.json().get("resumed"))
    guest = client.post("/auth/guest?code=from_get", json={"guest_code":"from_post","new_thread":True})
    print("GUEST", guest.status_code, guest.json().get("user_id"))
PY
```

4. For manual UI checks:
- `docker compose up --build -d`
- `docker compose ps`
- `docker compose logs --tail=200 app`

If Docker socket access is blocked by sandbox, rerun Docker commands with escalated permissions.

## Skills In This Repo

- LangGraph scaffold skill:
  `.agents/skills/langgraph-conversational-labour/SKILL.md`
- UI implementation skill:
  `.agents/skills/add-fastapi-chat-ui/SKILL.md`

When making behavior/layout changes in the app, sync corresponding guidance/assets in these skills.
