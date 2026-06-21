from typing import Any

from fastapi import APIRouter, Request

from ai_ppt_contracts import ProjectBrief
from app.errors import PublicError
from app.services.billing import PLANS, quote_project_credits


router = APIRouter(tags=["billing"])


@router.get("/billing/plans")
def list_billing_plans() -> dict[str, Any]:
    return {"plans": [plan.model_dump(by_alias=True, mode="json") for plan in PLANS]}


@router.get("/projects/{project_id}/credits/quote")
def quote_project(project_id: str, request: Request) -> dict[str, Any]:
    project = request.app.state.repository.get(project_id)
    if project is None:
        raise PublicError("project_not_found", "Project not found.", 404)
    quote = quote_project_credits(ProjectBrief(**project.brief))
    return {"quote": quote.model_dump(by_alias=True, mode="json")}