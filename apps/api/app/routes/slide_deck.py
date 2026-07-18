from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from ai_ppt_contracts import OutlineDecision, QualityReport, RenderResult, SlideDeck, VisualDirectionDecision
from app.domain.repositories import ProjectNotFound, VersionConflict
from app.errors import PublicError
from app.services.slide_deck import assemble_slide_deck, repair_slide_deck_for_quality


router = APIRouter(prefix="/projects/{project_id}/slide-deck", tags=["slide-deck"])


class SlideDeckAssembleRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    visual_direction_version: int = Field(alias="visualDirectionVersion", ge=1)


class SlideDeckRepairRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    slide_deck_version: int = Field(alias="slideDeckVersion", ge=1)
    quality_report_version: int = Field(alias="qualityReportVersion", ge=1)
    repair_pass: int = Field(default=1, alias="repairPass", ge=1, le=2)


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

    latest = request.app.state.repository.latest_checkpoint_for_stage(
        project_id, "slide_deck"
    )
    if (
        latest is not None
        and latest.status == "confirmed"
        and latest.payload.get("visualDirectionVersion") == body.visual_direction_version
    ):
        response = _checkpoint_response(latest)
        response["nextStep"] = "render"
        return response

    deck = assemble_slide_deck(
        outline=OutlineDecision(**outline_checkpoint.payload),
        outline_version=outline_checkpoint.version,
        visual=VisualDirectionDecision(**visual_checkpoint.payload),
        visual_direction_version=visual_checkpoint.version,
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


@router.post("/repair")
def repair_slide_deck_route(
    project_id: str,
    body: SlideDeckRepairRequest,
    request: Request,
) -> dict[str, Any]:
    _ensure_project(project_id, request)
    quality_checkpoint = request.app.state.repository.latest_checkpoint_for_stage(
        project_id, "quality"
    )
    if quality_checkpoint is None:
        raise PublicError("quality_not_found", "Quality report not found.", 404)
    if quality_checkpoint.version != body.quality_report_version:
        raise PublicError(
            "checkpoint_version_conflict",
            "Checkpoint was updated by another request.",
            409,
        )
    if quality_checkpoint.status != "failed":
        raise PublicError(
            "quality_already_passed",
            "The current render already passed quality checks.",
            409,
        )

    deck_checkpoint = request.app.state.repository.latest_checkpoint_for_stage(
        project_id, "slide_deck"
    )
    if deck_checkpoint is None or deck_checkpoint.status != "confirmed":
        raise PublicError("slide_deck_not_found", "Confirmed slide deck not found.", 404)
    if deck_checkpoint.version != body.slide_deck_version:
        raise PublicError(
            "checkpoint_version_conflict",
            "Checkpoint was updated by another request.",
            409,
        )
    render_checkpoint = request.app.state.repository.latest_checkpoint_for_stage(
        project_id, "render"
    )
    if render_checkpoint is None:
        raise PublicError("render_not_found", "Render result not found.", 404)
    report = QualityReport(**quality_checkpoint.payload)
    render_result = RenderResult(**render_checkpoint.payload)
    if (
        report.render_version != render_checkpoint.version
        or render_result.slide_deck_version != deck_checkpoint.version
    ):
        raise PublicError(
            "quality_not_current",
            "Quality report does not match the current render and slide deck.",
            409,
        )

    failed_names = [check.name for check in report.checks if check.status == "failed"]
    repaired_deck, applied_repairs = repair_slide_deck_for_quality(
        deck=SlideDeck(**deck_checkpoint.payload),
        failed_check_names=failed_names,
        repair_pass=body.repair_pass,
    )
    try:
        checkpoint = request.app.state.repository.put_checkpoint(
            project_id,
            "slide_deck",
            "confirmed",
            repaired_deck.model_dump(by_alias=True, mode="json"),
            deck_checkpoint.version,
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
    response["failedChecks"] = failed_names
    response["appliedRepairs"] = applied_repairs
    response["repairPass"] = body.repair_pass
    response["nextStep"] = "image_agent"
    return response
