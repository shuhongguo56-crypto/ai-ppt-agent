from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from .base import ContractModel, NonBlankString


DeckLanguage = Literal["zh", "en", "bilingual"]
SlidePurpose = Literal[
    "cover",
    "agenda",
    "context",
    "insight",
    "evidence",
    "framework",
    "recommendation",
    "conclusion",
]
SuggestedLayout = Literal[
    "hero",
    "section",
    "two_column",
    "three_cards",
    "timeline",
    "chart_focus",
    "quote",
    "closing",
]


class OutlineGeneratedBy(ContractModel):
    skill_name: Literal["HumanizePPT"]
    skill_version: NonBlankString
    model: NonBlankString
    prompt_hash: NonBlankString
    generation_id: NonBlankString
    generated_at: AwareDatetime


class OutlineSlide(ContractModel):
    slide_index: int = Field(ge=1)
    title: NonBlankString
    subtitle: str | None = None
    purpose: SlidePurpose
    key_point: NonBlankString
    talking_points: list[NonBlankString] = Field(min_length=1, max_length=6)
    suggested_layout: SuggestedLayout
    visual_intent: NonBlankString
    required_assets: list[str] = Field(default_factory=list, max_length=8)
    citation_ids: list[str] = Field(default_factory=list, max_length=8)
    speaker_notes_draft: str = Field(min_length=1, max_length=2000)
    constraints: list[str] = Field(default_factory=list, max_length=8)


class OutlineDecision(ContractModel):
    project_id: NonBlankString
    language: DeckLanguage
    deck_type: Literal[
        "course_presentation",
        "thesis_defense",
        "research_report",
        "business_pitch",
        "case_competition",
    ]
    audience: NonBlankString
    objective: NonBlankString
    target_slide_count: int = Field(ge=3, le=30)
    narrative: list[NonBlankString] = Field(min_length=3, max_length=12)
    slides: list[OutlineSlide] = Field(min_length=3, max_length=30)
    asset_needs: list[str] = Field(default_factory=list, max_length=40)
    citation_needs: list[str] = Field(default_factory=list, max_length=40)
    risks: list[str] = Field(default_factory=list, max_length=20)
    quality_scores: dict[str, int] = Field(default_factory=dict)
    generated_by: OutlineGeneratedBy

    @model_validator(mode="after")
    def enforce_outline_quality(self) -> "OutlineDecision":
        if self.target_slide_count != len(self.slides):
            raise ValueError("target_slide_count must match slides length")
        indexes = [slide.slide_index for slide in self.slides]
        if indexes != list(range(1, len(self.slides) + 1)):
            raise ValueError("slide_index values must be continuous from 1")
        purposes = [slide.purpose for slide in self.slides]
        if purposes[0] != "cover":
            raise ValueError("first slide must be cover")
        if purposes[-1] != "conclusion":
            raise ValueError("last slide must be conclusion")
        if any(score < 70 or score > 100 for score in self.quality_scores.values()):
            raise ValueError("quality scores must be between 70 and 100")
        key_points = [slide.key_point.strip().lower() for slide in self.slides]
        if len(set(key_points)) != len(key_points):
            raise ValueError("slide key points must not duplicate")
        return self


def outline_generated_at_now() -> datetime:
    return datetime.now().astimezone()

