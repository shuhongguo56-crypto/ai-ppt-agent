from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from ai_ppt_contracts import ProjectBrief, QualityReport, RenderResult, SlideDeck
from app.domain.repositories import ProjectNotFound, VersionConflict
from app.errors import PublicError
from app.services.agent_modes import execution_policy, project_agent_mode
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


def _load_brief(project_id: str, request: Request) -> ProjectBrief:
    project = request.app.state.repository.get(project_id)
    if project is None:
        raise PublicError("project_not_found", "Project not found.", 404)
    return ProjectBrief(**project.brief)


def _quality_closed_loop(report: QualityReport) -> dict[str, Any]:
    failed_checks = [
        {"name": check.name, "detail": check.detail}
        for check in report.checks
        if check.status != "passed"
    ]
    if not failed_checks:
        return {
            "status": "ready",
            "headline": "PPT 已达到客户交付标准。",
            "blocksExport": False,
            "failedChecks": [],
            "recommendedActions": ["export"],
        }
    return {
        "status": "repair_required",
        "headline": "PPT 还没有达到客户交付标准，已阻止导出并进入返修闭环。",
        "blocksExport": True,
        "failedChecks": failed_checks[:12],
        "recommendedActions": _recommended_actions_for_failed_checks(
            [item["name"] for item in failed_checks]
        ),
    }


def _recommended_actions_for_failed_checks(failed_names: list[str]) -> list[str]:
    actions: list[str] = []
    joined = " ".join(failed_names)
    if any(marker in joined for marker in ("visual_asset", "image_agent", "image_intent")):
        actions.append("refresh_images")
    if any(marker in joined for marker in ("text_", "copy", "foreground_bounds", "font_family")):
        actions.append("rerender_with_safe_layout")
    if any(marker in joined for marker in ("story", "outline", "page_delivery", "competition")):
        actions.append("review_outline")
    if any(marker in joined for marker in ("hyperframes", "html_", "motion")):
        actions.append("rerender_hyperframes")
    if not actions:
        actions.append("manual_review")
    return actions


@router.post("/check")
def check_quality(
    project_id: str,
    body: QualityCheckRequest,
    request: Request,
) -> dict[str, Any]:
    brief = _load_brief(project_id, request)
    settings = request.app.state.settings
    agent_mode = project_agent_mode(brief, settings.default_agent_mode)
    policy = execution_policy(agent_mode)
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
    slide_deck_checkpoint = request.app.state.repository.latest_checkpoint_for_stage(
        project_id, "slide_deck"
    )
    slide_deck = (
        SlideDeck(**slide_deck_checkpoint.payload)
        if slide_deck_checkpoint is not None
        else None
    )
    report = check_render_quality(
        render_result=RenderResult(**render_checkpoint.payload),
        render_version=render_checkpoint.version,
        asset_root=settings.asset_path,
        quality_profile=str(policy["qualityProfile"]),
        slide_deck=slide_deck,
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
    response["agentMode"] = agent_mode
    response["executionPolicy"] = policy
    response["qualityProfile"] = policy["qualityProfile"]
    response["closedLoop"] = _quality_closed_loop(report)
    response["nextStep"] = "export" if report.passed else "repair_and_rerender"
    return response
