from __future__ import annotations

import hashlib
import re

from ai_ppt_contracts import OutlineDecision, SlideDeck, VisualDirectionDecision
from app.services.image_agent import build_image_plan


_PURPOSE_ARCHETYPES: dict[str, tuple[str, ...]] = {
    "cover": ("cinematic_hero", "editorial_cover", "architectural_cover"),
    "agenda": ("chapter_index", "process_ribbon", "editorial_split"),
    "context": ("editorial_split", "diagonal_story", "proof_mosaic"),
    "insight": ("statement_focus", "editorial_split", "diagonal_story"),
    "evidence": ("data_landscape", "proof_mosaic", "split_comparison"),
    "framework": ("system_map", "process_ribbon", "split_comparison"),
    "recommendation": ("priority_stack", "process_ribbon", "statement_focus"),
    "conclusion": ("closing_echo", "manifesto_close", "future_horizon"),
}

_ARCHETYPE_TREATMENTS: dict[str, tuple[str, ...]] = {
    "cinematic_hero": ("full_bleed", "atmospheric_backdrop"),
    "editorial_cover": ("split_crop", "masked_window"),
    "architectural_cover": ("masked_window", "full_bleed"),
    "chapter_index": ("atmospheric_backdrop", "evidence_strip"),
    "editorial_split": ("split_crop", "masked_window"),
    "diagonal_story": ("layered_cutout", "full_bleed"),
    "statement_focus": ("atmospheric_backdrop", "masked_window"),
    "proof_mosaic": ("layered_cutout", "evidence_strip"),
    "data_landscape": ("evidence_strip", "split_crop"),
    "process_ribbon": ("evidence_strip", "atmospheric_backdrop"),
    "system_map": ("masked_window", "layered_cutout"),
    "split_comparison": ("split_crop", "evidence_strip"),
    "priority_stack": ("layered_cutout", "masked_window"),
    "closing_echo": ("atmospheric_backdrop", "full_bleed"),
    "manifesto_close": ("full_bleed", "masked_window"),
    "future_horizon": ("full_bleed", "split_crop"),
}

_ARCHETYPE_MOTION: dict[str, str] = {
    "cinematic_hero": "cinematic_reveal",
    "editorial_cover": "editorial_wipe",
    "architectural_cover": "depth_parallax",
    "chapter_index": "sequence_build",
    "editorial_split": "editorial_wipe",
    "diagonal_story": "depth_parallax",
    "statement_focus": "cinematic_reveal",
    "proof_mosaic": "depth_parallax",
    "data_landscape": "evidence_reveal",
    "process_ribbon": "sequence_build",
    "system_map": "diagram_orbit",
    "split_comparison": "evidence_reveal",
    "priority_stack": "sequence_build",
    "closing_echo": "closing_resolve",
    "manifesto_close": "closing_resolve",
    "future_horizon": "cinematic_reveal",
}


