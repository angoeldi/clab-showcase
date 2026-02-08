import base64

import pytest
from fastapi.testclient import TestClient

from haiku_example.server import app


def _basic_auth_header(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAB_CHECKPOINTER", "memory")
    monkeypatch.setenv("CLAB_USERS_PATH", "configs/examples/haiku_tutor/users.yaml")
    monkeypatch.setenv("CLAB_USERS_STATE_PATH", str(tmp_path / "user_sessions.json"))
    monkeypatch.setenv("CLAB_REGISTERED_USERS_STATE_PATH", str(tmp_path / "registered_users.json"))
    monkeypatch.setenv("CLAB_BASIC_AUTH_ENABLED", "true")
    with TestClient(app) as test_client:
        yield test_client


def test_bootstrap_users_endpoint_lists_seeded_profiles(client: TestClient):
    r = client.get("/users/bootstrap")
    assert r.status_code == 200
    data = r.json()
    assert data["auth_required"] is True
    users = data["users"]
    ids = {u["user_id"] for u in users}
    assert "demo_haiku_student" in ids
    assert "returning_poet" in ids


def test_session_start_requires_basic_auth(client: TestClient):
    r = client.post("/session/start", json={"user_id": "demo_haiku_student"})
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers


def test_session_start_resumes_same_thread_for_returning_user(client: TestClient):
    headers = _basic_auth_header("demo_haiku_student", "demo-haiku-123")

    r1 = client.post("/session/start", json={}, headers=headers)
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["resumed"] is False
    thread_1 = d1["thread_id"]

    r2 = client.post("/session/start", json={}, headers=headers)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["resumed"] is True
    assert d2["thread_id"] == thread_1


def test_session_start_new_thread_overrides_resume(client: TestClient):
    headers = _basic_auth_header("returning_poet", "demo-poet-123")

    r1 = client.post("/session/start", json={}, headers=headers)
    assert r1.status_code == 200
    t1 = r1.json()["thread_id"]

    r2 = client.post("/session/start", json={"new_thread": True}, headers=headers)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["resumed"] is False
    assert d2["thread_id"] != t1


def test_register_and_login_flow(client: TestClient):
    reg = client.post(
        "/auth/register",
        json={
            "user_id": "new_writer",
            "password": "writer-pass-123",
            "display_name": "New Writer",
            "new_thread": True,
        },
    )
    assert reg.status_code == 200
    reg_data = reg.json()
    assert reg_data["auth_mode"] == "registered"
    assert reg_data["user_id"] == "new_writer"
    assert reg_data["thread_id"]

    login = client.post(
        "/auth/login",
        json={
            "user_id": "new_writer",
            "password": "writer-pass-123",
        },
    )
    assert login.status_code == 200
    login_data = login.json()
    assert login_data["auth_mode"] == "registered"
    assert login_data["thread_id"] == reg_data["thread_id"]
    assert login_data["resumed"] is True


def test_auth_login_accepts_bootstrap_credentials(client: TestClient):
    login = client.post(
        "/auth/login",
        json={
            "user_id": "demo_haiku_student",
            "password": "demo-haiku-123",
        },
    )
    assert login.status_code == 200
    data = login.json()
    assert data["auth_mode"] == "bootstrap"
    assert data["thread_id"]


def test_guest_post_precedence_over_get_code(client: TestClient):
    r = client.post("/auth/guest?code=from_get", json={"guest_code": "from_post", "new_thread": True})
    assert r.status_code == 200
    data = r.json()
    assert data["auth_mode"] == "guest"
    assert data["user_id"].startswith("guest_from_post")


def test_guest_default_generates_uuid_code(client: TestClient):
    r = client.post("/auth/guest", json={})
    assert r.status_code == 200
    data = r.json()
    assert data["auth_mode"] == "guest"
    assert data["user_id"].startswith("guest_")
    assert len(data["user_id"]) > len("guest_")
