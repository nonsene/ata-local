import pytest
from fastapi.testclient import TestClient
from ata_local import store
from ata_local.app import app, supervisor


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    monkeypatch.setattr(supervisor, "start", lambda: None)
    monkeypatch.setattr(supervisor, "close", lambda: None)
    with TestClient(app) as client:
        yield client


def test_ui_and_model_status_are_accessible_offline(client):
    assert client.get("/").status_code == 200
    state = client.get("/api/state").json()
    assert state["meetings"] == []
    assert len(state["models"]) == 5
    assert "frame-ancestors 'none'" in client.get("/").headers["content-security-policy"]


def test_no_drive_by_recording_without_token_or_from_other_origin(client):
    assert client.post("/api/record/pause", json={}).status_code == 403
    token = client.get("/api/state").json()["token"]
    assert client.post("/api/record/pause", json={}, headers={"x-ata-token": token, "origin": "https://evil.invalid"}).status_code == 403
    assert client.get("/", headers={"host": "evil.invalid:8765"}).status_code == 403
    assert client.post("/api/record/pause", json={}, headers={"x-ata-token": token}).status_code == 409


def test_queued_job_can_cancel_and_retry_without_losing_audio(client):
    job = store.create("Teste", {})
    (store.folder(job["id"]) / "capture.json").write_text('{}')
    store.update(job["id"], status="queued")
    headers = {"x-ata-token": client.get("/api/state").json()["token"]}
    url = f"/api/meetings/{job['id']}"
    assert client.post(url + "/cancel", json={}, headers=headers).json()["status"] == "cancelled"
    assert client.post(url + "/retry", json={}, headers=headers).json()["status"] == "queued"


def test_external_network_is_blocked():
    import socket
    with pytest.raises(OSError, match="conexão externa"):
        socket.getaddrinfo("huggingface.co", 443)
    with socket.socket() as connection:
        with pytest.raises(OSError, match="conexão externa"):
            connection.connect(("1.1.1.1", 443))
