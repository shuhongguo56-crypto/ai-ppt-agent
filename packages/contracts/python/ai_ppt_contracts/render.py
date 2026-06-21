from typing import Literal

from pydantic import Field, model_validator

from .base import ContractModel, NonBlankString


RenderTarget = Literal["pptx", "hyperframes_html"]


class RenderArtifact(ContractModel):
    target: RenderTarget
    path: NonBlankString
    content_type: NonBlankString
    slide_count: int = Field(ge=1)


class RenderResult(ContractModel):
    project_id: NonBlankString
    slide_deck_version: int = Field(ge=1)
    artifacts: list[RenderArtifact] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def require_both_targets_once(self) -> "RenderResult":
        targets = [artifact.target for artifact in self.artifacts]
        if targets != ["pptx", "hyperframes_html"]:
            raise ValueError("artifacts must be pptx and hyperframes_html")
        counts = {artifact.slide_count for artifact in self.artifacts}
        if len(counts) != 1:
            raise ValueError("artifacts must report the same slide count")
        return self

