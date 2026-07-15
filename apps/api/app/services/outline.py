from __future__ import annotations

import json
import hashlib
import re
from dataclasses import dataclass
from typing import Any

from ai_ppt_contracts import OutlineDecision, ProjectBrief, SourcePack
from ai_ppt_contracts.outline import outline_generated_at_now
from app.ai.errors import ModelGatewayError
from ai_ppt_skills import builtin_registry
from app.ai.models import TextRequest
from app.ai.protocols import TextGateway


_GENERATION_ID_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["fakeId"],
    "properties": {"fakeId": {"type": "string", "minLength": 64, "maxLength": 64}},
    "additionalProperties": False,
}

_OUTLINE_CONTENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "objective",
        "narrative",
        "slides",
        "assetNeeds",
        "citationNeeds",
        "risks",
        "qualityScores",
    ],
    "additionalProperties": False,
    "properties": {
        "objective": {"type": "string", "minLength": 20, "maxLength": 600},
        "narrative": {
            "type": "array",
            "minItems": 3,
            "maxItems": 8,
            "items": {"type": "string", "minLength": 8, "maxLength": 260},
        },
        "slides": {
            "type": "array",
            "minItems": 6,
            "maxItems": 12,
            "items": {
                "type": "object",
                "required": [
                    "title",
                    "subtitle",
                    "purpose",
                    "keyPoint",
                    "talkingPoints",
                    "suggestedLayout",
                    "visualIntent",
                    "requiredAssets",
                    "citationIds",
                    "speakerNotesDraft",
                    "constraints",
                ],
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string", "minLength": 2, "maxLength": 120},
                    "subtitle": {"type": ["string", "null"], "maxLength": 160},
                    "purpose": {
                        "type": "string",
                        "enum": [
                            "cover",
                            "agenda",
                            "context",
                            "insight",
                            "evidence",
                            "framework",
                            "recommendation",
                            "conclusion",
                        ],
                    },
                    "keyPoint": {"type": "string", "minLength": 8, "maxLength": 220},
                    "talkingPoints": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 5,
                        "items": {"type": "string", "minLength": 4, "maxLength": 220},
                    },
                    "suggestedLayout": {
                        "type": "string",
                        "enum": [
                            "hero",
                            "section",
                            "two_column",
                            "three_cards",
                            "timeline",
                            "chart_focus",
                            "quote",
                            "closing",
                        ],
                    },
                    "visualIntent": {"type": "string", "minLength": 8, "maxLength": 260},
                    "requiredAssets": {
                        "type": "array",
                        "maxItems": 6,
                        "items": {"type": "string", "maxLength": 100},
                    },
                    "citationIds": {
                        "type": "array",
                        "maxItems": 6,
                        "items": {"type": "string", "maxLength": 80},
                    },
                    "speakerNotesDraft": {
                        "type": "string",
                        "minLength": 8,
                        "maxLength": 800,
                    },
                    "constraints": {
                        "type": "array",
                        "maxItems": 6,
                        "items": {"type": "string", "maxLength": 100},
                    },
                },
            },
        },
        "assetNeeds": {
            "type": "array",
            "maxItems": 20,
            "items": {"type": "string", "maxLength": 120},
        },
        "citationNeeds": {
            "type": "array",
            "maxItems": 20,
            "items": {"type": "string", "maxLength": 160},
        },
        "risks": {
            "type": "array",
            "maxItems": 12,
            "items": {"type": "string", "maxLength": 220},
        },
        "qualityScores": {
            "type": "object",
            "required": ["structure", "audienceFit", "visualPotential", "evidenceReadiness"],
            "additionalProperties": False,
            "properties": {
                "structure": {"type": "integer", "minimum": 70, "maximum": 100},
                "audienceFit": {"type": "integer", "minimum": 70, "maximum": 100},
                "visualPotential": {"type": "integer", "minimum": 70, "maximum": 100},
                "evidenceReadiness": {"type": "integer", "minimum": 70, "maximum": 100},
            },
        },
    },
}


_LOCAL_OUTLINE_CONTENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["objective", "narrative", "slides"],
    "additionalProperties": False,
    "properties": {
        "objective": {"type": "string", "minLength": 12, "maxLength": 500},
        "narrative": {
            "type": "array",
            "minItems": 3,
            "maxItems": 8,
            "items": {"type": "string", "minLength": 4, "maxLength": 220},
        },
        "slides": {
            "type": "array",
            "minItems": 1,
            "maxItems": 12,
            "items": {
                "type": "object",
                "required": ["title", "keyPoint"],
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string", "minLength": 2, "maxLength": 120},
                    "keyPoint": {"type": "string", "minLength": 6, "maxLength": 220},
                    "talkingPoints": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 5,
                        "items": {"type": "string", "minLength": 3, "maxLength": 180},
                    },
                    "speakerNotesDraft": {
                        "type": "string",
                        "minLength": 6,
                        "maxLength": 700,
                    },
                },
            },
        },
    },
}


_SLIDE_BLUEPRINTS = {
    "course_presentation": [
        ("cover", "hero"),
        ("agenda", "section"),
        ("context", "two_column"),
        ("framework", "three_cards"),
        ("evidence", "chart_focus"),
        ("insight", "two_column"),
        ("recommendation", "three_cards"),
        ("conclusion", "closing"),
    ],
    "thesis_defense": [
        ("cover", "hero"),
        ("agenda", "section"),
        ("context", "two_column"),
        ("framework", "timeline"),
        ("evidence", "chart_focus"),
        ("evidence", "chart_focus"),
        ("insight", "two_column"),
        ("recommendation", "three_cards"),
        ("recommendation", "timeline"),
        ("conclusion", "closing"),
    ],
    "research_report": [
        ("cover", "hero"),
        ("agenda", "section"),
        ("context", "two_column"),
        ("framework", "timeline"),
        ("evidence", "chart_focus"),
        ("insight", "two_column"),
        ("recommendation", "three_cards"),
        ("conclusion", "closing"),
    ],
    "business_pitch": [
        ("cover", "hero"),
        ("agenda", "section"),
        ("context", "two_column"),
        ("insight", "three_cards"),
        ("evidence", "chart_focus"),
        ("recommendation", "timeline"),
        ("recommendation", "three_cards"),
        ("conclusion", "closing"),
    ],
    "case_competition": [
        ("cover", "hero"),
        ("agenda", "section"),
        ("context", "two_column"),
        ("framework", "three_cards"),
        ("evidence", "chart_focus"),
        ("insight", "two_column"),
        ("recommendation", "timeline"),
        ("conclusion", "closing"),
    ],
}


@dataclass(frozen=True)
class _SourceProfile:
    title: str
    thesis: str
    key_points: list[str]
    evidence: list[str]
    ppt_flow: list[str]
    excerpts: list[str]
    source_ids: list[str]
    case_sections: dict[str, str]
    logic_chain: dict[str, str]


_TITLE_BY_PURPOSE = {
    "en": {
        "cover": "Presentation overview",
        "agenda": "Roadmap",
        "context": "Why this matters",
        "framework": "Analytical framework",
        "evidence": "Key evidence",
        "insight": "Core insight",
        "recommendation": "Recommended path",
        "conclusion": "Closing takeaway",
    },
    "zh": {
        "cover": "汇报总览",
        "agenda": "汇报路径",
        "context": "为什么值得关注",
        "framework": "分析框架",
        "evidence": "关键证据",
        "insight": "核心洞察",
        "recommendation": "行动建议",
        "conclusion": "收束与记忆点",
    },
}


def generate_outline_decision(
    *,
    brief: ProjectBrief,
    source_pack: SourcePack | None,
    text_gateway: TextGateway,
    model_backend: str = "fake",
    agent_mode: str = "research",
    prompt_quality_target: str | None = None,
) -> OutlineDecision:
    skill = builtin_registry().get("HumanizePPT", "1.0.0")
    if skill is None:
        raise RuntimeError("HumanizePPT skill is not registered")

    prompt = _outline_prompt(
        brief,
        source_pack,
        agent_mode=agent_mode,
        prompt_quality_target=prompt_quality_target,
    )
    if model_backend in {"openai", "cascade"}:
        try:
            generation = text_gateway.generate(
                TextRequest(
                    model=skill.model,
                    prompt=prompt,
                    response_schema=_OUTLINE_CONTENT_SCHEMA,
                    timeout_seconds=90,
                    max_attempts=2,
                )
            )
        except ModelGatewayError as error:
            if model_backend == "cascade" and error.code == "cascade_model_unavailable":
                return _deterministic_outline_decision(
                    brief=brief,
                    source_pack=source_pack,
                    skill=skill,
                    generation_id=_stable_generation_id({"cascadeFallback": prompt}),
                )
            raise
        if generation.model.startswith("enhanced-local-fallback:"):
            return _deterministic_outline_decision(
                brief=brief,
                source_pack=source_pack,
                skill=skill,
                generation_id=_stable_generation_id(generation.data),
            )
        return _outline_from_model_payload(
            brief=brief,
            source_pack=source_pack,
            payload=dict(generation.data),
            skill=skill,
            generation_id=_stable_generation_id(generation.data),
        )

    if model_backend == "ollama":
        generation = text_gateway.generate(
            TextRequest(
                model=skill.model,
                prompt=prompt,
                response_schema=_LOCAL_OUTLINE_CONTENT_SCHEMA,
                timeout_seconds=120,
                max_attempts=2,
            )
        )
        return _outline_from_local_model_payload(
            brief=brief,
            source_pack=source_pack,
            payload=dict(generation.data),
            skill=skill,
            model_name=generation.model,
            generation_id=_stable_generation_id(generation.data),
        )

    generation = text_gateway.generate(
        TextRequest(
            model=skill.model,
            prompt=prompt,
            response_schema=_GENERATION_ID_SCHEMA,
            timeout_seconds=30,
            max_attempts=1,
        )
    )
    generation_id = str(generation.data["fakeId"])
    return _deterministic_outline_decision(
        brief=brief,
        source_pack=source_pack,
        skill=skill,
        generation_id=generation_id,
    )


def _deterministic_outline_decision(
    *,
    brief: ProjectBrief,
    source_pack: SourcePack | None,
    skill,
    generation_id: str,
) -> OutlineDecision:
    blueprints = _SLIDE_BLUEPRINTS[brief.deck_type]
    source_hint = _source_hint(source_pack)
    source_profile = _source_profile(source_pack)
    slides: list[dict[str, Any]] = []
    for index, (purpose, layout) in enumerate(blueprints, start=1):
        slide = _slide_payload(brief, index, purpose, layout, source_hint=source_hint)
        if source_profile is not None:
            slide = _source_grounded_slide_payload(
                brief=brief,
                base=slide,
                index=index,
                purpose=purpose,
                layout=layout,
                source_profile=source_profile,
            )
        slides.append(slide)

    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "projectId": brief.project_id,
        "language": brief.output_language,
        "deckType": brief.deck_type,
        "audience": brief.audience,
        "objective": _source_grounded_objective(brief, source_profile) if source_profile else _objective(brief),
        "targetSlideCount": len(slides),
        "narrative": _source_grounded_narrative(brief, source_profile) if source_profile else _narrative(brief, source_pack),
        "slides": slides,
        "assetNeeds": _source_grounded_asset_needs(brief, source_profile) if source_profile else _asset_needs(brief),
        "citationNeeds": _citation_needs(brief, source_pack),
        "risks": _risks(brief, source_pack),
        "qualityScores": {
            "structure": 91 if source_profile else 88,
            "audienceFit": 88 if source_profile else 86,
            "visualPotential": 86 if source_profile else 84,
            "evidenceReadiness": 86 if source_profile and source_profile.evidence else (78 if source_pack and source_pack.sources else 72),
        },
        "generatedBy": {
            "schemaVersion": "1.0.0",
            "skillName": skill.name,
            "skillVersion": skill.version,
            "model": skill.model,
            "promptHash": skill.prompt_hash,
            "generationId": generation_id,
            "generatedAt": outline_generated_at_now(),
        },
    }
    return OutlineDecision(**payload)


