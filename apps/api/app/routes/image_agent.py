from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from ai_ppt_contracts import SlideDeck
from app.errors import PublicError
from app.services.render import VisualAsset, resolve_visual_assets


router = APIRouter(prefix="/projects/{project_id}/image-agent", tags=["image-agent"])


class ImageAgentResolveRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    slide_deck_version: int = Field(alias="slideDeckVersion", ge=1)
    mode: Literal["auto", "web_first", "generate"] = "auto"


def _ensure_deck(project_id: str, slide_deck_version: int, request: Request) -> SlideDeck:
    if request.app.state.repository.get(project_id) is None:
        raise PublicError("project_not_found", "Project not found.", 404)
    checkpoint = request.app.state.repository.latest_checkpoint_for_stage(project_id, "slide_deck")
    if checkpoint is None:
        raise PublicError("slide_deck_not_found", "Slide deck not found.", 404)
    if checkpoint.status != "confirmed":
        raise PublicError(
            "slide_deck_not_confirmed",
            "Slide deck must be confirmed before resolving images.",
            409,
        )
    if checkpoint.version != slide_deck_version:
        raise PublicError(
            "checkpoint_version_conflict",
            "Checkpoint was updated by another request.",
            409,
        )
    return SlideDeck(**checkpoint.payload)


@router.post("/resolve")
def resolve_project_images(
    project_id: str,
    body: ImageAgentResolveRequest,
    request: Request,
) -> dict[str, Any]:
    deck = _ensure_deck(project_id, body.slide_deck_version, request)
    settings = request.app.state.settings
    render_dir = settings.asset_path / "renders" / project_id / f"slide-deck-v{body.slide_deck_version}"
    assets = resolve_visual_assets(
        deck,
        render_dir,
        request.app.state.image_gateway,
        mode=body.mode,
        image_search_enabled=settings.image_search_enabled,
        image_search_timeout_seconds=settings.image_search_timeout_seconds,
    )
    return {
        "projectId": project_id,
        "slideDeckVersion": body.slide_deck_version,
        "mode": body.mode,
        "imageAssets": [_asset_payload(project_id, body.slide_deck_version, asset) for asset in assets.values()],
    }


@router.get("/assets/{slide_index}")
def download_image_asset(
    project_id: str,
    slide_index: int,
    slideDeckVersion: int,
    request: Request,
) -> FileResponse:
    if slide_index < 1:
        raise PublicError("image_asset_invalid", "Slide index is invalid.", 422)
    _ensure_deck(project_id, slideDeckVersion, request)
    root = request.app.state.settings.asset_path.resolve()
    assets_dir = root / "renders" / project_id / f"slide-deck-v{slideDeckVersion}" / "assets"
    if not assets_dir.is_dir():
        raise PublicError("image_asset_not_found", "Image asset has not been resolved yet.", 404)
    matches = sorted(
        path
        for path in assets_dir.glob(f"slide-{slide_index}-*")
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg"}
    )
    if not matches:
        raise PublicError("image_asset_not_found", "Image asset has not been resolved yet.", 404)
    asset_path = matches[0].resolve()
    try:
        asset_path.relative_to(root)
    except ValueError:
        raise PublicError("image_asset_invalid", "Image asset is unavailable.", 500) from None
    return FileResponse(asset_path, media_type=_media_type(asset_path), filename=asset_path.name)


def _asset_payload(project_id: str, slide_deck_version: int, asset: VisualAsset) -> dict[str, Any]:
    return {
        "slide": asset.slide_index,
        "imageType": asset.image_type,
        "sourceType": asset.source_type,
        "mimeType": asset.mime_type,
        "path": str(asset.path),
        "assetUrl": f"/api/projects/{project_id}/image-agent/assets/{asset.slide_index}?slideDeckVersion={slide_deck_version}",
        "query": asset.query,
        "purpose": asset.purpose,
        "attribution": asset.attribution,
        "providerChain": asset.provider_chain,
    }


def _media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".svg":
        return "image/svg+xml"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    return "image/png"
