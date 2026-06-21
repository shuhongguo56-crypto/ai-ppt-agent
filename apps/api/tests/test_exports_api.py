from pathlib import Path


PROJECT = {
    "schemaVersion": "1.0.0",
    "projectId": "project-export",
    "inputLanguage": "zh",
    "outputLanguage": "en",
    "deckType": "course_presentation",
    "topic": "CRISPR",
    "audience": "Undergraduates",
    "mode": "professional",
}


def render_project(client) -> dict:
    assert client.post("/api/projects", json=PROJECT).status_code == 201
    outline = client.post("/api/projects/project-export/outline/generate", json={})
    assert outline.status_code == 200
    confirmed_outline = client.post(
        "/api/projects/project-export/outline/confirm",
        json={"outlineDecisionVersion": outline.json()["version"]},
    )
    assert confirmed_outline.status_code == 200
    visual = client.post(
        "/api/projects/project-export/visual-directions/generate",
        json={"outlineDecisionVersion": confirmed_outline.json()["version"]},
    )
    assert visual.status_code == 200
    selected = client.post(
        "/api/projects/project-export/visual-directions/select",
        json={"visualDirectionVersion": visual.json()["version"], "directionId": "apple"},
    )
    assert selected.status_code == 200
    deck = client.post(
        "/api/projects/project-export/slide-deck/assemble",
        json={"visualDirectionVersion": selected.json()["version"]},
    )
    assert deck.status_code == 200
    rendered = client.post(
        "/api/projects/project-export/render",
        json={"slideDeckVersion": deck.json()["version"]},
    )
    assert rendered.status_code == 200
    quality = client.post(
        "/api/projects/project-export/quality/check",
        json={"renderVersion": rendered.json()["version"]},
    )
    assert quality.status_code == 200
    return rendered.json()


def test_list_and_download_exports(client) -> None:
    rendered = render_project(client)

    listed = client.get("/api/projects/project-export/exports")

    assert listed.status_code == 200
    exports = listed.json()["exports"]
    assert [item["target"] for item in exports] == ["pptx", "hyperframes_html"]
    assert exports[0]["downloadUrl"] == "/api/projects/project-export/exports/pptx"
    assert exports[1]["downloadUrl"] == "/api/projects/project-export/exports/hyperframes_html"

    pptx = client.get(exports[0]["downloadUrl"])
    html = client.get(exports[1]["downloadUrl"])

    assert pptx.status_code == 200
    assert pptx.content.startswith(b"PK")
    assert "presentation" in pptx.headers["content-type"]
    assert html.status_code == 200
    assert b"<!doctype html>" in html.content
    assert rendered["renderResult"]["projectId"] == "project-export"


def test_exports_require_completed_render(client) -> None:
    missing_project = client.get("/api/projects/missing/exports")
    assert missing_project.status_code == 404
    assert missing_project.json()["error"]["code"] == "project_not_found"

    assert client.post("/api/projects", json=PROJECT).status_code == 201
    missing_render = client.get("/api/projects/project-export/exports")
    assert missing_render.status_code == 404
    assert missing_render.json()["error"]["code"] == "render_not_found"


def test_exports_require_quality_check(client) -> None:
    assert client.post("/api/projects", json=PROJECT).status_code == 201
    outline = client.post("/api/projects/project-export/outline/generate", json={})
    confirmed_outline = client.post(
        "/api/projects/project-export/outline/confirm",
        json={"outlineDecisionVersion": outline.json()["version"]},
    )
    visual = client.post(
        "/api/projects/project-export/visual-directions/generate",
        json={"outlineDecisionVersion": confirmed_outline.json()["version"]},
    )
    selected = client.post(
        "/api/projects/project-export/visual-directions/select",
        json={"visualDirectionVersion": visual.json()["version"], "directionId": "apple"},
    )
    deck = client.post(
        "/api/projects/project-export/slide-deck/assemble",
        json={"visualDirectionVersion": selected.json()["version"]},
    )
    rendered = client.post(
        "/api/projects/project-export/render",
        json={"slideDeckVersion": deck.json()["version"]},
    )
    assert rendered.status_code == 200

    blocked = client.get("/api/projects/project-export/exports")

    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "quality_not_passed"


def test_export_download_rejects_paths_outside_asset_root(client, tmp_path) -> None:
    rendered = render_project(client)
    payload = rendered["renderResult"]
    payload["artifacts"][0]["path"] = str(Path(tmp_path).parent / "outside.pptx")

    update = client.put(
        "/api/projects/project-export/checkpoints/render",
        json={
            "expectedVersion": rendered["version"],
            "status": "complete",
            "payload": payload,
        },
    )
    assert update.status_code == 200
    quality = client.put(
        "/api/projects/project-export/checkpoints/quality",
        json={
            "expectedVersion": 1,
            "status": "complete",
            "payload": {
                "schemaVersion": "1.0.0",
                "projectId": "project-export",
                "renderVersion": update.json()["version"],
                "passed": True,
                "checks": [
                    {
                        "schemaVersion": "1.0.0",
                        "name": "manual_test_quality",
                        "status": "passed",
                        "detail": "Manual quality checkpoint for export path validation.",
                    }
                ],
            },
        },
    )
    assert quality.status_code == 200

    response = client.get("/api/projects/project-export/exports/pptx")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "export_artifact_invalid"
    assert "outside" not in response.text