def _outline_from_model_payload(
    *,
    brief: ProjectBrief,
    source_pack: SourcePack | None,
    payload: dict[str, Any],
    skill,
    generation_id: str,
) -> OutlineDecision:
    raw_slides = list(payload["slides"])
    source_profile = _source_profile(source_pack)
    slides: list[dict[str, Any]] = []
    seen_key_points: set[str] = set()
    for index, raw in enumerate(raw_slides, start=1):
        item = dict(raw)
        if index == 1:
            item["purpose"] = "cover"
            item["suggestedLayout"] = "hero"
        elif index == len(raw_slides):
            item["purpose"] = "conclusion"
            item["suggestedLayout"] = "closing"
        purpose = str(item["purpose"])
        if source_profile is not None:
            if _generic_outline_copy(str(item.get("title", "")), purpose=purpose):
                item["title"] = _source_slide_title(
                    brief, purpose, source_profile, index
                )
            if _generic_outline_copy(str(item.get("keyPoint", "")), purpose=purpose):
                item["keyPoint"] = _source_slide_key_point(
                    brief, purpose, source_profile, index
                )
            raw_points = item.get("talkingPoints")
            unique_points = {
                re.sub(r"\W+", "", str(point)).casefold()
                for point in raw_points or []
                if str(point).strip()
            }
            if not isinstance(raw_points, list) or len(unique_points) < 2:
                item["talkingPoints"] = _source_talking_points(
                    brief, purpose, source_profile, index
                )
        key_point = str(item["keyPoint"]).strip()
        normalized = key_point.lower()
        if normalized in seen_key_points:
            key_point = (
                _source_slide_key_point(brief, purpose, source_profile, index)
                if source_profile is not None
                else key_point
            )
            if key_point.lower() in seen_key_points:
                qualifier = str(item["talkingPoints"][0]).strip()
                separator = "；" if _is_zh(brief) else "; "
                key_point = _clip_text(
                    f"{key_point}{separator}{qualifier}",
                    104 if _is_zh(brief) else 170,
                )
            normalized = key_point.lower()
        seen_key_points.add(normalized)
        slides.append(
            {
                "schemaVersion": "1.0.0",
                "slideIndex": index,
                "title": item["title"],
                "subtitle": item.get("subtitle"),
                "purpose": item["purpose"],
                "keyPoint": key_point,
                "talkingPoints": item["talkingPoints"],
                "suggestedLayout": item["suggestedLayout"],
                "visualIntent": item["visualIntent"],
                "requiredAssets": item.get("requiredAssets", []),
                "citationIds": item.get("citationIds", []),
                "speakerNotesDraft": item["speakerNotesDraft"],
                "constraints": item.get("constraints", []),
            }
        )

    citation_needs = list(payload.get("citationNeeds", []))
    if not citation_needs:
        citation_needs = _citation_needs(brief, source_pack)

    return OutlineDecision(
        schemaVersion="1.0.0",
        projectId=brief.project_id,
        language=brief.output_language,
        deckType=brief.deck_type,
        audience=brief.audience,
        objective=payload["objective"],
        targetSlideCount=len(slides),
        narrative=payload["narrative"],
        slides=slides,
        assetNeeds=payload.get("assetNeeds", []),
        citationNeeds=citation_needs,
        risks=payload.get("risks", []),
        qualityScores=payload["qualityScores"],
        generatedBy={
            "schemaVersion": "1.0.0",
            "skillName": skill.name,
            "skillVersion": skill.version,
            "model": skill.model,
            "promptHash": skill.prompt_hash,
            "generationId": generation_id,
            "generatedAt": outline_generated_at_now(),
        },
    )


def _outline_from_local_model_payload(
    *,
    brief: ProjectBrief,
    source_pack: SourcePack | None,
    payload: dict[str, Any],
    skill,
    model_name: str,
    generation_id: str,
) -> OutlineDecision:
    blueprints = _SLIDE_BLUEPRINTS[brief.deck_type]
    source_hint = _source_hint(source_pack)
    source_profile = _source_profile(source_pack)
    raw_slides = list(payload.get("slides", []))
    slides: list[dict[str, Any]] = []
    seen_key_points: set[str] = set()
    for index, (purpose, layout) in enumerate(blueprints, start=1):
        base = _slide_payload(brief, index, purpose, layout, source_hint=source_hint)
        if source_profile is not None:
            base = _source_grounded_slide_payload(
                brief=brief,
                base=base,
                index=index,
                purpose=purpose,
                layout=layout,
                source_profile=source_profile,
            )
        raw = raw_slides[index - 1] if index - 1 < len(raw_slides) else {}
        if isinstance(raw, dict):
            title = str(raw.get("title") or base["title"]).strip()
            key_point = str(raw.get("keyPoint") or base["keyPoint"]).strip()
            talking_points = raw.get("talkingPoints")
            if not isinstance(talking_points, list) or len(talking_points) < 2:
                talking_points = base["talkingPoints"]
            speaker_notes = str(
                raw.get("speakerNotesDraft")
                or f"Explain the takeaway: {key_point}"
            ).strip()
        else:
            title = base["title"]
            key_point = base["keyPoint"]
            talking_points = base["talkingPoints"]
            speaker_notes = base["speakerNotesDraft"]
        normalized = key_point.lower()
        if normalized in seen_key_points:
            key_point = f"{key_point} (slide {index})"
            normalized = key_point.lower()
        seen_key_points.add(normalized)
        slides.append(
            {
                **base,
                "title": title,
                "keyPoint": key_point,
                "talkingPoints": [str(point).strip() for point in talking_points[:5]],
                "speakerNotesDraft": speaker_notes,
            }
        )

    narrative = payload.get("narrative")
    if not isinstance(narrative, list) or len(narrative) < 3:
        narrative = (
            _source_grounded_narrative(brief, source_profile)
            if source_profile is not None
            else [
                f"Frame the importance of {brief.topic}.",
                "Build a clear, evidence-backed explanation.",
                "End with a memorable action or takeaway.",
            ]
        )

    return OutlineDecision(
        schemaVersion="1.0.0",
        projectId=brief.project_id,
        language=brief.output_language,
        deckType=brief.deck_type,
        audience=brief.audience,
        objective=str(
            payload.get("objective")
            or (
                _source_grounded_objective(brief, source_profile)
                if source_profile is not None
                else _objective(brief)
            )
        ).strip(),
        targetSlideCount=len(slides),
        narrative=[str(item).strip() for item in narrative[:8]],
        slides=slides,
        assetNeeds=_source_grounded_asset_needs(brief, source_profile) if source_profile else _asset_needs(brief),
        citationNeeds=_citation_needs(brief, source_pack),
        risks=_risks(brief, source_pack),
        qualityScores={
            "structure": 86,
            "audienceFit": 84,
            "visualPotential": 84,
            "evidenceReadiness": 78 if source_pack and source_pack.sources else 72,
        },
        generatedBy={
            "schemaVersion": "1.0.0",
            "skillName": skill.name,
            "skillVersion": skill.version,
            "model": model_name,
            "promptHash": skill.prompt_hash,
            "generationId": generation_id,
            "generatedAt": outline_generated_at_now(),
        },
    )


