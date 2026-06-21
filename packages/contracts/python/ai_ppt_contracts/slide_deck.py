from typing import Literal

from pydantic import Field, model_validator

from .base import ContractModel, NonBlankString
from .outline import DeckLanguage, SlidePurpose
from .visual import VisualDirectionId


SlideBlockType = Literal["headline", "subtitle", "body", "card", "chart_placeholder", "image_placeholder", "speaker_notes"]


class SlideDeckTheme(ContractModel):
    direction_id: VisualDirectionId
    name: NonBlankString
    palette: list[NonBlankString] = Field(min_length=3, max_length=8)
    typography: NonBlankString
    texture_layer: NonBlankString
    layout_principles: list[NonBlankString] = Field(min_length=3, max_length=8)


class SlideBlock(ContractModel):
    block_id: NonBlankString
    block_type: SlideBlockType
    content: NonBlankString
    role: NonBlankString


class SlideDeckSlide(ContractModel):
    slide_id: NonBlankString
    slide_index: int = Field(ge=1)
    title: NonBlankString
    subtitle: str | None = None
    purpose: SlidePurpose
    layout: NonBlankString
    visual_intent: NonBlankString
    blocks: list[SlideBlock] = Field(min_length=2, max_length=12)
    speaker_notes: NonBlankString


class SlideDeck(ContractModel):
    project_id: NonBlankString
    outline_version: int = Field(ge=1)
    visual_direction_version: int = Field(ge=1)
    language: DeckLanguage
    title: NonBlankString
    theme: SlideDeckTheme
    slides: list[SlideDeckSlide] = Field(min_length=3, max_length=30)
    export_targets: list[Literal["pptx", "hyperframes_html"]] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def enforce_deck_invariants(self) -> "SlideDeck":
        indexes = [slide.slide_index for slide in self.slides]
        if indexes != list(range(1, len(self.slides) + 1)):
            raise ValueError("slide_index values must be continuous from 1")
        if self.export_targets != ["pptx", "hyperframes_html"]:
            raise ValueError("export_targets must be pptx and hyperframes_html")
        if len({slide.slide_id for slide in self.slides}) != len(self.slides):
            raise ValueError("slide_id values must be unique")
        return self