def assemble_slide_deck(
    *,
    outline: OutlineDecision,
    outline_version: int,
    visual: VisualDirectionDecision,
    visual_direction_version: int,
) -> SlideDeck:
    if visual.selected_direction_id is None:
        raise ValueError("visual direction must be selected")
    selected = next(
        direction
        for direction in visual.directions
        if direction.direction_id == visual.selected_direction_id
    )
    design_system_id, design_seed = _design_system_identity(outline, selected.direction_id)
    slides = []
    previous_archetype: str | None = None
    seen_title_fingerprints: set[str] = set()
    for slide in outline.slides:
        slide_title = _unique_slide_title(slide, outline.language, seen_title_fingerprints)
        design_plan = _plan_slide_design(
            outline=outline,
            slide=slide,
            direction_id=selected.direction_id,
            design_seed=design_seed,
            previous_archetype=previous_archetype,
        )
        previous_archetype = design_plan["compositionArchetype"]
        labels = _block_labels(outline.language)
        blocks = [
            {
                "schemaVersion": "1.0.0",
                "blockId": f"slide-{slide.slide_index}-headline",
                "blockType": "headline",
                "content": slide_title,
                "role": labels["headline"],
            },
        ]
        if slide.subtitle:
            blocks.append(
                {
                    "schemaVersion": "1.0.0",
                    "blockId": f"slide-{slide.slide_index}-subtitle",
                    "blockType": "subtitle",
                    "content": slide.subtitle,
                    "role": labels["subtitle"],
                }
            )
        blocks.append(
            {
                "schemaVersion": "1.0.0",
                "blockId": f"slide-{slide.slide_index}-key-point",
                "blockType": "body",
                "content": slide.key_point,
                "role": labels["takeaway"],
            }
        )
        blocks.extend(
            {
                "schemaVersion": "1.0.0",
                "blockId": f"slide-{slide.slide_index}-point-{point_index}",
                "blockType": "card" if point_index <= 3 else "body",
                "content": point,
                "role": f'{labels["point"]} {point_index}',
            }
            for point_index, point in enumerate(slide.talking_points, start=1)
        )
        blocks.append(
            {
                "schemaVersion": "1.0.0",
                "blockId": f"slide-{slide.slide_index}-asset",
                "blockType": "image_placeholder",
                "content": ", ".join(slide.required_assets) if slide.required_assets else slide.visual_intent,
                "role": labels["asset"],
            }
        )
        if slide.citation_ids:
            blocks.append(
                {
                    "schemaVersion": "1.0.0",
                    "blockId": f"slide-{slide.slide_index}-chart",
                    "blockType": "chart_placeholder",
                    "content": ", ".join(slide.citation_ids),
                    "role": labels["evidence"],
                }
            )
        slides.append(
            {
                "schemaVersion": "1.0.0",
                "slideId": f"{outline.project_id}-slide-{slide.slide_index}",
                "slideIndex": slide.slide_index,
                "title": slide_title,
                "subtitle": slide.subtitle,
                "purpose": slide.purpose,
                "layout": slide.suggested_layout,
                "visualIntent": slide.visual_intent,
                "designPlan": design_plan,
                "blocks": blocks,
                "speakerNotes": slide.speaker_notes_draft,
            }
        )

    image_plan = build_image_plan(
        outline=outline,
        deck_slides=slides,
        direction_name=selected.name,
    )

    return SlideDeck(
        schemaVersion="1.0.0",
        projectId=outline.project_id,
        outlineVersion=outline_version,
        visualDirectionVersion=visual_direction_version,
        language=outline.language,
        title=outline.slides[0].title,
        theme={
            "schemaVersion": "1.0.0",
            "directionId": selected.direction_id,
            "name": selected.name,
            "palette": selected.palette,
            "typography": selected.typography,
            "textureLayer": selected.texture_layer,
            "layoutPrinciples": selected.layout_principles,
            "designSystemId": design_system_id,
            "designSeed": design_seed,
        },
        slides=slides,
        imagePlan=image_plan,
        exportTargets=["pptx", "hyperframes_html"],
    )


