from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from ai_ppt_contracts import OutlineDecision, VisualDirectionDecision
from ai_ppt_contracts.visual import VisualDirectionId
from app.domain.repositories import ProjectNotFound, VersionConflict
from app.errors import PublicError
from app.services.visual import (
    generate_visual_direction_decision,
    select_visual_direction,
)


router = APIRouter(
    prefix="/projects/{project_id}/visual-directions",
    tags=["visual-directions"],
)


class VisualGenerateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    outline_decision_version: int = Field(alias="outlineDecisionVersion", ge=1)


class VisualSelectRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    visual_direction_version: int = Field(alias="visualDirectionVersion", ge=1)
    direction_id: VisualDirectionId = Field(alias="directionId")


def _checkpoint_response(checkpoint) -> dict[str, Any]:
    return {
        "projectId": checkpoint.project_id,
        "stage": checkpoint.stage,
        "status": checkpoint.status,
        "version": checkpoint.version,
        "visualDirection": checkpoint.payload,
        "createdAt": checkpoint.created_at.isoformat(),
    }


def _ensure_project(project_id: str, request: Request) -> None:
    if request.app.state.repository.get(project_id) is None:
        raise PublicError("project_not_found", "Project not found.", 404)


@router.post("/generate")
def generate_visual_directions(
    project_id: str,
    body: VisualGenerateRequest,
    request: Request,
) -> dict[str, Any]:
    _ensure_project(project_id, request)
    outline_checkpoint = request.app.state.repository.latest_checkpoint_for_stage(
        project_id, "outline"
    )
    if outline_checkpoint is None:
        raise PublicError("outline_not_found", "Outline not found.", 404)
    if outline_checkpoint.status != "confirmed":
        raise PublicError(
            "outline_not_confirmed",
            "Outline must be confirmed before visual directions.",
            409,
        )
    if outline_checkpoint.version != body.outline_decision_version:
        raise PublicError(
            "checkpoint_version_conflict",
            "Checkpoint was updated by another request.",
            409,
        )

    decision = generate_visual_direction_decision(
        outline=OutlineDecision(**outline_checkpoint.payload),
        outline_version=outline_checkpoint.version,
        text_gateway=request.app.state.text_gateway,
    )
    latest = request.app.state.repository.latest_checkpoint_for_stage(
        project_id, "visual_direction"
    )
    expected_version = 0 if latest is None else latest.version
    try:
        checkpoint = request.app.state.repository.put_checkpoint(
            project_id,
            "visual_direction",
            "draft",
            decision.model_dump(by_alias=True, mode="json"),
            expected_version,
        )
    except ProjectNotFound:
        raise PublicError("project_not_found", "Project not found.", 404) from None
    except VersionConflict:
        raise PublicError(
            "checkpoint_version_conflict",
            "Checkpoint was updated by another request.",
            409,
        ) from None
    response = _checkpoint_response(checkpoint)
    response["nextStep"] = "visual_direction_selection"
    return response


@router.post("/select")
def select_visual_direction_route(
    project_id: str,
    body: VisualSelectRequest,
    request: Request,
) -> dict[str, Any]:
    _ensure_project(project_id, request)
    latest = request.app.state.repository.latest_checkpoint_for_stage(
        project_id, "visual_direction"
    )
    if latest is None:
        raise PublicError("visual_direction_not_found", "Visual direction not found.", 404)
    if latest.version != body.visual_direction_version:
        raise PublicError(
            "checkpoint_version_conflict",
            "Checkpoint was updated by another request.",
            409,
        )

    selected = select_visual_direction(
        VisualDirectionDecision(**latest.payload),
        body.direction_id,
    )
    try:
        checkpoint = request.app.state.repository.put_checkpoint(
            project_id,
            "visual_direction",
            "confirmed",
            selected.model_dump(by_alias=True, mode="json"),
            latest.version,
        )
    except ProjectNotFound:
        raise PublicError("project_not_found", "Project not found.", 404) from None
    except VersionConflict:
        raise PublicError(
            "checkpoint_version_conflict",
            "Checkpoint was updated by another request.",
            409,
        ) from None
    response = _checkpoint_response(checkpoint)
    response["nextStep"] = "slide_deck"
    return response

