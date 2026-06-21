from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from .base import ContractModel, NonBlankString


VisualDirectionId = Literal["apple", "mckinsey", "airbnb"]


class VisualGeneratedBy(ContractModel):
    skill_name: Literal["Frontend-Slides"]
    skill_version: NonBlankString
    model: NonBlankString
    prompt_hash: NonBlankString
    generation_id: NonBlankString
    generated_at: AwareDatetime


class VisualDirection(ContractModel):
    direction_id: VisualDirectionId
    name: NonBlankString
    mood: NonBlankString
    palette: list[NonBlankString] = Field(min_length=3, max_length=8)
    typography: NonBlankString
    layout_principles: list[NonBlankString] = Field(min_length=3, max_length=8)
    texture_layer: NonBlankString
    sample_slide_intents: list[NonBlankString] = Field(min_length=3, max_length=12)
    risk_notes: list[str] = Field(default_factory=list, max_length=8)


class VisualDirectionDecision(ContractModel):
    project_id: NonBlankString
    outline_version: int = Field(ge=1)
    directions: list[VisualDirection] = Field(min_length=3, max_length=3)
    selected_direction_id: VisualDirectionId | None = None
    generated_by: VisualGeneratedBy

    @model_validator(mode="after")
    def require_exact_direction_set(self) -> "VisualDirectionDecision":
        ids = [direction.direction_id for direction in self.directions]
        if ids != ["apple", "mckinsey", "airbnb"]:
            raise ValueError("directions must be exactly apple, mckinsey, airbnb")
        if self.selected_direction_id is not None and self.selected_direction_id not in ids:
            raise ValueError("selected_direction_id must exist in directions")
        return self


def visual_generated_at_now() -> datetime:
    return datetime.now().astimezone()