def repair_slide_deck_for_quality(
    *,
    deck: SlideDeck,
    failed_check_names: list[str],
    repair_pass: int = 1,
) -> tuple[SlideDeck, list[str]]:
    """Create a new canonical deck version that addresses deterministic QA failures.

    The repair pass only compresses or reorganizes content already present in the
    canonical deck. It never invents presentation claims, so the outline remains
    the single source of truth for both PPTX and HyperFrames output.
    """

    failed = {name.casefold() for name in failed_check_names}
    text_repair = any(
        marker in name
        for name in failed
        for marker in (
            "text_",
            "copy",
            "foreground_bounds",
            "font_family",
            "page_delivery",
            "encoding_integrity",
        )
    )
    visual_repair = any(
        marker in name
        for name in failed
        for marker in (
            "visual_variety",
            "composition_diversity",
            "explanation_mode_diversity",
            "page_plan",
            "explainer_layers",
            "motion",
            "design_markers",
        )
    )
    image_repair = any(
        marker in name
        for name in failed
        for marker in (
            "visual_asset",
            "image_agent",
            "image_intent",
            "visual_assets",
            "reference_full_bleed",
        )
    )
    if not (text_repair or visual_repair or image_repair):
        text_repair = visual_repair = image_repair = True

    payload = deck.model_dump(by_alias=True, mode="json")
    language = deck.language
    title_limit = 34 if language == "zh" else 62
    subtitle_limit = 58 if language == "zh" else 104
    body_limit = 78 if language == "zh" else 142
    card_limit = 56 if language == "zh" else 108
    if repair_pass >= 2:
        title_limit = 30 if language == "zh" else 54
        subtitle_limit = 48 if language == "zh" else 88
        body_limit = 64 if language == "zh" else 118
        card_limit = 46 if language == "zh" else 92

    previous_archetype: str | None = None
    for slide_payload in payload["slides"]:
        slide_index = int(slide_payload["slideIndex"])
        if text_repair:
            repaired_title = _repair_visible_copy(slide_payload["title"], title_limit)
            slide_payload["title"] = repaired_title
            if slide_payload.get("subtitle"):
                slide_payload["subtitle"] = _repair_visible_copy(
                    slide_payload["subtitle"], subtitle_limit
                )
            seen_visible: set[str] = set()
            repaired_blocks: list[dict] = []
            card_count = 0
            for block in slide_payload["blocks"]:
                block_type = block["blockType"]
                if block_type == "headline":
                    block["content"] = repaired_title
                elif block_type == "subtitle":
                    block["content"] = _repair_visible_copy(
                        block["content"], subtitle_limit
                    )
                elif block_type in {"body", "card"}:
                    if block_type == "card":
                        card_count += 1
                        if card_count > (3 if repair_pass >= 2 else 4):
                            continue
                    block["content"] = _repair_visible_copy(
                        block["content"], card_limit if block_type == "card" else body_limit
                    )
                    fingerprint = _title_fingerprint(block["content"])
                    if fingerprint and fingerprint in seen_visible:
                        continue
                    if fingerprint:
                        seen_visible.add(fingerprint)
                repaired_blocks.append(block)
            slide_payload["blocks"] = repaired_blocks
            slide_payload["designPlan"]["contentDensity"] = (
                "sparse" if repair_pass >= 2 else "balanced"
            )

        if visual_repair:
            purpose = str(slide_payload["purpose"])
            pool = _PURPOSE_ARCHETYPES[purpose]
            offset = (slide_index + repair_pass) % len(pool)
            archetype = pool[offset]
            if archetype == previous_archetype:
                archetype = next(item for item in pool if item != previous_archetype)
            plan = slide_payload["designPlan"]
            plan["compositionArchetype"] = archetype
            plan["compositionVariant"] = f"quality-repair-{repair_pass}-{slide_index % 3 + 1}"
            treatments = _ARCHETYPE_TREATMENTS[archetype]
            plan["imageTreatment"] = treatments[(slide_index + repair_pass) % len(treatments)]
            plan["motionPreset"] = _ARCHETYPE_MOTION[archetype]
            plan["explanationMode"] = (
                "hero_photo",
                "concept_diagram",
                "process_diagram",
                "data_evidence",
                "comparison_visual",
                "annotated_image",
                "summary_map",
            )[(slide_index + repair_pass) % 7]
            previous_archetype = archetype
        else:
            previous_archetype = slide_payload["designPlan"]["compositionArchetype"]

    if text_repair:
        payload["title"] = payload["slides"][0]["title"]

    if image_repair:
        for item, slide_payload in zip(payload["imagePlan"], payload["slides"], strict=True):
            page_subject = " ".join(
                part
                for part in (
                    slide_payload["title"],
                    slide_payload["visualIntent"],
                    slide_payload["purpose"],
                )
                if part
            )
            item["searchQuery"] = _clip_text(
                f'{page_subject} {item["searchQuery"]}', 180
            )
            item["prompt"] = _clip_text(
                f'{page_subject}. {item["prompt"]}. No text, no watermark, presentation-ready.',
                360,
            )

    repairs: list[str] = []
    if text_repair:
        repairs.append("safe_copy_and_density")
    if visual_repair:
        repairs.append("page_composition_and_motion")
    if image_repair:
        repairs.append("page_specific_image_intent")
    return SlideDeck(**payload), repairs


