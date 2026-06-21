from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from ai_ppt_contracts import RenderResult
from app.domain.repositories import ProjectNotFound, VersionConflict
from app.errors import PublicError
from app.services.quality import check_render_quality


router = APIRouter(prefix="/projects/{project_id}/quality", tags=["quality"])


class QualityCheckRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    render_version: int = Field(alias="renderVersion", ge=1)


def _checkpoint_response(checkpoint) -> dict[str, Any]:
    return {
        "projectId": checkpoint.project_id,
        "stage": checkpoint.stage,
        "status": checkpoint.status,
        "version": checkpoint.version,
        "qualityReport": checkpoint.payload,
        "createdAt": checkpoint.created_at.isoformat(),
    }


@router.post("/check")
def check_quality(
    project_id: str,
    body: QualityCheckRequest,
    request: Request,
) -> dict[str, Any]:
    if request.app.state.repository.get(project_id) is None:
        raise PublicError("project_not_found", "Project not found.", 404)
    render_checkpoint = request.app.state.repository.latest_checkpoint_for_stage(
        project_id, "render"
    )
    if render_checkpoint is None or render_checkpoint.status != "complete":
        raise PublicError("render_not_found", "Render result not found.", 404)
    if render_checkpoint.version != body.render_version:
        raise PublicError(
            "checkpoint_version_conflict",
            "Checkpoint was updated by another request.",
            409,
        )
    report = check_render_quality(
        render_result=RenderResult(**render_checkpoint.payload),
        render_version=render_checkpoint.version,
        asset_root=request.app.state.settings.asset_path,
    )
    latest = request.app.state.repository.latest_checkpoint_for_stage(project_id, "quality")
    expected_version = 0 if latest is None else latest.version
    try:
        checkpoint = request.app.state.repository.put_checkpoint(
            project_id,
            "quality",
            "complete" if report.passed else "failed",
            report.model_dump(by_alias=True, mode="json"),
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
    response["nextStep"] = "export" if report.passed else "manual_review"
    return response

