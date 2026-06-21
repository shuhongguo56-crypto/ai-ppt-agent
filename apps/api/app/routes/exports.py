from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from app.errors import PublicError


ExportTarget = Literal["pptx", "hyperframes_html"]

router = APIRouter(prefix="/projects/{project_id}/exports", tags=["exports"])


def _latest_render(project_id: str, request: Request):
    if request.app.state.repository.get(project_id) is None:
        raise PublicError("project_not_found", "Project not found.", 404)
    checkpoint = request.app.state.repository.latest_checkpoint_for_stage(project_id, "render")
    if checkpoint is None or checkpoint.status != "complete":
        raise PublicError("render_not_found", "Render result not found.", 404)
    quality = request.app.state.repository.latest_checkpoint_for_stage(project_id, "quality")
    if quality is None or quality.status != "complete":
        raise PublicError("quality_not_passed", "Quality check must pass before export.", 409)
    if quality.payload.get("renderVersion") != checkpoint.version:
        raise PublicError("quality_not_current", "Quality check is stale.", 409)
    return checkpoint


def _artifact(payload: dict[str, Any], target: ExportTarget) -> dict[str, Any]:
    for artifact in payload.get("artifacts", []):
        if artifact.get("target") == target:
            return artifact
    raise PublicError("export_artifact_not_found", "Export artifact not found.", 404)


def _safe_path(root: Path, raw_path: str) -> Path:
    root_resolved = root.resolve()
    path = Path(raw_path)
    if not path.is_absolute():
        path = root_resolved / path
    resolved = path.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        raise PublicError("export_artifact_invalid", "Export artifact is unavailable.", 500) from None
    if not resolved.is_file():
        raise PublicError("export_artifact_missing", "Export artifact file is missing.", 404)
    return resolved


@router.get("")
def list_exports(project_id: str, request: Request) -> dict[str, Any]:
    checkpoint = _latest_render(project_id, request)
    exports = []
    for artifact in checkpoint.payload["artifacts"]:
        target = artifact["target"]
        exports.append(
            {
                "target": target,
                "contentType": artifact["contentType"],
                "slideCount": artifact["slideCount"],
                "downloadUrl": f"/api/projects/{project_id}/exports/{target}",
            }
        )
    return {
        "projectId": project_id,
        "renderVersion": checkpoint.version,
        "exports": exports,
    }


@router.get("/{target}")
def download_export(
    project_id: str,
    target: ExportTarget,
    request: Request,
) -> FileResponse:
    checkpoint = _latest_render(project_id, request)
    artifact = _artifact(checkpoint.payload, target)
    path = _safe_path(request.app.state.settings.asset_path, artifact["path"])
    filename = "deck.pptx" if target == "pptx" else "hyperframes.html"
    return FileResponse(
        path,
        media_type=artifact["contentType"],
        filename=filename,
    )