def _repair_visible_copy(value: str, limit: int) -> str:
    cleaned = _strip_outline_scaffold_label(str(value))
    cleaned = cleaned.replace("\ufffd", "")
    cleaned = re.sub(r"\?{4,}", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = re.sub(r"\s+", " ", str(value)).strip()
    return _clip_text(cleaned, limit)


def _unique_slide_title(slide, language: str, seen_fingerprints: set[str]) -> str:
    base = _clip_text(str(slide.title).strip(), 72 if language == "zh" else 96)
    if _low_information_title(base):
        qualifier = _duplicate_title_qualifier(slide, language)
        fallback = _purpose_title_qualifier(str(slide.purpose), language)
        separator = _title_separator(fallback, language)
        if _low_information_title(qualifier):
            qualifier = str(slide.slide_index)
        base = _clip_text(
            f"{fallback}{separator}{qualifier}",
            72 if language == "zh" else 96,
        )
    fingerprint = _title_fingerprint(base)
    if fingerprint and fingerprint not in seen_fingerprints:
        seen_fingerprints.add(fingerprint)
        return base

    qualifier = _duplicate_title_qualifier(slide, language)
    separator = _title_separator(base, language)
    candidate = _clip_text(f"{base}{separator}{qualifier}", 72 if language == "zh" else 96)
    candidate_fingerprint = _title_fingerprint(candidate)
    if candidate_fingerprint in seen_fingerprints:
        fallback = _purpose_title_qualifier(str(slide.purpose), language)
        candidate = _clip_text(
            f"{base}{separator}{fallback} {slide.slide_index}" if separator == ": " else f"{base}{separator}{fallback}{slide.slide_index}",
            72 if language == "zh" else 96,
        )
        candidate_fingerprint = _title_fingerprint(candidate)
    if candidate_fingerprint:
        seen_fingerprints.add(candidate_fingerprint)
    return candidate


def _duplicate_title_qualifier(slide, language: str) -> str:
    candidates = [
        str(slide.key_point),
        *(str(point) for point in slide.talking_points),
        str(slide.subtitle or ""),
    ]
    for candidate in candidates:
        cleaned = _compact_diagram_label(candidate)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t\r\n，。；：、,:;-—–")
        if cleaned and _title_fingerprint(cleaned) != _title_fingerprint(str(slide.title)):
            return _clip_text(cleaned, 18 if language == "zh" else 36)
    return _purpose_title_qualifier(str(slide.purpose), language)


def _purpose_title_qualifier(purpose: str, language: str) -> str:
    if language == "zh":
        return {
            "cover": "封面主张",
            "agenda": "汇报路径",
            "context": "背景边界",
            "insight": "核心洞察",
            "evidence": "证据核验",
            "framework": "机制框架",
            "recommendation": "行动优先级",
            "conclusion": "结论下一步",
        }.get(purpose, "关键判断")
    return {
        "cover": "Cover Claim",
        "agenda": "Roadmap",
        "context": "Context",
        "insight": "Insight",
        "evidence": "Evidence",
        "framework": "Framework",
        "recommendation": "Action Priority",
        "conclusion": "Next Step",
    }.get(purpose, "Key Claim")


def _title_separator(title: str, language: str) -> str:
    return "：" if language == "zh" or re.search(r"[\u3400-\u9fff]", title) else ": "


def _title_fingerprint(value: str) -> str:
    return re.sub(r"\W+", "", value.casefold())


def _low_information_title(value: str) -> bool:
    compact = _title_fingerprint(value)
    return not compact or len(value.strip()) < 4 or compact in {"ppt", "ai", "deck", "slide"}


def _block_labels(language: str) -> dict[str, str]:
    if language == "zh":
        return {
            "headline": "enterprise headline",
            "subtitle": "enterprise context",
            "takeaway": "decision takeaway",
            "point": "evidence/action cue",
            "structure": "enterprise structure visual",
            "asset": "content-serving visual asset",
            "evidence": "source trace / evidence anchor",
        }
    return {
        "headline": "enterprise headline",
        "subtitle": "enterprise context",
        "takeaway": "decision takeaway",
        "point": "evidence/action cue",
        "structure": "enterprise structure visual",
        "asset": "content-serving visual asset",
        "evidence": "source trace / evidence anchor",
    }


def _design_system_identity(outline: OutlineDecision, direction_id: str) -> tuple[str, int]:
    content = "|".join(
        [
            outline.project_id,
            direction_id,
            outline.deck_type,
            outline.audience,
            *(slide.title for slide in outline.slides),
            *(slide.key_point for slide in outline.slides),
        ]
    )
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"{direction_id}-{digest[:12]}", int(digest[:8], 16) % 2_147_483_648


def _plan_slide_design(
    *,
    outline: OutlineDecision,
    slide,
    direction_id: str,
    design_seed: int,
    previous_archetype: str | None,
) -> dict:
    content = " ".join(
        [
            slide.title,
            slide.subtitle or "",
            slide.key_point,
            *slide.talking_points,
            slide.visual_intent,
            *slide.required_assets,
        ]
    )
    token = _stable_token(
        f"{design_seed}|{direction_id}|{slide.slide_index}|{slide.purpose}|{content}"
    )
    pool = _PURPOSE_ARCHETYPES[str(slide.purpose)]
    archetype = _content_led_archetype(slide, content) or pool[token % len(pool)]
    if archetype == previous_archetype:
        alternatives = [item for item in pool if item != previous_archetype]
        archetype = alternatives[token % len(alternatives)]

    treatments = _ARCHETYPE_TREATMENTS[archetype]
    image_treatment = treatments[(token // 7) % len(treatments)]
    asset_role = _asset_role(slide, archetype)
    density = _content_density(slide)
    explanation_mode = _explanation_mode(slide, archetype, content)
    diagram_labels = _diagram_labels(slide)
    visual_brief = _visual_brief(slide, diagram_labels)
    variant_axis = ("left-anchor", "right-anchor", "center-axis", "asymmetric-grid")[(token // 13) % 4]
    return {
        "schemaVersion": "1.0.0",
        "compositionArchetype": archetype,
        "compositionVariant": f"{variant_axis}-{(token % 3) + 1}",
        "imageTreatment": image_treatment,
        "assetRole": asset_role,
        "assetQuery": _page_asset_query(outline, slide, asset_role, visual_brief),
        "contentDensity": density,
        "hierarchy": _award_grade_hierarchy(_hierarchy_for(archetype, density), slide),
        "visualLayers": _award_grade_visual_layers(
            _visual_layers_for(image_treatment, archetype, explanation_mode)
        ),
        "explanationMode": explanation_mode,
        "visualBrief": visual_brief,
        "diagramLabels": diagram_labels,
        "motionPreset": _ARCHETYPE_MOTION[archetype],
        "rationale": _award_grade_rationale(
            _design_rationale(slide, archetype, image_treatment, density, outline.language),
            outline.language,
        ),
    }


def _stable_token(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], 16)


def _content_led_archetype(slide, content: str) -> str | None:
    if slide.purpose in {"cover", "agenda", "conclusion"}:
        return None
    lowered = content.lower()
    comparison = (" vs ", "versus", "compare", "comparison", "对比", "比较", "差异", "区别")
    sequence = ("first", "second", "then", "finally", "step", "phase", "首先", "其次", "然后", "阶段", "步骤", "流程")
    numeric = _has_quantitative_signal(content)
    if any(marker in lowered for marker in comparison):
        return "split_comparison"
    if slide.purpose == "evidence" and numeric:
        return "data_landscape"
    if slide.purpose == "framework":
        return "process_ribbon" if any(marker in lowered for marker in sequence) else "system_map"
    if any(marker in lowered for marker in sequence) and len(slide.talking_points) >= 3:
        return "process_ribbon"
    if slide.purpose == "evidence":
        return "proof_mosaic"
    if slide.purpose == "recommendation" and len(slide.talking_points) >= 3:
        return "priority_stack"
    if slide.purpose == "insight" and len(slide.key_point) <= 90:
        return "statement_focus"
    return None


def _has_quantitative_signal(content: str) -> bool:
    if re.search(r"\d+(?:\.\d+)?\s*(?:%|％|倍|万人|亿元|美元|人|项|例)", content):
        return True
    if re.search(r"[$€¥£￥]\s?\d+", content):
        return True
    lowered = content.lower()
    quantitative_markers = (
        "increase",
        "decrease",
        "growth",
        "decline",
        "sample",
        "participants",
        "respondents",
        "ratio",
        "rate",
        "增长",
        "下降",
        "提升",
        "降低",
        "样本",
        "参与者",
        "受访者",
        "比例",
        "比率",
    )
    content_without_citation_years = re.sub(r"(?<!\d)(?:19|20)\d{2}\s*年?", "", content)
    content_without_citation_years = re.sub(r"\b(?:19|20)\d{2}\b", "", content_without_citation_years)
    return bool(re.search(r"\d", content_without_citation_years)) and any(
        marker in lowered for marker in quantitative_markers
    )


def _asset_role(slide, archetype: str) -> str:
    if slide.purpose == "cover":
        return "hero"
    if slide.purpose == "evidence" or archetype in {"data_landscape", "proof_mosaic", "split_comparison"}:
        return "evidence"
    if slide.purpose == "framework" or archetype in {"system_map", "process_ribbon"}:
        return "diagram"
    if slide.purpose == "conclusion":
        return "metaphor"
    if any(word in (slide.visual_intent or "").lower() for word in ("person", "people", "human", "人物", "用户")):
        return "portrait"
    return "context"


def _content_density(slide) -> str:
    character_count = len(slide.key_point) + sum(len(point) for point in slide.talking_points)
    if len(slide.talking_points) <= 2 and character_count < 160:
        return "sparse"
    if len(slide.talking_points) >= 5 or character_count > 420:
        return "dense"
    return "balanced"


def _hierarchy_for(archetype: str, density: str) -> list[str]:
    enterprise_base = [
        "enterprise decision claim",
        "source/evidence discipline",
        "action-ready implication",
    ]
    if archetype in {"cinematic_hero", "editorial_cover", "architectural_cover"}:
        return ["title", "promise", "hero image", "context", *enterprise_base]
    if archetype in {"data_landscape", "proof_mosaic", "split_comparison"}:
        return ["conclusion", "visual evidence", "supporting detail", "source", *enterprise_base]
    if archetype in {"process_ribbon", "system_map", "priority_stack", "chapter_index"}:
        return ["orientation", "structure", "sequence", "takeaway", *enterprise_base]
    if archetype in {"closing_echo", "manifesto_close", "future_horizon"}:
        return ["final claim", "memory image", "implication", *enterprise_base]
    return ["claim", "context image", "support", f"{density} detail", *enterprise_base]


def _award_grade_hierarchy(items: list[str], slide) -> list[str]:
    award_items = [
        "award answer-first action title",
        "single dominant focal point",
        "judge scan path: claim to proof to action",
        "enterprise decision claim",
        "source/evidence discipline",
        "action-ready implication",
    ]
    if slide.purpose in {"evidence", "insight", "recommendation"}:
        award_items.append("boardroom proof before decoration")
    merged = [*award_items, *items]
    return _unique_limited(merged, 8)


def _visual_layers_for(image_treatment: str, archetype: str, explanation_mode: str) -> list[str]:
    return [
        "direction-specific atmosphere",
        f"{image_treatment} content-grounded image",
        f"{explanation_mode} explanatory layer",
        f"{archetype} editable composition",
        "foreground takeaway and citation layer",
        "enterprise safe typography and image/text separation",
    ]


def _award_grade_visual_layers(items: list[str]) -> list[str]:
    award_items = [
        "award contrast hierarchy and negative space",
        "single focal image with protected text zone",
        "enterprise safe typography and image/text separation",
        "brand-uniform balance and alignment grid",
    ]
    return _unique_limited([*award_items, *items], 8)


def _award_grade_rationale(base: str, language: str) -> str:
    if language == "zh":
        addendum = (
            " Award-grade delivery contract: answer-first headline, one visual focal point, "
            "judge scan path, strong contrast, deliberate negative space, brand-uniform balance, "
            "proof before decoration."
        )
    else:
        addendum = (
            " Award-grade delivery contract: answer-first headline, one visual focal point, "
            "judge scan path, strong contrast, deliberate negative space, brand-uniform balance, "
            "proof before decoration."
        )
    return _clip_text(f"{base} {addendum}", 620)


def _unique_limited(items: list[str], limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = re.sub(r"\s+", " ", str(item)).strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            result.append(cleaned)
            seen.add(key)
        if len(result) == limit:
            break
    return result


def _page_asset_query(
    outline: OutlineDecision, slide, asset_role: str, visual_brief: str
) -> str:
    raw = " ".join(
        part
        for part in [
            outline.slides[0].title,
            slide.title,
            slide.key_point,
            " ".join(slide.talking_points[:3]),
            " ".join(slide.required_assets[:3]),
            slide.visual_intent,
            visual_brief,
            asset_role,
            "editorial explanatory visual",
        ]
        if part
    )
    return _clip_text(re.sub(r"\s+", " ", raw).strip(), 280)


def _explanation_mode(slide, archetype: str, content: str) -> str:
    lowered = content.lower()
    comparison_markers = (
        " vs ",
        "versus",
        "compare",
        "comparison",
        "对比",
        "比较",
        "差异",
        "区别",
    )
    sequence_markers = (
        "first",
        "second",
        "then",
        "finally",
        "step",
        "phase",
        "首先",
        "其次",
        "然后",
        "阶段",
        "步骤",
        "流程",
    )
    if any(marker in lowered for marker in comparison_markers) or archetype == "split_comparison":
        return "comparison_visual"
    if slide.purpose == "cover":
        return "hero_photo"
    if slide.purpose == "evidence" or archetype in {"data_landscape", "proof_mosaic"}:
        return "data_evidence"
    if slide.purpose in {"framework", "recommendation"} or any(
        marker in lowered for marker in sequence_markers
    ):
        return "process_diagram"
    if slide.purpose in {"agenda", "conclusion"}:
        return "summary_map"
    if slide.purpose == "insight":
        return "concept_diagram"
    return "annotated_image"


def _diagram_labels(slide) -> list[str]:
    candidates = [slide.title, slide.key_point, *slide.talking_points]
    labels: list[str] = []
    for candidate in candidates:
        cleaned = _compact_diagram_label(str(candidate))
        if cleaned and cleaned not in labels:
            labels.append(cleaned)
        if len(labels) == 4:
            break
    if len(labels) == 1:
        labels.append(_compact_diagram_label(slide.key_point))
    return labels


_CJK_NUMERAL_RE = r"[零〇一二三四五六七八九十百千万两\d]+"


def _strip_outline_scaffold_label(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    for _ in range(4):
        before = cleaned
        cleaned = re.sub(
            rf"^第\s*{_CJK_NUMERAL_RE}\s*(?:部分|章节|章|节|页|张|步|阶段|幕|层|点)\s*[：:\-—–]\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            rf"^行动优先级\s*{_CJK_NUMERAL_RE}\s*[：:\-—–]\s*(?:行动\s*[：:\-—–]\s*)?",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"^(?:"
            r"文章先回答的问题|原文线索|页面作用|可引用证据|可验证证据线索|证据线索|"
            r"讲解时可参考摘录|叙事路径|核心判断|核心问题|背景|洞察|行动|证据|结论|建议|"
            r"Source claim|Slide role|Traceable evidence|Useful excerpt|Core message|Main takeaway"
            r")\s*[：:\-—–]\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            rf"(^|[\s，,。；;：:、（(《“\"'—–-])第\s*{_CJK_NUMERAL_RE}\s*(?:部分|章节|章|节|页|张|步|阶段|幕|层|点)\s*[：:]\s*",
            r"\1",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            rf"(^|[\s，,。；;：:、（(《“\"'—–-])行动优先级\s*{_CJK_NUMERAL_RE}\s*[：:\-—–]\s*(?:行动\s*[：:\-—–]\s*)?",
            r"\1",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"(^|[\s，,。；;：:、（(《“\"'—–-])(?:"
            r"文章先回答的问题|原文线索|页面作用|可引用证据|可验证证据线索|证据线索|"
            r"讲解时可参考摘录|叙事路径|核心判断|核心问题|背景|洞察|行动|证据|结论|建议|"
            r"Source claim|Slide role|Traceable evidence|Useful excerpt|Core message|Main takeaway"
            r")\s*[：:]\s*",
            r"\1",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = cleaned.strip(" \t\r\n，。；：、,:;-—–")
        if cleaned == before:
            break
    return cleaned


def _compact_diagram_label(value: str) -> str:
    cleaned = _strip_outline_scaffold_label(value)
    cleaned = re.sub(
        r"^(?:"
        r"第\s*\d+\s*页\s*[：:]\s*|"
        r"Slide\s+\d+\s*[：:]\s*|"
        r"文章先回答的问题\s*[：:]\s*|"
        r"原文线索\s*[：:]\s*|"
        r"页面作用\s*[：:]\s*|"
        r"可引用证据\s*[：:]\s*|"
        r"讲解时可参考摘录\s*[：:]\s*|"
        r"Source claim\s*[：:]\s*|"
        r"Slide role\s*[：:]\s*|"
        r"Traceable evidence\s*[：:]\s*|"
        r"Useful excerpt\s*[：:]\s*"
        r")",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    has_cjk = bool(re.search(r"[\u3400-\u9fff]", cleaned))
    limit = 32 if has_cjk else 64
    if len(cleaned) <= limit:
        return cleaned
    shortened = cleaned[: limit - 1]
    boundary = max(shortened.rfind(mark) for mark in ("，", "。", "；", ",", ";", ":"))
    if boundary >= max(12, limit // 2):
        shortened = shortened[:boundary]
    return shortened.rstrip("，。；,;:： ") + "…"


def _visual_brief(slide, diagram_labels: list[str]) -> str:
    return _clip_text(" — ".join(diagram_labels), 520)


def _design_rationale(slide, archetype: str, image_treatment: str, density: str, language: str) -> str:
    if language == "zh":
        return f"本页承担{slide.purpose}任务，内容密度为{density}；采用{archetype}构图与{image_treatment}配图处理，使信息结构和视觉证据同步。Enterprise research contract: one decision, traceable evidence, one action implication, safe type scale."
    return (
        f"This {slide.purpose} slide has {density} content, so {archetype} with "
        f"{image_treatment} imagery aligns the information structure with its visual proof. "
        "Enterprise research contract: one decision, traceable evidence, one action implication, safe type scale."
    )


def _clip_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"
