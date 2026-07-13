from pathlib import Path
from typing import Any, Literal
import zipfile

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
    candidates = [path] if path.is_absolute() else [path, root_resolved / path]
    saw_outside_root = False
    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            saw_outside_root = True
            continue
        if resolved.is_file():
            return resolved
    if saw_outside_root:
        raise PublicError("export_artifact_invalid", "Export artifact is unavailable.", 500)
    raise PublicError("export_artifact_missing", "Export artifact file is missing.", 404)


@router.get("")
def list_exports(project_id: str, request: Request) -> dict[str, Any]:
    checkpoint = _latest_render(project_id, request)
    exports = []
    for artifact in checkpoint.payload["artifacts"]:
        target = artifact["target"]
        content_type = (
            "application/zip"
            if target == "hyperframes_html"
            else artifact["contentType"]
        )
        exports.append(
            {
                "target": target,
                "contentType": content_type,
                "slideCount": artifact["slideCount"],
                "downloadUrl": f"/api/projects/{project_id}/exports/{target}",
                "previewUrl": (
                    f"/api/projects/{project_id}/exports/{target}?inline=true"
                    if target == "hyperframes_html"
                    else None
                ),
            }
        )
    return {
        "projectId": project_id,
        "renderVersion": checkpoint.version,
        "exports": exports,
    }


@router.get("/assets/{file_name}")
def download_hyperframes_asset(project_id: str, file_name: str, request: Request) -> FileResponse:
    if "/" in file_name or "\\" in file_name or not file_name:
        raise PublicError("export_asset_invalid", "Export asset is unavailable.", 400)
    checkpoint = _latest_render(project_id, request)
    artifact = _artifact(checkpoint.payload, "hyperframes_html")
    html_path = _safe_path(request.app.state.settings.asset_path, artifact["path"])
    root_resolved = request.app.state.settings.asset_path.resolve()
    assets_dir = html_path.parent / "assets"
    asset_path = assets_dir / file_name
    try:
        asset_path.resolve().relative_to(root_resolved)
        asset_path.resolve().relative_to(assets_dir.resolve())
    except ValueError:
        raise PublicError("export_asset_invalid", "Export asset is unavailable.", 400) from None
    if not asset_path.is_file():
        raise PublicError("export_asset_missing", "Export asset file is missing.", 404)
    suffix = asset_path.suffix.lower()
    media_type = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/svg+xml" if suffix == ".svg" else "image/png"
    return FileResponse(asset_path, media_type=media_type)


@router.get("/{target}")
def download_export(
    project_id: str,
    target: ExportTarget,
    request: Request,
    inline: bool = False,
) -> FileResponse:
    checkpoint = _latest_render(project_id, request)
    artifact = _artifact(checkpoint.payload, target)
    path = _safe_path(request.app.state.settings.asset_path, artifact["path"])
    if inline and target == "hyperframes_html":
        return FileResponse(
            path,
            media_type=artifact["contentType"],
            headers={'Content-Disposition': 'inline; filename="hyperframes.html"'},
        )
    if target == "hyperframes_html":
        package_path = _build_hyperframes_package(
            root=request.app.state.settings.asset_path,
            html_path=path,
        )
        return FileResponse(
            package_path,
            media_type="application/zip",
            filename="hyperframes-package.zip",
        )
    return FileResponse(
        path,
        media_type=artifact["contentType"],
        filename="deck.pptx",
    )


def _build_hyperframes_package(*, root: Path, html_path: Path) -> Path:
    root_resolved = root.resolve()
    render_dir = html_path.parent
    package_path = render_dir / "hyperframes-package.zip"
    try:
        package_path.resolve().relative_to(root_resolved)
    except ValueError:
        raise PublicError("export_artifact_invalid", "Export artifact is unavailable.", 500) from None
    assets_dir = render_dir / "assets"
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(html_path, "hyperframes.html")
        if assets_dir.is_dir():
            for asset_path in sorted(path for path in assets_dir.rglob("*") if path.is_file()):
                resolved = asset_path.resolve()
                try:
                    resolved.relative_to(root_resolved)
                except ValueError:
                    continue
                archive.write(resolved, str(Path("assets") / resolved.relative_to(assets_dir.resolve())))
    return package_path
