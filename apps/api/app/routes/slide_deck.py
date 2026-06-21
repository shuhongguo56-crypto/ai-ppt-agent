from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from ai_ppt_contracts import OutlineDecision, VisualDirectionDecision
from app.domain.repositories import ProjectNotFound, VersionConflict
from app.errors import PublicError
from app.services.slide_deck import assemble_slide_deck


router = APIRouter(prefix="/projects/{project_id}/slide-deck", tags=["slide-deck"])


class SlideDeckAssembleRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    visual_direction_version: int = Field(alias="visualDirectionVersion", ge=1)


def _checkpoint_response(checkpoint) -> dict[str, Any]:
    return {
        "projectId": checkpoint.project_id,
        "stage": checkpoint.stage,
        "status": checkpoint.status,
        "version": checkpoint.version,
        "slideDeck": checkpoint.payload,
        "createdAt": checkpoint.created_at.isoformat(),
    }


def _ensure_project(project_id: str, request: Request) -> None:
    if request.app.state.repository.get(project_id) is None:
        raise PublicError("project_not_found", "Project not found.", 404)


@router.post("/assemble")
def assemble_slide_deck_route(
    project_id: str,
    body: SlideDeckAssembleRequest,
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
            "Outline must be confirmed before slide deck assembly.",
            409,
        )
    visual_checkpoint = request.app.state.repository.latest_checkpoint_for_stage(
        project_id, "visual_direction"
    )
    if visual_checkpoint is None:
        raise PublicError("visual_direction_not_found", "Visual direction not found.", 404)
    if visual_checkpoint.status != "confirmed":
        raise PublicError(
            "visual_direction_not_confirmed",
            "Visual direction must be selected before slide deck assembly.",
            409,
        )
    if visual_checkpoint.version != body.visual_direction_version:
        raise PublicError(
            "checkpoint_version_conflict",
            "Checkpoint was updated by another request.",
            409,
        )

    deck = assemble_slide_deck(
        outline=OutlineDecision(**outline_checkpoint.payload),
        outline_version=outline_checkpoint.version,
        visual=VisualDirectionDecision(**visual_checkpoint.payload),
        visual_direction_version=visual_checkpoint.version,
    )
    latest = request.app.state.repository.latest_checkpoint_for_stage(
        project_id, "slide_deck"
    )
    expected_version = 0 if latest is None else latest.version
    try:
        checkpoint = request.app.state.repository.put_checkpoint(
            project_id,
            "slide_deck",
            "confirmed",
            deck.model_dump(by_alias=True, mode="json"),
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
    response["nextStep"] = "render"
    return response

