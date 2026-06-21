from __future__ import annotations

import json
from typing import Any

from ai_ppt_contracts import OutlineDecision, VisualDirectionDecision
from ai_ppt_contracts.visual import visual_generated_at_now
from ai_ppt_skills import builtin_registry
from app.ai.models import TextRequest
from app.ai.protocols import TextGateway


_GENERATION_ID_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["fakeId"],
    "properties": {"fakeId": {"type": "string", "minLength": 64, "maxLength": 64}},
    "additionalProperties": False,
}


def generate_visual_direction_decision(
    *,
    outline: OutlineDecision,
    outline_version: int,
    text_gateway: TextGateway,
) -> VisualDirectionDecision:
    skill = builtin_registry().get("Frontend-Slides", "1.0.0")
    if skill is None:
        raise RuntimeError("Frontend-Slides skill is not registered")

    generation = text_gateway.generate(
        TextRequest(
            model=skill.model,
            prompt=json.dumps(
                {
                    "task": "Frontend-Slides visual direction planning",
                    "outline": outline.model_dump(by_alias=True, mode="json"),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            response_schema=_GENERATION_ID_SCHEMA,
            timeout_seconds=30,
            max_attempts=1,
        )
    )

    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "projectId": outline.project_id,
        "outlineVersion": outline_version,
        "directions": [
            {
                "schemaVersion": "1.0.0",
                "directionId": "apple",
                "name": "Apple Editorial Calm",
                "mood": "quiet, premium, spacious, product-keynote clarity",
                "palette": ["#0B0F19", "#F8FAFC", "#D7E3FF", "#8AB4F8"],
                "typography": "large editorial headings with restrained sans-serif body text",
                "layoutPrinciples": [
                    "one dominant idea per slide",
                    "generous whitespace",
                    "cinematic hero compositions",
                ],
                "textureLayer": "soft gradients, subtle masks, translucent panels, no plastic shine",
                "sampleSlideIntents": _sample_intents(outline, "cinematic clarity"),
                "riskNotes": ["Can feel sparse if the source has dense academic evidence."],
            },
            {
                "schemaVersion": "1.0.0",
                "directionId": "mckinsey",
                "name": "McKinsey Executive Logic",
                "mood": "consulting-grade, structured, evidence-first, decisive",
                "palette": ["#071A2C", "#FFFFFF", "#D6E4F0", "#2F80ED"],
                "typography": "crisp business sans-serif with chart-friendly labels",
                "layoutPrinciples": [
                    "headline states the conclusion",
                    "charts and tables drive the argument",
                    "strict grid with clear grouping",
                ],
                "textureLayer": "light card surfaces, precise dividers, restrained blue accents",
                "sampleSlideIntents": _sample_intents(outline, "executive logic"),
                "riskNotes": ["Can look too corporate for a creative classroom talk."],
            },
            {
                "schemaVersion": "1.0.0",
                "directionId": "airbnb",
                "name": "Airbnb Human Story",
                "mood": "warm, human, narrative, approachable, modern",
                "palette": ["#2B1B1B", "#FFF7F0", "#FF5A5F", "#FFC7B8"],
                "typography": "friendly rounded headings with readable presentation body text",
                "layoutPrinciples": [
                    "story-led section rhythm",
                    "floating cards and snapshots",
                    "human-scale examples before abstraction",
                ],
                "textureLayer": "paper warmth, rounded cards, transparent overlays, soft depth",
                "sampleSlideIntents": _sample_intents(outline, "human story"),
                "riskNotes": ["Needs careful evidence treatment for formal thesis defense decks."],
            },
        ],
        "selectedDirectionId": None,
        "generatedBy": {
            "schemaVersion": "1.0.0",
            "skillName": skill.name,
            "skillVersion": skill.version,
            "model": skill.model,
            "promptHash": skill.prompt_hash,
            "generationId": str(generation.data["fakeId"]),
            "generatedAt": visual_generated_at_now(),
        },
    }
    return VisualDirectionDecision(**payload)


def select_visual_direction(
    decision: VisualDirectionDecision,
    direction_id: str,
) -> VisualDirectionDecision:
    payload = decision.model_dump(by_alias=True, mode="json")
    payload["selectedDirectionId"] = direction_id
    return VisualDirectionDecision(**payload)


def _sample_intents(outline: OutlineDecision, style: str) -> list[str]:
    return [
        f"Slide {slide.slide_index}: express '{slide.title}' with {style}."
        for slide in outline.slides[:5]
    ]

