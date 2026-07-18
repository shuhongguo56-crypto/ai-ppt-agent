import json
import re
import zipfile
from pathlib import Path

from app.services import quality as quality_service


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


def test_quality_flags_outline_scaffold_in_customer_visible_copy() -> None:
    issues = quality_service._internal_copy_issues(
        "第四部分：迁移方法\n"
        "行动优先级 2：先建立验收指标\n"
        "可验证证据线索：财报和公开报道\n"
        "Core message: internal planning trace"
    )

    assert "section scaffold prefix" in issues
    assert "行动优先级" in issues
    assert "可验证证据线索" in issues
    assert "core message" in issues


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
    direction_id = visual.json()["visualDirection"]["directions"][0]["directionId"]
    selected = client.post(
        "/api/projects/project-quality/visual-directions/select",
        json={"visualDirectionVersion": visual.json()["version"], "directionId": direction_id},
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
    assert payload["closedLoop"]["status"] == "ready"
    assert payload["closedLoop"]["blocksExport"] is False
    assert payload["agentMode"] == "research"
    assert payload["qualityProfile"] == "enterprise_ppt"
    report = payload["qualityReport"]
    assert report["passed"] is True
    assert {check["name"] for check in report["checks"]} >= {
        "pptx_exists",
        "hyperframes_html_exists",
        "pptx_slide_count",
        "pptx_relationship_parts",
        "pptx_native_powerpoint_scaffold",
        "pptx_speaker_notes",
        "pptx_design_markers",
        "pptx_visual_assets",
        "visual_asset_source_quality",
        "visual_asset_resolution_quality",
        "visual_asset_license_readiness",
        "visual_asset_uniqueness",
        "pptx_visual_placement_diversity",
        "pptx_page_plan_markers",
        "pptx_image_agent_plan_markers",
        "pptx_explainer_layers",
        "pptx_text_autofit",
        "pptx_text_anchor_values",
        "pptx_font_family_contract",
        "pptx_foreground_bounds",
        "pptx_text_fit_estimate",
        "pptx_visible_copy_hygiene",
        "pptx_visible_copy_completeness",
        "pptx_text_encoding_integrity",
        "html_frame_count",
        "html_visual_assets",
        "hyperframes_renderer_marker",
        "hyperframes_motion",
        "html_content_driven_visual_system",
        "html_page_plan_markers",
        "html_image_agent_plan_markers",
        "html_composition_diversity",
        "html_explainer_layers",
        "html_explanation_mode_diversity",
        "html_visible_copy_hygiene",
        "html_visible_copy_completeness",
        "html_text_encoding_integrity",
        "competition_story_arc",
        "competition_copy_density",
        "competition_visual_variety",
        "competition_image_intent",
        "research_storyline_contract",
        "research_page_delivery_contract",
        "research_visual_delivery_contract",
        "customer_delivery_readiness",
        "competition_ppt_baseline",
        "enterprise_ppt_baseline",
    }


def test_terminal_ellipsis_quality_checks_inspect_final_artifacts(tmp_path) -> None:
    pptx_path = tmp_path / "truncated.pptx"
    with zipfile.ZipFile(pptx_path, "w") as archive:
        archive.writestr(
            "ppt/slides/slide1.xml",
            '<p:sld xmlns:p="p" xmlns:a="a"><p:sp><a:t>Visible title…</a:t></p:sp></p:sld>',
        )
    html_path = tmp_path / "truncated.html"
    html_path.write_text("<main><h1>Visible title...</h1></main>", encoding="utf-8")

    assert quality_service._pptx_terminal_ellipsis_issues(pptx_path)
    assert quality_service._html_terminal_ellipsis_issues(html_path)


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
    assert response.json()["nextStep"] == "repair_and_rerender"
    assert response.json()["closedLoop"]["status"] == "repair_required"
    assert response.json()["closedLoop"]["blocksExport"] is True


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


def test_quality_rejects_replacement_character_gibberish(client) -> None:
    rendered = render_project(client)
    html_artifact = next(
        artifact
        for artifact in rendered["renderResult"]["artifacts"]
        if artifact["target"] == "hyperframes_html"
    )
    html_path = Path(html_artifact["path"])
    html_path.write_text(
        html_path.read_text(encoding="utf-8") + "<p>????????</p>",
        encoding="utf-8",
    )

    response = client.post(
        "/api/projects/project-quality/quality/check",
        json={"renderVersion": rendered["version"]},
    )

    assert response.status_code == 200
    report = response.json()["qualityReport"]
    assert report["passed"] is False
    encoding_check = next(
        check for check in report["checks"] if check["name"] == "html_text_encoding_integrity"
    )
    assert encoding_check["status"] == "failed"


def test_visual_asset_source_quality_rejects_svg_or_local_fallback(tmp_path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "slide-1-local.svg").write_text("<svg></svg>", encoding="utf-8")
    (assets_dir / "slide-1-asset.json").write_text(
        json.dumps(
            {
                "slide": 1,
                "fileName": "slide-1-local.svg",
                "mimeType": "image/svg+xml",
                "sourceType": "safe_vector_fallback",
            }
        ),
        encoding="utf-8",
    )

    result = quality_service._visual_asset_source_quality(tmp_path, 1)

    assert result["passed"] is False
    assert result["usable"] == 0
    assert "source=safe_vector_fallback" in result["issues"][0]


def test_visual_asset_source_quality_accepts_openverse_photograph(tmp_path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "slide-1-openverse.jpg").write_bytes(b"\xff\xd8\xff\xe0licensed-photo")
    (assets_dir / "slide-1-asset.json").write_text(
        json.dumps(
            {
                "slide": 1,
                "fileName": "slide-1-openverse.jpg",
                "mimeType": "image/jpeg",
                "sourceType": "openverse_search",
            }
        ),
        encoding="utf-8",
    )

    result = quality_service._visual_asset_source_quality(tmp_path, 1)

    assert result["passed"] is True
    assert result["usable"] == 1


def test_visual_asset_uniqueness_rejects_reused_binary(tmp_path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    repeated = b"\x89PNG\r\n\x1a\nshared-visual"
    for slide_index in (1, 2):
        file_name = f"slide-{slide_index}.png"
        (assets_dir / file_name).write_bytes(repeated)
        (assets_dir / f"slide-{slide_index}-asset.json").write_text(
            json.dumps({"slide": slide_index, "fileName": file_name}),
            encoding="utf-8",
        )

    result = quality_service._visual_asset_uniqueness(tmp_path, 2)

    assert result["passed"] is False
    assert result["unique"] == 1
    assert "slides 1, 2 reuse the identical image" in result["issues"]


def test_visual_asset_uniqueness_accepts_page_specific_binaries(tmp_path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    for slide_index in (1, 2):
        file_name = f"slide-{slide_index}.png"
        (assets_dir / file_name).write_bytes(
            b"\x89PNG\r\n\x1a\n" + str(slide_index).encode("ascii")
        )
        (assets_dir / f"slide-{slide_index}-asset.json").write_text(
            json.dumps({"slide": slide_index, "fileName": file_name}),
            encoding="utf-8",
        )

    result = quality_service._visual_asset_uniqueness(tmp_path, 2)

    assert result == {"passed": True, "unique": 2, "issues": []}


def test_quality_rejects_pptx_foreground_shapes_outside_safe_bounds(client) -> None:
    rendered = render_project(client)
    pptx_artifact = next(
        artifact
        for artifact in rendered["renderResult"]["artifacts"]
        if artifact["target"] == "pptx"
    )
    pptx_path = Path(pptx_artifact["path"])
    tmp_path = pptx_path.with_suffix(".bounds-broken.pptx")
    with zipfile.ZipFile(pptx_path) as source, zipfile.ZipFile(
        tmp_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "ppt/slides/slide1.xml":
                xml = data.decode("utf-8")
                xml = re.sub(
                    r'(<p:cNvPr id="\d+" name="(?:Text|Card) \d+".*?<a:off x=")-?\d+(" y=")',
                    r"\g<1>-250000\2",
                    xml,
                    count=1,
                    flags=re.DOTALL,
                )
                data = xml.encode("utf-8")
            target.writestr(item, data)
    tmp_path.replace(pptx_path)

    response = client.post(
        "/api/projects/project-quality/quality/check",
        json={"renderVersion": rendered["version"]},
    )

    assert response.status_code == 200
    report = response.json()["qualityReport"]
    assert report["passed"] is False
    bounds_check = next(
        check for check in report["checks"] if check["name"] == "pptx_foreground_bounds"
    )
    assert bounds_check["status"] == "failed"

    repaired = client.post(
        "/api/projects/project-quality/slide-deck/repair",
        json={
            "slideDeckVersion": rendered["renderResult"]["slideDeckVersion"],
            "qualityReportVersion": response.json()["version"],
            "repairPass": 1,
        },
    )

    assert repaired.status_code == 200
    repair_payload = repaired.json()
    assert repair_payload["status"] == "confirmed"
    assert repair_payload["version"] == rendered["renderResult"]["slideDeckVersion"] + 1
    assert "safe_copy_and_density" in repair_payload["appliedRepairs"]
    assert repair_payload["nextStep"] == "image_agent"
    for slide in repair_payload["slideDeck"]["slides"]:
        assert len(slide["title"]) <= 34
        assert slide["designPlan"]["contentDensity"] == "balanced"


def test_slide_deck_repair_requires_current_failed_quality_report(client) -> None:
    rendered = render_project(client)
    passed = client.post(
        "/api/projects/project-quality/quality/check",
        json={"renderVersion": rendered["version"]},
    )
    assert passed.status_code == 200

    response = client.post(
        "/api/projects/project-quality/slide-deck/repair",
        json={
            "slideDeckVersion": rendered["renderResult"]["slideDeckVersion"],
            "qualityReportVersion": passed.json()["version"],
            "repairPass": 1,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "quality_already_passed"
