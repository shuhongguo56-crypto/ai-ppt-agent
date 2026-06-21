from pathlib import Path


PROJECT = {
    "schemaVersion": "1.0.0",
    "projectId": "project-quality",
    "inputLanguage": "zh",
    "outputLanguage": "en",
    "deckType": "course_presentation",
    "topic": "CRISPR",
    "audience": "Undergraduates",
    "mode": "professional",
}


def render_project(client) -> dict:
    assert client.post("/api/projects", json=PROJECT).status_code == 201
    outline = client.post("/api/projects/project-quality/outline/generate", json={})
    confirmed_outline = client.post(
        "/api/projects/project-quality/outline/confirm",
        json={"outlineDecisionVersion": outline.json()["version"]},
    )
    visual = client.post(
        "/api/projects/project-quality/visual-directions/generate",
        json={"outlineDecisionVersion": confirmed_outline.json()["version"]},
    )
    selected = client.post(
        "/api/projects/project-quality/visual-directions/select",
        json={"visualDirectionVersion": visual.json()["version"], "directionId": "apple"},
    )
    deck = client.post(
        "/api/projects/project-quality/slide-deck/assemble",
        json={"visualDirectionVersion": selected.json()["version"]},
    )
    rendered = client.post(
        "/api/projects/project-quality/render",
        json={"slideDeckVersion": deck.json()["version"]},
    )
    assert rendered.status_code == 200
    return rendered.json()


def test_quality_check_passes_for_rendered_artifacts(client) -> None:
    rendered = render_project(client)

    response = client.post(
        "/api/projects/project-quality/quality/check",
        json={"renderVersion": rendered["version"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["stage"] == "quality"
    assert payload["status"] == "complete"
    assert payload["nextStep"] == "export"
    report = payload["qualityReport"]
    assert report["passed"] is True
    assert {check["name"] for check in report["checks"]} >= {
        "pptx_exists",
        "hyperframes_html_exists",
        "pptx_slide_count",
        "html_frame_count",
    }


def test_quality_check_reports_failed_artifact_safely(client, tmp_path) -> None:
    rendered = render_project(client)
    payload = rendered["renderResult"]
    payload["artifacts"][0]["path"] = str(Path(tmp_path) / "missing.pptx")
    update = client.put(
        "/api/projects/project-quality/checkpoints/render",
        json={"expectedVersion": rendered["version"], "status": "complete", "payload": payload},
    )
    assert update.status_code == 200

    response = client.post(
        "/api/projects/project-quality/quality/check",
        json={"renderVersion": rendered["version"] + 1},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["nextStep"] == "manual_review"


def test_quality_requires_render_and_fresh_version(client) -> None:
    missing_project = client.post("/api/projects/missing/quality/check", json={"renderVersion": 1})
    assert missing_project.status_code == 404
    assert missing_project.json()["error"]["code"] == "project_not_found"

    rendered = render_project(client)
    stale = client.post(
        "/api/projects/project-quality/quality/check",
        json={"renderVersion": rendered["version"] + 1},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "checkpoint_version_conflict"