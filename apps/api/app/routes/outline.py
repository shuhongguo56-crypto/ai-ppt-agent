from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_ppt_contracts import OutlineDecision, ProjectBrief, SourcePack
from app.domain.repositories import ProjectNotFound, VersionConflict
from app.errors import PublicError
from app.services.agent_modes import execution_policy, project_agent_mode
from app.services.outline import generate_outline_decision
from app.services.research import research_topic_sources


router = APIRouter(prefix="/projects/{project_id}/outline", tags=["outline"])


class OutlineGenerateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_pack: SourcePack | None = Field(default=None, alias="sourcePack")
    supplement_research: bool = Field(default=False, alias="supplementResearch")


class OutlineConfirmRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    outline_decision_version: int = Field(alias="outlineDecisionVersion", ge=1)


class OutlinePatchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    expected_version: int = Field(alias="expectedVersion", ge=0)
    outline_decision: OutlineDecision = Field(alias="outlineDecision")

    @field_validator("outline_decision")
    @classmethod
    def outline_must_use_current_schema(
        cls, value: OutlineDecision
    ) -> OutlineDecision:
        if value.schema_version != "1.0.0":
            raise ValueError("outlineDecision schemaVersion must be 1.0.0")
        return value


def _checkpoint_response(checkpoint) -> dict[str, Any]:
    return {
        "projectId": checkpoint.project_id,
        "stage": checkpoint.stage,
        "status": checkpoint.status,
        "version": checkpoint.version,
        "outlineDecision": checkpoint.payload,
        "createdAt": checkpoint.created_at.isoformat(),
    }


def _load_brief(project_id: str, request: Request) -> ProjectBrief:
    project = request.app.state.repository.get(project_id)
    if project is None:
        raise PublicError("project_not_found", "Project not found.", 404)
    return ProjectBrief(**project.brief)


def _latest_outline(project_id: str, request: Request):
    checkpoint = request.app.state.repository.latest_checkpoint_for_stage(
        project_id, "outline"
    )
    if checkpoint is None:
        raise PublicError("outline_not_found", "Outline not found.", 404)
    return checkpoint


def _merge_source_packs(primary: SourcePack, supplement: SourcePack | None) -> SourcePack:
    if supplement is None:
        return primary
    sources = []
    seen: set[tuple[str, str]] = set()
    for source in [*primary.sources, *supplement.sources]:
        identity = (source.source_id.strip().casefold(), (source.url or "").strip().casefold())
        if identity in seen:
            continue
        seen.add(identity)
        sources.append(source)
    return SourcePack(schemaVersion="1.0.0", projectId=primary.project_id, sources=sources)


@router.post("/generate")
def generate_outline(
    project_id: str,
    body: OutlineGenerateRequest,
    request: Request,
) -> dict[str, Any]:
    brief = _load_brief(project_id, request)
    settings = request.app.state.settings
    agent_mode = project_agent_mode(brief, settings.default_agent_mode)
    policy = execution_policy(agent_mode)
    if body.source_pack is not None and body.source_pack.project_id != project_id:
        raise PublicError(
            "source_pack_project_mismatch",
            "Source pack does not belong to this project.",
            422,
        )
    effective_source_pack = body.source_pack
    should_research = effective_source_pack is None or (
        body.supplement_research
        and settings.topic_research_enabled
        and bool(policy["researchEnabled"])
    )
    if should_research:
        enterprise_grade = bool(policy["enterpriseGrade"])
        research_max_sources = int(policy["researchMaxSources"])
        research_timeout_seconds = float(policy["researchTimeoutSeconds"])
        research_result = research_topic_sources(
            project_id=project_id,
            topic=brief.topic,
            audience=brief.audience,
            language=brief.output_language,
            enabled=settings.topic_research_enabled and bool(policy["researchEnabled"]),
            timeout_seconds=(
                max(settings.topic_research_timeout_seconds, research_timeout_seconds)
                if enterprise_grade
                else min(settings.topic_research_timeout_seconds, research_timeout_seconds)
            ),
            max_sources=(
                min(8, max(settings.topic_research_max_sources, research_max_sources))
                if enterprise_grade
                else min(settings.topic_research_max_sources, research_max_sources)
            ),
            user_agent=settings.topic_research_user_agent,
        )
        if effective_source_pack is None:
            effective_source_pack = research_result.source_pack
        else:
            effective_source_pack = _merge_source_packs(
                effective_source_pack,
                research_result.source_pack,
            )
    else:
        research_result = None
    outline = generate_outline_decision(
        brief=brief,
        source_pack=effective_source_pack,
        text_gateway=request.app.state.text_gateway,
        model_backend=request.app.state.settings.model_backend,
        agent_mode=agent_mode,
        prompt_quality_target=str(policy["promptQualityTarget"]),
    )
    latest = request.app.state.repository.latest_checkpoint_for_stage(project_id, "outline")
    expected_version = 0 if latest is None else latest.version
    try:
        checkpoint = request.app.state.repository.put_checkpoint(
            project_id,
            "outline",
            "draft",
            outline.model_dump(by_alias=True, mode="json"),
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
    response["sourcePack"] = (
        effective_source_pack.model_dump(by_alias=True, mode="json")
        if effective_source_pack is not None
        else None
    )
    response["research"] = (
        {
            "mode": "supplied",
            "providers": [],
            "query": brief.topic,
            "warnings": [],
        }
        if research_result is None
        else {
            "mode": (
                f"supplied_plus_{research_result.mode}"
                if body.source_pack is not None
                else research_result.mode
            ),
            "providers": research_result.providers,
            "query": research_result.query,
            "warnings": research_result.warnings,
        }
    )
    response["agentMode"] = agent_mode
    response["executionPolicy"] = policy
    response["nextStep"] = "outline_review"
    return response


@router.patch("")
def patch_outline(
    project_id: str,
    body: OutlinePatchRequest,
    request: Request,
) -> dict[str, Any]:
    _load_brief(project_id, request)
    if body.outline_decision.project_id != project_id:
        raise PublicError(
            "outline_project_mismatch",
            "Outline does not belong to this project.",
            422,
        )
    try:
        checkpoint = request.app.state.repository.put_checkpoint(
            project_id,
            "outline",
            "draft",
            body.outline_decision.model_dump(by_alias=True, mode="json"),
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
    response = _checkpoint_response(checkpoint)
    response["nextStep"] = "outline_review"
    return response


@router.post("/confirm")
def confirm_outline(
    project_id: str,
    body: OutlineConfirmRequest,
    request: Request,
) -> dict[str, Any]:
    _load_brief(project_id, request)
    latest = _latest_outline(project_id, request)
    if latest.version != body.outline_decision_version:
        raise PublicError(
            "checkpoint_version_conflict",
            "Checkpoint was updated by another request.",
            409,
        )
    try:
        checkpoint = request.app.state.repository.put_checkpoint(
            project_id,
            "outline",
            "confirmed",
            latest.payload,
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
    response["nextStep"] = "visual_direction"
    return response
