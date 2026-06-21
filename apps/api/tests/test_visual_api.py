PROJECT = {
    "schemaVersion": "1.0.0",
    "projectId": "project-visual",
    "inputLanguage": "zh",
    "outputLanguage": "en",
    "deckType": "course_presentation",
    "topic": "CRISPR",
    "audience": "Undergraduates",
    "mode": "professional",
}


def create_project(client) -> None:
    assert client.post("/api/projects", json=PROJECT).status_code == 201


def generate_outline(client) -> dict:
    created = client.post("/api/projects/project-visual/outline/generate", json={})
    assert created.status_code == 200
    version = created.json()["version"]
    confirmed = client.post(
        "/api/projects/project-visual/outline/confirm",
        json={"outlineDecisionVersion": version},
    )
    assert confirmed.status_code == 200
    return confirmed.json()


def generate_visual(client, outline_version: int):
    return client.post(
        "/api/projects/project-visual/visual-directions/generate",
        json={"outlineDecisionVersion": outline_version},
    )


def test_generate_visual_directions_requires_confirmed_outline(client) -> None:
    create_project(client)

    missing = generate_visual(client, 1)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "outline_not_found"

    draft = client.post("/api/projects/project-visual/outline/generate", json={})
    assert draft.status_code == 200
    rejected = generate_visual(client, draft.json()["version"])
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "outline_not_confirmed"


def test_generate_and_select_visual_direction(client) -> None:
    create_project(client)
    outline = generate_outline(client)

    generated = generate_visual(client, outline["version"])

    assert generated.status_code == 200
    payload = generated.json()
    assert payload["stage"] == "visual_direction"
    assert payload["status"] == "draft"
    assert payload["version"] == 1
    assert payload["nextStep"] == "visual_direction_selection"
    visual = payload["visualDirection"]
    assert visual["projectId"] == "project-visual"
    assert visual["outlineVersion"] == outline["version"]
    assert [item["directionId"] for item in visual["directions"]] == [
        "apple",
        "mckinsey",
        "airbnb",
    ]
    assert visual["selectedDirectionId"] is None

    selected = client.post(
        "/api/projects/project-visual/visual-directions/select",
        json={"visualDirectionVersion": 1, "directionId": "mckinsey"},
    )

    assert selected.status_code == 200
    assert selected.json()["version"] == 2
    assert selected.json()["status"] == "confirmed"
    assert selected.json()["nextStep"] == "slide_deck"
    assert selected.json()["visualDirection"]["selectedDirectionId"] == "mckinsey"


def test_visual_direction_version_conflicts_are_safe(client) -> None:
    create_project(client)
    outline = generate_outline(client)

    stale_generate = generate_visual(client, outline["version"] - 1)
    assert stale_generate.status_code == 409
    assert stale_generate.json()["error"]["code"] == "checkpoint_version_conflict"

    generated = generate_visual(client, outline["version"])
    assert generated.status_code == 200

    stale_select = client.post(
        "/api/projects/project-visual/visual-directions/select",
        json={"visualDirectionVersion": 99, "directionId": "apple"},
    )
    assert stale_select.status_code == 409
    assert stale_select.json()["error"]["code"] == "checkpoint_version_conflict"


def test_select_visual_direction_validates_missing_and_direction_id(client) -> None:
    missing_project = client.post(
        "/api/projects/missing/visual-directions/select",
        json={"visualDirectionVersion": 1, "directionId": "apple"},
    )
    assert missing_project.status_code == 404
    assert missing_project.json()["error"]["code"] == "project_not_found"

    create_project(client)
    missing_visual = client.post(
        "/api/projects/project-visual/visual-directions/select",
        json={"visualDirectionVersion": 1, "directionId": "apple"},
    )
    assert missing_visual.status_code == 404
    assert missing_visual.json()["error"]["code"] == "visual_direction_not_found"

    invalid_direction = client.post(
        "/api/projects/project-visual/visual-directions/select",
        json={"visualDirectionVersion": 1, "directionId": "unknown"},
    )
    assert invalid_direction.status_code == 422

