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
    direction_ids = [item["directionId"] for item in visual["directions"]]
    assert 4 <= len(direction_ids) <= 6
    assert len(set(direction_ids)) == len(direction_ids)
    assert direction_ids[:3] == [
        "medical_science",
        "cinematic_research",
        "academic_clean",
    ]
    assert visual["generatedBy"]["skillName"] == "Frontend-Slides"
    first_direction = visual["directions"][0]
    assert "Frontend-Slides" in " ".join(first_direction["layoutPrinciples"] + first_direction["riskNotes"])
    assert len(first_direction["motionPlan"]) >= 3
    assert len(first_direction["layeringPlan"]) >= 3
    assert len(first_direction["imageStrategy"]) >= 3
    assert len(first_direction["hyperframesPlan"]) >= 3
    combined_plan = " ".join(
        first_direction["motionPlan"]
        + first_direction["layeringPlan"]
        + first_direction["imageStrategy"]
        + first_direction["hyperframesPlan"]
    )
    assert "Frontend-Slides" in combined_plan
    assert "HyperFrames" in combined_plan
    assert "GPT Image 2" in combined_plan
    assert "search" in combined_plan.lower() or "检索" in combined_plan
    assert outline["outlineDecision"]["slides"][0]["title"] in first_direction["sampleSlideIntents"][0]
    assert outline["outlineDecision"]["slides"][0]["keyPoint"][:24] in first_direction["sampleSlideIntents"][0]
    assert visual["selectedDirectionId"] is None

    selected = client.post(
        "/api/projects/project-visual/visual-directions/select",
        json={"visualDirectionVersion": 1, "directionId": "cinematic_research"},
    )

    assert selected.status_code == 200
    assert selected.json()["version"] == 2
    assert selected.json()["status"] == "confirmed"
    assert selected.json()["nextStep"] == "slide_deck"
    assert selected.json()["visualDirection"]["selectedDirectionId"] == "cinematic_research"

    retried = client.post(
        "/api/projects/project-visual/visual-directions/select",
        json={"visualDirectionVersion": 1, "directionId": "cinematic_research"},
    )

    assert retried.status_code == 200
    assert retried.json()["version"] == selected.json()["version"]
    assert retried.json()["visualDirection"] == selected.json()["visualDirection"]


def test_chinese_classroom_project_gets_content_aware_visual_directions(client) -> None:
    project = PROJECT | {
        "projectId": "project-visual-zh",
        "outputLanguage": "zh",
        "topic": "人工智能如何帮助大学生提升课堂展示质量",
        "audience": "课堂老师和本科生",
    }
    assert client.post("/api/projects", json=project).status_code == 201
    created = client.post("/api/projects/project-visual-zh/outline/generate", json={})
    assert created.status_code == 200
    confirmed = client.post(
        "/api/projects/project-visual-zh/outline/confirm",
        json={"outlineDecisionVersion": created.json()["version"]},
    )
    assert confirmed.status_code == 200

    generated = client.post(
        "/api/projects/project-visual-zh/visual-directions/generate",
        json={"outlineDecisionVersion": confirmed.json()["version"]},
    )

    assert generated.status_code == 200
    direction_ids = [
        item["directionId"]
        for item in generated.json()["visualDirection"]["directions"]
    ]
    assert 4 <= len(direction_ids) <= 6
    assert len(set(direction_ids)) == len(direction_ids)
    assert direction_ids[:3] == ["workshop_playbook", "classroom_friendly", "data_story"]


def test_brand_retail_case_gets_non_generic_visual_directions(client) -> None:
    project = PROJECT | {
        "projectId": "project-visual-luckin",
        "outputLanguage": "zh",
        "deckType": "case_competition",
        "topic": "瑞幸咖啡真正改变了什么，为什么值得现在讨论？",
        "audience": "商业课学生",
    }
    assert client.post("/api/projects", json=project).status_code == 201
    created = client.post("/api/projects/project-visual-luckin/outline/generate", json={})
    assert created.status_code == 200
    confirmed = client.post(
        "/api/projects/project-visual-luckin/outline/confirm",
        json={"outlineDecisionVersion": created.json()["version"]},
    )
    assert confirmed.status_code == 200

    generated = client.post(
        "/api/projects/project-visual-luckin/visual-directions/generate",
        json={"outlineDecisionVersion": confirmed.json()["version"]},
    )

    assert generated.status_code == 200
    direction_ids = [
        item["directionId"]
        for item in generated.json()["visualDirection"]["directions"]
    ]
    assert direction_ids[0] == "product_showcase"
    assert {"architectural_premium", "editorial_magazine"} <= set(direction_ids)
    assert direction_ids != ["apple", "mckinsey", "airbnb"]


def test_actual_chinese_brand_retail_topic_gets_custom_visual_directions(client) -> None:
    project = PROJECT | {
        "projectId": "project-visual-luckin-unicode",
        "outputLanguage": "zh",
        "deckType": "business_pitch",
        "topic": "瑞幸咖啡品牌复兴与新消费增长策略",
        "audience": "品牌咨询客户和投资人",
    }
    assert client.post("/api/projects", json=project).status_code == 201
    created = client.post("/api/projects/project-visual-luckin-unicode/outline/generate", json={})
    assert created.status_code == 200
    confirmed = client.post(
        "/api/projects/project-visual-luckin-unicode/outline/confirm",
        json={"outlineDecisionVersion": created.json()["version"]},
    )
    assert confirmed.status_code == 200

    generated = client.post(
        "/api/projects/project-visual-luckin-unicode/visual-directions/generate",
        json={"outlineDecisionVersion": confirmed.json()["version"]},
    )

    assert generated.status_code == 200
    directions = generated.json()["visualDirection"]["directions"]
    direction_ids = [item["directionId"] for item in directions]
    assert 4 <= len(direction_ids) <= 6
    assert len(set(direction_ids)) == len(direction_ids)
    assert direction_ids[:3] == [
        "product_showcase",
        "architectural_premium",
        "editorial_magazine",
    ]
    assert direction_ids != ["apple", "mckinsey", "airbnb"]
    combined_plan = " ".join(
        text
        for direction in directions
        for key in ["sampleSlideIntents", "motionPlan", "layeringPlan", "imageStrategy", "hyperframesPlan"]
        for text in direction[key]
    )
    assert "瑞幸" in combined_plan or "咖啡" in combined_plan
    assert "HyperFrames" in combined_plan
    assert "Frontend-Slides" in combined_plan


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