def _stable_generation_id(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _generic_outline_copy(value: str, *, purpose: str) -> bool:
    normalized = re.sub(r"[\W_]+", "", value).casefold()
    if len(normalized) < 5:
        return True
    generic_by_purpose = {
        "cover": {"presentationoverview", "汇报总览", "主题介绍"},
        "agenda": {"agenda", "roadmap", "corenarrative", "目录", "汇报路径", "主要内容"},
        "context": {"context", "background", "whythismatters", "背景", "问题背景", "为什么值得关注", "背景与问题边界"},
        "framework": {"framework", "analyticalframework", "分析框架", "作用机制", "方法框架"},
        "evidence": {"evidence", "keyevidence", "关键证据", "数据分析", "研究证据"},
        "insight": {"insight", "coreinsight", "核心洞察", "主要发现"},
        "recommendation": {"recommendation", "recommendedpath", "行动建议", "落地路径", "策略建议"},
        "conclusion": {"conclusion", "closingtakeaway", "结论", "总结", "结论与下一步"},
    }
    candidates = generic_by_purpose.get(purpose, set())
    return normalized in {re.sub(r"[\W_]+", "", item).casefold() for item in candidates}


def _outline_prompt(
    brief: ProjectBrief,
    source_pack: SourcePack | None,
    *,
    agent_mode: str = "research",
    prompt_quality_target: str | None = None,
) -> str:
    source_summaries = []
    if source_pack is not None:
        source_summaries = [
            {"sourceId": item.source_id, "summary": item.summary}
            for item in source_pack.sources
        ]
    return json.dumps(
        {
            "task": "HumanizePPT outline planning",
            "qualityBar": (
                "Create a premium, personalized presentation outline. Do not write generic slide titles. "
                "Infer the audience's motivation, the likely evaluation criteria, the narrative tension, "
                "and the minimum evidence needed. Every slide must have one sharp takeaway, a clear role "
                "in the story, and speaker notes that sound useful to a real presenter."
            ),
            "agentMode": agent_mode,
            "modeQualityTarget": prompt_quality_target or "",
            "enterpriseGradeRules": (
                [
                    "Research and enterprise modes must produce a client-ready PPT storyline, not a shallow school-report outline.",
                    "Tie the whole deck into one rigorous logic chain: problem, mechanism, evidence, implications, and action.",
                    "Each slide title must be a specific judgment or question answer; avoid generic labels unless the wording adds new meaning.",
                    "Make every page advance the argument with genuinely new information. Never repeat one claim under several renamed headings.",
                    "For every content page, write a claim, the source-backed support for that claim, and the implication for this audience; keep those roles visible in talkingPoints.",
                    "Use an intentional page rhythm: alternate anchor pages, dense proof/framework pages, and breathing insight pages instead of repeating card grids.",
                    "Evidence pages must name the fact, figure, case, or source limitation being shown; never substitute phrases such as 'research shows' for actual evidence.",
                    "Every visualIntent and requiredAssets entry must be useful for a later image/search plan.",
                    "Separate verified source claims from inference; put uncertainty into citationNeeds or risks.",
                ]
                if agent_mode in {"research", "enterprise"}
                else [
                    "Fast mode may be concise, but it must still preserve source grounding and outline-first structure.",
                    "Label missing evidence honestly instead of filling with generic claims.",
                ]
            ),
            "personalizationRules": [
                "Use the user's topic, audience, deck type, and source material to shape the storyline.",
                "Avoid template filler such as 'overview', 'background', or 'key evidence' unless it is made specific.",
                "Prefer memorable claims, contrast, before/after logic, frameworks, and decision-ready summaries.",
                "If source material exists, treat SourcePack.summary as a structured reading report. Use its thesis, key arguments, evidence, recommended PPT flow, and excerpts explicitly.",
                "Never invent evidence outside SourcePack. If the source lacks evidence, say what needs verification in citationNeeds or risks.",
                "Agenda slides should preview the actual argument, not list generic section names. Conclusion slides must synthesize the evidence and action rather than repeat the cover verbatim.",
                "Keep text concise enough for professional slides; put elaboration in speaker notes.",
            ],
            "visualPlanningRules": [
                "Choose suggested layouts based on information shape, not a fixed sequence.",
                "Mark where a framework diagram, comparison chart, timeline, or visual metaphor would help.",
                "Call out citation needs and risks honestly instead of pretending evidence exists.",
            ],
            "brief": brief.model_dump(by_alias=True, mode="json"),
            "sources": source_summaries,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _objective(brief: ProjectBrief) -> str:
    if _is_zh(brief):
        if brief.deck_type == "business_pitch":
            return f"说服{brief.audience}相信「{brief.topic}」具备清晰的问题、方案和价值路径。"
        if brief.deck_type == "thesis_defense":
            return f"帮助{brief.audience}快速理解并评估「{brief.topic}」的研究工作、方法和贡献。"
        if brief.deck_type == "research_report":
            return f"帮助{brief.audience}理解「{brief.topic}」的研究脉络、关键发现和可行动结论。"
        if brief.deck_type == "case_competition":
            return f"用结构化分析和清晰建议，让{brief.audience}看懂「{brief.topic}」的案例价值。"
        return f"帮助{brief.audience}通过一份清晰、有节奏、容易记住的 PPT 理解「{brief.topic}」。"
    if brief.deck_type == "business_pitch":
        return f"Persuade {brief.audience} that {brief.topic} has a clear problem, solution, and value path."
    if brief.deck_type == "thesis_defense":
        return f"Help {brief.audience} understand and evaluate the thesis work on {brief.topic}."
    return f"Help {brief.audience} understand {brief.topic} through a clear, memorable presentation."


def _narrative(brief: ProjectBrief, source_pack: SourcePack | None) -> list[str]:
    source_hint = _source_hint(source_pack)
    if _is_zh(brief):
        narrative = [
            f"先用一句话说明「{brief.topic}」和{brief.audience}之间的关系。",
            "再把信息拆成背景、框架、证据、洞察和建议，避免一页塞满文字。",
            "最后用一个可复述的结论收束，让听众知道下一步该记住什么。",
        ]
        if source_hint:
            narrative.insert(1, f"优先吸收用户资料中的核心线索：{source_hint}")
        return narrative[:8]
    narrative = [
        f"Open by connecting {brief.topic} to the audience's immediate context.",
        "Move through context, framework, evidence, insight, and recommendation without overloading any single slide.",
        "Close with one repeatable takeaway and a clear next step.",
    ]
    if source_hint:
        narrative.insert(1, f"Use the provided source material as the evidence anchor: {source_hint}")
    return narrative[:8]


def _slide_payload(
    brief: ProjectBrief,
    index: int,
    purpose: str,
    layout: str,
    *,
    source_hint: str = "",
) -> dict[str, Any]:
    language = "zh" if _is_zh(brief) else "en"
    base_title = _TITLE_BY_PURPOSE[language][purpose]
    topic = brief.topic.strip()
    if _is_zh(brief):
        title = _zh_slide_title(base_title, topic, purpose)
        key_point = _zh_key_point(brief, purpose, index, source_hint)
        talking_points = _zh_talking_points(brief, purpose, source_hint)
        visual_intent = f"采用高级 {layout.replace('_', ' ')} 构图：强层级、低噪声、留白充足，并把本页结论做成视觉焦点。"
        speaker_notes = _zh_speaker_notes(brief, purpose, source_hint)
        constraints = ["避免大段文字", "每页只保留一个主结论", "优先图示化抽象概念"]
        asset_label = "主题视觉或概念图"
        citation_label = f"citation-{index}"
    else:
        title = f"{base_title}: {topic}" if purpose in {"cover", "conclusion"} else base_title
        key_point = (
            f"{purpose}-{index}: use the provided material to explain {topic} for {brief.audience}"
            if source_hint and purpose == "evidence"
            else f"{purpose}-{index}: {topic} for {brief.audience}"
        )
        talking_points = [
            f"Connect {topic} to the audience context.",
            "Keep the message focused on one idea for this slide.",
        ]
        if source_hint and purpose in {"context", "evidence", "insight"}:
            talking_points[0] = f"Anchor the slide in this source signal: {source_hint}"
        visual_intent = f"Use a premium {layout.replace('_', ' ')} composition with strong hierarchy."
        speaker_notes = f"Explain how this slide advances the story about {topic}."
        constraints = ["avoid dense paragraphs", "keep one main takeaway"]
        asset_label = "supporting visual"
        citation_label = f"citation-{index}"
    return {
        "schemaVersion": "1.0.0",
        "slideIndex": index,
        "title": title,
        "subtitle": brief.audience if purpose == "cover" else None,
        "purpose": purpose,
        "keyPoint": key_point,
        "talkingPoints": talking_points,
        "suggestedLayout": layout,
        "visualIntent": visual_intent,
        "requiredAssets": [asset_label] if purpose in {"evidence", "framework"} else [],
        "citationIds": [citation_label] if purpose == "evidence" else [],
        "speakerNotesDraft": speaker_notes,
        "constraints": constraints,
    }


def _asset_needs(brief: ProjectBrief) -> list[str]:
    if _is_zh(brief):
        if brief.deck_type == "business_pitch":
            return ["问题场景视觉", "解决方案流程图", "增长或价值指标图"]
        if brief.deck_type in {"thesis_defense", "research_report"}:
            return ["研究框架图", "方法流程图", "关键结果图表"]
        return ["主题封面视觉", "概念解释图", "证据或对比图表"]
    if brief.deck_type == "business_pitch":
        return ["market/problem visual", "solution diagram", "traction or value chart"]
    return ["topic hero image", "framework diagram", "evidence chart"]


def _citation_needs(brief: ProjectBrief, source_pack: SourcePack | None) -> list[str]:
    if source_pack and source_pack.sources:
        return [item.source_id for item in source_pack.sources]
    if _is_zh(brief) and brief.deck_type in {"thesis_defense", "research_report", "course_presentation"}:
        return ["正式导出前建议补充可信文献、课程资料或行业来源"]
    if brief.deck_type in {"thesis_defense", "research_report", "course_presentation"}:
        return ["credible academic or industry sources required before final export"]
    return []


def _risks(brief: ProjectBrief, source_pack: SourcePack | None) -> list[str]:
    if _is_zh(brief):
        risks = ["大纲由项目输入和资料自动生成，正式导出前建议人工确认标题、证据和页数节奏。"]
        if source_pack is None or not source_pack.sources:
            risks.append("未提供资料包；证据页需要在最终版前补充引用或数据。")
        if brief.mode == "one_click":
            risks.append("一键模式会为了速度自动确认大纲。")
        return risks
    risks = ["Outline is generated from the project brief and should be reviewed before rendering."]
    if source_pack is None or not source_pack.sources:
        risks.append("No source pack was provided; evidence slides need citations before final export.")
    if brief.mode == "one_click":
        risks.append("One-click mode auto-confirms the draft outline for speed.")
    return risks


def _is_zh(brief: ProjectBrief) -> bool:
    return brief.output_language == "zh"


def _source_profile(source_pack: SourcePack | None) -> _SourceProfile | None:
    if source_pack is None or not source_pack.sources:
        return None
    summaries = [item.summary.strip() for item in source_pack.sources if item.summary.strip()]
    if not summaries:
        return None
    first_summary = summaries[0]
    case_sections = _source_case_sections("\n".join(summaries))
    title = (
        _section_value(first_summary, "核心主题")
        or next((item.title for item in source_pack.sources if item.title), None)
        or _first_sentence(first_summary)
    )
    thesis = (
        _section_value(first_summary, "文章主旨")
        or case_sections.get("conclusion")
        or case_sections.get("insight")
        or case_sections.get("central_question")
        or _first_sentence(first_summary)
    )
    key_points: list[str] = []
    scholarly_evidence: list[str] = []
    general_evidence: list[str] = []
    ppt_flow: list[str] = []
    excerpts: list[str] = []
    logic_chain_values: dict[str, str] = {}
    for item in source_pack.sources:
        summary = item.summary.strip()
        if not summary:
            continue
        source_thesis = _section_value(summary, "文章主旨")
        key_points.extend(_section_items(summary, "关键论点"))
        key_points.extend(
            item
            for item in [
                case_sections.get("central_question", ""),
                case_sections.get("background", ""),
                case_sections.get("insight", ""),
                case_sections.get("recommendation", ""),
            ]
            if item
        )
        if source_thesis and source_thesis != thesis:
            key_points.append(source_thesis)
        logic_chain = _logic_chain_profile(summary)
        key_points.extend(logic_chain["points"])
        for logic_key in ("central", "why", "mechanism", "risk", "action"):
            logic_value = str(logic_chain.get(logic_key, "")).strip()
            if logic_value and logic_key not in logic_chain_values:
                logic_chain_values[logic_key] = logic_value
        source_evidence = _section_items(summary, "重要事实/数据/证据")
        if case_sections.get("evidence"):
            source_evidence.append(case_sections["evidence"])
        source_evidence.extend(logic_chain["evidence"])
        scholarly = (
            "openalex" in item.source_id.lower()
            or "crossref" in item.source_id.lower()
            or bool(item.url and "doi.org" in item.url.lower())
        )
        (scholarly_evidence if scholarly else general_evidence).extend(source_evidence)
        ppt_flow.extend(_section_items(summary, "可做成PPT的大纲建议"))
        ppt_flow.extend(
            item
            for item in [
                case_sections.get("central_question", ""),
                case_sections.get("insight", ""),
                case_sections.get("recommendation", ""),
                case_sections.get("conclusion", ""),
            ]
            if item
        )
        ppt_flow.extend(logic_chain["flow"])
        excerpts.extend(_section_items(summary, "原文摘录"))
    key_points = _unique_source_items(key_points)
    evidence = _unique_source_items([*scholarly_evidence, *general_evidence])
    ppt_flow = _unique_source_items(ppt_flow)
    excerpts = _unique_source_items(excerpts)
    if not key_points:
        key_points = [_first_sentence(summary) for summary in summaries if _first_sentence(summary)]
    if not ppt_flow:
        ppt_flow = [
            f"围绕“{_clip_text(title, 48)}”建立封面主张。",
            f"用“{_clip_text(thesis, 86)}”解释文章主旨。",
            "把原文论点拆成背景、论点、证据、启示和结论。",
        ]
    source_ids = [item.source_id for item in source_pack.sources]
    return _SourceProfile(
        title=_clip_text(title, 120),
        thesis=_clip_text(thesis, 220),
        key_points=[_clip_text(item, 220) for item in key_points[:8]],
        evidence=[_clip_text(item, 220) for item in evidence[:6]],
        ppt_flow=[_clip_text(item, 220) for item in ppt_flow[:8]],
        excerpts=[_clip_text(item, 220) for item in excerpts[:5]],
        source_ids=source_ids[:6],
        case_sections=case_sections,
        logic_chain=logic_chain_values,
    )


_CASE_SECTION_KEYS: dict[str, str] = {
    "背景": "background",
    "案例背景": "background",
    "行业背景": "background",
    "问题": "central_question",
    "核心问题": "central_question",
    "关键问题": "central_question",
    "挑战": "central_question",
    "关键挑战": "central_question",
    "证据": "evidence",
    "关键证据": "evidence",
    "重要证据": "evidence",
    "数据": "evidence",
    "事实": "evidence",
    "洞察": "insight",
    "核心洞察": "insight",
    "启示": "insight",
    "建议": "recommendation",
    "行动建议": "recommendation",
    "策略建议": "recommendation",
    "落地建议": "recommendation",
    "结论": "conclusion",
    "总结": "conclusion",
}


def _source_case_sections(text: str) -> dict[str, str]:
    """Extract common Chinese case-analysis sections from user-provided material."""
    sections: dict[str, list[str]] = {}
    current_key = ""
    heading_pattern = re.compile(
        r"^(?:[一二三四五六七八九十]+[、.．]|[0-9]+[、.．)]?)?\s*"
        r"(?P<label>背景|案例背景|行业背景|问题|核心问题|关键问题|挑战|关键挑战|"
        r"证据|关键证据|重要证据|数据|事实|洞察|核心洞察|启示|"
        r"建议|行动建议|策略建议|落地建议|结论|总结)\s*[：:]\s*(?P<body>.*)$"
    )
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line:
            continue
        match = heading_pattern.match(line)
        if match:
            current_key = _CASE_SECTION_KEYS[match.group("label")]
            body = match.group("body").strip()
            if body:
                sections.setdefault(current_key, []).append(body)
            continue
        if current_key and not re.match(r"^[一二三四五六七八九十0-9]+[、.．)]", line):
            sections.setdefault(current_key, []).append(line)
    compacted: dict[str, str] = {}
    for key, parts in sections.items():
        cleaned_parts = []
        for part in parts:
            cleaned = _strip_section_prefix(part)
            if cleaned and cleaned not in cleaned_parts:
                cleaned_parts.append(cleaned)
        if cleaned_parts:
            compacted[key] = _clip_text("；".join(cleaned_parts), 260)
    return compacted


def _strip_section_prefix(value: str) -> str:
    text = " ".join(str(value).split()).strip()
    text = re.sub(r"^(?:[一二三四五六七八九十]+[、.．]|[0-9]+[、.．)]?)\s*", "", text)
    text = re.sub(
        r"^(背景|案例背景|行业背景|问题|核心问题|关键问题|挑战|关键挑战|"
        r"证据|关键证据|重要证据|数据|事实|洞察|核心洞察|启示|"
        r"建议|行动建议|策略建议|落地建议|结论|总结)\s*[：:]\s*",
        "",
        text,
    )
    return text.strip()


def _case_sections_are_complete(case_sections: dict[str, str]) -> bool:
    return bool(
        case_sections
        and {"background", "central_question", "evidence", "insight"}.issubset(
            case_sections
        )
    )


def _case_section_value(
    case_sections: dict[str, str],
    *keys: str,
    fallback: str = "",
    limit: int = 104,
) -> str:
    for key in keys:
        value = case_sections.get(key, "")
        if value:
            return _clip_text(_strip_section_prefix(value), limit)
    return _clip_text(fallback, limit)


def _case_title_fragment(
    value: str,
    fallback: str,
    *,
    purpose: str,
    limit: int = 18,
) -> str:
    text = _strip_section_prefix(value)
    if purpose == "context":
        if all(keyword in text for keyword in ("财务", "信任")):
            return "危机后信任修复"
        if "增长" in text:
            return "增长背景与问题边界"
        return _source_title_fragment(text, fallback, limit)
    if purpose == "framework":
        if all(keyword in text for keyword in ("产品", "门店")) or "飞轮" in text:
            return "增长飞轮"
        if "系统" in text:
            return "增长系统"
        return _source_title_fragment(text, fallback, limit)
    if purpose == "evidence":
        axes = []
        for label in ("产品", "渠道", "门店", "用户", "会员", "复购", "供应链"):
            if label in text and label not in axes:
                axes.append(label)
        if len(axes) >= 3:
            return " × ".join(axes[:3])
        if axes:
            return "、".join(axes[:3]) + "证据"
        return _source_title_fragment(text, fallback, limit)
    if purpose == "insight":
        if "不是" in text and "而是" in text:
            return "单点营销不是复兴"
        if "飞轮" in text:
            return "真正变量是飞轮"
        return _source_title_fragment(text, fallback, limit)
    if purpose == "recommendation":
        axes = [label for label in ("会员", "品类", "供应链", "区域化") if label in text]
        if len(axes) >= 2:
            return "、".join(axes[:3])
        return _source_title_fragment(text, fallback, limit)
    if purpose == "conclusion":
        if all(keyword in text for keyword in ("信任", "数字化")):
            return "信任修复与数字效率"
        return _source_title_fragment(text, fallback, limit)
    return _source_title_fragment(text, fallback, limit)


def _case_slide_title(
    brief: ProjectBrief,
    purpose: str,
    source_profile: _SourceProfile,
) -> str:
    sections = source_profile.case_sections
    topic_label = _source_title_topic(brief, source_profile)
    central = sections.get("central_question", "")
    evidence = sections.get("evidence", "")
    insight = sections.get("insight", "")
    recommendation = sections.get("recommendation", "")
    conclusion = sections.get("conclusion", "")
    mapping = {
        "cover": topic_label,
        "agenda": "汇报路径",
        "context": _case_title_fragment(
            sections.get("background", ""), "背景与问题边界", purpose="context"
        ),
        "framework": f"作用机制：{_case_title_fragment(insight or central, '增长系统', purpose='framework')}",
        "evidence": f"关键证据：{_case_title_fragment(evidence, '证据地图', purpose='evidence')}",
        "insight": _case_title_fragment(insight, "关键洞察", purpose="insight", limit=20),
        "recommendation": f"落地路径：{_case_title_fragment(recommendation, '行动优先级', purpose='recommendation')}",
        "conclusion": f"结论：{_case_title_fragment(conclusion or insight, '下一步', purpose='conclusion')}",
    }
    return _clip_text(mapping[purpose], 36)


def _case_slide_key_point(
    brief: ProjectBrief,
    purpose: str,
    source_profile: _SourceProfile,
) -> str:
    sections = source_profile.case_sections
    background = _case_section_value(sections, "background", limit=98)
    central = _case_section_value(sections, "central_question", limit=104)
    evidence = _case_section_value(sections, "evidence", limit=104)
    insight = _case_section_value(sections, "insight", limit=104)
    recommendation = _case_section_value(sections, "recommendation", limit=104)
    conclusion = _case_section_value(
        sections,
        "conclusion",
        fallback=source_profile.thesis,
        limit=104,
    )
    mapping = {
        "cover": f"核心判断：{conclusion or insight or central}",
        "agenda": "叙事路径：先界定危机后的增长问题，再用产品、渠道、用户证据解释复兴机制，最后落到可执行策略。",
        "context": f"背景：{background}",
        "framework": f"机制：{insight or central}",
        "evidence": f"证据：{evidence}",
        "insight": f"洞察：{insight}",
        "recommendation": f"行动：{recommendation}",
        "conclusion": f"结论：{conclusion}",
    }
    return _clip_text(mapping[purpose], 104)


def _case_talking_points(
    purpose: str,
    source_profile: _SourceProfile,
) -> list[str]:
    sections = source_profile.case_sections
    background = _case_section_value(sections, "background", limit=72)
    central = _case_section_value(sections, "central_question", limit=72)
    evidence = _case_section_value(sections, "evidence", limit=72)
    insight = _case_section_value(sections, "insight", limit=72)
    recommendation = _case_section_value(sections, "recommendation", limit=72)
    conclusion = _case_section_value(sections, "conclusion", fallback=source_profile.thesis, limit=72)
    mapping = {
        "cover": [conclusion, insight or central],
        "agenda": [
            "背景 → 问题 → 机制 → 证据 → 策略 → 结论",
            "每一页只保留一个判断，避免把资料堆成说明书",
        ],
        "context": [background, central],
        "framework": [central, insight],
        "evidence": [evidence, "证据必须服务判断：产品、渠道和用户闭环共同解释增长"],
        "insight": [insight, central],
        "recommendation": [recommendation, "先验证会员分层和品类矩阵，再扩大供应链投入"],
        "conclusion": [conclusion, "把案例价值压缩成可复述、可执行的商业判断"],
    }
    points: list[str] = []
    for point in mapping[purpose]:
        cleaned = _clip_text(point, 72)
        if cleaned and cleaned not in points:
            points.append(cleaned)
    return points[:4] if len(points) >= 2 else [conclusion, insight or central][:2]


def _unique_source_items(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        cleaned = _normalize_source_item(item)
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def _normalize_source_item(value: str) -> str:
    """Remove internal PPT-planning scaffolds from customer-facing source claims."""

    cleaned = " ".join(str(value or "").split()).strip()
    if not cleaned:
        return ""
    quoted_claim = re.search(
        r"(?:论点页围绕|围绕|聚焦)[“\"](.+?)[”\"](?:展开|组织|呈现|$)",
        cleaned,
    )
    if quoted_claim:
        return quoted_claim.group(1).strip("。；; ")
    if cleaned.startswith("背景页解释") and "：" in cleaned:
        return cleaned.split("：", 1)[1].strip("。；; ")
    if cleaned.startswith(("封面直接给出主题", "结尾页回到原文主旨")):
        return ""
    if cleaned.startswith("原文没有明显数字型证据"):
        return "当前资料提供方向性判断，但尚缺可直接引用的量化证据。"
    return cleaned


def _logic_chain_profile(summary: str) -> dict[str, Any]:
    value_prefixes = {
        "central": ("Central question:", "中心问题："),
        "why": ("Why now:", "为什么现在："),
        "mechanism": ("Mechanism:", "作用机制："),
        "risk": ("Risk boundary:", "风险边界："),
        "action": ("Action for audience:", "面向受众的行动："),
    }
    values: dict[str, str] = {}
    lines = [line.strip() for line in summary.splitlines()]
    for line in lines:
        for key, prefixes in value_prefixes.items():
            for prefix in prefixes:
                if line.startswith(prefix):
                    normalized = _normalize_source_item(line[len(prefix) :].strip())
                    if normalized:
                        values[key] = normalized
    evidence = []
    for heading in ("Evidence map:", "证据地图："):
        start = next((index for index, line in enumerate(lines) if line == heading), -1)
        if start < 0:
            continue
        for line in lines[start + 1 :]:
            if not line:
                continue
            if not line.startswith(("-", "•", "*")):
                break
            normalized = _normalize_source_item(line[1:].strip())
            if normalized:
                evidence.append(normalized)
    points = [
        item
        for item in [
            values.get("central", ""),
            values.get("why", ""),
            values.get("mechanism", ""),
            values.get("risk", ""),
        ]
        if item
    ]
    flow = [
        item
        for item in [
            values.get("central", ""),
            values.get("mechanism", ""),
            values.get("action", ""),
            values.get("risk", ""),
        ]
        if item
    ]
    return {
        "points": points,
        "evidence": evidence,
        "flow": flow,
        **values,
    }


def _source_grounded_objective(brief: ProjectBrief, source_profile: _SourceProfile | None) -> str:
    if source_profile is None:
        return _objective(brief)
    if _is_zh(brief):
        return (
            f"把项目资料《{_clip_text(source_profile.title, 48)}》转化为一份面向{brief.audience}的 PPT："
            f"先准确讲清文章主旨“{_clip_text(source_profile.thesis, 88)}”，再用原文论点和证据组织页面。"
        )
    return (
        f"Turn the project source pack “{_clip_text(source_profile.title, 48)}” into a presentation for {brief.audience}: "
        f"explain the source thesis, organize the argument, and keep every slide grounded in the provided material."
    )


def _source_grounded_narrative(brief: ProjectBrief, source_profile: _SourceProfile) -> list[str]:
    central = source_profile.logic_chain.get("central") or source_profile.case_sections.get("central_question")
    mechanism = source_profile.logic_chain.get("mechanism") or _pick(source_profile.ppt_flow, 0, "")
    action = source_profile.logic_chain.get("action") or source_profile.case_sections.get("recommendation")
    if _is_zh(brief):
        narrative = [
            f"主张：{_clip_text(source_profile.thesis, 108)}",
            f"问题：{_clip_text(central or source_profile.key_points[0], 108)}",
            f"机制：{_clip_text(mechanism, 108)}",
            "证据：只使用 SourcePack 中提取出的事实、数字、案例或原文摘录，并明确证据边界。",
            f"行动：{_clip_text(action or source_profile.ppt_flow[-1], 108)}",
        ]
    else:
        narrative = [
            f"Claim: {_clip_text(source_profile.thesis, 140)}",
            f"Question: {_clip_text(central or source_profile.key_points[0], 140)}",
            f"Mechanism: {_clip_text(mechanism, 140)}",
            "Evidence: use only extracted claims, facts, data, cases, or quotes and state the evidence boundary.",
            f"Action: {_clip_text(action or source_profile.ppt_flow[-1], 140)}",
        ]
    return narrative[:8]


def _source_grounded_asset_needs(brief: ProjectBrief, source_profile: _SourceProfile | None) -> list[str]:
    if source_profile is None:
        return _asset_needs(brief)
    if _is_zh(brief):
        assets = [
            f"原文主旨封面视觉：{_clip_text(source_profile.title, 32)}",
            "文章结构/论点关系图",
            "从 SourcePack 证据生成的图表或证据卡片",
        ]
        if source_profile.evidence:
            assets.append(f"证据可视化：{_clip_text(source_profile.evidence[0], 46)}")
        return assets[:6]
    assets = [
        f"source-thesis hero visual: {_clip_text(source_profile.title, 32)}",
        "argument map from the uploaded source",
        "evidence cards or chart based on SourcePack facts",
    ]
    if source_profile.evidence:
        assets.append(f"evidence visualization: {_clip_text(source_profile.evidence[0], 46)}")
    return assets[:6]


def _source_grounded_slide_payload(
    *,
    brief: ProjectBrief,
    base: dict[str, Any],
    index: int,
    purpose: str,
    layout: str,
    source_profile: _SourceProfile,
) -> dict[str, Any]:
    title = _source_slide_title(brief, purpose, source_profile, index)
    key_point = _source_slide_key_point(brief, purpose, source_profile, index)
    talking_points = _source_talking_points(brief, purpose, source_profile, index)
    speaker_notes = _source_speaker_notes(brief, purpose, source_profile, key_point)
    if _is_zh(brief):
        visual_intent = f"按 {layout.replace('_', ' ')} 构图呈现原文信息：突出“{_clip_text(key_point, 58)}”，不新增大纲外内容。"
        constraints = ["所有正文来自大纲", "证据页必须可追溯到 SourcePack", "每页只保留一个主判断"]
        asset_label = "SourcePack 论点/证据可视化"
    else:
        visual_intent = f"Use a {layout.replace('_', ' ')} composition to visualize the source-backed point: {_clip_text(key_point, 72)}."
        constraints = ["use outline content only", "keep source-backed evidence traceable", "one claim per slide"]
        asset_label = "SourcePack argument/evidence visual"
    citation_ids = source_profile.source_ids if purpose in {"context", "evidence", "insight", "framework"} else []
    required_assets = [asset_label] if purpose in {"framework", "evidence", "insight"} else []
    return {
        **base,
        "title": title,
        "subtitle": brief.audience if purpose == "cover" else base.get("subtitle"),
        "keyPoint": key_point,
        "talkingPoints": talking_points,
        "visualIntent": visual_intent,
        "requiredAssets": required_assets,
        "citationIds": citation_ids,
        "speakerNotesDraft": speaker_notes,
        "constraints": constraints,
    }


def _source_title_topic(brief: ProjectBrief, source_profile: _SourceProfile) -> str:
    if _is_zh(brief):
        cleaned = _clean_topic_for_outline(brief.topic, 36)
        if re.fullmatch(r"(?i)A\.?\s*I\.?", cleaned):
            return "人工智能（AI）"
        if cleaned and cleaned.lower() != "ai":
            return cleaned
        return _clip_text(source_profile.title, 36)
    cleaned = _clean_topic_for_outline(brief.topic, 64)
    if re.fullmatch(r"(?i)A\.?\s*I\.?", cleaned):
        return "Artificial Intelligence (AI)"
    return cleaned or _clip_text(source_profile.title, 64)


def _source_title_fragment(value: str, fallback: str, limit: int) -> str:
    text = " ".join(str(value).split()).strip()
    text = _strip_encoding_damage(text)
    text = re.sub(r"^[^：:]{1,12}[：:]\s*", "", text)
    text = re.sub(r"^核心判断[：:]\s*", "", text)
    text = re.sub(r"^Core (?:claim|idea|insight)[：:]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[。！？.!?].*$", "", text).strip()
    text = text.strip("“”\"'「」")
    return _clip_text(text or fallback, limit)


def _source_argument_anchor(
    source_profile: _SourceProfile,
    purpose: str,
    index: int,
) -> str:
    """Return the most relevant source claim for this page's actual job."""

    sections = source_profile.case_sections
    logic = source_profile.logic_chain
    point = _pick(source_profile.key_points, max(0, index - 3), source_profile.thesis)
    flow = _pick(source_profile.ppt_flow, max(0, index - 2), point)
    evidence = _pick(source_profile.evidence, max(0, index - 5), point)
    mapping = {
        "cover": source_profile.thesis,
        "agenda": flow,
        "context": sections.get("central_question") or logic.get("central") or logic.get("why") or sections.get("background") or point,
        "framework": logic.get("mechanism") or flow or point,
        "evidence": sections.get("evidence") or evidence,
        "insight": sections.get("insight") or point,
        "recommendation": sections.get("recommendation") or logic.get("action") or flow or point,
        "conclusion": sections.get("conclusion") or logic.get("action") or sections.get("insight") or source_profile.thesis,
    }
    return str(mapping.get(purpose) or point).strip()


def _source_support_set(
    source_profile: _SourceProfile,
    purpose: str,
    index: int,
) -> list[str]:
    """Build claim-support-implication page copy without generic filler."""

    logic = source_profile.logic_chain
    sections = source_profile.case_sections
    anchor = _source_argument_anchor(source_profile, purpose, index)
    point = _pick(source_profile.key_points, max(0, index - 2), source_profile.thesis)
    next_point = _pick(source_profile.key_points, max(0, index - 1), point)
    evidence = _pick(source_profile.evidence, max(0, index - 4), "")
    next_evidence = _pick(source_profile.evidence, max(0, index - 3), evidence)
    excerpt = _pick(source_profile.excerpts, max(0, index - 1), "")
    flow = _pick(source_profile.ppt_flow, max(0, index - 2), point)
    candidates_by_purpose = {
        "cover": [source_profile.thesis, sections.get("insight", "") or point],
        "agenda": [*source_profile.ppt_flow[:4]],
        "context": [logic.get("why", "") or sections.get("background", ""), anchor, point],
        "framework": [anchor, point, next_point, flow],
        "evidence": [evidence, next_evidence, excerpt, logic.get("risk", "")],
        "insight": [anchor, evidence, logic.get("risk", "") or next_point],
        "recommendation": [anchor, logic.get("action", ""), next_point, logic.get("risk", "")],
        "conclusion": [sections.get("conclusion", "") or source_profile.thesis, sections.get("insight", "") or point, logic.get("action", "")],
    }
    candidates = candidates_by_purpose.get(purpose, [anchor, point, evidence, excerpt])
    points: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        raw_candidate = str(candidate or "")
        cleaned = _clip_text(raw_candidate, 72 if re.search(r"[\u3400-\u9fff]", raw_candidate) else 120).strip()
        fingerprint = re.sub(r"\W+", "", cleaned).casefold()
        if cleaned and fingerprint and fingerprint not in seen:
            points.append(cleaned)
            seen.add(fingerprint)
    if len(points) < 2:
        for candidate in [anchor, point, flow, evidence, excerpt, source_profile.thesis]:
            raw_candidate = str(candidate or "")
            cleaned = _clip_text(raw_candidate, 72 if re.search(r"[\u3400-\u9fff]", raw_candidate) else 120).strip()
            fingerprint = re.sub(r"\W+", "", cleaned).casefold()
            if cleaned and fingerprint and fingerprint not in seen:
                points.append(cleaned)
                seen.add(fingerprint)
            if len(points) >= 2:
                break
    return points[:4]


def _is_brand_growth_source(brief: ProjectBrief, source_profile: _SourceProfile) -> bool:
    haystack = " ".join(
        [
            brief.topic,
            brief.audience,
            source_profile.title,
            source_profile.thesis,
            *source_profile.key_points,
            *source_profile.evidence,
            *source_profile.ppt_flow,
        ]
    ).lower()
    case_specific_markers = (
        "瑞幸",
        "咖啡",
        "luckin",
        "新消费",
        "门店",
        "会员",
        "复购",
        "供应链",
        "联名",
        "爆品",
        "retail",
        "store",
    )
    growth_markers = ("品牌", "增长", "用户运营", "brand", "growth", "consumer")
    specific_hits = sum(1 for marker in case_specific_markers if marker in haystack)
    growth_hits = sum(1 for marker in growth_markers if marker in haystack)
    named_case = any(marker in haystack for marker in ("瑞幸", "luckin"))
    return named_case or (specific_hits >= 2 and growth_hits >= 1)


def _brand_growth_title(
    brief: ProjectBrief,
    purpose: str,
    index: int,
    source_profile: _SourceProfile,
) -> str:
    topic_label = _source_title_topic(brief, source_profile)
    mapping = {
        "cover": topic_label,
        "agenda": "汇报路径",
        "context": "背景边界：信任修复不是终点",
        "framework": "增长机制：产品 × 门店 × 会员",
        "evidence": "证据地图：门店、APP 与复购",
        "insight": "核心洞察：从营销热度到增长飞轮",
        "recommendation": "落地路径：验证可迁移能力",
        "conclusion": "结论：增长质量比声量更重要",
    }
    if purpose == "recommendation" and index > 6:
        return "落地路径：指标化验收"
    return mapping[purpose]


def _brand_growth_key_point(
    brief: ProjectBrief,
    purpose: str,
    index: int,
    source_profile: _SourceProfile,
) -> str:
    thesis = _source_title_fragment(source_profile.thesis, "品牌增长需要被拆成可验证机制", 92)
    mapping = {
        "cover": f"核心判断：{thesis}",
        "agenda": "叙事路径：先界定品牌为什么重新进入讨论，再拆解增长机制、证据地图、迁移条件和行动优先级。",
        "context": "背景：危机后的讨论价值不只是热度回升，而是信任修复与经营效率能否支撑长期增长。",
        "framework": "机制：产品创新、价格心智、门店密度、数字化履约、会员复购和供应链效率共同形成增长飞轮。",
        "evidence": "证据：门店扩张、APP/小程序下单、联名爆品、会员复购、供应链效率和品牌信任修复共同支撑判断。",
        "insight": "洞察：真正的复兴不是单点营销胜利，而是把产品、渠道、用户和履约组织成可复制系统。",
        "recommendation": f"行动：为{brief.audience}建立迁移判断表，区分可复制能力、行业条件和需要继续验证的风险。",
        "conclusion": "结论：瑞幸案例的价值在于把信任修复、新消费心智和数字化效率放进同一系统评估。",
    }
    if purpose == "recommendation" and index > 6:
        mapping["recommendation"] = "行动：用会员分层、品类矩阵、复购效率、履约成本和扩张风险做阶段性验收。"
    return _clip_text(mapping[purpose], 104)


def _brand_growth_talking_points(purpose: str, index: int) -> list[str]:
    mapping = {
        "cover": [
            "主线不是单次营销，而是可复制的增长系统。",
            "判断要同时看信任、产品、渠道、用户和履约。",
        ],
        "agenda": [
            "问题边界：品牌为何重新被讨论。",
            "机制拆解：增长飞轮由哪些环节构成。",
            "证据地图：哪些指标能支撑判断。",
            "行动收束：哪些能力可迁移、哪些仍需验证。",
        ],
        "context": [
            "信任修复决定品牌能否重新进入消费选择。",
            "低价促销只能带来流量，不能单独证明增长质量。",
        ],
        "framework": [
            "产品创新负责制造讨论和购买理由。",
            "门店密度与数字化履约缩短购买路径。",
            "会员和私域复购决定增长是否可持续。",
            "供应链效率决定扩张后的履约稳定性。",
        ],
        "evidence": [
            "门店扩张说明触达能力，但需要结合履约效率判断。",
            "APP/小程序下单体现数字化购买路径。",
            "联名和爆品证明声量，但必须回到复购和利润质量。",
            "财务表现与品牌信任修复共同约束结论边界。",
        ],
        "insight": [
            "增长飞轮比爆款更重要。",
            "可迁移的是机制组合，不是单个营销动作。",
        ],
        "recommendation": [
            "先验证会员分层和复购路径。",
            "再判断品类矩阵能否稳定制造购买理由。",
            "最后用履约成本和供应链效率约束扩张节奏。",
        ],
        "conclusion": [
            "客户真正需要的是可验证的增长判断。",
            "下一步应把声量、复购、履约和利润质量放进同一张表。",
        ],
    }
    if purpose == "recommendation" and index > 6:
        return [
            "把会员分层、品类矩阵和复购效率设为短周期验收指标。",
            "把履约成本、供应链效率和扩张风险设为长期约束指标。",
            "用指标区分可迁移方法与不可复制条件。",
        ]
    return mapping[purpose]


def _is_ai_education_topic(value: str) -> bool:
    normalized = value.lower()
    ai_terms = ("ai", "人工智能", "生成式", "aigc", "artificial intelligence", "generative ai")
    education_terms = (
        "教育",
        "高等教育",
        "高校",
        "大学",
        "教学",
        "课堂",
        "课程",
        "学习",
        "复习",
        "评价",
        "形成性评价",
        "education",
        "higher education",
        "university",
        "college",
        "teaching",
        "learning",
        "assessment",
        "formative assessment",
    )
    return any(term in normalized for term in ai_terms) and any(
        term in normalized for term in education_terms
    )


def _is_auto_research_profile(source_profile: _SourceProfile) -> bool:
    return any(
        source_id.startswith(
            (
                "web-research-synthesis-",
                "web-local-research-fallback-",
                "web-research-gap-",
            )
        )
        for source_id in source_profile.source_ids
    )


def _distinct_source_claims(source_profile: _SourceProfile) -> list[str]:
    candidates = [
        *source_profile.key_points,
        source_profile.logic_chain.get("why", ""),
        source_profile.case_sections.get("background", ""),
        source_profile.logic_chain.get("mechanism", ""),
        source_profile.case_sections.get("insight", ""),
        source_profile.thesis,
    ]
    claims: list[str] = []
    fingerprints: list[str] = []
    for candidate in candidates:
        cleaned = _normalize_source_item(candidate)
        fingerprint = re.sub(r"[^0-9a-z㐀-鿿]+", "", cleaned.casefold())
        if not fingerprint:
            continue
        if any(
            fingerprint == existing
            or (len(fingerprint) >= 12 and fingerprint in existing)
            or (len(existing) >= 12 and existing in fingerprint)
            for existing in fingerprints
        ):
            continue
        claims.append(cleaned)
        fingerprints.append(fingerprint)
    return claims


def _is_business_strategy_source(brief: ProjectBrief, source_profile: _SourceProfile) -> bool:
    haystack = " ".join(
        [
            brief.topic,
            brief.audience,
            source_profile.thesis,
            *source_profile.key_points,
        ]
    ).casefold()
    terms = (
        "企业",
        "行业",
        "市场",
        "竞争",
        "品牌",
        "增长",
        "利润",
        "用户",
        "客户",
        "渠道",
        "成本",
        "business",
        "market",
        "growth",
        "brand",
        "customer",
    )
    return sum(term in haystack for term in terms) >= 3


def _business_story_parts(source_profile: _SourceProfile) -> tuple[str, str, str]:
    claims = _distinct_source_claims(source_profile)
    thesis = source_profile.thesis
    non_thesis = [claim for claim in claims if claim != thesis]
    context = _pick(non_thesis, 0, thesis)
    customer = next(
        (
            claim
            for claim in non_thesis[1:]
            if re.search(r"用户|客户|消费者|决策|需求|体验|customer|consumer|decision", claim, re.IGNORECASE)
        ),
        _pick(non_thesis, 1, context),
    )
    return context, customer, thesis


def _business_source_title(purpose: str, source_profile: _SourceProfile, index: int) -> str:
    context, customer, thesis = _business_story_parts(source_profile)
    context_text = f"{context} {customer} {thesis}"
    evidence_text = " ".join(source_profile.evidence)
    evidence_is_boundary = any(
        marker in evidence_text
        for marker in ("尚缺", "待补", "需补", "需要交付前", "to verify", "needed before")
    )
    mapping = {
        "agenda": "从外部变化到战略选择",
        "context": (
            "竞争规则：补贴退场，能力上桌"
            if "补贴" in context_text
            else "外部规则正在改变"
        ),
        "framework": (
            "用户决策：长期价值正在上桌"
            if re.search(r"用户|客户|消费者|决策|全生命周期", customer)
            else "价值选择标准正在改变"
        ),
        "evidence": (
            "证据交叉验证：趋势是否成立"
            if source_profile.evidence and not evidence_is_boundary
            else "证据边界：方向已清，数据待补"
        ),
        "insight": "增长逻辑：规模不再自动等于优势",
        "recommendation": (
            "验收机制：把战略变成指标"
            if index > 6
            else (
                "三项优先级：利润、心智、效率"
                if all(term in thesis for term in ("利润", "心智", "效率"))
                else "把战略判断变成经营优先级"
            )
        ),
        "conclusion": "最终判断：下一阶段比拼增长质量",
    }
    return mapping[purpose]


def _business_source_key_point(
    purpose: str,
    source_profile: _SourceProfile,
    index: int,
) -> str:
    context, customer, thesis = _business_story_parts(source_profile)
    context = context.rstrip("。；; ")
    customer = customer.rstrip("。；; ")
    thesis = thesis.rstrip("。；; ")
    evidence = _pick(source_profile.evidence, 0, "")
    mapping = {
        "agenda": "叙事路径：先看竞争规则如何变化，再拆用户决策标准，最后把结论转成经营优先级。",
        "context": f"外部变化：{context}",
        "framework": f"需求机制：{customer}",
        "evidence": (
            f"证据：{evidence}"
            if evidence
            else "证据边界：现有资料形成了‘外部竞争变化—用户标准变化—企业战略重构’的一致方向，但尚缺可直接引用的量化指标。"
        ),
        "insight": (
            f"综合判断：{_clip_text(context, 44)}；同时，{_clip_text(customer, 44)}。"
            "因此，只靠规模扩张难以形成下一阶段优势。"
        ),
        "recommendation": (
            "验收：用利润质量、品牌心智、组织效率与用户价值四组指标，检查战略转向是否真正发生。"
            if index > 6
            else (
                f"行动：把‘{_clip_text(thesis, 64)}’拆成可追踪的经营优先级，"
                "并逐项对应资料中的竞争维度与用户决策标准。"
            )
        ),
        "conclusion": (
            "结论：下一阶段优势不只取决于做大规模，更取决于能否落实‘"
            f"{_clip_text(thesis, 66)}’。"
        ),
    }
    return mapping[purpose]


def _business_source_talking_points(
    purpose: str,
    source_profile: _SourceProfile,
    index: int,
) -> list[str]:
    context, customer, thesis = _business_story_parts(source_profile)
    evidence = _pick(source_profile.evidence, 0, "")
    mapping = {
        "agenda": [
            "外部竞争维度发生了什么变化？",
            "用户正在用什么标准重新选择？",
            "企业应该把哪些能力放到同一套增长模型中？",
        ],
        "context": [context, "竞争焦点正在从单一红利转向产品、成本、渠道与组织的系统能力。"],
        "framework": [customer, "用户标准变化，会反向重塑产品承诺、体验可信度与经营效率。"],
        "evidence": [
            evidence or context,
            customer,
            "量化结论需继续补充行业、用户与经营结果数据后再对外引用。",
        ],
        "insight": [context, customer, "规模增长只有与利润、心智和效率同步，才能沉淀为长期优势。"],
        "recommendation": (
            [
                "利润质量：增长是否伴随可持续盈利改善。",
                "品牌心智：用户是否形成稳定、可复述的选择理由。",
                "组织效率：产品、渠道与履约能否协同兑现承诺。",
                "用户价值：补能、可信度与全生命周期成本是否改善。",
            ]
            if index > 6
            else [
                thesis,
                "把外部竞争维度转成内部经营指标。",
                "把用户决策标准转成产品与服务验收条件。",
            ]
        ),
        "conclusion": [
            "下一阶段竞争的分水岭是增长质量，而不是规模数字本身。",
            thesis,
        ],
    }
    return mapping[purpose]


def _source_slide_title(
    brief: ProjectBrief,
    purpose: str,
    source_profile: _SourceProfile,
    index: int,
) -> str:
    topic_label = _source_title_topic(brief, source_profile)
    point = _pick(source_profile.key_points, index - 3, source_profile.thesis)
    evidence = _pick(source_profile.evidence, index - 5, point)
    anchor = _source_argument_anchor(source_profile, purpose, index)
    if _is_zh(brief):
        if _is_auto_research_profile(source_profile) and _is_ai_education_topic(
            f"{topic_label} {brief.audience} {source_profile.thesis}"
        ):
            mapping = {
                "cover": topic_label,
                "agenda": "汇报路径",
                "context": "为什么现在必须讨论 AI",
                "framework": "教学—学习—评价—治理",
                "evidence": "研究与案例证据地图",
                "insight": "核心洞察：效率不等于质量",
                "recommendation": "课程落地路径",
                "conclusion": "结论：让 AI 服务真实学习",
            }
        elif _case_sections_are_complete(source_profile.case_sections):
            return _case_slide_title(brief, purpose, source_profile)
        elif _is_brand_growth_source(brief, source_profile):
            return _brand_growth_title(brief, purpose, index, source_profile)
        elif purpose != "cover" and _is_business_strategy_source(brief, source_profile):
            return _business_source_title(purpose, source_profile, index)
        else:
            point_label = _source_title_fragment(anchor or point, "核心机制", 18)
            evidence_label = _source_title_fragment(evidence, "关键证据", 18)
            evidence_title = (
                "公开资料与研究证据"
                if _is_auto_research_profile(source_profile)
                and not re.search(r"[\u3400-\u9fff]", evidence)
                else f"证据指向：{evidence_label}"
            )
            mapping = {
                "cover": topic_label,
                "agenda": "从问题到行动：论证路径",
                "context": f"问题边界：{point_label}",
                "framework": f"作用机制：{point_label}",
                "evidence": evidence_title,
                "insight": f"因此：{_source_title_fragment(anchor, '关键洞察', 20)}",
                "recommendation": f"行动优先级：{_source_title_fragment(anchor, '落地路径', 18)}",
                "conclusion": f"最终判断：{_source_title_fragment(anchor, '下一步', 20)}",
            }
    else:
        mapping = {
            "cover": topic_label,
            "agenda": "From question to action",
            "context": f"The real issue: {_source_title_fragment(anchor, 'why this matters', 34)}",
            "framework": f"How it works: {_source_title_fragment(anchor, 'mechanism', 34)}",
            "evidence": f"Evidence map: {_source_title_fragment(evidence, 'proof', 34)}",
            "insight": f"What this means: {_source_title_fragment(anchor, 'core insight', 34)}",
            "recommendation": f"Act on: {_source_title_fragment(anchor, 'priority', 34)}",
            "conclusion": f"Final judgment: {_source_title_fragment(anchor, 'next step', 34)}",
        }
    return _clip_text(mapping[purpose], 110)


def _source_slide_key_point(
    brief: ProjectBrief,
    purpose: str,
    source_profile: _SourceProfile,
    index: int,
) -> str:
    point = _pick(source_profile.key_points, index - 3, source_profile.thesis)
    evidence = _pick(source_profile.evidence, index - 5, point)
    flow = _pick(source_profile.ppt_flow, index - 2, point)
    anchor = _source_argument_anchor(source_profile, purpose, index)
    evidence_copy = (
        evidence
        if not _is_zh(brief) or re.search(r"[\u3400-\u9fff]", evidence)
        else point
    )
    if _is_zh(brief):
        if _is_auto_research_profile(source_profile) and _is_ai_education_topic(
            f"{source_profile.title} {brief.audience} {source_profile.thesis}"
        ):
            mapping = {
                "cover": f"核心判断：{source_profile.thesis}",
                "agenda": "叙事路径：先说明教育场景中的真实痛点，再拆解 AI 如何影响教学、学习、评价与治理。",
                "context": "背景：AI 的价值不只是更快生成内容，而是改变课程复习、反馈和形成性评价的组织方式。",
                "framework": "机制：从教学设计、学习支持、评价证据和治理边界四层拆解，避免只讨论工具功能。",
                "evidence": "证据：公开资料与论文检索共同指向，AI 在高等教育中的效果必须同时看学习质量、过程证据和责任边界。",
                "insight": "洞察：效率提升只是入口，真正高级的应用要把 AI 变成反馈、复盘和判断训练的基础设施。",
                "recommendation": f"行动：{brief.audience}可以先在课程复习、练习反馈和形成性评价中试点，明确输入规范、审核标准、披露要求和复盘指标。",
                "conclusion": "结论：让 AI 服务真实学习，而不是替代阅读、推理和原创表达。",
            }
            selected = mapping[purpose]
            if purpose == "recommendation" and index > 6:
                selected = f"行动优先级 {index - 5}：{selected}"
            return _clip_text(selected, 104)
        if _case_sections_are_complete(source_profile.case_sections):
            return _case_slide_key_point(brief, purpose, source_profile)
        if _is_brand_growth_source(brief, source_profile):
            return _brand_growth_key_point(brief, purpose, index, source_profile)
        if purpose != "cover" and _is_business_strategy_source(brief, source_profile):
            return _clip_text(_business_source_key_point(purpose, source_profile, index), 132)
        mapping = {
            "cover": f"核心判断：{source_profile.thesis}",
            "agenda": "叙事路径：先界定核心问题，再解释作用机制与证据，最后收束为面向受众的行动。",
            "context": f"问题：{anchor}",
            "framework": f"机制：{anchor}",
            "evidence": f"证据：{evidence_copy}",
            "insight": f"洞察：{anchor}",
            "recommendation": f"行动：{anchor}",
            "conclusion": f"结论：{anchor}",
        }
    else:
        mapping = {
            "cover": f"Core claim: {source_profile.thesis}",
            "agenda": "Narrative path: define the question, explain the mechanism and evidence, then turn the conclusion into action.",
            "context": f"Question: {anchor}",
            "framework": f"Mechanism: {anchor}",
            "evidence": f"Evidence: {evidence}",
            "insight": f"Insight: {anchor}",
            "recommendation": f"Action for {brief.audience}: {anchor}",
            "conclusion": f"Conclusion: {anchor}",
        }
    selected = mapping[purpose]
    if purpose == "recommendation" and index > 6:
        selected = (
            f"行动优先级 {index - 5}：{selected}"
            if _is_zh(brief)
            else f"Action priority {index - 5}: {selected}"
        )
    return _clip_text(selected, 104 if _is_zh(brief) else 170)


def _source_talking_points(
    brief: ProjectBrief,
    purpose: str,
    source_profile: _SourceProfile,
    index: int,
) -> list[str]:
    if (
        _is_zh(brief)
        and _is_auto_research_profile(source_profile)
        and _is_ai_education_topic(
        f"{source_profile.title} {brief.audience} {source_profile.thesis}"
        )
    ):
        mapping = {
            "cover": [
                "本 deck 聚焦教学、学习、评价与治理的协同重构。",
                "判断重点不是工具炫技，而是学习质量与责任边界。",
            ],
            "agenda": [
                "先建立为什么现在必须讨论 AI。",
                "再用机制、证据、洞察和行动建议形成完整叙事。",
            ],
            "context": [
                "教师需要更快反馈与更个性化的学习支持。",
                "学生需要练习伙伴，但仍要保留阅读、推理和原创表达。",
            ],
            "framework": [
                "教学端：备课、案例、反馈和个性化支持。",
                "学习端：启发、练习、复盘和理解校验。",
                "评价端：过程证据、反思与口头答辩。",
                "治理端：披露、隐私、事实核验和责任归属。",
            ],
            "evidence": [
                "公开资料说明 AI 的能力边界与典型应用场景。",
                "论文检索提示高等教育评估要关注教学、学习与评价质量。",
                "形成性评价需要过程证据和反馈闭环，而不是只看最终答案。",
            ],
            "insight": [
                "低级用法是替代完成任务，高级用法是训练判断。",
                "好的 PPT 应把 AI 的收益和风险同时讲清。",
            ],
            "recommendation": [
                "先选择低风险课程复习场景试点。",
                "为学生明确可用/不可用边界与披露规则。",
                "把评价标准改成过程证据、口头解释和复盘记录。",
            ],
            "conclusion": [
                "AI 应成为反馈与理解增强器，而不是学习替身。",
                "最终目标是让学生更会判断、更会表达、更会负责。",
            ],
        }
        return mapping[purpose]
    if _is_zh(brief) and _case_sections_are_complete(source_profile.case_sections):
        return _case_talking_points(purpose, source_profile)
    if _is_zh(brief) and _is_brand_growth_source(brief, source_profile):
        return _brand_growth_talking_points(purpose, index)
    if _is_zh(brief) and purpose != "cover" and _is_business_strategy_source(brief, source_profile):
        return _business_source_talking_points(purpose, source_profile, index)
    return _source_support_set(source_profile, purpose, index)


def _source_speaker_notes(
    brief: ProjectBrief,
    purpose: str,
    source_profile: _SourceProfile,
    key_point: str,
) -> str:
    evidence = source_profile.evidence[0] if source_profile.evidence else ""
    if _is_zh(brief):
        note = (
            f"讲这一页时先说明它来自项目资料《{source_profile.title}》，再讲本页判断：{key_point}。"
            "不要补写资料里没有的观点。"
        )
        if purpose == "evidence" and evidence:
            note += f" 证据部分引用：{evidence}"
        return _clip_text(note, 760)
    note = (
        f"Present this slide as a source-backed claim from “{source_profile.title}”: {key_point}. "
        "Do not add arguments that are not present in the outline."
    )
    if purpose == "evidence" and evidence:
        note += f" Evidence anchor: {evidence}"
    return _clip_text(note, 760)


def _source_hint(source_pack: SourcePack | None) -> str:
    if source_pack is None or not source_pack.sources:
        return ""
    profile = _source_profile(source_pack)
    if profile is not None:
        return _clip_text(profile.thesis or profile.title, 120)
    summary = " ".join(item.summary.strip() for item in source_pack.sources if item.summary.strip())
    summary = " ".join(summary.split())
    if not summary:
        return ""
    for separator in ("。", ".", "；", ";", "\n"):
        if separator in summary:
            summary = summary.split(separator)[0]
            break
    return summary[:120]


def _section_value(text: str, heading: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        prefix = f"{heading}："
        ascii_prefix = f"{heading}:"
        if stripped.startswith(prefix):
            return stripped[len(prefix) :].strip()
        if stripped.startswith(ascii_prefix):
            return stripped[len(ascii_prefix) :].strip()
    return ""


def _section_items(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    start = -1
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped in {f"{heading}：", f"{heading}:"} or stripped.startswith(f"{heading}："):
            start = index
            break
    if start < 0:
        return []
    items: list[str] = []
    inline = lines[start].split("：", 1)
    if len(inline) == 2 and inline[1].strip():
        items.append(inline[1].strip())
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith(("-", "•", "*", "·")) and stripped.endswith(("：", ":")):
            break
        if re.match(r"^[\w\u4e00-\u9fff /-]{2,30}[：:]$", stripped):
            break
        if stripped.startswith(("-", "•", "*", "·")):
            stripped = stripped[1:].strip()
        items.append(stripped)
    return [item for item in items if item][:10]


def _first_sentence(text: str) -> str:
    cleaned = " ".join(text.split())
    for separator in ("。", "！", "？", ".", "!", "?"):
        if separator in cleaned:
            value = cleaned.split(separator)[0].strip()
            if value:
                return _clip_text(value, 220)
    return _clip_text(cleaned, 220)


def _pick(items: list[str], index: int, fallback: str) -> str:
    if not items:
        return fallback
    return items[index % len(items)]


def _clip_text(value: str, limit: int) -> str:
    value = " ".join(str(value).split()).strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def _strip_encoding_damage(value: str) -> str:
    text = str(value).replace("\ufffd", " ")
    text = re.sub(r"\?{3,}", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _clean_topic_for_outline(value: str, limit: int = 48) -> str:
    text = _strip_encoding_damage(value)
    if re.fullmatch(r"(?i)A\.?\s*I\.?", text):
        text = "人工智能（AI）"
    text = re.sub(r"^AI\s*可以指\s*[：:]\s*", "", text, flags=re.IGNORECASE).strip()
    if re.search(r"[\u3400-\u9fff]", text):
        text = re.sub(
            r"\s*[（(][A-Za-z][A-Za-z0-9 ,./&:;+\-]{2,80}[）)]",
            "",
            text,
        ).strip()
        text = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", text)
    return _clip_text(text, limit)


def _compact_zh_axis(items: list[str]) -> str:
    unique: list[str] = []
    for item in items:
        if item and item not in unique:
            unique.append(item)
    if not unique:
        return ""
    if len(unique) == 1:
        return unique[0]
    return "、".join(unique[:-1]) + f"与{unique[-1]}"


def _compact_zh_domain(domain: str) -> str:
    cleaned = _clean_topic_for_outline(domain, 40)
    if "高等教育" in cleaned:
        axes: list[str] = []
        if any(keyword in cleaned for keyword in ("课程", "复习", "学习", "课堂", "教学")):
            axes.append("学习")
        if any(keyword in cleaned for keyword in ("评价", "评估", "考核")):
            axes.append("评价")
        if any(keyword in cleaned for keyword in ("治理", "诚信", "风险", "责任")):
            axes.append("治理")
        axis = _compact_zh_axis(axes)
        return f"高等教育{axis}" if axis else "高等教育"
    parts = [part for part in re.split(r"[、，,；;和与]", cleaned) if part]
    if len(parts) >= 2:
        return _clip_text(_compact_zh_axis(parts[:2]), 18)
    return _clip_text(cleaned, 18)


def _compact_zh_topic_title(value: str, limit: int = 36) -> str:
    topic = _clean_topic_for_outline(value, 96)
    if len(topic) <= limit:
        return topic
    relation = re.match(r"(?P<subject>.+?)在(?P<domain>.+?)(?:中|中的)(?P<tail>.+)$", topic)
    if relation:
        subject = _clip_text(relation.group("subject"), 12).rstrip("…")
        tail = relation.group("tail")
        verb = "重构" if "重构" in tail else "赋能" if any(keyword in tail for keyword in ("帮助", "提升", "支持")) else "应用于"
        domain = _compact_zh_domain(relation.group("domain"))
        return _clip_text(f"{subject}{verb}{domain}", limit)
    if "人工智能" in topic and "高等教育" in topic:
        domain = _compact_zh_domain(topic)
        return _clip_text(f"人工智能重构{domain}", limit)
    return _clip_text(topic, limit)


def _zh_slide_title(base_title: str, topic: str, purpose: str) -> str:
    clean_topic = _compact_zh_topic_title(topic, 36)
    if purpose == "cover":
        return clean_topic
    if purpose == "conclusion":
        return f"{base_title}：{_compact_zh_topic_title(topic, 24)}"
    return base_title


def _zh_key_point(brief: ProjectBrief, purpose: str, index: int, source_hint: str = "") -> str:
    topic = _compact_zh_topic_title(brief.topic, 36)
    audience = brief.audience.strip()
    ai_topic = any(keyword in topic.lower() for keyword in ("ai", "人工智能", "智能体", "生成式"))
    if ai_topic:
        base_claim = f"「{topic}」的核心不是替代人，而是重构{audience}的目标、反馈、评价与责任边界。"
        context_claim = f"它值得关注，因为它会同时改变{audience}的学习效率、判断质量和学术/组织责任。"
        framework_claim = "可从目标定义、任务流程、证据校验、风险治理四层拆解，避免只讨论工具功能。"
        evidence_claim = (
            f"资料线索显示：{source_hint}"
            if source_hint
            else "证据应同时检验效率提升、理解质量、评价公平和风险控制，不能只看生成速度。"
        )
        insight_claim = "真正的价值不在更快生成内容，而在把重复劳动转化为更高质量的理解、判断和表达。"
        action_claim = f"{audience}可以先选择低风险场景试点，设置输入规范、审核标准和复盘指标，再扩展到完整流程。"
    else:
        base_claim = f"「{topic}」的核心是把复杂问题拆成可判断的结构，让{audience}看清背景、机制、证据和行动边界。"
        context_claim = f"它值得关注，因为它会影响{audience}对问题成因、风险和机会的判断。"
        framework_claim = "可从背景变化、关键变量、证据强度和行动选择四层拆解，形成清晰的分析路径。"
        evidence_claim = (
            f"资料线索显示：{source_hint}"
            if source_hint
            else "证据页需要用案例、数据、文献或课程材料验证核心判断，避免停留在抽象观点。"
        )
        insight_claim = "关键不是罗列事实，而是找到真正改变结果的变量，并说明它如何影响判断。"
        action_claim = f"{audience}应把结论转化为可执行标准：先判断适用场景，再选择行动优先级。"
    mapping = {
        "cover": base_claim,
        "agenda": f"叙事路径从现实变化进入机制拆解，再用证据校验判断，最后落到{audience}可执行的下一步。",
        "context": context_claim,
        "framework": framework_claim,
        "evidence": evidence_claim,
        "insight": insight_claim,
        "recommendation": action_claim,
        "conclusion": f"最终记忆点：让「{topic}」服务目标、证据和责任，而不是让流程被概念或工具牵着走。",
    }
    selected = mapping[purpose]
    if purpose == "recommendation" and index > 6:
        selected = f"行动优先级 {index - 5}：先建立验收指标与风险边界，再决定是否扩大投入。"
    return _clip_text(selected, 110)


def _zh_talking_points(brief: ProjectBrief, purpose: str, source_hint: str = "") -> list[str]:
    topic = _compact_zh_topic_title(brief.topic, 36)
    audience = brief.audience.strip()
    ai_topic = any(keyword in topic.lower() for keyword in ("ai", "人工智能", "智能体", "生成式"))
    value_axis = "效率、质量、责任" if ai_topic else "背景、机制、证据"
    risk_axis = "学术诚信、评价公平、数据边界" if ai_topic else "证据不足、场景不匹配、行动成本"
    mapping = {
        "cover": [
            f"{audience}关心的不是概念本身，而是「{topic}」会改变什么。",
            f"本页主张聚焦{value_axis}，不堆砌定义。",
        ],
        "agenda": [
            "背景解释变化来源，框架说明影响机制。",
            "证据检验判断强度，建议转化为行动标准。",
        ],
        "context": [
            f"资料线索：{source_hint}" if source_hint else f"{topic}正在改变任务完成和判断方式。",
            f"忽略它会带来{risk_axis}等判断盲区。",
        ],
        "framework": [
            "目标层：先明确要改善的结果。",
            "流程层、证据层、治理层分别对应做法、效果和边界。",
        ],
        "evidence": [
            f"资料线索：{source_hint}" if source_hint else "优先寻找案例、数据、文献或课程要求支撑判断。",
            "证据必须能回答：是否有效、对谁有效、代价是什么。",
        ],
        "insight": [
            f"关键判断来自资料线索：{source_hint}" if source_hint else f"{topic}的价值取决于能否改善真实任务结果。",
            "洞察必须和前面的证据一一对应。",
        ],
        "recommendation": [
            "先选低风险、高频场景做小规模验证。",
            "用清晰标准判断是否扩大使用范围。",
        ],
        "conclusion": [
            f"回到{audience}最需要记住的判断。",
            f"一句话收束：{topic}必须服务目标、证据和责任。",
        ],
    }
    return [_clip_text(point, 72) for point in mapping[purpose]]


def _zh_speaker_notes(brief: ProjectBrief, purpose: str, source_hint: str = "") -> str:
    topic = _compact_zh_topic_title(brief.topic, 36)
    mapping = {
        "cover": f"开场时不要急着解释所有细节，先告诉听众：这份 PPT 会用清晰结构帮助他们理解「{topic}」。",
        "agenda": "这一页用来建立预期。建议用 20 秒说明本次汇报会按背景、框架、证据、洞察和建议推进。",
        "context": (
            f"这一页要回答为什么现在要讲「{topic}」。可以先引用资料线索：{source_hint}，再转入听众关心的问题。"
            if source_hint
            else f"这一页要回答为什么现在要讲「{topic}」。可以结合课程要求、现实案例或听众已有认知切入。"
        ),
        "framework": "这一页是全篇的骨架。讲清楚框架后，后面的证据页才不会显得散。",
        "evidence": (
            f"讲证据时不要照读资料。先给结论，再说明资料线索「{source_hint}」如何支持这个结论。"
            if source_hint
            else "讲证据时不要照读资料。先给结论，再解释证据如何支持这个结论。"
        ),
        "insight": (
            f"这一页要做提炼，把资料线索「{source_hint}」压缩成一个更高级、更容易复述的判断。"
            if source_hint
            else "这一页要做提炼，把前面材料压缩成一个更高级的判断。"
        ),
        "recommendation": "建议页要具体，最好让听众知道如果自己要使用这个结论，第一步该做什么。",
        "conclusion": "最后回到主题和听众，把全篇压缩成一句可复述的话，并自然结束。",
    }
    return mapping[purpose]
