from typing import Literal

from pydantic import Field

from .base import ContractModel, NonBlankString


class ProjectBrief(ContractModel):
    project_id: NonBlankString
    input_language: Literal["zh", "en"]
    output_language: Literal["zh", "en", "bilingual"]
    deck_type: Literal[
        "course_presentation",
        "thesis_defense",
        "research_report",
        "business_pitch",
        "case_competition",
    ]
    topic: str = Field(min_length=1, max_length=500)
    audience: str = Field(min_length=1, max_length=500)
    mode: Literal["professional", "one_click"]


class SourceItem(ContractModel):
    source_id: NonBlankString
    source_type: Literal["text", "document", "url", "image"]
    summary: NonBlankString
    title: str | None = None
    url: str | None = None


class SourcePack(ContractModel):
    project_id: NonBlankString
    sources: list[SourceItem] = Field(default_factory=list)
