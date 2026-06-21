from copy import deepcopy


PROJECT = {
    "schemaVersion": "1.0.0",
    "projectId": "project-outline",
    "inputLanguage": "zh",
    "outputLanguage": "en",
    "deckType": "course_presentation",
    "topic": "CRISPR",
    "audience": "Undergraduates",
    "mode": "professional",
}


def create_project(client, project: dict = PROJECT):
    return client.post("/api/projects", json=project)


def generate_outline(client, project_id: str = "project-outline", body: dict | None = None):
    return client.post(
        f"/api/projects/{project_id}/outline/generate",
        json={} if body is None else body,
    )


def test_generate_outline_creates_draft_checkpoint(client) -> None:
    assert create_project(client).status_code == 201

    response = generate_outline(client)

    assert response.status_code == 200
    payload = response.json()
    assert payload["stage"] == "outline"
    assert payload["status"] == "draft"
    assert payload["version"] == 1
    assert payload["nextStep"] == "outline_review"
    outline = payload["outlineDecision"]
    assert outline["schemaVersion"] == "1.0.0"
    assert outline["projectId"] == "project-outline"
    assert outline["language"] == "en"
    assert outline["targetSlideCount"] == len(outline["slides"])
    assert outline["slides"][0]["purpose"] == "cover"
    assert outline["slides"][-1]["purpose"] == "conclusion"
    assert outline["generatedBy"]["skillName"] == "HumanizePPT"


def test_one_click_generation_auto_confirms(client) -> None:
    project = PROJECT | {"projectId": "one-click", "mode": "one_click"}
    assert create_project(client, project).status_code == 201

    response = generate_outline(client, "one-click")

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    assert response.json()["nextStep"] == "visual_direction"


def test_generate_outline_accepts_source_pack_and_rejects_mismatch(client) -> None:
    assert create_project(client).status_code == 201
    source_pack = {
        "schemaVersion": "1.0.0",
        "projectId": "project-outline",
        "sources": [
            {
                "schemaVersion": "1.0.0",
                "sourceId": "source-1",
                "sourceType": "text",
                "summary": "A source summary",
            }
        ],
    }

    response = generate_outline(client, body={"sourcePack": source_pack})

    assert response.status_code == 200
    assert response.json()["outlineDecision"]["citationNeeds"] == ["source-1"]

    mismatch = deepcopy(source_pack)
    mismatch["projectId"] = "other"
    rejected = generate_outline(client, body={"sourcePack": mismatch})
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "source_pack_project_mismatch"


def test_patch_and_confirm_outline_flow(client) -> None:
    assert create_project(client).status_code == 201
    generated = generate_outline(client).json()
    outline = generated["outlineDecision"]
    outline["slides"][1]["title"] = "Edited evidence slide"

    patched = client.patch(
        "/api/projects/project-outline/outline",
        json={"expectedVersion": 1, "outlineDecision": outline},
    )

    assert patched.status_code == 200
    assert patched.json()["version"] == 2
    assert patched.json()["status"] == "draft"
    assert patched.json()["outlineDecision"]["slides"][1]["title"] == "Edited evidence slide"

    stale = client.post(
        "/api/projects/project-outline/outline/confirm",
        json={"outlineDecisionVersion": 1},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "checkpoint_version_conflict"

    confirmed = client.post(
        "/api/projects/project-outline/outline/confirm",
        json={"outlineDecisionVersion": 2},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["version"] == 3
    assert confirmed.json()["status"] == "confirmed"
    assert confirmed.json()["nextStep"] == "visual_direction"


def test_outline_routes_return_safe_missing_and_validation_errors(client) -> None:
    missing = generate_outline(client, "missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "project_not_found"

    assert create_project(client).status_code == 201
    missing_outline = client.post(
        "/api/projects/project-outline/outline/confirm",
        json={"outlineDecisionVersion": 1},
    )
    assert missing_outline.status_code == 404
    assert missing_outline.json()["error"]["code"] == "outline_not_found"

    generated = generate_outline(client).json()
    outline = generated["outlineDecision"]
    outline["projectId"] = "other"
    mismatch = client.patch(
        "/api/projects/project-outline/outline",
        json={"expectedVersion": 1, "outlineDecision": outline},
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "outline_project_mismatch"

