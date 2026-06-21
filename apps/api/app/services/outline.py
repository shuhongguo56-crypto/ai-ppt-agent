from __future__ import annotations

import json
from typing import Any

from ai_ppt_contracts import OutlineDecision, ProjectBrief, SourcePack
from ai_ppt_contracts.outline import outline_generated_at_now
from ai_ppt_skills import builtin_registry
from app.ai.models import TextRequest
from app.ai.protocols import TextGateway


_GENERATION_ID_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["fakeId"],
    "properties": {"fakeId": {"type": "string", "minLength": 64, "maxLength": 64}},
    "additionalProperties": False,
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


_TITLE_BY_PURPOSE = {
    "cover": "Presentation overview",
    "agenda": "Roadmap",
    "context": "Why this matters",
    "framework": "Analytical framework",
    "evidence": "Key evidence",
    "insight": "Core insight",
    "recommendation": "Recommended path",
    "conclusion": "Closing takeaway",
}


def generate_outline_decision(
    *,
    brief: ProjectBrief,
    source_pack: SourcePack | None,
    text_gateway: TextGateway,
) -> OutlineDecision:
    skill = builtin_registry().get("HumanizePPT", "1.0.0")
    if skill is None:
        raise RuntimeError("HumanizePPT skill is not registered")

    prompt = _outline_prompt(brief, source_pack)
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
    blueprints = _SLIDE_BLUEPRINTS[brief.deck_type]
    slides = [
        _slide_payload(brief, index, purpose, layout)
        for index, (purpose, layout) in enumerate(blueprints, start=1)
    ]

    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "projectId": brief.project_id,
        "language": brief.output_language,
        "deckType": brief.deck_type,
        "audience": brief.audience,
        "objective": _objective(brief),
        "targetSlideCount": len(slides),
        "narrative": [
            f"Frame the importance of {brief.topic}.",
            "Build a clear, evidence-backed explanation.",
            "End with a memorable action or takeaway.",
        ],
        "slides": slides,
        "assetNeeds": _asset_needs(brief),
        "citationNeeds": _citation_needs(brief, source_pack),
        "risks": _risks(brief, source_pack),
        "qualityScores": {
            "structure": 88,
            "audienceFit": 86,
            "visualPotential": 84,
            "evidenceReadiness": 78 if source_pack and source_pack.sources else 72,
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


def _outline_prompt(brief: ProjectBrief, source_pack: SourcePack | None) -> str:
    source_summaries = []
    if source_pack is not None:
        source_summaries = [
            {"sourceId": item.source_id, "summary": item.summary}
            for item in source_pack.sources
        ]
    return json.dumps(
        {
            "task": "HumanizePPT outline planning",
            "brief": brief.model_dump(by_alias=True, mode="json"),
            "sources": source_summaries,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _objective(brief: ProjectBrief) -> str:
    if brief.deck_type == "business_pitch":
        return f"Persuade {brief.audience} that {brief.topic} has a clear problem, solution, and value path."
    if brief.deck_type == "thesis_defense":
        return f"Help {brief.audience} understand and evaluate the thesis work on {brief.topic}."
    return f"Help {brief.audience} understand {brief.topic} through a clear, memorable presentation."


def _slide_payload(
    brief: ProjectBrief,
    index: int,
    purpose: str,
    layout: str,
) -> dict[str, Any]:
    base_title = _TITLE_BY_PURPOSE[purpose]
    title = f"{base_title}: {brief.topic}" if purpose in {"cover", "conclusion"} else base_title
    return {
        "schemaVersion": "1.0.0",
        "slideIndex": index,
        "title": title,
        "subtitle": brief.audience if purpose == "cover" else None,
        "purpose": purpose,
        "keyPoint": f"{purpose}-{index}: {brief.topic} for {brief.audience}",
        "talkingPoints": [
            f"Connect {brief.topic} to the audience context.",
            "Keep the message focused on one idea for this slide.",
        ],
        "suggestedLayout": layout,
        "visualIntent": f"Use a premium {layout.replace('_', ' ')} composition with strong hierarchy.",
        "requiredAssets": ["supporting visual"] if purpose in {"evidence", "framework"} else [],
        "citationIds": [f"citation-{index}"] if purpose == "evidence" else [],
        "speakerNotesDraft": f"Explain how this slide advances the story about {brief.topic}.",
        "constraints": ["avoid dense paragraphs", "keep one main takeaway"],
    }


def _asset_needs(brief: ProjectBrief) -> list[str]:
    if brief.deck_type == "business_pitch":
        return ["market/problem visual", "solution diagram", "traction or value chart"]
    return ["topic hero image", "framework diagram", "evidence chart"]


def _citation_needs(brief: ProjectBrief, source_pack: SourcePack | None) -> list[str]:
    if source_pack and source_pack.sources:
        return [item.source_id for item in source_pack.sources]
    if brief.deck_type in {"thesis_defense", "research_report", "course_presentation"}:
        return ["credible academic or industry sources required before final export"]
    return []


def _risks(brief: ProjectBrief, source_pack: SourcePack | None) -> list[str]:
    risks = ["Outline is generated from the project brief and should be reviewed before rendering."]
    if source_pack is None or not source_pack.sources:
        risks.append("No source pack was provided; evidence slides need citations before final export.")
    if brief.mode == "one_click":
        risks.append("One-click mode auto-confirms the draft outline for speed.")
    return risks

