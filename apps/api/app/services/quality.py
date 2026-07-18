from __future__ import annotations

import html
import hashlib
import json
import re
import zipfile
from pathlib import Path

from ai_ppt_contracts import QualityReport, RenderResult, SlideDeck


SLIDE_CX = 12192000
SLIDE_CY = 6858000
FOREGROUND_SAFE_X = 460000
FOREGROUND_SAFE_TOP = 340000
FOREGROUND_SAFE_BOTTOM = 430000
EMU_PER_POINT = 12700
ENTERPRISE_PPT_BASELINE_CHECKS = {
    "pptx_exists",
    "hyperframes_html_exists",
    "pptx_slide_count",
    "pptx_native_powerpoint_scaffold",
    "pptx_speaker_notes",
    "pptx_visual_assets",
    "visual_asset_source_quality",
    "visual_asset_uniqueness",
    "pptx_page_plan_markers",
    "pptx_image_agent_plan_markers",
    "pptx_explainer_layers",
    "pptx_text_autofit",
    "pptx_text_anchor_values",
    "pptx_font_family_contract",
    "pptx_foreground_bounds",
    "pptx_text_fit_estimate",
    "pptx_visible_copy_hygiene",
    "pptx_text_encoding_integrity",
    "html_frame_count",
    "html_visual_assets",
    "hyperframes_renderer_marker",
    "hyperframes_motion",
    "html_page_plan_markers",
    "html_image_agent_plan_markers",
    "html_composition_diversity",
    "html_explainer_layers",
    "html_explanation_mode_diversity",
    "html_visible_copy_hygiene",
    "html_text_encoding_integrity",
    "competition_story_arc",
    "competition_copy_density",
    "competition_visual_variety",
    "competition_image_intent",
    "award_grade_design_contract",
    "research_storyline_contract",
    "research_page_delivery_contract",
    "research_visual_delivery_contract",
    "competition_ppt_baseline",
    "customer_delivery_readiness",
}


