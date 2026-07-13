from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from ai_ppt_contracts import SourcePack
from app.errors import PublicError
from app.services.sources import extract_source_pack


router = APIRouter(prefix="/projects/{project_id}/sources", tags=["sources"])


class SourceExtractRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    file_name: str = Field(alias="fileName", min_length=1, max_length=240)
    content_type: str | None = Field(default=None, alias="contentType", max_length=160)
    data_base64: str = Field(alias="dataBase64", min_length=1)


class ExtractionCoverageResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    unit: str
    discovered: int | None = None
    processed: int = Field(ge=0)
    failed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    analyzed_chars: int = Field(alias="analyzedChars", ge=0)


class ExtractionWarningResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str
    message: str
    affected_units: list[str] = Field(default_factory=list, alias="affectedUnits")


class SourceExtractResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_pack: SourcePack = Field(alias="sourcePack")
    extracted_chars: int = Field(alias="extractedChars", ge=1)
    truncated: bool
    understanding_status: Literal["complete", "partial"] = Field(alias="understandingStatus")
    coverage: ExtractionCoverageResponse
    warnings: list[ExtractionWarningResponse] = Field(default_factory=list)


@router.post("/extract")
def extract_source(
    project_id: str,
    body: SourceExtractRequest,
    request: Request,
) -> dict[str, Any]:
    if request.app.state.repository.get(project_id) is None:
        raise PublicError("project_not_found", "Project not found.", 404)
    extracted = extract_source_pack(
        project_id=project_id,
        file_name=body.file_name,
        content_type=body.content_type,
        data_base64=body.data_base64,
    )
    response = SourceExtractResponse(
        sourcePack=extracted.source_pack,
        extractedChars=extracted.extracted_chars,
        truncated=extracted.truncated,
        understandingStatus=extracted.understanding_status,
        coverage=extracted.coverage,
        warnings=extracted.warnings,
    )
    return response.model_dump(by_alias=True, mode="json")
