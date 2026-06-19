from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .base import ContractModel


class WorkflowCheckpoint(ContractModel):
    project_id: str
    stage: Literal[
        "brief",
        "outline",
        "visual_direction",
        "slide_deck",
        "render",
        "quality",
        "export",
    ]
    status: Literal["pending", "draft", "confirmed", "failed", "complete"]
    version: int = Field(ge=1)
    payload: dict[str, Any]
    created_at: datetime