def check_render_quality(
    *,
    render_result: RenderResult,
    render_version: int,
    asset_root: Path,
    quality_profile: str = "standard",
    slide_deck: SlideDeck | None = None,
) -> QualityReport:
    checks = []
    root = asset_root.resolve()
    artifacts = {artifact.target: artifact for artifact in render_result.artifacts}
    expected_slide_count = render_result.artifacts[0].slide_count

    for target in ("pptx", "hyperframes_html"):
        artifact = artifacts[target]
        path = _safe_path(root, artifact.path)
        if path is None:
            checks.append(
                {
                    "schemaVersion": "1.0.0",
                    "name": f"{target}_path",
                    "status": "failed",
                    "detail": "Artifact path is outside the asset root or missing.",
                }
            )
            continue
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": f"{target}_exists",
                "status": "passed",
                "detail": f"{target} artifact exists and is readable.",
            }
        )

    pptx_path = _safe_path(root, artifacts["pptx"].path)
    if pptx_path is not None:
        slide_count = _pptx_slide_count(pptx_path)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "pptx_slide_count",
                "status": "passed" if slide_count == expected_slide_count else "failed",
                "detail": f"PPTX contains {slide_count} slides; expected {expected_slide_count}.",
            }
        )
        missing_relationships = _missing_pptx_relationship_parts(pptx_path, expected_slide_count)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "pptx_relationship_parts",
                "status": "passed" if not missing_relationships else "failed",
                "detail": (
                    "PPTX relationship parts are present."
                    if not missing_relationships
                    else f"Missing relationship parts: {', '.join(missing_relationships[:5])}."
                ),
            }
        )
        asset_uniqueness = _visual_asset_uniqueness(pptx_path.parent, expected_slide_count)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "visual_asset_uniqueness",
                "status": "passed" if asset_uniqueness["passed"] else "failed",
                "detail": (
                    f"All {asset_uniqueness['unique']} rendered slide visuals are content-distinct assets."
                    if asset_uniqueness["passed"]
                    else (
                        "Rendered slide visuals are reused or unreadable: "
                        f"{', '.join(asset_uniqueness['issues'][:6])}."
                    )
                ),
            }
        )
        native_scaffold = _pptx_has_native_powerpoint_scaffold(pptx_path)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "pptx_native_powerpoint_scaffold",
                "status": "passed" if native_scaffold else "failed",
                "detail": (
                    "PPTX contains the PowerPoint-native master, notes master, view, table-style, and relationship scaffold."
                    if native_scaffold
                    else "PPTX is missing part of the PowerPoint-native compatibility scaffold."
                ),
            }
        )
        notes_count = _pptx_notes_slide_count(pptx_path)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "pptx_speaker_notes",
                "status": "passed" if notes_count == expected_slide_count else "failed",
                "detail": f"PPTX contains {notes_count} speaker-note slides; expected {expected_slide_count}.",
            }
        )
        design_marker_count = _pptx_design_marker_count(pptx_path)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "pptx_design_markers",
                "status": "passed" if design_marker_count >= expected_slide_count else "failed",
                "detail": f"PPTX contains {design_marker_count} design markers across {expected_slide_count} slides.",
            }
        )
        media_count = _pptx_media_count(pptx_path)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "pptx_visual_assets",
                "status": "passed" if media_count >= expected_slide_count else "failed",
                "detail": f"PPTX contains {media_count} visual media assets; expected at least {expected_slide_count}.",
            }
        )
        asset_source = _visual_asset_source_quality(pptx_path.parent, expected_slide_count)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "visual_asset_source_quality",
                "status": "passed" if asset_source["passed"] else "failed",
                "detail": (
                    f"Visual assets are sourced/generated for {asset_source['usable']} of {expected_slide_count} slides."
                    if asset_source["passed"]
                    else (
                        f"Visual assets still use placeholders or are missing: "
                        f"{', '.join(asset_source['issues'][:6])}."
                    )
                ),
            }
        )
        full_bleed_count = _pptx_full_bleed_visual_count(pptx_path)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "pptx_reference_full_bleed_visuals",
                "status": "passed" if full_bleed_count >= expected_slide_count else "failed",
                "detail": f"PPTX contains {full_bleed_count} reference-style full-bleed visual layers; expected {expected_slide_count}.",
            }
        )
        page_plan_count = _pptx_page_plan_marker_count(pptx_path)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "pptx_page_plan_markers",
                "status": "passed" if page_plan_count >= expected_slide_count else "failed",
                "detail": f"PPTX contains {page_plan_count} content-aware page-plan markers; expected {expected_slide_count}.",
            }
        )
        image_agent_count = _pptx_image_agent_marker_count(pptx_path)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "pptx_image_agent_plan_markers",
                "status": "passed" if image_agent_count >= expected_slide_count else "failed",
                "detail": f"PPTX contains {image_agent_count} Image Agent plan markers; expected {expected_slide_count}.",
            }
        )
        explainer_count = _pptx_explainer_layer_count(pptx_path)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "pptx_explainer_layers",
                "status": "passed" if explainer_count == expected_slide_count else "failed",
                "detail": f"PPTX contains {explainer_count} outline-grounded explainer layers; expected {expected_slide_count}.",
            }
        )
        autofit = _pptx_text_autofit_metrics(pptx_path)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "pptx_text_autofit",
                "status": "passed" if autofit["passed"] else "failed",
                "detail": (
                    f"PPTX applies native autofit to {autofit['fitted']} of "
                    f"{autofit['total']} visible slide text bodies."
                ),
            }
        )
        anchor_issues = _pptx_text_anchor_issues(pptx_path)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "pptx_text_anchor_values",
                "status": "passed" if not anchor_issues else "failed",
                "detail": (
                    "PPTX text boxes use PowerPoint-compatible vertical anchor values."
                    if not anchor_issues
                    else f"PPTX contains unsupported text anchor values: {', '.join(anchor_issues[:6])}."
                ),
            }
        )
        font_contract_issues = _pptx_font_family_contract_issues(pptx_path)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "pptx_font_family_contract",
                "status": "passed" if not font_contract_issues else "failed",
                "detail": (
                    "PPTX visible text uses SimSun for Chinese/East Asian text and Times New Roman for Latin text."
                    if not font_contract_issues
                    else f"PPTX font contract violations: {', '.join(font_contract_issues[:6])}."
                ),
            }
        )
        foreground_bounds_issues = _pptx_foreground_bounds_issues(pptx_path)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "pptx_foreground_bounds",
                "status": "passed" if not foreground_bounds_issues else "failed",
                "detail": (
                    "PPTX foreground text boxes and cards stay inside the slide safe area."
                    if not foreground_bounds_issues
                    else f"PPTX foreground shapes exceed the slide safe area: {', '.join(foreground_bounds_issues[:6])}."
                ),
            }
        )
        text_fit_issues = _pptx_text_fit_issues(pptx_path)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "pptx_text_fit_estimate",
                "status": "passed" if not text_fit_issues else "failed",
                "detail": (
                    "PPTX text frames have enough estimated height for visible copy."
                    if not text_fit_issues
                    else f"PPTX text may clip or overflow in slideshow mode: {', '.join(text_fit_issues[:6])}."
                ),
            }
        )
        pptx_copy_issues = _pptx_visible_copy_issues(pptx_path)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "pptx_visible_copy_hygiene",
                "status": "passed" if not pptx_copy_issues else "failed",
                "detail": (
                    "PPTX visible copy contains no internal planning labels."
                    if not pptx_copy_issues
                    else f"PPTX exposes internal planning labels: {', '.join(pptx_copy_issues[:5])}."
                ),
            }
        )
        pptx_encoding_issues = _pptx_text_encoding_issues(pptx_path)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "pptx_text_encoding_integrity",
                "status": "passed" if not pptx_encoding_issues else "failed",
                "detail": (
                    "PPTX visible text contains no replacement-character gibberish."
                    if not pptx_encoding_issues
                    else f"PPTX visible text contains encoding damage: {', '.join(pptx_encoding_issues)}."
                ),
            }
        )

    html_path = _safe_path(root, artifacts["hyperframes_html"].path)
    if html_path is not None:
        frame_count = _html_frame_count(html_path)
        renderer_marker = _html_has_hyperframes_marker(html_path)
        asset_count = _html_visual_asset_count(html_path)
        motion_marker = _html_has_motion_marker(html_path)
        reference_style_marker = _html_has_reference_style_marker(html_path)
        page_plan_count = _html_page_plan_marker_count(html_path)
        image_agent_count = _html_image_agent_marker_count(html_path)
        composition_diversity = _html_composition_diversity(html_path, expected_slide_count)
        explainer_metrics = _html_explainer_metrics(html_path, expected_slide_count)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "html_frame_count",
                "status": "passed" if frame_count == expected_slide_count else "failed",
                "detail": f"HTML contains {frame_count} frames; expected {expected_slide_count}.",
            }
        )
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "hyperframes_renderer_marker",
                "status": "passed" if renderer_marker else "failed",
                "detail": (
                    "HTML declares the HyperFrames local renderer and SlideDeck JSON source."
                    if renderer_marker
                    else "HTML is missing the HyperFrames renderer marker."
                ),
            }
        )
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "html_page_plan_markers",
                "status": "passed" if page_plan_count >= expected_slide_count else "failed",
                "detail": f"HTML exposes {page_plan_count} content-aware page plans; expected {expected_slide_count}.",
            }
        )
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "html_image_agent_plan_markers",
                "status": "passed" if image_agent_count >= expected_slide_count else "failed",
                "detail": f"HTML exposes {image_agent_count} Image Agent image-plan markers; expected {expected_slide_count}.",
            }
        )
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "html_composition_diversity",
                "status": "passed" if composition_diversity["passed"] else "failed",
                "detail": composition_diversity["detail"],
            }
        )
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "html_explainer_layers",
                "status": "passed" if explainer_metrics["coverage_passed"] else "failed",
                "detail": f"HTML contains {explainer_metrics['count']} outline-grounded explainer layers; expected {expected_slide_count}.",
            }
        )
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "html_explanation_mode_diversity",
                "status": "passed" if explainer_metrics["diversity_passed"] else "failed",
                "detail": explainer_metrics["detail"],
            }
        )
        html_copy_issues = _html_visible_copy_issues(html_path)
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "html_visible_copy_hygiene",
                "status": "passed" if not html_copy_issues else "failed",
                "detail": (
                    "HTML visible copy contains no internal planning labels."
                    if not html_copy_issues
                    else f"HTML exposes internal planning labels: {', '.join(html_copy_issues[:5])}."
                ),
            }
        )
        html_encoding_issues = _text_encoding_issues(html_path.read_text(encoding="utf-8"))
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "html_text_encoding_integrity",
                "status": "passed" if not html_encoding_issues else "failed",
                "detail": (
                    "HTML visible text contains no replacement-character gibberish."
                    if not html_encoding_issues
                    else f"HTML visible text contains encoding damage: {', '.join(html_encoding_issues)}."
                ),
            }
        )
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "html_visual_assets",
                "status": "passed" if asset_count >= expected_slide_count else "failed",
                "detail": f"HTML contains {asset_count} frame visual assets; expected at least {expected_slide_count}.",
            }
        )
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "hyperframes_motion",
                "status": "passed" if motion_marker else "failed",
                "detail": (
                    "HTML declares HyperFrames motion choreography and reduced-motion fallback."
                    if motion_marker
                    else "HTML is missing HyperFrames motion or reduced-motion markers."
                ),
            }
        )
        checks.append(
            {
                "schemaVersion": "1.0.0",
                "name": "html_reference_cinematic_style",
                "status": "passed" if reference_style_marker else "failed",
                "detail": (
                    "HTML uses the reference-style cinematic full-bleed visual system."
                    if reference_style_marker
                    else "HTML is missing the reference-style cinematic full-bleed visual system."
                ),
            }
        )

    if quality_profile in {"enterprise_ppt", "competition_ppt"}:
        checks.extend(_competition_grade_checks(slide_deck))
        checks.append(_customer_delivery_readiness_check(checks))
        checks.append(_enterprise_ppt_baseline_check(checks))

    return QualityReport(
        schemaVersion="1.0.0",
        projectId=render_result.project_id,
        renderVersion=render_version,
        passed=all(check["status"] == "passed" for check in checks),
        checks=checks,
    )


