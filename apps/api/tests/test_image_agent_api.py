from pathlib import Path

PROJECT = {
    "schemaVersion": "1.0.0",
    "projectId": "project-image-agent",
    "inputLanguage": "zh",
    "outputLanguage": "en",
    "deckType": "course_presentation",
    "topic": "CRISPR",
    "audience": "Undergraduates",
    "mode": "professional",
}


def create_slide_deck(client) -> dict:
    assert client.post("/api/projects", json=PROJECT).status_code == 201
    outline = client.post("/api/projects/project-image-agent/outline/generate", json={})
    assert outline.status_code == 200
    confirmed_outline = client.post(
        "/api/projects/project-image-agent/outline/confirm",
        json={"outlineDecisionVersion": outline.json()["version"]},
    )
    assert confirmed_outline.status_code == 200
    visual = client.post(
        "/api/projects/project-image-agent/visual-directions/generate",
        json={"outlineDecisionVersion": confirmed_outline.json()["version"]},
    )
    assert visual.status_code == 200
    direction_id = visual.json()["visualDirection"]["directions"][0]["directionId"]
    selected = client.post(
        "/api/projects/project-image-agent/visual-directions/select",
        json={"visualDirectionVersion": visual.json()["version"], "directionId": direction_id},
    )
    assert selected.status_code == 200
    deck = client.post(
        "/api/projects/project-image-agent/slide-deck/assemble",
        json={"visualDirectionVersion": selected.json()["version"]},
    )
    assert deck.status_code == 200
    return deck.json()


def test_image_agent_resolves_assets_and_serves_one_click_generated_images(client) -> None:
    deck = create_slide_deck(client)

    response = client.post(
        "/api/projects/project-image-agent/image-agent/resolve",
        json={"slideDeckVersion": deck["version"], "mode": "generate"},
    )

    assert response.status_code == 200
    payload = response.json()
    assets = payload["imageAssets"]
    assert payload["mode"] == "generate"
    assert len(assets) == len(deck["slideDeck"]["slides"])
    assert all(asset["sourceType"] == "ai_fallback" for asset in assets)
    assert all(asset["assetUrl"].startswith("/api/projects/project-image-agent/image-agent/assets/") for asset in assets)
    assert all(asset["query"] for asset in assets)
    assert all(asset["purpose"] for asset in assets)

    image = client.get(assets[0]["assetUrl"])

    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/png")
    assert image.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_render_reuses_image_agent_resolved_assets_when_provider_is_unavailable(client) -> None:
    deck = create_slide_deck(client)
    resolved = client.post(
        "/api/projects/project-image-agent/image-agent/resolve",
        json={"slideDeckVersion": deck["version"], "mode": "generate"},
    )
    assert resolved.status_code == 200
    assert all(asset["sourceType"] == "ai_fallback" for asset in resolved.json()["imageAssets"])

    client.app.state.image_gateway = None
    rendered = client.post(
        "/api/projects/project-image-agent/render",
        json={"slideDeckVersion": deck["version"], "imageResolutionMode": "auto"},
    )

    assert rendered.status_code == 200
    html_path = Path(rendered.json()["renderResult"]["artifacts"][1]["path"])
    html = html_path.read_text(encoding="utf-8")
    assert html.count('data-source-type="ai_fallback"') == len(deck["slideDeck"]["slides"])
    assert 'data-source-type="local_svg_fallback"' not in html


def test_image_agent_requires_current_confirmed_slide_deck(client) -> None:
    assert client.post("/api/projects", json=PROJECT).status_code == 201

    missing = client.post(
        "/api/projects/project-image-agent/image-agent/resolve",
        json={"slideDeckVersion": 1},
    )

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "slide_deck_not_found"
