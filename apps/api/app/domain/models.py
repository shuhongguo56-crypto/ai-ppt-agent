from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class ProjectRecord:
    project_id: str
    brief: dict[str, Any]
    created_at: datetime

    @classmethod
    def new(cls, project_id: str, brief: dict[str, Any]) -> "ProjectRecord":
        return cls(
            project_id=project_id,
            brief=deepcopy(brief),
            created_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class CheckpointRecord:
    project_id: str
    stage: str
    status: str
    version: int
    payload: dict[str, Any]
    created_at: datetime
