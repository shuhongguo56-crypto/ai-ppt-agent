from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_ppt_contracts import ProjectBrief
from app.domain.models import CheckpointRecord, ProjectRecord
from app.domain.repositories import (
    ProjectAlreadyExists,
    ProjectNotFound,
    VersionConflict,
)
from app.errors import PublicError


Stage = Literal[
    "brief",
    "outline",
    "visual_direction",
    "slide_deck",
    "render",
    "quality",
    "export",
]

router = APIRouter(prefix="/projects", tags=["projects"])


class CheckpointWrite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    expected_version: int = Field(alias="expectedVersion", ge=0)
    status: Literal["pending", "draft", "confirmed", "failed", "complete"]
    payload: dict[str, Any]

    @field_validator("payload")
    @classmethod
    def supported_payload_version(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("schemaVersion") != "1.0.0":
            raise ValueError("payload schemaVersion must be 1.0.0")
        return value


def _checkpoint_response(checkpoint: CheckpointRecord) -> dict[str, Any]:
    return {
        "projectId": checkpoint.project_id,
        "stage": checkpoint.stage,
        "status": checkpoint.status,
        "version": checkpoint.version,
        "payload": checkpoint.payload,
        "createdAt": checkpoint.created_at.isoformat(),
    }


@router.post("", status_code=201)
def create_project(brief: ProjectBrief, request: Request) -> dict[str, Any]:
    serialized = brief.model_dump(by_alias=True, mode="json")
    try:
        request.app.state.repository.create(ProjectRecord.new(brief.project_id, serialized))
    except ProjectAlreadyExists:
        raise PublicError("project_already_exists", "Project already exists.", 409) from None
    return {"projectId": brief.project_id, "brief": serialized}


@router.get("/{project_id}")
def get_project(project_id: str, request: Request) -> dict[str, Any]:
    project = request.app.state.repository.get(project_id)
    if project is None:
        raise PublicError("project_not_found", "Project not found.", 404)
    return {
        "projectId": project.project_id,
        "brief": project.brief,
        "createdAt": project.created_at.isoformat(),
    }


@router.get("/{project_id}/checkpoints/latest")
def latest_checkpoint(project_id: str, request: Request) -> dict[str, Any]:
    if request.app.state.repository.get(project_id) is None:
        raise PublicError("project_not_found", "Project not found.", 404)
    checkpoint = request.app.state.repository.latest_checkpoint(project_id)
    if checkpoint is None:
        raise PublicError("checkpoint_not_found", "Checkpoint not found.", 404)
    return _checkpoint_response(checkpoint)


@router.put("/{project_id}/checkpoints/{stage}")
def put_checkpoint(
    project_id: str,
    stage: Stage,
    body: CheckpointWrite,
    request: Request,
) -> dict[str, Any]:
    try:
        checkpoint = request.app.state.repository.put_checkpoint(
            project_id,
            stage,
            body.status,
            body.payload,
            body.expected_version,
        )
    except ProjectNotFound:
        raise PublicError("project_not_found", "Project not found.", 404) from None
    except VersionConflict:
        raise PublicError(
            "checkpoint_version_conflict",
            "Checkpoint was updated by another request.",
            409,
        ) from None
    return _checkpoint_response(checkpoint)
