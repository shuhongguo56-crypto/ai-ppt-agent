from dataclasses import dataclass
from typing import Any, Protocol

from .models import CheckpointRecord, ProjectRecord


class ProjectNotFound(Exception):
    """Raised when a write references a project that does not exist."""


class ProjectAlreadyExists(Exception):
    """Raised when a project identifier is already in use."""


@dataclass(frozen=True)
class VersionConflict(Exception):
    current_version: int


class ProjectRepository(Protocol):
    def create(self, project: ProjectRecord) -> None: ...

    def get(self, project_id: str) -> ProjectRecord | None: ...

    def latest_checkpoint(self, project_id: str) -> CheckpointRecord | None: ...

    def latest_checkpoint_for_stage(
        self, project_id: str, stage: str
    ) -> CheckpointRecord | None: ...

    def put_checkpoint(
        self,
        project_id: str,
        stage: str,
        status: str,
        payload: dict[str, Any],
        expected_version: int,
    ) -> CheckpointRecord: ...
