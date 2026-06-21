PROJECT = {
    "schemaVersion": "1.0.0",
    "projectId": "project-deck",
    "inputLanguage": "zh",
    "outputLanguage": "en",
    "deckType": "course_presentation",
    "topic": "CRISPR",
    "audience": "Undergraduates",
    "mode": "professional",
}


def create_project(client) -> None:
    assert client.post("/api/projects", json=PROJECT).status_code == 201


def confirm_outline(client) -> dict:
    generated = client.post("/api/projects/project-deck/outline/generate", json={})
    assert generated.status_code == 200
    confirmed = client.post(
        "/api/projects/project-deck/outline/confirm",
        json={"outlineDecisionVersion": generated.json()["version"]},
    )
    assert confirmed.status_code == 200
    return confirmed.json()


def select_visual(client, outline_version: int) -> dict:
    generated = client.post(
        "/api/projects/project-deck/visual-directions/generate",
        json={"outlineDecisionVersion": outline_version},
    )
    assert generated.status_code == 200
    selected = client.post(
        "/api/projects/project-deck/visual-directions/select",
        json={"visualDirectionVersion": generated.json()["version"], "directionId": "apple"},
    )
    assert selected.status_code == 200
    return selected.json()


def assemble_deck(client, visual_version: int):
    return client.post(
        "/api/projects/project-deck/slide-deck/assemble",
        json={"visualDirectionVersion": visual_version},
    )


def test_assemble_slide_deck_from_confirmed_outline_and_visual_direction(client) -> None:
    create_project(client)
    outline = confirm_outline(client)
    visual = select_visual(client, outline["version"])

    response = assemble_deck(client, visual["version"])

    assert response.status_code == 200
    payload = response.json()
    assert payload["stage"] == "slide_deck"
    assert payload["status"] == "confirmed"
    assert payload["version"] == 1
    assert payload["nextStep"] == "render"
    deck = payload["slideDeck"]
    assert deck["projectId"] == "project-deck"
    assert deck["outlineVersion"] == outline["version"]
    assert deck["visualDirectionVersion"] == visual["version"]
    assert deck["theme"]["directionId"] == "apple"
    assert deck["exportTargets"] == ["pptx", "hyperframes_html"]
    assert len(deck["slides"]) == 8
    assert [slide["slideIndex"] for slide in deck["slides"]] == list(range(1, 9))
    assert deck["slides"][0]["blocks"][0]["blockType"] == "headline"


def test_slide_deck_requires_confirmed_dependencies(client) -> None:
    missing_project = assemble_deck(client, 1)
    assert missing_project.status_code == 404
    assert missing_project.json()["error"]["code"] == "project_not_found"

    create_project(client)
    no_outline = assemble_deck(client, 1)
    assert no_outline.status_code == 404
    assert no_outline.json()["error"]["code"] == "outline_not_found"

    draft_outline = client.post("/api/projects/project-deck/outline/generate", json={})
    assert draft_outline.status_code == 200
    rejected = assemble_deck(client, 1)
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "outline_not_confirmed"


def test_slide_deck_requires_selected_visual_direction_and_fresh_version(client) -> None:
    create_project(client)
    outline = confirm_outline(client)

    no_visual = assemble_deck(client, 1)
    assert no_visual.status_code == 404
    assert no_visual.json()["error"]["code"] == "visual_direction_not_found"

    visual_draft = client.post(
        "/api/projects/project-deck/visual-directions/generate",
        json={"outlineDecisionVersion": outline["version"]},
    )
    assert visual_draft.status_code == 200
    rejected = assemble_deck(client, visual_draft.json()["version"])
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "visual_direction_not_confirmed"

    visual = client.post(
        "/api/projects/project-deck/visual-directions/select",
        json={"visualDirectionVersion": visual_draft.json()["version"], "directionId": "mckinsey"},
    )
    assert visual.status_code == 200

    stale = assemble_deck(client, visual.json()["version"] - 1)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "checkpoint_version_conflict"
