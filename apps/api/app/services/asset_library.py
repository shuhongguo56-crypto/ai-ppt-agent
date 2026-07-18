from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from app.services.image_quality import raster_dimensions


PROMOTABLE_SOURCES = {
    "openverse_search",
    "wikimedia_commons_search",
    "ai_fallback",
    "free_ai_fallback",
}
QUALITY_FLOOR = 80


def promote_asset(asset: Any, library_root: Path | None) -> bool:
    """Promote a delivery-safe visual into the reusable project library."""

    if library_root is None or str(getattr(asset, "source_type", "")) not in PROMOTABLE_SOURCES:
        return False
    source = Path(getattr(asset, "path"))
    dimensions = raster_dimensions(source)
    if dimensions is None or _contains_sensitive_text(
        " ".join(
            [
                str(getattr(asset, "query", "")),
                str(getattr(asset, "purpose", "")),
            ]
        )
    ):
        return False
    score = _quality_score(asset, dimensions)
    library_root.mkdir(parents=True, exist_ok=True)
    catalog_path = library_root / "catalog.json"
    catalog = _read_catalog(catalog_path)
    image_type = _safe_slug(str(getattr(asset, "image_type", "visual")))
    category_scores = sorted(
        int(item.get("qualityScore") or 0)
        for item in catalog
        if item.get("imageType") == image_type
    )
    dynamic_threshold = _top_decile_threshold(category_scores)
    if score < max(QUALITY_FLOOR, dynamic_threshold):
        return False
    content = source.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if any(item.get("contentHash") == digest for item in catalog):
        return False
    extension = ".jpg" if str(getattr(asset, "mime_type", "")) == "image/jpeg" else ".png"
    destination_dir = library_root / "images" / image_type
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{digest[:20]}{extension}"
    shutil.copy2(source, destination)
    width, height = dimensions
    catalog.append(
        {
            "schemaVersion": "1.0.0",
            "contentHash": digest,
            "imageType": image_type,
            "sourceType": str(getattr(asset, "source_type", "")),
            "licenseStatus": "generated" if "ai_fallback" in str(getattr(asset, "source_type", "")) else "open-license",
            "qualityScore": score,
            "width": width,
            "height": height,
            "path": destination.relative_to(library_root).as_posix(),
            "attribution": str(getattr(asset, "attribution", ""))[:320],
            "tags": _safe_public_tags(str(getattr(asset, "query", ""))),
        }
    )
    _write_catalog(catalog_path, catalog)
    return True


def _quality_score(asset: Any, dimensions: tuple[int, int]) -> int:
    width, height = dimensions
    long_edge, short_edge = max(width, height), min(width, height)
    resolution = 45 if long_edge >= 3840 and short_edge >= 2160 else 35 if long_edge >= 1920 and short_edge >= 1080 else 15
    source = 30 if "ai_fallback" in str(getattr(asset, "source_type", "")) else 25
    return min(100, resolution + source + 25 + 10)


def _top_decile_threshold(scores: list[int]) -> int:
    if len(scores) < 10:
        return QUALITY_FLOOR
    position = max(0, int(len(scores) * 0.9) - 1)
    return scores[position]


def _safe_public_tags(value: str) -> list[str]:
    blocked = {"image", "photo", "presentation", "slide", "visual", "with", "from", "about"}
    return sorted(
        {
            token
            for token in re.findall(r"[a-z]{3,}", value.casefold())
            if token not in blocked
        }
    )[:12]


def _contains_sensitive_text(value: str) -> bool:
    return bool(
        re.search(r"\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b", value, re.IGNORECASE)
        or re.search(r"(?<!\d)1[3-9]\d{9}(?!\d)", value)
        or re.search(r"\b(?:password|secret|private key|身份证|银行卡|手机号)\b", value, re.IGNORECASE)
    )


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", value.casefold()).strip("-")
    return slug[:64] or "visual"


def _read_catalog(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _write_catalog(path: Path, catalog: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)
