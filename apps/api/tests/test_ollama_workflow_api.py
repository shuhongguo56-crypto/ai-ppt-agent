import json

import httpx
from fastapi.testclient import TestClient

from app.ai.fakes import FakeImageGateway
from app.config import Settings
from app.main import create_app


PROJECT = {
    "schemaVersion": "1.0.0",
    "projectId": "project-ollama",
    "inputLanguage": "zh",
    "outputLanguage": "en",
    "deckType": "course_presentation",
    "topic": "AI classroom presentation",
    "audience": "Students",
    "mode": "professional",
}


def test_ollama_backend_can_complete_generation_flow(tmp_path, monkeypatch) -> None:
    calls: list[dict] = []

    def fake_post(url: str, json: dict, timeout: float) -> httpx.Response:
        calls.append({"url": url, "schema": json["format"]})
        required = set(json["format"]["required"])
        if "objective" in required:
            return httpx.Response(
                200,
                json={
                    "response": json_module_dumps(
                        {
                            "objective": "Help students explain AI presentation quality with a clear classroom story.",
                            "narrative": [
                                "Start with the classroom problem.",
                                "Explain the AI workflow.",
                                "End with a practical checklist.",
                            ],
                            "slides": [
                                {
                                    "title": "AI improves classroom presentations",
                                    "keyPoint": "AI helps students structure and polish presentations.",
                                    "talkingPoints": [
                                        "Students need clearer storylines.",
                                        "AI can organize evidence and visuals.",
                                    ],
                                    "speakerNotesDraft": "Introduce the value of AI-assisted preparation.",
                                }
                            ],
                        }
                    ),
                    "prompt_eval_count": 20,
                    "eval_count": 12,
                },
            )
        if "recommendedDirectionIds" in required:
            return httpx.Response(
                200,
                json={
                    "response": json_module_dumps(
                        {
                            "recommendedDirectionIds": ["classroom_friendly", "data_story"],
                            "rationale": "The audience needs clarity, friendly pacing, and visible structure.",
                        }
                    ),
                    "prompt_eval_count": 13,
                    "eval_count": 8,
                },
            )
        raise AssertionError("Unexpected Ollama schema")

    monkeypatch.setattr("app.ai.ollama.httpx.post", fake_post)
    app = create_app(
        Settings(
            database_path=tmp_path / "ollama-flow.db",
            asset_path=tmp_path / "assets",
            model_backend="ollama",
            ollama_text_model="qwen2.5:7b",
            topic_research_enabled=False,
            expert_image_min_long_edge=1024,
            expert_image_min_short_edge=576,
            expert_key_image_min_long_edge=1024,
            expert_key_image_min_short_edge=576,
            shared_asset_library_path=tmp_path / "asset-library",
        )
    )
    app.state.image_gateway = FakeImageGateway()
    with TestClient(app) as client:
        assert client.post("/api/projects", json=PROJECT).status_code == 201
        outline = client.post("/api/projects/project-ollama/outline/generate", json={})
        assert outline.status_code == 200
        assert outline.json()["outlineDecision"]["generatedBy"]["model"] == "qwen2.5:7b"
        confirmed = client.post(
            "/api/projects/project-ollama/outline/confirm",
            json={"outlineDecisionVersion": outline.json()["version"]},
        )
        assert confirmed.status_code == 200
        visual = client.post(
            "/api/projects/project-ollama/visual-directions/generate",
            json={"outlineDecisionVersion": confirmed.json()["version"]},
        )
        assert visual.status_code == 200
        directions = visual.json()["visualDirection"]["directions"]
        assert 4 <= len(directions) <= 6
        assert len({direction["directionId"] for direction in directions}) == len(directions)
        assert [direction["directionId"] for direction in directions][:2] == [
            "classroom_friendly",
            "data_story",
        ]
        assert any("本地免费 AI 推荐理由" in note for note in directions[0]["riskNotes"])
        selected = client.post(
            "/api/projects/project-ollama/visual-directions/select",
            json={"visualDirectionVersion": visual.json()["version"], "directionId": "classroom_friendly"},
        )
        deck = client.post(
            "/api/projects/project-ollama/slide-deck/assemble",
            json={"visualDirectionVersion": selected.json()["version"]},
        )
        rendered = client.post(
            "/api/projects/project-ollama/render",
            json={"slideDeckVersion": deck.json()["version"]},
        )
        quality = client.post(
            "/api/projects/project-ollama/quality/check",
            json={"renderVersion": rendered.json()["version"]},
        )
        exports = client.get("/api/projects/project-ollama/exports")

    assert deck.status_code == 200
    assert quality.json()["qualityReport"]["passed"] is True
    assert exports.status_code == 200
    assert [call["url"] for call in calls] == [
        "http://127.0.0.1:11434/api/generate",
        "http://127.0.0.1:11434/api/generate",
    ]


def json_module_dumps(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False)
