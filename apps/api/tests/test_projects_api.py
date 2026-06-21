from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


PROJECT = {
    "schemaVersion": "1.0.0",
    "projectId": "project-1",
    "inputLanguage": "zh",
    "outputLanguage": "en",
    "deckType": "course_presentation",
    "topic": "CRISPR",
    "audience": "Undergraduates",
    "mode": "professional",
}


def create_project(client):
    return client.post("/api/projects", json=PROJECT)


def test_create_read_duplicate_and_missing_project(client) -> None:
    created = create_project(client)
    assert created.status_code == 201
    assert client.get("/api/projects/project-1").json()["brief"] == PROJECT

    duplicate = create_project(client)
    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "error": {"code": "project_already_exists", "message": "Project already exists."}
    }
    missing = client.get("/api/projects/missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "project_not_found"


def test_checkpoint_write_latest_stale_and_missing(client) -> None:
    create_project(client)
    body = {
        "expectedVersion": 0,
        "status": "draft",
        "payload": {"schemaVersion": "1.0.0", "custom": {"allowed": True}},
    }
    first = client.put("/api/projects/project-1/checkpoints/brief", json=body)
    assert first.status_code == 200
    assert first.json()["version"] == 1
    assert first.json()["payload"]["custom"]["allowed"] is True

    latest = client.get("/api/projects/project-1/checkpoints/latest")
    assert latest.status_code == 200
    assert latest.json()["stage"] == "brief"

    stale = client.put("/api/projects/project-1/checkpoints/brief", json=body)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "checkpoint_version_conflict"
    assert "database" not in stale.text.lower()

    missing_checkpoint = client.get("/api/projects/project-1/checkpoints/latest")
    assert missing_checkpoint.status_code == 200
    missing_project = client.put("/api/projects/missing/checkpoints/brief", json=body)
    assert missing_project.status_code == 404
    assert missing_project.json()["error"]["code"] == "project_not_found"


def test_latest_checkpoint_missing_is_safe(client) -> None:
    create_project(client)
    response = client.get("/api/projects/project-1/checkpoints/latest")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "checkpoint_not_found"


def test_checkpoint_request_validation(client) -> None:
    create_project(client)
    valid = {
        "expectedVersion": 0,
        "status": "draft",
        "payload": {"schemaVersion": "1.0.0"},
    }
    cases = [
        ("unknown", valid),
        ("brief", {**valid, "status": "unknown"}),
        ("brief", {**valid, "expectedVersion": -1}),
        ("brief", {**valid, "payload": []}),
        ("brief", {**valid, "payload": {"schemaVersion": "2.0.0"}}),
        ("brief", {**valid, "payload": {}}),
    ]
    for stage, body in cases:
        assert client.put(f"/api/projects/project-1/checkpoints/{stage}", json=body).status_code == 422


def test_persistence_survives_app_restart(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "restart.db", asset_path=tmp_path / "assets")
    with TestClient(create_app(settings)) as first:
        assert create_project(first).status_code == 201
        assert first.put(
            "/api/projects/project-1/checkpoints/brief",
            json={
                "expectedVersion": 0,
                "status": "draft",
                "payload": {"schemaVersion": "1.0.0"},
            },
        ).status_code == 200

    with TestClient(create_app(settings)) as second:
        assert second.get("/api/projects/project-1").status_code == 200
        assert second.get("/api/projects/project-1/checkpoints/latest").json()["version"] == 1


def test_database_is_opened_and_closed_by_application_lifespan(tmp_path) -> None:
    database_path = tmp_path / "lifecycle.db"
    app = create_app(Settings(database_path=database_path, asset_path=tmp_path / "assets"))
    assert not database_path.exists()
    with TestClient(app):
        assert database_path.exists()
    assert app.state.repository._connection is None
