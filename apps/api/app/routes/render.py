from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from ai_ppt_contracts import SlideDeck
from app.domain.repositories import ProjectNotFound, VersionConflict
from app.errors import PublicError
from app.services.render import render_slide_deck


router = APIRouter(prefix="/projects/{project_id}/render", tags=["render"])


class RenderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    slide_deck_version: int = Field(alias="slideDeckVersion", ge=1)


def _checkpoint_response(checkpoint) -> dict[str, Any]:
    return {
        "projectId": checkpoint.project_id,
        "stage": checkpoint.stage,
        "status": checkpoint.status,
        "version": checkpoint.version,
        "renderResult": checkpoint.payload,
        "createdAt": checkpoint.created_at.isoformat(),
    }


@router.post("")
def render_project(
    project_id: str,
    body: RenderRequest,
    request: Request,
) -> dict[str, Any]:
    if request.app.state.repository.get(project_id) is None:
        raise PublicError("project_not_found", "Project not found.", 404)
    deck_checkpoint = request.app.state.repository.latest_checkpoint_for_stage(
        project_id, "slide_deck"
    )
    if deck_checkpoint is None:
        raise PublicError("slide_deck_not_found", "Slide deck not found.", 404)
    if deck_checkpoint.status != "confirmed":
        raise PublicError(
            "slide_deck_not_confirmed",
            "Slide deck must be confirmed before rendering.",
            409,
        )
    if deck_checkpoint.version != body.slide_deck_version:
        raise PublicError(
            "checkpoint_version_conflict",
            "Checkpoint was updated by another request.",
            409,
        )

    result = render_slide_deck(
        deck=SlideDeck(**deck_checkpoint.payload),
        slide_deck_version=deck_checkpoint.version,
        output_root=request.app.state.settings.asset_path,
    )
    latest = request.app.state.repository.latest_checkpoint_for_stage(project_id, "render")
    expected_version = 0 if latest is None else latest.version
    try:
        checkpoint = request.app.state.repository.put_checkpoint(
            project_id,
            "render",
            "complete",
            result.model_dump(by_alias=True, mode="json"),
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
    response["nextStep"] = "export"
    return response

