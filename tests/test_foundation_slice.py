from uuid import uuid4

from fastapi.testclient import TestClient

from app.ai.fakes import FakeImageGateway, FakeTextGateway
from app.ai.models import ImageRequest, TextRequest
from app.ai.png_validator import validate_png_bytes


def test_offline_foundation_slice(client: TestClient) -> None:
    project_id = f"foundation-{uuid4()}"
    brief = {
        "schemaVersion": "1.0.0",
        "projectId": project_id,
        "inputLanguage": "zh",
        "outputLanguage": "en",
        "deckType": "course_presentation",
        "topic": "Local-first presentation workflow",
        "audience": "Undergraduates",
        "mode": "professional",
    }

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "service": "ai-ppt-api",
        "version": "0.1.0",
    }

    created = client.post("/api/projects", json=brief)
    assert created.status_code == 201
    assert created.json() == {"projectId": project_id, "brief": brief}

    checkpoint_payload = {"schemaVersion": "1.0.0", "brief": brief}
    checkpoint = client.put(
        f"/api/projects/{project_id}/checkpoints/brief",
        json={
            "expectedVersion": 0,
            "status": "confirmed",
            "payload": checkpoint_payload,
        },
    )
    assert checkpoint.status_code == 200
    assert checkpoint.json()["version"] == 1

    latest = client.get(f"/api/projects/{project_id}/checkpoints/latest")
    assert latest.status_code == 200
    assert latest.json()["projectId"] == project_id
    assert latest.json()["stage"] == "brief"
    assert latest.json()["version"] == 1
    assert latest.json()["payload"] == checkpoint_payload

    skills = client.get("/api/skills")
    assert skills.status_code == 200
    assert [item["name"] for item in skills.json()["skills"]] == [
        "Frontend-Slides",
        "HumanizePPT",
    ]
    assert len(skills.json()["skills"]) == 2

    text = FakeTextGateway().generate(
        TextRequest(
            model="gpt-5.4-mini",
            prompt=f"Summarize {project_id}",
            response_schema={
                "type": "object",
                "required": ["schemaVersion"],
                "properties": {"schemaVersion": {"const": "1.0.0"}},
            },
        )
    )
    assert text.data["schemaVersion"] == "1.0.0"

    image_request = ImageRequest(
        model="gpt-image-2",
        prompt=f"Create a local test image for {project_id}",
        width=4,
        height=3,
    )
    image = FakeImageGateway().generate(image_request)
    assert image.model == "gpt-image-2"
    validate_png_bytes(
        image.bytes,
        expected_width=image_request.width,
        expected_height=image_request.height,
    )