def _enterprise_ppt_baseline_check(checks: list[dict[str, str]]) -> dict[str, str]:
    status_by_name = {check["name"]: check["status"] for check in checks}
    missing_or_failed = sorted(
        name
        for name in ENTERPRISE_PPT_BASELINE_CHECKS
        if status_by_name.get(name) != "passed"
    )
    return {
        "schemaVersion": "1.0.0",
        "name": "enterprise_ppt_baseline",
        "status": "passed" if not missing_or_failed else "failed",
        "detail": (
            "Research/enterprise mode passed the enterprise PPT baseline: source-to-deck artifacts, editable PPTX scaffold, "
            "content-grounded image plan, safe typography, HyperFrames motion, and visible-copy hygiene are all present."
            if not missing_or_failed
            else "Research/enterprise mode failed enterprise PPT baseline checks: "
            + ", ".join(missing_or_failed[:12])
            + ("." if len(missing_or_failed) <= 12 else ", ...")
        ),
    }


def _customer_delivery_readiness_check(checks: list[dict[str, str]]) -> dict[str, str]:
    required = {
        "pptx_exists",
        "hyperframes_html_exists",
        "pptx_slide_count",
        "pptx_native_powerpoint_scaffold",
        "pptx_visual_assets",
        "visual_asset_source_quality",
        "visual_asset_uniqueness",
        "pptx_font_family_contract",
        "pptx_foreground_bounds",
        "pptx_text_fit_estimate",
        "pptx_visible_copy_hygiene",
        "pptx_text_encoding_integrity",
        "html_visual_assets",
        "hyperframes_motion",
        "html_visible_copy_hygiene",
        "html_text_encoding_integrity",
        "competition_ppt_baseline",
        "award_grade_design_contract",
        "research_storyline_contract",
        "research_page_delivery_contract",
        "research_visual_delivery_contract",
    }
    status_by_name = {check["name"]: check["status"] for check in checks}
    failed = sorted(name for name in required if status_by_name.get(name) != "passed")
    return {
        "schemaVersion": "1.0.0",
        "name": "customer_delivery_readiness",
        "status": "passed" if not failed else "failed",
        "detail": (
            "Deck is ready for customer delivery: PPTX opens safely, HTML presents with motion, visuals are real/generated assets, copy is clean, and the award-grade story/design contract passed."
            if not failed
            else "Deck is not ready for customer delivery; repair required for: "
            + ", ".join(failed[:12])
            + ("." if len(failed) <= 12 else ", ...")
        ),
    }


def _competition_grade_checks(slide_deck: SlideDeck | None) -> list[dict[str, str]]:
    if slide_deck is None:
        return [
            {
                "schemaVersion": "1.0.0",
                "name": "competition_ppt_baseline",
                "status": "failed",
                "detail": "Competition-grade checks require the canonical SlideDeck JSON.",
            }
        ]
    checks = [
        _competition_story_arc_check(slide_deck),
        _competition_copy_density_check(slide_deck),
        _competition_visual_variety_check(slide_deck),
        _competition_image_intent_check(slide_deck),
        _award_grade_design_contract_check(slide_deck),
        _research_storyline_contract_check(slide_deck),
        _research_page_delivery_contract_check(slide_deck),
        _research_visual_delivery_contract_check(slide_deck),
    ]
    failed = [check["name"] for check in checks if check["status"] != "passed"]
    checks.append(
        {
            "schemaVersion": "1.0.0",
            "name": "competition_ppt_baseline",
            "status": "passed" if not failed else "failed",
            "detail": (
                "Deck meets the competition-grade baseline: strategic story arc, readable copy density, varied page design, and content-serving image plan."
                if not failed
                else f"Deck misses competition-grade checks: {', '.join(failed)}."
            ),
        }
    )
    return checks


def _research_storyline_contract_check(slide_deck: SlideDeck) -> dict[str, str]:
    purposes = [slide.purpose for slide in slide_deck.slides]
    required = {
        "cover",
        "agenda",
        "context",
        "evidence",
        "insight",
        "recommendation",
        "conclusion",
    }
    missing = sorted(required - set(purposes))
    framework_capability = "framework" in purposes or any(
        slide.design_plan.explanation_mode == "process_diagram"
        or slide.design_plan.composition_archetype in {"system_map", "process_ribbon", "split_comparison"}
        for slide in slide_deck.slides
    )
    passed = (
        len(slide_deck.slides) >= 8
        and purposes[0] == "cover"
        and purposes[-1] == "conclusion"
        and not missing
        and framework_capability
    )
    return {
        "schemaVersion": "1.0.0",
        "name": "research_storyline_contract",
        "status": "passed" if passed else "failed",
        "detail": (
            "Research mode has an enterprise storyline: cover, roadmap, context, mechanism/framework capability, evidence, insight, recommendation, and conclusion."
            if passed
            else (
                f"Research storyline is incomplete: slideCount={len(slide_deck.slides)}, "
                f"first={purposes[0] if purposes else 'none'}, last={purposes[-1] if purposes else 'none'}, "
                f"missing={','.join(missing) or 'none'}, frameworkCapability={framework_capability}."
            )
        ),
    }


