import zipfile
from pathlib import Path


PROJECT = {
    "schemaVersion": "1.0.0",
    "projectId": "project-render",
    "inputLanguage": "zh",
    "outputLanguage": "en",
    "deckType": "course_presentation",
    "topic": "CRISPR",
    "audience": "Undergraduates",
    "mode": "professional",
}


def create_renderable_deck(client) -> dict:
    assert client.post("/api/projects", json=PROJECT).status_code == 201
    outline = client.post("/api/projects/project-render/outline/generate", json={})
    assert outline.status_code == 200
    outline_confirmed = client.post(
        "/api/projects/project-render/outline/confirm",
        json={"outlineDecisionVersion": outline.json()["version"]},
    )
    assert outline_confirmed.status_code == 200
    visual = client.post(
        "/api/projects/project-render/visual-directions/generate",
        json={"outlineDecisionVersion": outline_confirmed.json()["version"]},
    )
    assert visual.status_code == 200
    selected = client.post(
        "/api/projects/project-render/visual-directions/select",
        json={"visualDirectionVersion": visual.json()["version"], "directionId": "airbnb"},
    )
    assert selected.status_code == 200
    deck = client.post(
        "/api/projects/project-render/slide-deck/assemble",
        json={"visualDirectionVersion": selected.json()["version"]},
    )
    assert deck.status_code == 200
    return deck.json()


def test_render_creates_pptx_and_hyperframes_from_same_slide_deck(client) -> None:
    deck = create_renderable_deck(client)

    response = client.post(
        "/api/projects/project-render/render",
        json={"slideDeckVersion": deck["version"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["stage"] == "render"
    assert payload["status"] == "complete"
    assert payload["nextStep"] == "export"
    result = payload["renderResult"]
    artifacts = result["artifacts"]
    assert [artifact["target"] for artifact in artifacts] == ["pptx", "hyperframes_html"]
    assert {artifact["slideCount"] for artifact in artifacts} == {
        len(deck["slideDeck"]["slides"])
    }

    pptx_path = Path(artifacts[0]["path"])
    html_path = Path(artifacts[1]["path"])
    assert pptx_path.is_file()
    assert html_path.is_file()
    assert "project-render" in html_path.read_text(encoding="utf-8") or "CRISPR" in html_path.read_text(encoding="utf-8")
    with zipfile.ZipFile(pptx_path) as archive:
        names = set(archive.namelist())
    assert "ppt/presentation.xml" in names
    assert "ppt/slides/slide1.xml" in names


def test_render_requires_confirmed_slide_deck_and_fresh_version(client) -> None:
    missing_project = client.post(
        "/api/projects/missing/render",
        json={"slideDeckVersion": 1},
    )
    assert missing_project.status_code == 404
    assert missing_project.json()["error"]["code"] == "project_not_found"

    assert client.post("/api/projects", json=PROJECT).status_code == 201
    missing_deck = client.post(
        "/api/projects/project-render/render",
        json={"slideDeckVersion": 1},
    )
    assert missing_deck.status_code == 404
    assert missing_deck.json()["error"]["code"] == "slide_deck_not_found"


def test_render_rejects_stale_slide_deck_version(client) -> None:
    deck = create_renderable_deck(client)

    stale = client.post(
        "/api/projects/project-render/render",
        json={"slideDeckVersion": deck["version"] + 1},
    )

    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "checkpoint_version_conflict"

