from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from ai_ppt_contracts import ProjectBrief, SlideDeck
from app.domain.repositories import ProjectNotFound, VersionConflict
from app.errors import PublicError
from app.services.agent_modes import execution_policy, project_agent_mode
from app.services.render import render_slide_deck


router = APIRouter(prefix="/projects/{project_id}/render", tags=["render"])


class RenderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    slide_deck_version: int = Field(alias="slideDeckVersion", ge=1)
    image_resolution_mode: Literal["auto", "web_first", "generate"] = Field(
        default="auto",
        alias="imageResolutionMode",
    )


def _checkpoint_response(checkpoint) -> dict[str, Any]:
    return {
        "projectId": checkpoint.project_id,
        "stage": checkpoint.stage,
        "status": checkpoint.status,
        "version": checkpoint.version,
        "renderResult": checkpoint.payload,
        "createdAt": checkpoint.created_at.isoformat(),
    }


def _load_brief(project_id: str, request: Request) -> ProjectBrief:
    project = request.app.state.repository.get(project_id)
    if project is None:
        raise PublicError("project_not_found", "Project not found.", 404)
    return ProjectBrief(**project.brief)


@router.post("")
def render_project(
    project_id: str,
    body: RenderRequest,
    request: Request,
) -> dict[str, Any]:
    brief = _load_brief(project_id, request)
    settings = request.app.state.settings
    agent_mode = project_agent_mode(brief, settings.default_agent_mode)
    policy = execution_policy(agent_mode)
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

    enterprise_grade = bool(policy["enterpriseGrade"])
    image_resolution_mode = body.image_resolution_mode
    if image_resolution_mode == "auto":
        image_resolution_mode = str(policy["imageResolutionMode"])
    policy_image_timeout = float(policy["imageSearchTimeoutSeconds"])
    result = render_slide_deck(
        deck=SlideDeck(**deck_checkpoint.payload),
        slide_deck_version=deck_checkpoint.version,
        output_root=settings.asset_path,
        image_gateway=request.app.state.image_gateway,
        image_resolution_mode=image_resolution_mode,
        image_search_enabled=settings.image_search_enabled,
        image_search_timeout_seconds=(
            max(settings.image_search_timeout_seconds, policy_image_timeout)
            if enterprise_grade
            else min(settings.image_search_timeout_seconds, policy_image_timeout)
        ),
        expert_mode=enterprise_grade,
        expert_image_min_long_edge=settings.expert_image_min_long_edge,
        expert_image_min_short_edge=settings.expert_image_min_short_edge,
        expert_key_image_min_long_edge=settings.expert_key_image_min_long_edge,
        expert_key_image_min_short_edge=settings.expert_key_image_min_short_edge,
        realesrgan_executable=(
            settings.realesrgan_executable if settings.realesrgan_enabled else None
        ),
        realesrgan_model=settings.realesrgan_model,
        realesrgan_timeout_seconds=settings.realesrgan_timeout_seconds,
        shared_asset_library_path=settings.shared_asset_library_path,
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
    response["agentMode"] = agent_mode
    response["executionPolicy"] = policy
    response["nextStep"] = "quality"
    return response