def _research_page_delivery_contract_check(slide_deck: SlideDeck) -> dict[str, str]:
    issues: list[str] = []
    for slide in slide_deck.slides:
        hierarchy_text = " | ".join(slide.design_plan.hierarchy).lower()
        roles_text = " | ".join(block.role for block in slide.blocks).lower()
        visible_blocks = [
            block
            for block in slide.blocks
            if block.block_type not in {"image_placeholder", "chart_placeholder", "speaker_notes"}
        ]
        if "decision" not in hierarchy_text or "evidence" not in hierarchy_text or "action" not in hierarchy_text:
            issues.append(f"slide {slide.slide_index} missing decision/evidence/action hierarchy")
        if "decision" not in roles_text or "evidence/action" not in roles_text:
            issues.append(f"slide {slide.slide_index} missing enterprise block roles")
        if len(visible_blocks) > 8:
            issues.append(f"slide {slide.slide_index} has {len(visible_blocks)} visible text blocks")
        if any(len(block.content.strip()) < 4 for block in visible_blocks):
            issues.append(f"slide {slide.slide_index} has low-information visible copy")
    return {
        "schemaVersion": "1.0.0",
        "name": "research_page_delivery_contract",
        "status": "passed" if not issues else "failed",
        "detail": (
            "Every research-mode slide carries a decision/evidence/action page contract while keeping visible copy bounded."
            if not issues
            else f"Research page delivery contract issues: {', '.join(issues[:8])}."
        ),
    }


