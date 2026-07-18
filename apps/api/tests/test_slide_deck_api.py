from ai_ppt_contracts import SlideDeck
from app.services.slide_deck import repair_slide_deck_for_quality


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
    direction_id = generated.json()["visualDirection"]["directions"][0]["directionId"]
    selected = client.post(
        "/api/projects/project-deck/visual-directions/select",
        json={"visualDirectionVersion": generated.json()["version"], "directionId": direction_id},
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
    assert deck["theme"]["directionId"] == visual["visualDirection"]["selectedDirectionId"]
    assert deck["exportTargets"] == ["pptx", "hyperframes_html"]
    assert len(deck["slides"]) == 8
    assert [slide["slideIndex"] for slide in deck["slides"]] == list(range(1, 9))
    assert [item["slide"] for item in deck["imagePlan"]] == list(range(1, 9))
    assert all(item["needsImage"] for item in deck["imagePlan"])

    retried = assemble_deck(client, visual["version"])
    assert retried.status_code == 200
    assert retried.json()["version"] == payload["version"]
    assert retried.json()["slideDeck"] == payload["slideDeck"]
    assert all(
        item["imageType"]
        in {
            "background",
            "course_review_atmosphere",
            "business_scene",
            "classical_element",
            "thesis_concept",
            "product_showcase",
            "icon_illustration",
            "data_visual",
        }
        for item in deck["imagePlan"]
    )
    assert all("OpenAI Image API" in item["providerChain"] for item in deck["imagePlan"])
    assert all("Pollinations FLUX API" in item["providerChain"] for item in deck["imagePlan"])
    assert all("custom image2 API" in item["providerChain"] for item in deck["imagePlan"])
    assert all(item["purpose"] and item["prompt"] and item["searchQuery"] for item in deck["imagePlan"])
    for slide, image_item in zip(deck["slides"], deck["imagePlan"]):
        assert slide["title"] in image_item["prompt"]
        assert slide["designPlan"]["assetRole"] in image_item["purpose"]
        assert "decorative" not in image_item["purpose"].lower()
    assert deck["slides"][0]["blocks"][0]["blockType"] == "headline"
    assert all(
        any(block["blockType"] == "image_placeholder" for block in slide["blocks"])
        for slide in deck["slides"]
    )
    assert deck["theme"]["designSystemId"].startswith(f"{deck['theme']['directionId']}-")
    assert isinstance(deck["theme"]["designSeed"], int)
    plans = [slide["designPlan"] for slide in deck["slides"]]
    assert all(plan["assetQuery"] and plan["assetRole"] for plan in plans)
    assert all(plan["hierarchy"] and plan["visualLayers"] for plan in plans)
    assert all(
        {"enterprise decision claim", "source/evidence discipline", "action-ready implication"}
        <= set(plan["hierarchy"])
        for plan in plans
    )
    assert all(
        "enterprise safe typography and image/text separation" in plan["visualLayers"]
        for plan in plans
    )
    assert all("Enterprise research contract" in plan["rationale"] for plan in plans)
    assert all(plan["explanationMode"] for plan in plans)
    assert all(plan["visualBrief"] for plan in plans)
    assert all(2 <= len(plan["diagramLabels"]) <= 4 for plan in plans)
    assert all(
        any(block["role"] == "decision takeaway" for block in slide["blocks"])
        for slide in deck["slides"]
    )
    assert all(
        any(block["role"].startswith("evidence/action cue") for block in slide["blocks"])
        for slide in deck["slides"]
    )
    assert all(
        len(label) <= 64
        for plan in plans
        for label in plan["diagramLabels"]
    )
    assert len({plan["explanationMode"] for plan in plans}) >= 3
    for outline_slide, deck_slide, plan in zip(
        outline["outlineDecision"]["slides"], deck["slides"], plans
    ):
        assert outline_slide["title"] in plan["visualBrief"]
        outline_content = [
            outline_slide["title"],
            outline_slide["keyPoint"],
            *outline_slide["talkingPoints"],
        ]
        for label in plan["diagramLabels"]:
            needle = label.removesuffix("…")
            assert any(needle in source for source in outline_content)
            assert not any(
                forbidden in label
                for forbidden in (
                    "第 ",
                    "Slide ",
                    "原文线索：",
                    "页面作用：",
                    "可引用证据：",
                    "Source claim:",
                    "Slide role:",
                )
            )
        assert deck_slide["title"] == outline_slide["title"]
    archetypes = [plan["compositionArchetype"] for plan in plans]
    treatments = [plan["imageTreatment"] for plan in plans]
    variants = [plan["compositionVariant"] for plan in plans]
    signatures = set(zip(archetypes, treatments, variants))
    assert all(left != right for left, right in zip(archetypes, archetypes[1:]))
    assert len(set(archetypes)) >= 3
    assert len(set(treatments)) >= 2
    assert len(signatures) == len(plans)
    assert {variant.split("-", 1)[0] for variant in variants} == {
        "anchor",
        "dense",
        "breathing",
    }
    assert plans[0]["compositionArchetype"] in {
        "cinematic_hero",
        "editorial_cover",
        "architectural_cover",
    }
    assert plans[-1]["compositionArchetype"] in {
        "closing_echo",
        "manifesto_close",
        "future_horizon",
    }
    for slide, plan in zip(deck["slides"], plans):
        if slide["purpose"] == "evidence":
            assert plan["compositionArchetype"] in {
                "data_landscape",
                "proof_mosaic",
                "split_comparison",
            }
            assert plan["assetRole"] == "evidence"
        if slide["purpose"] == "framework":
            assert plan["compositionArchetype"] in {
                "system_map",
                "process_ribbon",
                "split_comparison",
            }
            assert plan["assetRole"] == "diagram"


def test_assembled_deck_uses_edited_outline(client) -> None:
    create_project(client)
    generated = client.post("/api/projects/project-deck/outline/generate", json={})
    assert generated.status_code == 200
    outline_decision = generated.json()["outlineDecision"]
    outline_decision["slides"][0]["title"] = "用户编辑后的封面标题"
    outline_decision["slides"][0]["keyPoint"] = "用户编辑后的核心信息必须进入最终 SlideDeck"

    patched = client.patch(
        "/api/projects/project-deck/outline",
        json={"expectedVersion": generated.json()["version"], "outlineDecision": outline_decision},
    )
    assert patched.status_code == 200
    confirmed = client.post(
        "/api/projects/project-deck/outline/confirm",
        json={"outlineDecisionVersion": patched.json()["version"]},
    )
    assert confirmed.status_code == 200
    visual = select_visual(client, confirmed.json()["version"])

    response = assemble_deck(client, visual["version"])

    assert response.status_code == 200
    first_slide = response.json()["slideDeck"]["slides"][0]
    assert first_slide["title"] == "用户编辑后的封面标题"
    assert first_slide["blocks"][0]["content"] == "用户编辑后的封面标题"
    assert any(
        block["content"] == "用户编辑后的核心信息必须进入最终 SlideDeck"
        for block in first_slide["blocks"]
    )


def test_slide_deck_visible_content_is_derived_from_outline_only(client) -> None:
    create_project(client)
    generated = client.post("/api/projects/project-deck/outline/generate", json={})
    assert generated.status_code == 200
    outline_decision = generated.json()["outlineDecision"]
    outline_decision["slides"][0]["title"] = "Outline Title Only"
    outline_decision["slides"][0]["subtitle"] = "Outline Subtitle Only"
    outline_decision["slides"][0]["keyPoint"] = "Outline Key Point Only"
    outline_decision["slides"][0]["talkingPoints"] = [
        "Outline Talking Point A",
        "Outline Talking Point B",
    ]
    outline_decision["slides"][0]["visualIntent"] = "Outline Visual Intent Only"
    outline_decision["slides"][0]["requiredAssets"] = ["Outline Asset Only"]
    outline_decision["slides"][0]["citationIds"] = ["Outline Citation Only"]
    outline_decision["slides"][0]["speakerNotesDraft"] = "Outline Speaker Notes Only"

    patched = client.patch(
        "/api/projects/project-deck/outline",
        json={"expectedVersion": generated.json()["version"], "outlineDecision": outline_decision},
    )
    assert patched.status_code == 200
    confirmed = client.post(
        "/api/projects/project-deck/outline/confirm",
        json={"outlineDecisionVersion": patched.json()["version"]},
    )
    assert confirmed.status_code == 200
    visual = select_visual(client, confirmed.json()["version"])

    response = assemble_deck(client, visual["version"])

    assert response.status_code == 200
    outline_slide = outline_decision["slides"][0]
    allowed_content = {
        outline_slide["title"],
        outline_slide["subtitle"],
        outline_slide["keyPoint"],
        *outline_slide["talkingPoints"],
        ", ".join(outline_slide["requiredAssets"]),
        ", ".join(outline_slide["citationIds"]),
        outline_slide["speakerNotesDraft"],
        outline_slide["visualIntent"],
    }
    deck_slide = response.json()["slideDeck"]["slides"][0]
    actual_content = {
        deck_slide["title"],
        deck_slide["subtitle"],
        deck_slide["visualIntent"],
        deck_slide["speakerNotes"],
        *(block["content"] for block in deck_slide["blocks"]),
    }
    assert actual_content <= allowed_content
    assert "Direction:" not in deck_slide["visualIntent"]
    assert all("placeholder" not in block["content"].lower() for block in deck_slide["blocks"])


def test_slide_deck_disambiguates_duplicate_outline_titles(client) -> None:
    create_project(client)
    generated = client.post("/api/projects/project-deck/outline/generate", json={})
    assert generated.status_code == 200
    outline_decision = generated.json()["outlineDecision"]
    outline_decision["slides"][5]["title"] = "落地路径"
    outline_decision["slides"][5]["keyPoint"] = "把判断转化为可执行的门店、会员和供应链动作"
    outline_decision["slides"][6]["title"] = "落地路径"
    outline_decision["slides"][6]["keyPoint"] = "用验证指标区分可迁移方法与不可复制条件"

    patched = client.patch(
        "/api/projects/project-deck/outline",
        json={"expectedVersion": generated.json()["version"], "outlineDecision": outline_decision},
    )
    assert patched.status_code == 200
    confirmed = client.post(
        "/api/projects/project-deck/outline/confirm",
        json={"outlineDecisionVersion": patched.json()["version"]},
    )
    assert confirmed.status_code == 200
    visual = select_visual(client, confirmed.json()["version"])

    response = assemble_deck(client, visual["version"])

    assert response.status_code == 200
    titles = [slide["title"] for slide in response.json()["slideDeck"]["slides"]]
    assert len({title.casefold() for title in titles}) == len(titles)
    assert titles[5] == "落地路径"
    assert titles[6].startswith("落地路径：")
    assert "验证指标" in titles[6]
    assert response.json()["slideDeck"]["slides"][6]["blocks"][0]["content"] == titles[6]


def test_slide_deck_compacts_long_internal_copy_into_readable_diagram_labels(client) -> None:
    create_project(client)
    generated = client.post("/api/projects/project-deck/outline/generate", json={})
    assert generated.status_code == 200
    outline_decision = generated.json()["outlineDecision"]
    target = outline_decision["slides"][2]
    target["title"] = "文章先回答的问题：大型语言模型如何在高校教学场景中形成真正可验证的学习价值"
    target["keyPoint"] = "第 3 页：大型语言模型的价值取决于课程目标、教师引导、事实核验与评价机制是否形成闭环"
    target["talkingPoints"] = [
        "原文线索：教师需要先定义学习目标，再决定使用何种人工智能能力与课堂活动",
        "页面作用：把技术能力、教学流程、评价方式和学术诚信组织成可以复述的因果链",
        "可引用证据：课堂实践需要同时观察学习质量、效率、事实准确性与学生自主判断",
        "讲解时可参考摘录：技术采用必须服务于清晰的教学判断，而不是追逐工具本身",
    ]

    patched = client.patch(
        "/api/projects/project-deck/outline",
        json={"expectedVersion": generated.json()["version"], "outlineDecision": outline_decision},
    )
    assert patched.status_code == 200
    confirmed = client.post(
        "/api/projects/project-deck/outline/confirm",
        json={"outlineDecisionVersion": patched.json()["version"]},
    )
    visual = select_visual(client, confirmed.json()["version"])

    response = assemble_deck(client, visual["version"])

    assert response.status_code == 200
    labels = response.json()["slideDeck"]["slides"][2]["designPlan"]["diagramLabels"]
    assert 2 <= len(labels) <= 4
    assert all(len(label) <= 32 for label in labels)
    assert all(
        not any(
            forbidden in label
            for forbidden in ("第 3 页：", "原文线索：", "页面作用：", "可引用证据：", "讲解时可参考摘录：")
        )
        for label in labels
    )
    assert any("大型语言模型" in label for label in labels)


def test_non_quantitative_evidence_uses_proof_layout_instead_of_fake_bar_chart(client) -> None:
    create_project(client)
    generated = client.post("/api/projects/project-deck/outline/generate", json={})
    assert generated.status_code == 200
    outline_decision = generated.json()["outlineDecision"]
    evidence = next(slide for slide in outline_decision["slides"] if slide["purpose"] == "evidence")
    evidence["title"] = "同行评审研究揭示课程设计的重要性"
    evidence["keyPoint"] = "证据：2025 年研究强调课程目标与评价机制需要同步设计，才能降低代写和幻觉风险"
    evidence["talkingPoints"] = [
        "2025 年论文讨论评价机制，但没有提供可画成柱状图的数量指标",
        "评价需要覆盖事实准确性与学生自主判断",
    ]
    evidence["citationIds"] = ["web-crossref-study"]

    patched = client.patch(
        "/api/projects/project-deck/outline",
        json={"expectedVersion": generated.json()["version"], "outlineDecision": outline_decision},
    )
    confirmed = client.post(
        "/api/projects/project-deck/outline/confirm",
        json={"outlineDecisionVersion": patched.json()["version"]},
    )
    visual = select_visual(client, confirmed.json()["version"])

    response = assemble_deck(client, visual["version"])

    evidence_plan = next(
        slide["designPlan"]
        for slide in response.json()["slideDeck"]["slides"]
        if slide["purpose"] == "evidence"
    )
    assert evidence_plan["compositionArchetype"] == "proof_mosaic"


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

    direction_id = visual_draft.json()["visualDirection"]["directions"][0]["directionId"]
    visual = client.post(
        "/api/projects/project-deck/visual-directions/select",
        json={"visualDirectionVersion": visual_draft.json()["version"], "directionId": direction_id},
    )
    assert visual.status_code == 200

    stale = assemble_deck(client, visual.json()["version"] - 1)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "checkpoint_version_conflict"


def test_quality_repair_keeps_one_valid_deck_contract_and_increases_visual_variety(client) -> None:
    create_project(client)
    outline = confirm_outline(client)
    visual = select_visual(client, outline["version"])
    assembled = assemble_deck(client, visual["version"])
    assert assembled.status_code == 200

    repaired, repairs = repair_slide_deck_for_quality(
        deck=SlideDeck(**assembled.json()["slideDeck"]),
        failed_check_names=[
            "pptx_text_fit_estimate",
            "competition_visual_variety",
            "visual_asset_source_quality",
        ],
        repair_pass=2,
    )

    assert repairs == [
        "safe_copy_and_density",
        "page_composition_and_motion",
        "page_specific_image_intent",
    ]
    for item in repaired.image_plan:
        lowered = item.prompt.casefold()
        assert "award-winning" in lowered
        assert "single focal" in lowered
        assert lowered.count("award-winning corporate presentation standard") == 1
    assert all(len(slide.title) <= 54 for slide in repaired.slides)
    assert all(slide.design_plan.content_density == "sparse" for slide in repaired.slides)
    assert len({slide.design_plan.composition_archetype for slide in repaired.slides}) >= 5
    assert len({slide.design_plan.image_treatment for slide in repaired.slides}) >= 3
    assert len({slide.design_plan.motion_preset for slide in repaired.slides}) >= 3
    assert repaired.export_targets == ["pptx", "hyperframes_html"]