def _research_visual_delivery_contract_check(slide_deck: SlideDeck) -> dict[str, str]:
    issues: list[str] = []
    image_by_slide = {item.slide: item for item in slide_deck.image_plan}
    query_fingerprints = {_copy_fingerprint(item.search_query) for item in slide_deck.image_plan}
    for slide in slide_deck.slides:
        layers_text = " | ".join(slide.design_plan.visual_layers).lower()
        rationale = slide.design_plan.rationale.lower()
        image_item = image_by_slide.get(slide.slide_index)
        if "safe typography" not in layers_text or "image/text separation" not in layers_text:
            issues.append(f"slide {slide.slide_index} missing safe typography visual layer")
        if "enterprise research contract" not in rationale:
            issues.append(f"slide {slide.slide_index} missing enterprise rationale")
        if image_item is None:
            issues.append(f"slide {slide.slide_index} missing image plan")
            continue
        if _copy_fingerprint(slide.title) not in _copy_fingerprint(image_item.prompt):
            issues.append(f"slide {slide.slide_index} image prompt does not include title intent")
        if slide.design_plan.asset_role not in image_item.purpose:
            issues.append(f"slide {slide.slide_index} image purpose does not state asset role")
    required_unique_queries = max(4, len(slide_deck.slides) // 2)
    if len(query_fingerprints) < required_unique_queries:
        issues.append(
            f"image search intents too repetitive: {len(query_fingerprints)}/{required_unique_queries}"
        )
    return {
        "schemaVersion": "1.0.0",
        "name": "research_visual_delivery_contract",
        "status": "passed" if not issues else "failed",
        "detail": (
            "Research mode has page-specific image intent, safe typography layers, and enterprise visual rationale."
            if not issues
            else f"Research visual delivery contract issues: {', '.join(issues[:8])}."
        ),
    }


def _competition_story_arc_check(slide_deck: SlideDeck) -> dict[str, str]:
    purposes = [slide.purpose for slide in slide_deck.slides]
    unique_purposes = set(purposes)
    title_fingerprints = {
        _copy_fingerprint(slide.title)
        for slide in slide_deck.slides
        if _copy_fingerprint(slide.title)
    }
    required_middle = {"context", "evidence", "insight", "recommendation"}
    missing_middle = sorted(required_middle - unique_purposes)
    passed = (
        len(slide_deck.slides) >= 6
        and purposes[0] == "cover"
        and purposes[-1] == "conclusion"
        and len(unique_purposes) >= 6
        and not missing_middle
        and len(title_fingerprints) == len(slide_deck.slides)
    )
    return {
        "schemaVersion": "1.0.0",
        "name": "competition_story_arc",
        "status": "passed" if passed else "failed",
        "detail": (
            f"Deck uses {len(unique_purposes)} slide roles, starts with cover, ends with conclusion, and avoids repeated title claims."
            if passed
            else (
                f"Deck story arc is not competition-ready: roles={','.join(purposes)}, "
                f"missing={','.join(missing_middle) or 'none'}, uniqueTitles={len(title_fingerprints)}/{len(slide_deck.slides)}."
            )
        ),
    }


def _competition_copy_density_check(slide_deck: SlideDeck) -> dict[str, str]:
    issues: list[str] = []
    for slide in slide_deck.slides:
        visible_blocks = [
            block
            for block in slide.blocks
            if block.block_type not in {"image_placeholder", "chart_placeholder", "speaker_notes"}
        ]
        card_count = sum(1 for block in visible_blocks if block.block_type == "card")
        total_chars = sum(len(block.content.strip()) for block in visible_blocks)
        longest_block = max((len(block.content.strip()) for block in visible_blocks), default=0)
        if len(slide.title) > 88:
            issues.append(f"slide {slide.slide_index} title too long")
        if card_count > 6:
            issues.append(f"slide {slide.slide_index} has {card_count} cards")
        if longest_block > 260:
            issues.append(f"slide {slide.slide_index} block has {longest_block} chars")
        if total_chars > 900:
            issues.append(f"slide {slide.slide_index} has {total_chars} visible chars")
    return {
        "schemaVersion": "1.0.0",
        "name": "competition_copy_density",
        "status": "passed" if not issues else "failed",
        "detail": (
            "Visible copy stays within competition-presentation density limits."
            if not issues
            else f"Visible copy is too dense for a competition deck: {', '.join(issues[:8])}."
        ),
    }


def _competition_visual_variety_check(slide_deck: SlideDeck) -> dict[str, str]:
    archetypes = [slide.design_plan.composition_archetype for slide in slide_deck.slides]
    treatments = [slide.design_plan.image_treatment for slide in slide_deck.slides]
    motions = [slide.design_plan.motion_preset for slide in slide_deck.slides]
    signatures = [
        (
            slide.design_plan.composition_archetype,
            slide.design_plan.image_treatment,
            slide.design_plan.composition_variant,
        )
        for slide in slide_deck.slides
    ]
    rhythms = [slide.design_plan.composition_variant.split("-", 1)[0] for slide in slide_deck.slides]
    slide_count = len(slide_deck.slides)
    required_archetypes = 5 if slide_count >= 8 else 4 if slide_count >= 6 else min(3, slide_count)
    required_treatments = 3 if slide_count >= 6 else min(2, slide_count)
    required_motions = 3 if slide_count >= 6 else min(2, slide_count)
    required_signatures = max(1, round(slide_count * 0.85))
    required_rhythms = 3 if slide_count >= 6 else min(2, slide_count)
    no_adjacent_repeats = all(left != right for left, right in zip(archetypes, archetypes[1:]))
    passed = (
        len(set(archetypes)) >= required_archetypes
        and len(set(treatments)) >= required_treatments
        and len(set(motions)) >= required_motions
        and len(set(signatures)) >= required_signatures
        and len(set(rhythms)) >= required_rhythms
        and no_adjacent_repeats
    )
    return {
        "schemaVersion": "1.0.0",
        "name": "competition_visual_variety",
        "status": "passed" if passed else "failed",
        "detail": (
            f"Deck uses {len(set(archetypes))} composition archetypes, {len(set(signatures))} unique page signatures, {len(set(rhythms))} page rhythms, {len(set(treatments))} image treatments, and {len(set(motions))} motion presets."
            if passed
            else (
                f"Visual system lacks competition-level variety: archetypes {len(set(archetypes))}/{required_archetypes}, "
                f"signatures {len(set(signatures))}/{required_signatures}, rhythms {len(set(rhythms))}/{required_rhythms}, "
                f"treatments {len(set(treatments))}/{required_treatments}, motions {len(set(motions))}/{required_motions}, "
                f"adjacentDistinct={no_adjacent_repeats}."
            )
        ),
    }


def _competition_image_intent_check(slide_deck: SlideDeck) -> dict[str, str]:
    slide_count = len(slide_deck.slides)
    image_by_slide = {item.slide: item for item in slide_deck.image_plan}
    missing = [slide.slide_index for slide in slide_deck.slides if slide.slide_index not in image_by_slide]
    weak = [
        item.slide
        for item in slide_deck.image_plan
        if (
            not item.needs_image
            or len(item.prompt.strip()) < 36
            or len(item.search_query.strip()) < 16
            or len(item.purpose.strip()) < 24
        )
    ]
    image_types = {item.image_type for item in slide_deck.image_plan}
    queries = {_copy_fingerprint(item.search_query) for item in slide_deck.image_plan}
    required_types = 3 if slide_count >= 6 else min(2, slide_count)
    required_unique_queries = max(1, slide_count // 2)
    passed = (
        not missing
        and not weak
        and len(image_types) >= required_types
        and len(queries) >= required_unique_queries
    )
    return {
        "schemaVersion": "1.0.0",
        "name": "competition_image_intent",
        "status": "passed" if passed else "failed",
        "detail": (
            f"Every slide has a content-serving image plan with {len(image_types)} image roles and {len(queries)} distinct search intents."
            if passed
            else (
                f"Image plan is not competition-ready: missing={missing}, weak={weak[:8]}, "
                f"roles={len(image_types)}/{required_types}, queryVariety={len(queries)}/{required_unique_queries}."
            )
        ),
    }


def _award_grade_design_contract_check(slide_deck: SlideDeck) -> dict[str, str]:
    issues: list[str] = []
    image_by_slide = {item.slide: item for item in slide_deck.image_plan}
    for slide in slide_deck.slides:
        hierarchy_text = " | ".join(slide.design_plan.hierarchy).casefold()
        layers_text = " | ".join(slide.design_plan.visual_layers).casefold()
        rationale = slide.design_plan.rationale.casefold()
        image_item = image_by_slide.get(slide.slide_index)
        if "answer-first" not in hierarchy_text:
            issues.append(f"slide {slide.slide_index} missing answer-first hierarchy")
        if "single dominant focal point" not in hierarchy_text:
            issues.append(f"slide {slide.slide_index} missing single focal point")
        if "judge scan path" not in hierarchy_text or "judge scan path" not in rationale:
            issues.append(f"slide {slide.slide_index} missing judge scan path")
        if "proof before decoration" not in rationale:
            issues.append(f"slide {slide.slide_index} missing proof-before-decoration rationale")
        if "contrast" not in layers_text or "negative space" not in layers_text:
            issues.append(f"slide {slide.slide_index} missing contrast/negative-space layer")
        if "protected text zone" not in layers_text:
            issues.append(f"slide {slide.slide_index} missing protected text zone")
        if image_item is None:
            issues.append(f"slide {slide.slide_index} missing image plan")
        else:
            prompt = image_item.prompt.casefold()
            if "award-winning" not in prompt or "single focal" not in prompt:
                issues.append(f"slide {slide.slide_index} image prompt below award-grade")
    return {
        "schemaVersion": "1.0.0",
        "name": "award_grade_design_contract",
        "status": "passed" if not issues else "failed",
        "detail": (
            "Deck applies award-grade presentation rules: answer-first story, one focal point, judge scan path, proof before decoration, strong contrast, and protected text zones."
            if not issues
            else f"Award-grade design contract issues: {', '.join(issues[:10])}."
        ),
    }


def _copy_fingerprint(value: str) -> str:
    return re.sub(r"\W+", "", value.casefold())


def _html_frame_count(path: Path) -> int:
    return sum(
        1
        for class_value in re.findall(r'class="([^"]+)"', path.read_text(encoding="utf-8"))
        if "frame" in class_value.split()
    )


def _html_has_hyperframes_marker(path: Path) -> bool:
    html = path.read_text(encoding="utf-8")
    return (
        'name="generator" content="HyperFrames local renderer"' in html
        and 'data-hyperframes-renderer="local"' in html
        and 'data-motion-engine="HyperFrames"' in html
        and 'data-deck-contract="SlideDeck JSON"' in html
    )


def _html_visual_asset_count(path: Path) -> int:
    html = path.read_text(encoding="utf-8")
    return html.count('class="frame-asset"')


def _html_has_motion_marker(path: Path) -> bool:
    html = path.read_text(encoding="utf-8")
    return (
        'data-motion-engine="HyperFrames"' in html
        and "@keyframes asset-float" in html
        and "@keyframes block-rise" in html
        and "@keyframes reference-light-sweep" in html
        and "@media (prefers-reduced-motion: reduce)" in html
    )


def _html_has_reference_style_marker(path: Path) -> bool:
    html = path.read_text(encoding="utf-8")
    return (
        'data-reference-style="cinematic-full-bleed"' in html
        and ".frame-asset" in html
        and "position: absolute" in html
        and "object-fit: cover" in html
    )


def _html_page_plan_marker_count(path: Path) -> int:
    html = path.read_text(encoding="utf-8")
    if 'data-design-system="' not in html:
        return 0
    return len(re.findall(r'data-composition-archetype="[^"]+"[^>]+data-image-treatment="[^"]+"', html))


def _html_image_agent_marker_count(path: Path) -> int:
    html = path.read_text(encoding="utf-8")
    return len(re.findall(r'data-image-plan-type="[^"]+"[^>]+data-image-plan-purpose="[^"]+"', html))


def _html_composition_diversity(path: Path, slide_count: int) -> dict[str, object]:
    html = path.read_text(encoding="utf-8")
    archetypes = re.findall(r'data-composition-archetype="([^"]+)"', html)
    treatments = re.findall(r'data-image-treatment="([^"]+)"', html)
    no_adjacent_repeats = all(left != right for left, right in zip(archetypes, archetypes[1:]))
    required_archetypes = 3 if slide_count >= 6 else min(slide_count, 2)
    required_treatments = 2 if slide_count >= 3 else 1
    passed = (
        len(archetypes) == slide_count
        and len(treatments) == slide_count
        and len(set(archetypes)) >= required_archetypes
        and len(set(treatments)) >= required_treatments
        and no_adjacent_repeats
    )
    return {
        "passed": passed,
        "detail": (
            f"HTML uses {len(set(archetypes))} composition archetypes and "
            f"{len(set(treatments))} image treatments across {slide_count} slides; "
            f"adjacent archetypes are {'distinct' if no_adjacent_repeats else 'repeated'}."
        ),
    }


def _html_explainer_metrics(path: Path, slide_count: int) -> dict[str, object]:
    html = path.read_text(encoding="utf-8")
    modes = re.findall(
        r'<div class="explainer-layer" data-explanation-mode="([^"]+)"', html
    )
    required_modes = 3 if slide_count >= 6 else min(slide_count, 2)
    return {
        "count": len(modes),
        "coverage_passed": len(modes) == slide_count,
        "diversity_passed": len(modes) == slide_count and len(set(modes)) >= required_modes,
        "detail": (
            f"HTML uses {len(set(modes))} explanation modes across {len(modes)} "
            f"explainer layers; expected at least {required_modes} modes across {slide_count} slides."
        ),
    }


def _safe_path(root: Path, raw_path: str) -> Path | None:
    path = Path(raw_path)
    candidates = [path] if path.is_absolute() else [path, root / path]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root)
        except (OSError, ValueError):
            continue
        if resolved.is_file():
            return resolved
    return None


def _pptx_slide_count(path: Path) -> int:
    with zipfile.ZipFile(path) as archive:
        return sum(
            1
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )


def _missing_pptx_relationship_parts(path: Path, slide_count: int) -> list[str]:
    expected = {
        "_rels/.rels",
        "ppt/_rels/presentation.xml.rels",
        "ppt/slideMasters/_rels/slideMaster1.xml.rels",
        "ppt/slideLayouts/_rels/slideLayout7.xml.rels",
        "ppt/notesMasters/_rels/notesMaster1.xml.rels",
    }
    expected.update(
        f"ppt/slides/_rels/slide{index}.xml.rels"
        for index in range(1, slide_count + 1)
    )
    expected.update(
        f"ppt/notesSlides/_rels/notesSlide{index}.xml.rels"
        for index in range(1, slide_count + 1)
    )
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
    return sorted(expected - names)


def _pptx_notes_slide_count(path: Path) -> int:
    with zipfile.ZipFile(path) as archive:
        return sum(
            1
            for name in archive.namelist()
            if name.startswith("ppt/notesSlides/notesSlide") and name.endswith(".xml")
        )


def _pptx_design_marker_count(path: Path) -> int:
    count = 0
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("ppt/slides/slide") or not name.endswith(".xml"):
                continue
            xml = archive.read(name).decode("utf-8", errors="ignore")
            if 'prst="roundRect"' in xml:
                count += 1
            if "EVIDENCE VIEW" in xml or "SECTION " in xml:
                count += 1
            if "Design Shape" in xml:
                count += 1
    return count


def _pptx_has_native_powerpoint_scaffold(path: Path) -> bool:
    required = {
        "ppt/presProps.xml",
        "ppt/viewProps.xml",
        "ppt/tableStyles.xml",
        "ppt/slideMasters/slideMaster1.xml",
        "ppt/slideLayouts/slideLayout7.xml",
        "ppt/notesMasters/notesMaster1.xml",
        "ppt/notesMasters/_rels/notesMaster1.xml.rels",
        "ppt/theme/theme1.xml",
        "ppt/theme/theme2.xml",
    }
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if not required <= names:
            return False
        presentation_rels = archive.read("ppt/_rels/presentation.xml.rels").decode(
            "utf-8", errors="ignore"
        )
        master = archive.read("ppt/slideMasters/slideMaster1.xml").decode(
            "utf-8", errors="ignore"
        )
    layout_ids = [int(value) for value in re.findall(r'<p:sldLayoutId id="(\d+)"', master)]
    return (
        bool(layout_ids)
        and all(value >= 2_147_483_648 for value in layout_ids)
        and "relationships/notesMaster" in presentation_rels
        and "relationships/presProps" in presentation_rels
        and "relationships/viewProps" in presentation_rels
        and "relationships/tableStyles" in presentation_rels
    )


def _pptx_media_count(path: Path) -> int:
    with zipfile.ZipFile(path) as archive:
        return sum(1 for name in archive.namelist() if name.startswith("ppt/media/"))


def _pptx_full_bleed_visual_count(path: Path) -> int:
    count = 0
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("ppt/slides/slide") or not name.endswith(".xml"):
                continue
            xml = archive.read(name).decode("utf-8", errors="ignore")
            if (
                "Reference Full-Bleed Visual" in xml
                and '<a:off x="0" y="0"/>' in xml
                and f'<a:ext cx="{12192000}" cy="{6858000}"/>' in xml
            ):
                count += 1
    return count


def _pptx_page_plan_marker_count(path: Path) -> int:
    count = 0
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("ppt/slides/slide") or not name.endswith(".xml"):
                continue
            xml = archive.read(name).decode("utf-8", errors="ignore")
            if "Page Plan " in xml:
                count += 1
    return count


def _pptx_image_agent_marker_count(path: Path) -> int:
    count = 0
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("ppt/slides/slide") or not name.endswith(".xml"):
                continue
            xml = archive.read(name).decode("utf-8", errors="ignore")
            if "Image Agent " in xml:
                count += 1
    return count


def _pptx_explainer_layer_count(path: Path) -> int:
    count = 0
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("ppt/slides/slide") or not name.endswith(".xml"):
                continue
            xml = archive.read(name).decode("utf-8", errors="ignore")
            if "Page Explainer " in xml:
                count += 1
    return count


def _pptx_text_autofit_metrics(path: Path) -> dict[str, int | bool]:
    total = 0
    fitted = 0
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("ppt/slides/slide") or not name.endswith(".xml"):
                continue
            xml = archive.read(name).decode("utf-8", errors="ignore")
            total += xml.count("<p:txBody>")
            fitted += xml.count("<a:normAutofit")
    return {"total": total, "fitted": fitted, "passed": total > 0 and fitted == total}


def _pptx_text_anchor_issues(path: Path) -> list[str]:
    allowed = {"t", "ctr", "b", "just", "dist"}
    issues: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("ppt/slides/slide") or not name.endswith(".xml"):
                continue
            slide_match = re.search(r"slide(\d+)\.xml$", name)
            slide_label = f"slide {slide_match.group(1)}" if slide_match else name
            xml = archive.read(name).decode("utf-8", errors="ignore")
            for value in re.findall(r"<a:bodyPr\b[^>]*\banchor=\"([^\"]+)\"", xml):
                if value not in allowed:
                    issues.append(f"{slide_label} anchor={value}")
    return issues[:12]


def _pptx_font_family_contract_issues(path: Path) -> list[str]:
    issues: list[str] = []
    required = {
        "latin": "Times New Roman",
        "ea": "SimSun",
        "cs": "Times New Roman",
    }
    banned = ("Aptos", "Calibri", "Microsoft YaHei", "微软雅黑", "黑体", "Arial")
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("ppt/slides/slide") or not name.endswith(".xml"):
                continue
            slide_match = re.search(r"slide(\d+)\.xml$", name)
            slide_label = f"slide {slide_match.group(1)}" if slide_match else name
            xml = archive.read(name).decode("utf-8", errors="ignore")
            for shape in re.findall(r"<p:sp>.*?</p:sp>", xml, flags=re.DOTALL):
                if "<a:t>" not in shape:
                    continue
                name_match = re.search(r'<p:cNvPr id="\d+" name="([^"]+)"', shape)
                shape_name = name_match.group(1) if name_match else "text shape"
                if not (
                    shape_name.startswith("Text ")
                    or shape_name.startswith("Card ")
                    or shape_name.startswith("Page ")
                ):
                    continue
                for banned_font in banned:
                    if banned_font in shape:
                        issues.append(f"{slide_label} {shape_name} uses banned font {banned_font}")
                for slot, expected in required.items():
                    if f'<a:{slot} typeface="{expected}"' not in shape:
                        issues.append(f"{slide_label} {shape_name} missing {slot}={expected}")
    return issues[:12]


def _pptx_foreground_bounds_issues(path: Path) -> list[str]:
    issues: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("ppt/slides/slide") or not name.endswith(".xml"):
                continue
            slide_match = re.search(r"slide(\d+)\.xml$", name)
            slide_label = f"slide {slide_match.group(1)}" if slide_match else name
            xml = archive.read(name).decode("utf-8", errors="ignore")
            for shape in re.findall(r"<p:sp>.*?</p:sp>", xml, flags=re.DOTALL):
                name_match = re.search(r'<p:cNvPr id="\d+" name="([^"]+)"', shape)
                if not name_match:
                    continue
                shape_name = name_match.group(1)
                if not (shape_name.startswith("Text ") or shape_name.startswith("Card ")):
                    continue
                box_match = re.search(
                    r'<a:off x="(-?\d+)" y="(-?\d+)"/><a:ext cx="(-?\d+)" cy="(-?\d+)"/>',
                    shape,
                )
                if not box_match:
                    issues.append(f"{slide_label} {shape_name} missing geometry")
                    continue
                x, y, cx, cy = [int(value) for value in box_match.groups()]
                if (
                    x < FOREGROUND_SAFE_X
                    or y < FOREGROUND_SAFE_TOP
                    or cx <= 0
                    or cy <= 0
                    or x + cx > SLIDE_CX - FOREGROUND_SAFE_X
                    or y + cy > SLIDE_CY - FOREGROUND_SAFE_BOTTOM
                ):
                    issues.append(f"{slide_label} {shape_name}")
    return issues[:12]


def _visual_asset_source_quality(render_dir: Path, expected_slide_count: int) -> dict[str, object]:
    assets_dir = render_dir / "assets"
    issues: list[str] = []
    usable = 0
    accepted = {
        "bing_image_search",
        "wikipedia_page_image",
        "wikimedia_commons_search",
        "openverse_search",
        "ai_fallback",
        "free_ai_fallback",
    }
    for slide_index in range(1, expected_slide_count + 1):
        sidecar = assets_dir / f"slide-{slide_index}-asset.json"
        if not sidecar.exists():
            issues.append(f"slide {slide_index} missing asset sidecar")
            continue
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            issues.append(f"slide {slide_index} unreadable asset sidecar")
            continue
        source_type = str(data.get("sourceType") or "")
        file_name = str(data.get("fileName") or "")
        asset_path = assets_dir / file_name
        if source_type not in accepted:
            issues.append(f"slide {slide_index} source={source_type or 'missing'}")
            continue
        mime_type = str(data.get("mimeType") or "").casefold()
        if mime_type not in {"image/png", "image/jpeg"}:
            issues.append(f"slide {slide_index} mime={mime_type or 'missing'}")
            continue
        if not file_name or not asset_path.exists() or asset_path.stat().st_size <= 0:
            issues.append(f"slide {slide_index} missing image file")
            continue
        usable += 1
    return {"passed": usable >= expected_slide_count and not issues, "usable": usable, "issues": issues[:12]}


def _visual_asset_uniqueness(render_dir: Path, expected_slide_count: int) -> dict[str, object]:
    assets_dir = render_dir / "assets"
    issues: list[str] = []
    slides_by_hash: dict[str, list[int]] = {}
    for slide_index in range(1, expected_slide_count + 1):
        sidecar = assets_dir / f"slide-{slide_index}-asset.json"
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            issues.append(f"slide {slide_index} missing or unreadable asset sidecar")
            continue
        file_name = str(data.get("fileName") or "")
        if not file_name or Path(file_name).name != file_name:
            issues.append(f"slide {slide_index} has an invalid image file name")
            continue
        asset_path = assets_dir / file_name
        try:
            content = asset_path.read_bytes()
        except OSError:
            issues.append(f"slide {slide_index} image file is unreadable")
            continue
        if not content:
            issues.append(f"slide {slide_index} image file is empty")
            continue
        digest = hashlib.sha256(content).hexdigest()
        slides_by_hash.setdefault(digest, []).append(slide_index)

    for slide_indexes in slides_by_hash.values():
        if len(slide_indexes) > 1:
            joined = ", ".join(str(index) for index in slide_indexes)
            issues.append(f"slides {joined} reuse the identical image")
    unique = len(slides_by_hash)
    return {
        "passed": unique >= expected_slide_count and not issues,
        "unique": unique,
        "issues": issues[:12],
    }


def _pptx_text_fit_issues(path: Path) -> list[str]:
    issues: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("ppt/slides/slide") or not name.endswith(".xml"):
                continue
            slide_match = re.search(r"slide(\d+)\.xml$", name)
            slide_label = f"slide {slide_match.group(1)}" if slide_match else name
            xml = archive.read(name).decode("utf-8", errors="ignore")
            for shape in re.findall(r"<p:sp>.*?</p:sp>", xml, flags=re.DOTALL):
                name_match = re.search(r'<p:cNvPr id="\d+" name="([^"]+)"', shape)
                if not name_match:
                    continue
                shape_name = name_match.group(1)
                if not (shape_name.startswith("Text ") or shape_name.startswith("Card ")):
                    continue
                box_match = re.search(
                    r'<a:off x="(-?\d+)" y="(-?\d+)"/><a:ext cx="(-?\d+)" cy="(-?\d+)"/>',
                    shape,
                )
                if not box_match:
                    continue
                _x, _y, cx, cy = [int(value) for value in box_match.groups()]
                font_sizes = [int(value) for value in re.findall(r'<a:rPr\b[^>]*\bsz="(\d+)"', shape)]
                font_size = min(font_sizes) if font_sizes else 1200
                body_pr = re.search(r"<a:bodyPr\b([^>]*)>", shape)
                inset_x = _xml_int_attr(body_pr.group(1), "lIns", 100000) if body_pr else 100000
                inset_y = _xml_int_attr(body_pr.group(1), "tIns", 60000) if body_pr else 60000
                text = _pptx_shape_text(shape)
                if not text:
                    continue
                role = "card" if shape_name.startswith("Card ") else "title" if font_size >= 2200 else "body"
                required = _estimated_required_text_height(text, cx, font_size, role, inset_x, inset_y)
                if required > int(cy * 1.08):
                    issues.append(f"{slide_label} {shape_name} needs {required}emu in {cy}emu")
    return issues[:12]


def _xml_int_attr(attrs: str, name: str, fallback: int) -> int:
    match = re.search(rf'\b{name}="(-?\d+)"', attrs)
    if not match:
        return fallback
    try:
        return int(match.group(1))
    except ValueError:
        return fallback


def _pptx_shape_text(shape_xml: str) -> str:
    parts = [html.unescape(part) for part in re.findall(r"<a:t>(.*?)</a:t>", shape_xml, flags=re.DOTALL)]
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _estimated_required_text_height(
    text: str,
    cx: int,
    font_size: int,
    role: str,
    inset_x: int,
    inset_y: int,
) -> int:
    usable_cx = max(300000, cx - inset_x * 2)
    point_size = max(8.0, font_size / 100.0)
    avg_weight_emu = point_size * EMU_PER_POINT * 0.56
    capacity = max(10, int((usable_cx * 2) / max(avg_weight_emu, 1.0)))
    weight = sum(2 if "\u3400" <= character <= "\u9fff" else 1 for character in text)
    lines = max(1, (weight + capacity - 1) // capacity)
    line_height = int(point_size * EMU_PER_POINT * (1.16 if role == "title" else 1.28))
    return lines * line_height + inset_y * 2


def _pptx_visible_copy_issues(path: Path) -> list[str]:
    text_parts: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                text_parts.append(archive.read(name).decode("utf-8", errors="ignore"))
    return _internal_copy_issues("\n".join(text_parts))


def _pptx_text_encoding_issues(path: Path) -> list[str]:
    text_parts: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                text_parts.append(archive.read(name).decode("utf-8", errors="replace"))
    return _text_encoding_issues("\n".join(text_parts))


def _html_visible_copy_issues(path: Path) -> list[str]:
    return _internal_copy_issues(path.read_text(encoding="utf-8"))


def _text_encoding_issues(value: str) -> list[str]:
    issues: list[str] = []
    if "\ufffd" in value:
        issues.append("Unicode replacement character")
    if re.search(r"\?{3,}", value):
        issues.append("repeated question marks")
    if re.search(r"(?:锛|鐢|绗|闁|閳|鈥|€){2,}", value) or re.search(
        r"(?:涓|婁|竴|椤|璺|宠|浆|鍒|扮||骞|荤|伅|鐗|囧||鑸|璁|茬|){4,}",
        value,
    ):
        issues.append("mojibake glyph cluster")
    return issues


def _internal_copy_issues(value: str) -> list[str]:
    patterns = {
        "numbered page prefix": r"第\s*\d+\s*页\s*[：:]",
        "section scaffold prefix": r"第\s*[零〇一二三四五六七八九十百千万两\d]+\s*(?:部分|章节|章|节|步|阶段)\s*[：:]",
        "numbered slide prefix": r"Slide\s+\d+\s*[：:]",
        "原文线索": r"原文线索\s*[：:]",
        "页面作用": r"页面作用\s*[：:]",
        "可引用证据": r"可引用证据\s*[：:]",
        "可验证证据线索": r"可验证证据线索\s*[：:]",
        "行动优先级": r"行动优先级\s*[零〇一二三四五六七八九十百千万两\d]+\s*[：:]",
        "叙事路径": r"叙事路径\s*[：:]",
        "核心判断": r"核心判断\s*[：:]",
        "本页结论": r"本页结论\s*[：:]",
        "source claim": r"Source claim\s*[：:]",
        "slide role": r"Slide role\s*[：:]",
        "traceable evidence": r"Traceable evidence\s*[：:]",
        "useful excerpt": r"Useful excerpt\s*[：:]",
        "core message": r"Core message\s*[：:]",
        "what to expect": r"What to expect\s*[：:]",
        "main takeaway": r"Main takeaway\s*[：:]",
    }
    return [label for label, pattern in patterns.items() if re.search(pattern, value, re.IGNORECASE)]
