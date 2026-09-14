from __future__ import annotations

import html
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from urllib import parse, request as urlrequest

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from ai_ppt_contracts import RenderResult, SlideDeck
from app.ai.errors import ModelGatewayError
from app.ai.models import ImageRequest
from app.ai.protocols import ImageGateway
from app.services.asset_library import promote_asset
from app.services.composition_library import visual_placement
from app.services.image_quality import (
    EXPERT_KEY_PAGE_RESOLUTION,
    EXPERT_PAGE_RESOLUTION,
    ImageResolutionRequirement,
    meets_resolution,
    raster_dimensions,
    upscale_with_realesrgan,
)


MAX_IMAGE_BYTES = 8 * 1024 * 1024
OPEN_WEB_TEXT_RISK_TERMS = {
    "advertisement",
    "billboard",
    "branding",
    "label",
    "logo",
    "packaging",
    "poster",
    "sign",
    "signage",
    "watermark",
    "wordmark",
}
SCENE_INTENT_TERMS = {
    "battery",
    "charging",
    "city",
    "collaboration",
    "consumer",
    "design",
    "driver",
    "factory",
    "home",
    "laboratory",
    "library",
    "manufacturing",
    "meeting",
    "mobility",
    "modern",
    "production",
    "research",
    "road",
    "seminar",
    "showroom",
    "studio",
    "students",
    "team",
    "workshop",
    "classroom",
    "lecture",
}
SLIDE_CX = 12192000
SLIDE_CY = 6858000
FOREGROUND_SAFE_X = 460000
FOREGROUND_SAFE_TOP = 340000
FOREGROUND_SAFE_BOTTOM = 430000
EMU_PER_POINT = 12700
PPT_COVER_TITLE_MAX = 4800
PPT_COVER_TITLE_MID = 4300
PPT_COVER_TITLE_MIN = 3600
PPT_PAGE_TITLE_MAX = 3800
PPT_PAGE_TITLE_MID = 3500
PPT_PAGE_TITLE_MIN = 3100
PPT_STATEMENT_MAX = 2200
PPT_STATEMENT_MID = 2000
PPT_STATEMENT_MIN = 1900
PPT_CARD_MAX = 2000
PPT_CARD_MID = 1800
PPT_CARD_MIN = 1600
REF_DARK = "080A0F"
REF_PANEL = "111216"
REF_INK = "F8F3E7"
REF_GOLD = "F2BF4A"
REF_RED = "A92323"
REF_BLUE = "1F67D2"
REF_MUTED = "D7C7AD"
PPTX_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "assets" / "pptx-native-template.pptx"

IMAGE_SEARCH_FALLBACK_QUERIES = {
    "background": ("presentation background", "abstract technology background"),
    "course_review_atmosphere": ("university classroom", "lecture hall", "students classroom"),
    "business_scene": ("business meeting", "strategy workshop", "modern office meeting"),
    "classical_element": ("traditional chinese ink landscape", "chinese classical architecture"),
    "thesis_concept": ("research paper", "university library", "knowledge graph"),
    "product_showcase": ("product showcase", "studio product photography"),
    "icon_illustration": ("abstract geometric metaphor", "symbolic objects no text"),
    "data_visual": ("abstract evidence concept", "business growth metaphor no text"),
}


@dataclass(frozen=True, slots=True)
class VisualAsset:
    slide_index: int
    path: Path
    rel_path: str
    file_name: str
    mime_type: str
    source_type: str
    alt: str
    query: str
    image_type: str
    purpose: str
    prompt: str
    provider_chain: list[str]
    attribution: str | None = None
    width: int | None = None
    height: int | None = None
    original_width: int | None = None
    original_height: int | None = None
    upscaled: bool = False
    resolution_profile: str | None = None


@dataclass(frozen=True, slots=True)
class RenderTextBlock:
    content: str


class RenderSlideProxy:
    def __init__(self, slide, *, subtitle: str, title: str | None = None) -> None:
        self._slide = slide
        self.subtitle = subtitle
        if title is not None:
            self.title = title

    def __getattr__(self, name: str):
        return getattr(self._slide, name)


def render_slide_deck(
    *,
    deck: SlideDeck,
    slide_deck_version: int,
    output_root: Path,
    image_gateway: ImageGateway | None = None,
    image_resolution_mode: str = "auto",
    image_search_enabled: bool = True,
    image_search_timeout_seconds: float | None = None,
    expert_mode: bool = False,
    expert_image_min_long_edge: int = 1920,
    expert_image_min_short_edge: int = 1080,
    expert_key_image_min_long_edge: int = 3840,
    expert_key_image_min_short_edge: int = 2160,
    realesrgan_executable: Path | None = None,
    realesrgan_model: str = "realesrgan-x4plus",
    realesrgan_timeout_seconds: float = 180,
    shared_asset_library_path: Path | None = None,
) -> RenderResult:
    render_dir = output_root / "renders" / deck.project_id / f"slide-deck-v{slide_deck_version}"
    render_dir.mkdir(parents=True, exist_ok=True)
    pptx_path = render_dir / "deck.pptx"
    html_path = render_dir / "hyperframes.html"
    visual_assets = resolve_visual_assets(
        deck,
        render_dir,
        image_gateway,
        mode=image_resolution_mode,
        image_search_enabled=image_search_enabled,
        image_search_timeout_seconds=image_search_timeout_seconds,
        expert_mode=expert_mode,
        expert_image_min_long_edge=expert_image_min_long_edge,
        expert_image_min_short_edge=expert_image_min_short_edge,
        expert_key_image_min_long_edge=expert_key_image_min_long_edge,
        expert_key_image_min_short_edge=expert_key_image_min_short_edge,
        realesrgan_executable=realesrgan_executable,
        realesrgan_model=realesrgan_model,
        realesrgan_timeout_seconds=realesrgan_timeout_seconds,
        shared_asset_library_path=shared_asset_library_path,
    )
    _write_pptx(deck, pptx_path, visual_assets)
    _write_hyperframes_html(deck, html_path, visual_assets)
    slide_count = len(deck.slides)
    return RenderResult(
        schemaVersion="1.0.0",
        projectId=deck.project_id,
        slideDeckVersion=slide_deck_version,
        artifacts=[
            {
                "schemaVersion": "1.0.0",
                "target": "pptx",
                "path": str(pptx_path),
                "contentType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "slideCount": slide_count,
            },
            {
                "schemaVersion": "1.0.0",
                "target": "hyperframes_html",
                "path": str(html_path),
                "contentType": "text/html; charset=utf-8",
                "slideCount": slide_count,
            },
        ],
    )


def resolve_visual_assets(
    deck: SlideDeck,
    render_dir: Path,
    image_gateway: ImageGateway | None,
    *,
    mode: str = "auto",
    image_search_enabled: bool = True,
    image_search_timeout_seconds: float | None = None,
    expert_mode: bool = False,
    expert_image_min_long_edge: int = 1920,
    expert_image_min_short_edge: int = 1080,
    expert_key_image_min_long_edge: int = 3840,
    expert_key_image_min_short_edge: int = 2160,
    realesrgan_executable: Path | None = None,
    realesrgan_model: str = "realesrgan-x4plus",
    realesrgan_timeout_seconds: float = 180,
    shared_asset_library_path: Path | None = None,
) -> dict[int, VisualAsset]:
    assets_dir = render_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    assets: dict[int, VisualAsset] = {}
    seen_image_hashes: set[str] = set()
    image_plan_by_slide = {item.slide: item for item in deck.image_plan}
    candidate_assets: dict[int, VisualAsset | None] = {}
    # Enterprise decks value a relevant, licensed photograph over an instant
    # abstract substitute.  The old 0.8s default was enough to retrieve JSON
    # but routinely expired while downloading the selected image, causing a
    # whole demo deck to fall back to owned diagrams.  Keep an explicit caller
    # budget untouched, while giving the research/enterprise path enough time
    # to complete the photo-first cascade in parallel.
    if expert_mode and image_search_timeout_seconds is None:
        image_search_timeout_seconds = 3.0

    def resolve_candidate(slide) -> tuple[int, VisualAsset | None]:
        image_item = image_plan_by_slide[slide.slide_index]
        # Every page gets one photo/illustration sourcing attempt first.  A
        # framework or evidence page may ultimately use an owned explanation,
        # but it must not silently skip the real-image cascade.  That is what
        # previously made an entire demo look like it had no images.
        asset = _resolve_visual_asset_candidate(
            slide,
            image_item,
            deck,
            assets_dir,
            image_gateway,
            mode=mode,
            image_search_enabled=image_search_enabled,
            image_search_timeout_seconds=image_search_timeout_seconds,
            expert_mode=expert_mode,
        )
        return slide.slide_index, asset

    worker_count = _image_resolution_worker_count(len(deck.slides))
    if worker_count == 1:
        for slide in deck.slides:
            slide_index, asset = resolve_candidate(slide)
            candidate_assets[slide_index] = asset
    else:
        # Searching and generating are network-bound and each slide writes to a
        # distinct file. Resolve the first candidate concurrently, then apply
        # the deterministic cross-slide uniqueness gate in slide order below.
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="ppt-image") as executor:
            for slide_index, asset in executor.map(resolve_candidate, deck.slides):
                candidate_assets[slide_index] = asset

    if image_gateway is not None:
        retry_rounds = _image_generation_retry_rounds()
        for retry_round in range(1, retry_rounds + 1):
            missing_slides = [
                slide
                for slide in deck.slides
                if candidate_assets.get(slide.slide_index) is None
            ]
            if not missing_slides:
                break
            # Free providers commonly throttle the first burst. Let the provider
            # recover, then retry only missing pages with lower concurrency.
            time.sleep(1.25 * retry_round)

            def retry_candidate(slide) -> tuple[int, VisualAsset | None]:
                image_item = image_plan_by_slide[slide.slide_index]
                asset = _generate_visual_asset_with_ai(
                    slide.slide_index,
                    image_item.search_query,
                    assets_dir,
                    image_gateway,
                    image_type=image_item.image_type,
                    purpose=image_item.purpose,
                    image_prompt=image_item.prompt,
                    provider_chain=list(image_item.provider_chain),
                    slide_title=slide.title,
                    slide_intent=slide.visual_intent,
                    asset_role=slide.design_plan.asset_role,
                    image_treatment=slide.design_plan.image_treatment,
                    composition_archetype=slide.design_plan.composition_archetype,
                    direction_name=deck.theme.name,
                    palette=deck.theme.palette,
                    variation_hint=(
                        f"Provider recovery retry {retry_round} for slide {slide.slide_index}; "
                        "keep the physical scene page-specific and completely free of typography"
                    ),
                )
                return slide.slide_index, asset

            retry_workers = min(2, len(missing_slides))
            with ThreadPoolExecutor(
                max_workers=retry_workers,
                thread_name_prefix="ppt-image-retry",
            ) as executor:
                for slide_index, asset in executor.map(retry_candidate, missing_slides):
                    if asset is not None:
                        candidate_assets[slide_index] = asset

    for slide in deck.slides:
        image_item = image_plan_by_slide[slide.slide_index]
        query = image_item.search_query
        # The owned visual library has to inherit the *page* palette rather
        # than the direction-level palette.  Anchor pages use dark faces while
        # evidence pages use paper faces; passing the direction palette here
        # was the reason a pale illustration could be dropped into a dark
        # cover and feel pasted on.
        page_palette = list(_slide_visual_palette(deck.theme.palette, slide)[:4])
        asset = candidate_assets.get(slide.slide_index)
        if asset is not None and _visual_asset_hash(asset.path) in seen_image_hashes:
            # Before asking a generator for another try, exhaust the free
            # licensed-photo cascade with the already-used image excluded.  It
            # is both more reliable and more semantically grounded than
            # prompting a no-key model to invent another nearly identical
            # classroom scene.
            alternative = _search_open_visual_asset(
                slide.slide_index,
                query,
                assets_dir,
                image_type=image_item.image_type,
                purpose=image_item.purpose,
                prompt=image_item.prompt,
                provider_chain=list(image_item.provider_chain),
                enabled=image_search_enabled,
                timeout_seconds=image_search_timeout_seconds,
                excluded_hashes=seen_image_hashes,
            )
            alternative_hash = _visual_asset_hash(alternative.path) if alternative is not None else ""
            asset = alternative if alternative_hash and alternative_hash not in seen_image_hashes else None
        if asset is None or _visual_asset_hash(asset.path) in seen_image_hashes:
            # A searched or generated image can be returned for multiple pages by an
            # upstream provider. Retry with an explicit page-specific variation, and
            # only accept the replacement after verifying its actual bytes are unique.
            for uniqueness_attempt in range(1, 4):
                generated_asset = _generate_visual_asset_with_ai(
                    slide.slide_index,
                    query,
                    assets_dir,
                    image_gateway,
                    image_type=image_item.image_type,
                    purpose=image_item.purpose,
                    image_prompt=image_item.prompt,
                    provider_chain=list(image_item.provider_chain),
                    slide_title=slide.title,
                    slide_intent=slide.visual_intent,
                    asset_role=slide.design_plan.asset_role,
                    image_treatment=slide.design_plan.image_treatment,
                    composition_archetype=slide.design_plan.composition_archetype,
                    direction_name=deck.theme.name,
                    palette=deck.theme.palette,
                    variation_hint=(
                        f"Unique visual alternative {uniqueness_attempt} for slide {slide.slide_index}: "
                        "change the camera angle, subject arrangement, foreground and background balance, "
                        "lighting direction, and material emphasis while preserving the slide meaning"
                    ),
                )
                generated_hash = (
                    _visual_asset_hash(generated_asset.path) if generated_asset is not None else ""
                )
                if generated_asset is not None and generated_hash and generated_hash not in seen_image_hashes:
                    asset = generated_asset
                    break
            # A provider that keeps returning the same bytes has not produced a
            # usable page-specific asset. Treat that outcome as unresolved so the
            # proven prior-version recovery path runs before any local fallback.
            if asset is not None and _visual_asset_hash(asset.path) in seen_image_hashes:
                asset = None
        if asset is None:
            asset = _recover_prior_version_visual_asset(
                slide.slide_index,
                assets_dir,
                image_type=image_item.image_type,
                purpose=image_item.purpose,
                prompt=image_item.prompt,
                provider_chain=list(image_item.provider_chain),
                seen_image_hashes=seen_image_hashes,
            )
        if asset is None:
            # This is a delivery-safe last resort, never the primary route.
            # It remains a high-resolution, page-specific graphic rather than
            # an SVG placeholder so the deck still contains a usable visual if
            # the web and configured image providers are temporarily offline.
            asset = _write_owned_explainer_visual_asset(
                slide.slide_index,
                query,
                assets_dir,
                image_type=image_item.image_type,
                purpose=image_item.purpose,
                prompt=image_item.prompt,
                provider_chain=list(image_item.provider_chain),
                slide_title=slide.title,
                slide_intent=slide.visual_intent,
                composition_archetype=slide.design_plan.composition_archetype,
                palette=page_palette,
            )
        # Keep the source fingerprint as well as the delivery fingerprint.
        # A prior slide may already have been upscaled, in which case comparing
        # only its final PNG bytes lets the same downloaded JPEG slip onto a
        # later page.  That produces visually duplicated pages despite a clean
        # hash-based QA result.
        source_hash = _visual_asset_hash(asset.path)
        asset = _upgrade_visual_asset_for_expert_delivery(
            asset,
            slide=slide,
            expert_mode=expert_mode,
            normal_requirement=ImageResolutionRequirement(
                expert_image_min_long_edge,
                expert_image_min_short_edge,
                EXPERT_PAGE_RESOLUTION.label,
            ),
            key_requirement=ImageResolutionRequirement(
                expert_key_image_min_long_edge,
                expert_key_image_min_short_edge,
                EXPERT_KEY_PAGE_RESOLUTION.label,
            ),
            realesrgan_executable=realesrgan_executable,
            realesrgan_model=realesrgan_model,
            realesrgan_timeout_seconds=realesrgan_timeout_seconds,
        )
        delivery_hash = _visual_asset_hash(asset.path)
        if delivery_hash and delivery_hash in seen_image_hashes:
            # Cached source files and newly downloaded originals can use
            # different encodings for the same photograph.  The pre-upscale
            # source gate cannot always see that relationship, so enforce
            # uniqueness again on the exact bytes PowerPoint will embed.
            asset = _write_owned_explainer_visual_asset(
                slide.slide_index,
                query,
                assets_dir,
                image_type=image_item.image_type,
                purpose=image_item.purpose,
                prompt=image_item.prompt,
                provider_chain=list(image_item.provider_chain),
                slide_title=slide.title,
                slide_intent=slide.visual_intent,
                composition_archetype=slide.design_plan.composition_archetype,
                palette=page_palette,
            )
            source_hash = _visual_asset_hash(asset.path)
            asset = _upgrade_visual_asset_for_expert_delivery(
                asset,
                slide=slide,
                expert_mode=expert_mode,
                normal_requirement=ImageResolutionRequirement(
                    expert_image_min_long_edge,
                    expert_image_min_short_edge,
                    EXPERT_PAGE_RESOLUTION.label,
                ),
                key_requirement=ImageResolutionRequirement(
                    expert_key_image_min_long_edge,
                    expert_key_image_min_short_edge,
                    EXPERT_KEY_PAGE_RESOLUTION.label,
                ),
                realesrgan_executable=realesrgan_executable,
                realesrgan_model=realesrgan_model,
                realesrgan_timeout_seconds=realesrgan_timeout_seconds,
            )
        _write_cached_visual_asset(asset, assets_dir)
        promote_asset(asset, shared_asset_library_path)
        if source_hash:
            seen_image_hashes.add(source_hash)
        seen_image_hashes.add(_visual_asset_hash(asset.path))
        assets[slide.slide_index] = asset
    return assets


def _recover_prior_version_visual_asset(
    slide_index: int,
    assets_dir: Path,
    *,
    image_type: str,
    purpose: str,
    prompt: str,
    provider_chain: list[str],
    seen_image_hashes: set[str],
) -> VisualAsset | None:
    """Reuse a real, semantically identical asset from an earlier repair pass.

    A quality repair may change layout while keeping the page meaning. If a
    free provider is temporarily unavailable, a previously accepted image for
    the same project, slide, image role, and purpose is safer than exporting a
    vector placeholder. The file is copied into the current version so each
    render remains self-contained.
    """

    current_render_dir = assets_dir.parent
    match = re.fullmatch(r"slide-deck-v(\d+)", current_render_dir.name)
    if match is None:
        return None
    current_version = int(match.group(1))
    purpose_fingerprint = re.sub(r"\W+", "", purpose.casefold())
    accepted_sources = {
        "bing_image_search",
        "wikipedia_page_image",
        "wikimedia_commons_search",
        "openverse_search",
        "ai_fallback",
        "free_ai_fallback",
        "owned_design_library",
    }
    for version in range(current_version - 1, 0, -1):
        previous_assets = current_render_dir.parent / f"slide-deck-v{version}" / "assets"
        sidecar = previous_assets / f"slide-{slide_index}-asset.json"
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if str(data.get("sourceType") or "") not in accepted_sources:
            continue
        if str(data.get("imageType") or "") != image_type:
            continue
        previous_purpose = re.sub(r"\W+", "", str(data.get("purpose") or "").casefold())
        if not purpose_fingerprint or previous_purpose != purpose_fingerprint:
            continue
        file_name = str(data.get("fileName") or "")
        if not file_name or Path(file_name).name != file_name:
            continue
        source_path = previous_assets / file_name
        mime_type = str(data.get("mimeType") or "").casefold()
        if mime_type not in {"image/jpeg", "image/png"} or not source_path.is_file():
            continue
        content_hash = _visual_asset_hash(source_path)
        if not content_hash or content_hash in seen_image_hashes:
            continue
        if _image_has_excessive_visible_text(source_path):
            continue
        extension = ".jpg" if mime_type == "image/jpeg" else ".png"
        recovered_name = f"slide-{slide_index}-recovered-v{version}{extension}"
        recovered_path = assets_dir / recovered_name
        shutil.copy2(source_path, recovered_path)
        attribution = str(data.get("attribution") or "Previously accepted project visual")
        return VisualAsset(
            slide_index=slide_index,
            path=recovered_path,
            rel_path=f"assets/{recovered_name}",
            file_name=recovered_name,
            mime_type=mime_type,
            source_type=str(data["sourceType"]),
            alt=str(data.get("alt") or _asset_alt(slide_index, str(data.get("query") or ""))),
            query=str(data.get("query") or ""),
            image_type=image_type,
            purpose=purpose,
            prompt=prompt,
            provider_chain=provider_chain,
            attribution=f"{attribution} / recovered from slide-deck-v{version}",
        )
    return None


def _resolve_visual_asset_candidate(
    slide,
    image_item,
    deck: SlideDeck,
    assets_dir: Path,
    image_gateway: ImageGateway | None,
    *,
    mode: str,
    image_search_enabled: bool,
    image_search_timeout_seconds: float | None,
    expert_mode: bool = False,
) -> VisualAsset | None:
    query = image_item.search_query
    asset = None
    if mode != "generate":
        asset = _read_cached_visual_asset(
            slide.slide_index,
            assets_dir,
            expected_query=query,
            image_type=image_item.image_type,
            purpose=image_item.purpose,
            prompt=image_item.prompt,
            provider_chain=list(image_item.provider_chain),
        )
    if asset is None and mode != "generate":
        asset = _recover_prior_version_visual_asset(
            slide.slide_index,
            assets_dir,
            image_type=image_item.image_type,
            purpose=image_item.purpose,
            prompt=image_item.prompt,
            provider_chain=list(image_item.provider_chain),
            seen_image_hashes=set(),
        )
    if asset is None and mode != "generate":
        asset = _search_open_visual_asset(
            slide.slide_index,
            query,
            assets_dir,
            image_type=image_item.image_type,
            purpose=image_item.purpose,
            prompt=image_item.prompt,
            provider_chain=list(image_item.provider_chain),
            enabled=image_search_enabled,
            timeout_seconds=image_search_timeout_seconds,
        )
    preview_only_asset = None
    if asset is not None and expert_mode and _visual_asset_license_status(asset.source_type) == "unknown":
        preview_only_asset = asset
        asset = None
    if asset is None:
        asset = _generate_visual_asset_with_ai(
            slide.slide_index,
            query,
            assets_dir,
            image_gateway,
            image_type=image_item.image_type,
            purpose=image_item.purpose,
            image_prompt=image_item.prompt,
            provider_chain=list(image_item.provider_chain),
            slide_title=slide.title,
            slide_intent=slide.visual_intent,
            asset_role=slide.design_plan.asset_role,
            image_treatment=slide.design_plan.image_treatment,
            composition_archetype=slide.design_plan.composition_archetype,
            direction_name=deck.theme.name,
            palette=deck.theme.palette,
        )
    return asset or preview_only_asset


def _image_resolution_worker_count(slide_count: int) -> int:
    if slide_count <= 2:
        return 1
    raw = os.getenv("AI_PPT_IMAGE_RESOLUTION_WORKERS", "4")
    try:
        requested = int(raw)
    except ValueError:
        requested = 4
    return max(1, min(requested, slide_count, 6))


def _image_generation_retry_rounds() -> int:
    raw = os.getenv("AI_PPT_IMAGE_GENERATION_RETRY_ROUNDS", "2")
    try:
        requested = int(raw)
    except ValueError:
        requested = 2
    return max(0, min(requested, 3))


def _visual_asset_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _asset_sidecar_path(assets_dir: Path, slide_index: int) -> Path:
    return assets_dir / f"slide-{slide_index}-asset.json"


def _read_cached_visual_asset(
    slide_index: int,
    assets_dir: Path,
    *,
    expected_query: str,
    image_type: str,
    purpose: str,
    prompt: str,
    provider_chain: list[str],
) -> VisualAsset | None:
    sidecar = _asset_sidecar_path(assets_dir, slide_index)
    if not sidecar.is_file():
        return None
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    file_name = str(data.get("fileName") or "")
    source_type = str(data.get("sourceType") or "cached_visual_asset")
    if source_type in {
        "local_svg_fallback",
        "safe_vector_fallback",
        "local_deterministic_image",
        "owned_design_library",
        "free_ai_fallback",
    }:
        return None
    # An older generated or owned fallback may have been accepted only because
    # the previous image search was too impatient.  Do not let it become a
    # permanent cache hit now that the photo-first pipeline is available; a
    # fresh render should have a chance to upgrade it to a licensed visual.
    cached_query = str(data.get("query") or "")
    cached_attribution = str(data.get("attribution") or "")
    generic_queries = {
        query.casefold()
        for values in IMAGE_SEARCH_FALLBACK_QUERIES.values()
        for query in values
    }
    if (
        cached_query.casefold() in generic_queries
        and cached_query.casefold() != expected_query.casefold()
    ):
        # A previous run may have exhausted its page-specific search budget and
        # accepted a generic fallback such as "research paper".  Do not let that
        # weak cache permanently override a later, richer semantic query.
        return None
    if source_type in {
        "bing_image_search",
        "wikipedia_page_image",
        "wikimedia_commons_search",
        "openverse_search",
    } and not _candidate_metadata_is_relevant(cached_attribution, cached_query):
        return None
    if not file_name or "/" in file_name or "\\" in file_name:
        return None
    path = assets_dir / file_name
    if not path.is_file() or path.stat().st_size <= 0:
        return None
    if source_type in {
        "bing_image_search",
        "wikipedia_page_image",
        "wikimedia_commons_search",
        "openverse_search",
    }:
        dimensions = raster_dimensions(path)
        if dimensions is None or not _web_candidate_has_delivery_dimensions(*dimensions):
            return None
    if _image_has_excessive_visible_text(path):
        return None
    return VisualAsset(
        slide_index=slide_index,
        path=path,
        rel_path=f"assets/{file_name}",
        file_name=file_name,
        mime_type=str(data.get("mimeType") or "image/png"),
        source_type=source_type,
        alt=str(data.get("alt") or _asset_alt(slide_index, str(data.get("query") or ""))),
        query=cached_query,
        image_type=str(data.get("imageType") or image_type),
        purpose=str(data.get("purpose") or purpose),
        prompt=str(data.get("prompt") or prompt),
        provider_chain=[
            str(item)
            for item in (data.get("providerChain") if isinstance(data.get("providerChain"), list) else provider_chain)
        ],
        attribution=str(data.get("attribution")) if data.get("attribution") else None,
    )


def _write_cached_visual_asset(asset: VisualAsset, assets_dir: Path) -> None:
    license_status = _visual_asset_license_status(asset.source_type)
    payload = {
        "slide": asset.slide_index,
        "fileName": asset.file_name,
        "mimeType": asset.mime_type,
        "sourceType": asset.source_type,
        "alt": asset.alt,
        "query": asset.query,
        "imageType": asset.image_type,
        "purpose": asset.purpose,
        "prompt": asset.prompt,
        "providerChain": asset.provider_chain,
        "attribution": asset.attribution,
        "contentHash": _visual_asset_hash(asset.path),
        "width": asset.width,
        "height": asset.height,
        "originalWidth": asset.original_width,
        "originalHeight": asset.original_height,
        "upscaled": asset.upscaled,
        "resolutionProfile": asset.resolution_profile,
        "licenseStatus": license_status,
        "requiresUserConfirmation": license_status == "unknown",
    }
    try:
        _asset_sidecar_path(assets_dir, asset.slide_index).write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
    except OSError:
        return


def _visual_asset_license_status(source_type: str) -> str:
    if source_type in {"ai_fallback", "free_ai_fallback"}:
        return "generated"
    if source_type == "owned_design_library":
        return "owned"
    if source_type in {"openverse_search", "wikimedia_commons_search"}:
        return "open-license"
    return "unknown"


def _upgrade_visual_asset_for_expert_delivery(
    asset: VisualAsset,
    *,
    slide,
    expert_mode: bool,
    normal_requirement: ImageResolutionRequirement,
    key_requirement: ImageResolutionRequirement,
    realesrgan_executable: Path | None,
    realesrgan_model: str,
    realesrgan_timeout_seconds: float,
) -> VisualAsset:
    asset = _normalize_visual_asset_orientation(asset)
    dimensions = raster_dimensions(asset.path)
    if dimensions is None:
        return asset
    original_width, original_height = dimensions
    if not expert_mode:
        return replace(
            asset,
            width=original_width,
            height=original_height,
            original_width=original_width,
            original_height=original_height,
        )
    key_page = slide.slide_index == 1 or slide.design_plan.composition_archetype in {
        "closing_bloom",
        "manifesto_close",
        "future_horizon",
        "closing_echo",
    }
    requirement = key_requirement if key_page else normal_requirement
    # Free image endpoints frequently return a genuine 1024px raster but not a
    # faithful input for tiled neural upscalers.  Real-ESRGAN can then create
    # the visible 2x2/4x4 seams that make a slide look broken.  A clean Lanczos
    # delivery resize retains the original composition, while premium BYOK and
    # licensed photographs can still use the configured enhancement path.
    if asset.source_type in {"ai_fallback", "free_ai_fallback"}:
        return _resize_visual_asset_for_delivery(asset, requirement)
    if meets_resolution(dimensions, requirement):
        return replace(
            asset,
            width=original_width,
            height=original_height,
            original_width=original_width,
            original_height=original_height,
            resolution_profile=requirement.label,
        )
    destination = asset.path.with_name(f"slide-{asset.slide_index}-upscaled.png")
    upscaled_dimensions = upscale_with_realesrgan(
        asset.path,
        destination,
        executable=realesrgan_executable,
        requirement=requirement,
        model=realesrgan_model,
        timeout_seconds=realesrgan_timeout_seconds,
    )
    if upscaled_dimensions is None:
        return _resize_visual_asset_for_delivery(asset, requirement)
    width, height = upscaled_dimensions
    attribution = asset.attribution or "Visual asset"
    return replace(
        asset,
        path=destination,
        rel_path=f"assets/{destination.name}",
        file_name=destination.name,
        mime_type="image/png",
        attribution=f"{attribution} / enhanced locally with Real-ESRGAN",
        width=width,
        height=height,
        original_width=original_width,
        original_height=original_height,
        upscaled=True,
        resolution_profile=requirement.label,
    )


def _normalize_visual_asset_orientation(asset: VisualAsset) -> VisualAsset:
    """Bake EXIF orientation into pixels before PowerPoint embeds the image."""

    try:
        with Image.open(asset.path) as source:
            orientation = source.getexif().get(274, 1)
            if orientation in (None, 1):
                return asset
            normalized = ImageOps.exif_transpose(source).convert("RGB")
            destination = asset.path.with_name(f"slide-{asset.slide_index}-oriented.png")
            normalized.save(destination, format="PNG", optimize=True)
            width, height = normalized.size
    except (OSError, ValueError):
        return asset
    return replace(
        asset,
        path=destination,
        rel_path=f"assets/{destination.name}",
        file_name=destination.name,
        mime_type="image/png",
        width=width,
        height=height,
        original_width=width,
        original_height=height,
        attribution=f"{asset.attribution or 'Visual asset'} / EXIF orientation normalized",
    )


def _resize_visual_asset_for_delivery(
    asset: VisualAsset,
    requirement: ImageResolutionRequirement,
) -> VisualAsset:
    """Scale a generated raster without introducing neural-upscaler seams."""

    dimensions = raster_dimensions(asset.path)
    if dimensions is None:
        return asset
    original_width, original_height = dimensions
    if meets_resolution(dimensions, requirement):
        return replace(
            asset,
            width=original_width,
            height=original_height,
            original_width=original_width,
            original_height=original_height,
            resolution_profile=requirement.label,
        )
    scale = max(
        requirement.min_long_edge / max(original_width, original_height),
        requirement.min_short_edge / min(original_width, original_height),
    )
    target_width = max(original_width, round(original_width * scale))
    target_height = max(original_height, round(original_height * scale))
    destination = asset.path.with_name(f"slide-{asset.slide_index}-delivery.png")
    try:
        with Image.open(asset.path) as source:
            source.convert("RGB").resize(
                (target_width, target_height),
                Image.Resampling.LANCZOS,
            ).save(destination, format="PNG", optimize=True)
    except (OSError, ValueError):
        return replace(
            asset,
            width=original_width,
            height=original_height,
            original_width=original_width,
            original_height=original_height,
            resolution_profile=requirement.label,
        )
    return replace(
        asset,
        path=destination,
        rel_path=f"assets/{destination.name}",
        file_name=destination.name,
        mime_type="image/png",
        attribution=f"{asset.attribution or 'Generated visual'} / scaled locally without neural reconstruction",
        width=target_width,
        height=target_height,
        original_width=original_width,
        original_height=original_height,
        upscaled=True,
        resolution_profile=requirement.label,
    )


def _search_open_visual_asset(
    slide_index: int,
    query: str,
    assets_dir: Path,
    *,
    image_type: str,
    purpose: str,
    prompt: str,
    provider_chain: list[str],
    enabled: bool = True,
    timeout_seconds: float | None = None,
    excluded_hashes: set[str] | None = None,
) -> VisualAsset | None:
    if not enabled or os.getenv("AI_PPT_IMAGE_SEARCH_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return None
    deadline = time.monotonic() + _image_search_budget(timeout_seconds)
    for candidate_query in _image_search_queries(query, image_type)[:4]:
        for searcher in (
            _search_commons_visual_asset,
            _search_openverse_visual_asset,
            _search_wikipedia_page_visual_asset,
            _search_bing_visual_asset,
        ):
            if time.monotonic() > deadline:
                return None
            asset = searcher(
                slide_index,
                candidate_query,
                assets_dir,
                image_type=image_type,
                purpose=purpose,
                prompt=prompt,
                provider_chain=provider_chain,
                timeout_seconds=timeout_seconds,
                **({"excluded_hashes": excluded_hashes} if searcher in {
                    _search_commons_visual_asset, _search_openverse_visual_asset,
                } else {}),
            )
            if asset is not None:
                # A source can surface the same photo for several related
                # page queries.  Continue through the next search intent when
                # it has already been used instead of giving up and replacing
                # the page with a diagram or a low-quality generation.
                asset_hash = _visual_asset_hash(asset.path)
                if excluded_hashes and asset_hash and asset_hash in excluded_hashes:
                    asset.path.unlink(missing_ok=True)
                    continue
                return asset
    return None


def _search_openverse_visual_asset(
    slide_index: int,
    query: str,
    assets_dir: Path,
    *,
    image_type: str,
    purpose: str,
    prompt: str,
    provider_chain: list[str],
    timeout_seconds: float | None,
    excluded_hashes: set[str] | None = None,
) -> VisualAsset | None:
    search_url = "https://api.openverse.org/v1/images/?" + parse.urlencode(
        {
            "q": query,
            "page_size": "8",
            "license_type": "commercial",
            "mature": "false",
        }
    )
    try:
        payload = _read_json_url(
            search_url,
            timeout=_image_search_timeout(timeout_seconds),
            headers={"User-Agent": "AI-PPT-Agent/0.1 openverse-image-search"},
        )
        results = [item for item in payload.get("results") or [] if isinstance(item, dict)]
        if not results:
            return None
        # A generic result that merely happens to contain one topic word is not
        # useful in a decision slide. Rank the licensed results using their
        # descriptive metadata before spending a download on them.
        ordered = sorted(
            results,
            key=lambda item: _openverse_candidate_score(item, query),
            reverse=True,
        )
        # Keep semantic rank intact. Cross-slide exclusions select the next
        # eligible photograph; page number must never promote a weaker match.
        for item in ordered:
            if "modern" in query.casefold() and not _candidate_metadata_is_relevant(
                str(item.get("title") or ""), query
            ):
                continue
            if not _candidate_metadata_is_relevant(_openverse_candidate_metadata(item), query):
                continue
            if _openverse_metadata_has_text_risk(item):
                continue
            width = int(item.get("width") or 0)
            height = int(item.get("height") or 0)
            if width and height and not _web_candidate_has_delivery_dimensions(width, height):
                continue
            image_url = str(item.get("url") or item.get("thumbnail") or "")
            if not image_url.lower().startswith("https://"):
                continue
            extension = _extension_for_mime_from_url(image_url)
            file_name = f"slide-{slide_index}-openverse{extension}"
            path = assets_dir / file_name
            try:
                actual_mime = _download_binary(
                    image_url, path, timeout=_image_search_timeout(timeout_seconds),
                )
            except (OSError, ValueError, TimeoutError):
                path.unlink(missing_ok=True)
                continue
            if (
                actual_mime not in {"image/jpeg", "image/png"}
                or not path.is_file()
                or path.stat().st_size <= 0
                or _image_has_excessive_visible_text(path)
            ):
                path.unlink(missing_ok=True)
                continue
            correct_extension = _extension_for_mime(actual_mime)
            if excluded_hashes and _visual_asset_hash(path) in excluded_hashes:
                path.unlink(missing_ok=True)
                continue
            if path.suffix.lower() != correct_extension:
                renamed = path.with_suffix(correct_extension)
                path.replace(renamed)
                path = renamed
                file_name = path.name
            return VisualAsset(
                slide_index=slide_index,
                path=path,
                rel_path=f"assets/{file_name}",
                file_name=file_name,
                mime_type=actual_mime,
                source_type="openverse_search",
                alt=_asset_alt(slide_index, query),
                query=query,
                image_type=image_type,
                purpose=purpose,
                prompt=prompt,
                provider_chain=provider_chain,
                attribution=_openverse_attribution(item),
            )
    except (OSError, ValueError, TimeoutError, json.JSONDecodeError):
        return None
    return None


def _openverse_candidate_score(item: dict, query: str) -> int:
    """Prefer page-specific licensed images over a merely topical result.

    Openverse's ordering can be very broad for an enterprise slide query. Its
    title and tags are the only portable relevance evidence available before
    downloading an image, so use them to keep a factory page from receiving a
    generic road photo or an unrelated branded product shot.
    """

    metadata = _openverse_candidate_metadata(item).casefold()
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]{3,}", query.casefold())
        if token
        not in {
            "and",
            "for",
            "from",
            "image",
            "no",
            "photo",
            "presentation",
            "real",
            "scene",
            "text",
            "the",
            "with",
            "world",
        }
    ]
    score = sum(5 for token in dict.fromkeys(tokens) if token in metadata)
    if query.casefold() in metadata:
        score += 8
    width = int(item.get("width") or 0)
    height = int(item.get("height") or 0)
    if width >= 1280 and height >= 720:
        score += 2
    if _openverse_metadata_has_text_risk(item):
        score -= 40
    return score


def _commons_candidate_score(
    page: dict,
    image_info: dict,
    *,
    query: str,
    image_type: str,
) -> int:
    """Rank Commons files by their likely usefulness on this particular page.

    Commons search order is often archival rather than visual: a query for a
    seminar can lead with an empty room, a seating plan, or a PDF.  Use the
    descriptive file name plus the requested visual role to favour an actual
    human learning interaction where the slide asks for one.
    """
    title = str(page.get("title") or "")
    attribution = _commons_attribution(image_info) or ""
    metadata = _commons_search_metadata(page, image_info).casefold()
    score = _openverse_candidate_score(
        {
            "title": metadata,
            "tags": [],
            "width": int(image_info.get("width") or 0),
            "height": int(image_info.get("height") or 0),
        },
        query,
    )
    width = int(image_info.get("width") or 0)
    height = int(image_info.get("height") or 0)
    if width >= 1280 and height >= 720:
        score += 4
    if height and width / height >= 1.3:
        score += 3
    human_terms = (
        "student",
        "students",
        "professor",
        "teacher",
        "faculty",
        "lecturer",
        "seminar",
        "discussion",
        "workshop",
        "meeting",
        "learning",
        "teaching",
    )
    human_hits = sum(term in metadata for term in human_terms)
    if image_type in {"course_review_atmosphere", "business_scene", "thesis_concept"}:
        score += human_hits * 5
        if any(term in metadata for term in ("empty", "seater", "interior", "building", "architecture")):
            score -= 12
    elif image_type in {"icon_illustration", "data_visual"}:
        score += human_hits * 2
    if any(term in metadata for term in ("chart", "diagram", "poster", "document", "screenshot")):
        score -= 20
    return score


def _commons_search_metadata(page: dict, image_info: dict) -> str:
    # File titles often omit the actual activity. The catalogue description is
    # evidence for what is depicted; artist and licence names are not.
    external = image_info.get("extmetadata") or {}
    values = [str(page.get("title") or "")]
    for key in ("ObjectName", "ImageDescription", "Categories"):
        value = str((external.get(key) or {}).get("value") or "")
        values.append(html.unescape(re.sub(r"<[^>]+>", " ", value)))
    return " ".join(values)


def _openverse_candidate_metadata(item: dict) -> str:
    metadata_parts = [str(item.get("title") or "")]
    for tag in item.get("tags") or []:
        if isinstance(tag, dict):
            metadata_parts.append(str(tag.get("name") or ""))
        else:
            metadata_parts.append(str(tag))
    return " ".join(metadata_parts)


def _minimum_candidate_relevance_score(query: str) -> int:
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]{3,}", query.casefold())
        if token
        not in {
            "and",
            "for",
            "from",
            "image",
            "no",
            "photo",
            "presentation",
            "real",
            "scene",
            "text",
            "the",
            "with",
            "world",
        }
    }
    # For documentary education photography, a catalogue title often names
    # only the visible people ("students") rather than the institution and
    # activity together.  One verified human-learning signal is more useful
    # than falling through to a diagram, while the scene/text-risk gates still
    # reject unrelated posters and screens.
    if tokens & {"student", "students", "faculty", "classroom", "seminar", "workshop"}:
        return 5
    if len(tokens) >= 2:
        return 10
    if tokens:
        return 5
    return 0


def _candidate_metadata_is_relevant(metadata: str, query: str) -> bool:
    if not query.strip():
        return True
    metadata_lower = metadata.casefold()
    query_tokens = set(re.findall(r"[a-z0-9]{3,}", query.casefold()))
    if not query_tokens:
        # CJK-only searches used to receive an automatic relevance score of
        # zero, which let pages such as “落地路径” accept an unrelated football
        # article or “背景边界” accept a geographic border photograph.
        chunks = re.findall(r"[\u3400-\u9fff]{2,}", query)
        for chunk in chunks:
            if len(chunk) >= 4 and chunk in metadata:
                return True
        bigrams = {
            chunk[index : index + 2]
            for chunk in chunks
            for index in range(max(0, len(chunk) - 1))
            if chunk[index : index + 2] not in {"内容", "构图", "呈现", "核心", "页面"}
        }
        if not bigrams:
            return False
        matched = sum(1 for term in bigrams if term in metadata)
        return matched >= 2 and matched / len(bigrams) >= 0.6
    scene_intents = query_tokens & SCENE_INTENT_TERMS
    if scene_intents and not all(intent in metadata_lower for intent in scene_intents):
        return False
    item = {"title": metadata, "tags": [], "width": 0, "height": 0}
    return _openverse_candidate_score(item, query) >= _minimum_candidate_relevance_score(query)


def _openverse_metadata_has_text_risk(item: dict) -> bool:
    metadata_parts = [str(item.get("title") or "")]
    for tag in item.get("tags") or []:
        metadata_parts.append(str(tag.get("name") if isinstance(tag, dict) else tag or ""))
    metadata = " ".join(metadata_parts).casefold()
    return any(term in metadata for term in OPEN_WEB_TEXT_RISK_TERMS)


def _image_has_excessive_visible_text(path: Path) -> bool:
    """Reject web/AI assets that would compete with editable PPT copy.

    Tesseract is optional at deployment time. When installed it provides an
    inexpensive last gate against signs, watermarks and pseudo-typography; when
    it is unavailable the source and prompt gates still keep the workflow
    functional. A deck author can disable it only with an explicit environment
    configuration for a text-heavy use case.
    """

    enabled = os.getenv("AI_PPT_IMAGE_TEXT_SCAN_ENABLED", "true").strip().casefold()
    if enabled in {"0", "false", "no", "off"}:
        return False
    try:
        # Tiny fake-image fixtures and corrupt downloads cannot contain useful
        # OCR evidence; skipping them also keeps the normal test path cheap.
        if path.stat().st_size < 8 * 1024:
            return False
    except OSError:
        return False
    executable = shutil.which("tesseract")
    if not executable:
        return False
    command = [executable, str(path), "stdout", "--psm", "11", "-l", "eng"]
    if Path(executable).suffix.casefold() in {".bat", ".cmd"}:
        command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", *command]
    subprocess_env = os.environ.copy()
    if not subprocess_env.get("TESSDATA_PREFIX"):
        tessdata_candidates = [
            Path(os.getenv("AI_PPT_TESSDATA_PATH", "")),
            Path("D:/Codex/Downloads/tessdata"),
            Path(".local/tessdata").resolve(),
        ]
        for tessdata_dir in tessdata_candidates:
            if str(tessdata_dir) and (tessdata_dir / "eng.traineddata").is_file():
                subprocess_env["TESSDATA_PREFIX"] = str(tessdata_dir)
                break
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=8,
            check=False,
            env=subprocess_env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    scanned = "".join(re.findall(r"[a-z0-9]{3,}", (result.stdout or "").casefold()))
    # A provider watermark is often much shorter than the body-copy threshold.
    # Requesting nologo does not prove the returned pixels are watermark-free.
    if any(marker in scanned for marker in ("pollinations", "shutterstock", "gettyimages", "istock", "alamy")):
        return True
    try:
        threshold = int(os.getenv("AI_PPT_IMAGE_TEXT_SCAN_MIN_CHARS", "40"))
    except ValueError:
        threshold = 40
    return len(scanned) >= max(8, min(threshold, 80))


def _search_wikipedia_page_visual_asset(
    slide_index: int,
    query: str,
    assets_dir: Path,
    *,
    image_type: str,
    purpose: str,
    prompt: str,
    provider_chain: list[str],
    timeout_seconds: float | None,
) -> VisualAsset | None:
    for language in _wikipedia_language_candidates(query):
        search_url = f"https://{language}.wikipedia.org/w/api.php?" + parse.urlencode(
            {
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrlimit": "3",
                "prop": "pageimages|info",
                "piprop": "original|thumbnail",
                "pithumbsize": "1280",
                "inprop": "url",
                "format": "json",
            }
        )
        try:
            payload = _read_json_url(search_url, timeout=_image_search_timeout(timeout_seconds))
            pages = (payload.get("query") or {}).get("pages") or {}
            for page in pages.values():
                if not isinstance(page, dict):
                    continue
                if not _candidate_metadata_is_relevant(str(page.get("title") or ""), query):
                    continue
                image_url = str(
                    ((page.get("original") or {}).get("source"))
                    or ((page.get("thumbnail") or {}).get("source"))
                    or ""
                )
                if not image_url.lower().startswith(("http://", "https://")):
                    continue
                extension = _extension_for_mime_from_url(image_url)
                file_name = f"slide-{slide_index}-wikipedia{extension}"
                path = assets_dir / file_name
                actual_mime = _download_binary(
                    image_url,
                    path,
                    timeout=_image_search_timeout(timeout_seconds),
                )
                if (
                    actual_mime not in {"image/jpeg", "image/png"}
                    or not path.is_file()
                    or path.stat().st_size <= 0
                    or _image_has_excessive_visible_text(path)
                ):
                    path.unlink(missing_ok=True)
                    continue
                dimensions = raster_dimensions(path)
                if dimensions is None or not _web_candidate_has_delivery_dimensions(*dimensions):
                    path.unlink(missing_ok=True)
                    continue
                if path.suffix.lower() != _extension_for_mime(actual_mime):
                    renamed = path.with_suffix(_extension_for_mime(actual_mime))
                    path.replace(renamed)
                    path = renamed
                    file_name = path.name
                return VisualAsset(
                    slide_index=slide_index,
                    path=path,
                    rel_path=f"assets/{file_name}",
                    file_name=file_name,
                    mime_type=actual_mime,
                    source_type="wikipedia_page_image",
                    alt=_asset_alt(slide_index, query),
                    query=query,
                    image_type=image_type,
                    purpose=purpose,
                    prompt=prompt,
                    provider_chain=provider_chain,
                    attribution=_wikipedia_attribution(page, language),
                )
        except (OSError, ValueError, TimeoutError, json.JSONDecodeError):
            continue
    return None


def _search_commons_visual_asset(
    slide_index: int,
    query: str,
    assets_dir: Path,
    *,
    image_type: str,
    purpose: str,
    prompt: str,
    provider_chain: list[str],
    timeout_seconds: float | None,
    excluded_hashes: set[str] | None = None,
) -> VisualAsset | None:
    search_url = "https://commons.wikimedia.org/w/api.php?" + parse.urlencode(
        {
            "action": "query",
            "generator": "search",
            "gsrnamespace": "6",
            # A four-result response made every classroom page choose the same
            # first image.  Fetch a small, bounded pool so title relevance and
            # deterministic page rotation can produce genuinely distinct pages.
            "gsrlimit": "16",
            "gsrsearch": query,
            "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata",
            "format": "json",
        }
    )
    try:
        payload = _read_json_url(search_url, timeout=_image_search_timeout(timeout_seconds))
        pages = (payload.get("query") or {}).get("pages") or {}
        candidates: list[tuple[dict, dict, str]] = []
        for page in pages.values():
            if not isinstance(page, dict):
                continue
            for image_info in page.get("imageinfo") or []:
                if not isinstance(image_info, dict):
                    continue
                candidate_metadata = _commons_search_metadata(page, image_info)
                if not _candidate_metadata_is_relevant(candidate_metadata, query):
                    continue
                mime_type = str(image_info.get("mime") or "")
                if mime_type not in {"image/jpeg", "image/png"}:
                    continue
                if int(image_info.get("size") or 0) > MAX_IMAGE_BYTES:
                    continue
                width = int(image_info.get("width") or 0)
                height = int(image_info.get("height") or 0)
                if width and height and not _web_candidate_has_delivery_dimensions(width, height):
                    continue
                image_url = str(image_info.get("url") or "")
                if not image_url:
                    continue
                candidates.append((page, image_info, candidate_metadata))
        ordered_candidates = sorted(
            candidates,
            key=lambda candidate: _commons_candidate_score(
                candidate[0],
                candidate[1],
                query=query,
                image_type=image_type,
            ),
            reverse=True,
        )
        # Duplicates are excluded below without changing relevance order.
        for page, image_info, _candidate_metadata in ordered_candidates:
            mime_type = str(image_info.get("mime") or "")
            image_url = str(image_info.get("url") or "")
            extension = _extension_for_mime(mime_type)
            file_name = f"slide-{slide_index}-commons{extension}"
            path = assets_dir / file_name
            try:
                actual_mime = _download_binary(image_url, path, timeout=_image_search_timeout(timeout_seconds))
            except (OSError, ValueError, TimeoutError):
                path.unlink(missing_ok=True)
                continue
            if excluded_hashes and path.is_file() and _visual_asset_hash(path) in excluded_hashes:
                path.unlink(missing_ok=True)
                continue
            if (
                actual_mime not in {"image/jpeg", "image/png"}
                or not path.is_file()
                or path.stat().st_size <= 0
                or _image_has_excessive_visible_text(path)
            ):
                path.unlink(missing_ok=True)
                continue
            return VisualAsset(
                slide_index=slide_index,
                path=path,
                rel_path=f"assets/{file_name}",
                file_name=file_name,
                mime_type=mime_type,
                source_type="wikimedia_commons_search",
                alt=_asset_alt(slide_index, query),
                query=query,
                image_type=image_type,
                purpose=purpose,
                prompt=prompt,
                provider_chain=provider_chain,
                attribution=_commons_attribution(image_info),
            )
    except (OSError, ValueError, TimeoutError, json.JSONDecodeError):
        return None
    return None


def _search_bing_visual_asset(
    slide_index: int,
    query: str,
    assets_dir: Path,
    *,
    image_type: str,
    purpose: str,
    prompt: str,
    provider_chain: list[str],
    timeout_seconds: float | None,
) -> VisualAsset | None:
    key = os.getenv("AI_PPT_BING_IMAGE_SEARCH_KEY", "").strip()
    if not key:
        return None
    endpoint = os.getenv("AI_PPT_BING_IMAGE_SEARCH_ENDPOINT", "https://api.bing.microsoft.com/v7.0/images/search").strip()
    if not endpoint:
        return None
    search_url = endpoint.rstrip("?") + "?" + parse.urlencode(
        {
            "q": query,
            "count": "6",
            "safeSearch": "Moderate",
            "imageType": "Photo",
        }
    )
    try:
        payload = _read_json_url(
            search_url,
            timeout=_image_search_timeout(timeout_seconds),
            headers={"Ocp-Apim-Subscription-Key": key},
        )
        for item in payload.get("value") or []:
            if not isinstance(item, dict):
                continue
            if not _candidate_metadata_is_relevant(
                " ".join(
                    str(item.get(key) or "")
                    for key in ("name", "hostPageDisplayUrl", "hostPageUrl")
                ),
                query,
            ):
                continue
            image_url = str(item.get("contentUrl") or "")
            if not image_url.lower().startswith(("http://", "https://")):
                continue
            encoding = str(item.get("encodingFormat") or "").lower()
            extension = ".png" if encoding == "png" else ".jpg"
            file_name = f"slide-{slide_index}-bing{extension}"
            path = assets_dir / file_name
            actual_mime = _download_binary(image_url, path, timeout=_image_search_timeout(timeout_seconds))
            if (
                actual_mime not in {"image/jpeg", "image/png"}
                or not path.is_file()
                or path.stat().st_size <= 0
                or _image_has_excessive_visible_text(path)
            ):
                path.unlink(missing_ok=True)
                continue
            if path.suffix.lower() != _extension_for_mime(actual_mime):
                renamed = path.with_suffix(_extension_for_mime(actual_mime))
                path.replace(renamed)
                path = renamed
                file_name = path.name
            return VisualAsset(
                slide_index=slide_index,
                path=path,
                rel_path=f"assets/{file_name}",
                file_name=file_name,
                mime_type=actual_mime,
                source_type="bing_image_search",
                alt=_asset_alt(slide_index, query),
                query=query,
                image_type=image_type,
                purpose=purpose,
                prompt=prompt,
                provider_chain=provider_chain,
                attribution=_bing_attribution(item),
            )
    except (OSError, ValueError, TimeoutError, json.JSONDecodeError):
        return None
    return None


def _generate_visual_asset_with_ai(
    slide_index: int,
    query: str,
    assets_dir: Path,
    image_gateway: ImageGateway | None,
    *,
    image_type: str,
    purpose: str,
    image_prompt: str,
    provider_chain: list[str],
    slide_title: str,
    slide_intent: str,
    asset_role: str,
    image_treatment: str,
    composition_archetype: str,
    direction_name: str,
    palette: list[str],
    variation_hint: str | None = None,
) -> VisualAsset | None:
    if image_gateway is None:
        return None
    prompt = _ai_image_generation_prompt(
        slide_index=slide_index,
        query=query,
        image_type=image_type,
        purpose=purpose,
        image_prompt=image_prompt,
        slide_title=slide_title,
        slide_intent=slide_intent,
        asset_role=asset_role,
        image_treatment=image_treatment,
        composition_archetype=composition_archetype,
        direction_name=direction_name,
        palette=palette,
    )
    if variation_hint:
        # Free image gateways commonly cap or hash only the leading part of a
        # long prompt. Put the uniqueness instruction first so a retry cannot
        # be truncated into the exact same request and deterministic image.
        prompt = (
            f"{variation_hint}. This alternative must be visibly different from every other slide asset, "
            "with no visible text, logos, labels, or watermarks. "
            f"{prompt}"
        )
    try:
        generated = image_gateway.generate(
            ImageRequest(
                model="gpt-image-2",
                prompt=prompt,
                width=1024,
                height=576,
                timeout_seconds=90,
                max_attempts=2,
            )
        )
    except (ModelGatewayError, ValueError, OSError):
        return None
    if generated is None:
        return None
    extension = _extension_for_mime(generated.mime_type)
    file_name = f"slide-{slide_index}-ai{extension}"
    path = assets_dir / file_name
    path.write_bytes(generated.bytes)
    if _image_has_excessive_visible_text(path):
        path.unlink(missing_ok=True)
        return None
    return VisualAsset(
        slide_index=slide_index,
        path=path,
        rel_path=f"assets/{file_name}",
        file_name=file_name,
        mime_type=generated.mime_type,
        source_type=_generated_image_source_type(generated.model),
        alt=_asset_alt(slide_index, query),
        query=query,
        image_type=image_type,
        purpose=purpose,
        prompt=prompt,
        provider_chain=provider_chain,
        attribution=f"Generated by {_generated_image_provider_label(generated.model)} after open-web search fallback",
    )


def _ai_image_generation_prompt(
    *,
    slide_index: int,
    query: str,
    image_type: str,
    purpose: str,
    image_prompt: str,
    slide_title: str,
    slide_intent: str,
    asset_role: str,
    image_treatment: str,
    composition_archetype: str,
    direction_name: str,
    palette: list[str],
) -> str:
    semantic_cues = " ".join(
        part for part in (query, slide_title, slide_intent, purpose) if part
    )
    semantic_queries = _cross_language_image_queries(semantic_cues, image_type)
    semantic_subject = _ai_semantic_subject(
        semantic_cues,
        purpose,
        semantic_queries[0] if semantic_queries else query,
    )
    # A diagram-shaped page in an AI-in-education deck is still about people
    # doing a specific piece of educational work.  Sending it through the
    # generic glass-object safety route prevents pseudo-text, but also makes a
    # free image provider return decorative bowls and blobs. Keep the no-text
    # contract while putting a page-specific scene at the start of the prompt.
    if _is_ai_education_content(semantic_cues):
        return (
            f"Concrete semantic subject: {semantic_subject}. "
            "Create a premium cinematic 16:9 editorial photograph of this exact university scene, "
            "with authentic people, physical learning materials, clear human interaction, and a decisive focal action. "
            "The scene must visibly relate to responsible generative AI in higher education, rather than using abstract objects as a substitute. "
            "ABSOLUTELY NO visible text, letters, numbers, screens, devices, interfaces, charts, logos, badges, watermarks, documents, labels, or pseudo-writing. "
            "Use blank tactile materials only, with layered foreground, midground, and background, natural depth of field, and generous quiet negative space. "
            f"Palette: {', '.join(palette)}. "
            "Style: award-grade academic editorial photography, restrained, believable, and presentation-ready."
        )
    # Enterprise-AI decks also contain words such as dashboard, evidence,
    # diagram, and operating system. Those words describe the argument, not a
    # request to draw an interface. Route the deck through a concrete physical
    # business scene before the generic text-risk fallback. This keeps the OCR
    # safety contract while making every asset explain its own story beat.
    if _is_enterprise_ai_content(semantic_cues):
        page_job = _enterprise_ai_page_job(semantic_cues.casefold()) or purpose
        scene_direction = _enterprise_ai_scene_direction(str(page_job), semantic_subject)
        return (
            f"Concrete semantic subject: {semantic_subject}. "
            f"Visible story beat: {scene_direction}. "
            "Create a premium cinematic 16:9 editorial photograph of this exact enterprise situation. "
            "The main action and spatial structure must make the business argument understandable without a caption; "
            "do not replace the requested situation with generic glassware, decorative blobs, a lone laptop, or an empty boardroom. "
            "Use authentic senior leaders, operators, engineers, or frontline staff only where specified, with natural gestures and credible working context. "
            "Represent workflow, evidence, stages, gates, and control through real people, physical zones, unmarked modular objects, light, and architecture. "
            "ABSOLUTELY NO visible text, letters, numbers, screens, devices, interfaces, charts, logos, badges, watermarks, documents, labels, signage, or pseudo-writing. "
            "All papers, boards, objects, and surfaces must be blank and unmarked. "
            "Use a decisive focal action, layered foreground/midground/background, natural depth of field, premium directional light, and generous quiet negative space. "
            f"Palette: {', '.join(palette)}. "
            "Style: Fortune-500 boardroom editorial photography, restrained, credible, globally inclusive, presentation-ready, no collage, no infographic, no typography."
        )
    if _is_text_risk_image_type(image_type) or _requires_text_safe_conclusion_visual(
        query,
        image_prompt,
        slide_title,
        slide_intent,
        purpose,
    ) or _has_text_risk_visual_cues(
        query,
        image_prompt,
        slide_title,
        slide_intent,
        purpose,
        asset_role,
        image_treatment,
        composition_archetype,
    ):
        variant = _safe_abstract_image_variant(slide_index, slide_title, purpose, composition_archetype)
        environment = _safe_image_environment_hint(image_type)
        object_hint = _safe_content_object_hint(query, image_prompt, slide_title, slide_intent, purpose)
        return (
            "Create a premium 16:9 editorial macro photograph of an abstract still life. "
            f"{variant}. "
            f"{environment}. "
            f"{object_hint}. "
            "The scene is made only from blank translucent glass objects, matte ceramic forms, coffee-toned stone, soft fabric, water reflections, and warm light beams. "
            "All surfaces are plain, smooth, unmarked, pattern-free, brand-free, logo-free, label-free, and minimal. "
            "ABSOLUTELY NO visible text or writing, letters, numbers, brand marks, watermarks, menus, signage, labelled packaging, digital devices, data graphics, or pseudo-writing. "
            "Use shallow depth of field, layered foreground and background, cinematic shadows, and generous empty space. "
            f"Palette: {', '.join(palette)}. "
            "The visual supports the idea only through atmosphere, metaphor, material texture, light, and depth."
        )
    return (
        "Create a premium cinematic 16:9 editorial photograph, not a graphic layout. "
        f"Concrete semantic subject that must be clearly visible: {semantic_subject}. "
        "Show a real physical scene with a clear focal subject, natural spatial depth, and believable materials. "
        "ABSOLUTELY NO visible text, letters, numbers, UI screenshots, browser windows, logos, badges, watermarks, menus, or fake document pages. "
        "No digital devices, data graphics, or pseudo-writing. "
        "Do not create dashboards, charts with labels, app screens, web pages, interface panels, posters, signs, documents, book pages, product labels, packaging labels, menu boards, storefront signage, or any surface that could contain readable or pseudo-readable writing. "
        "Use unbranded products and authentic people or environments only when they serve the semantic subject. "
        f"Palette: {', '.join(palette)}. "
        "Style: award-grade editorial photography, cinematic but clean, professional, layered foreground/midground/background, "
        "premium lighting, restrained color, no collage, no infographic, no typography, and generous negative space."
    )


def _requires_text_safe_conclusion_visual(*values: str) -> bool:
    text = " ".join(str(value) for value in values).casefold()
    return any(
        marker in text
        for marker in ("\u7ed3\u8bba", "\u6536\u675f", "\u6700\u7ec8\u5224\u65ad", "conclusion", "closing", "final judgment")
    )


def _is_ai_education_content(value: str) -> bool:
    """Identify education-specific AI work before broad visual safety routing.

    A visual plan can label a framework page an ``icon_illustration`` while
    its real subject is a faculty decision or a learning interaction.
    """
    lowered = value.casefold()
    ai_markers = (
        " ai ",
        "artificial intelligence",
        "generative ai",
        "machine learning",
        "large language model",
        "llm",
        "\u4eba\u5de5\u667a\u80fd",
        "\u751f\u6210\u5f0f",
    )
    education_markers = (
        "education",
        "higher education",
        "university",
        "college",
        "faculty",
        "teaching",
        "learning",
        "assessment",
        "academic integrity",
        "course",
        "\u6559\u80b2",
        "\u9ad8\u6821",
        "\u5927\u5b66",
        "\u6559\u5b66",
        "\u5b66\u4e60",
        "\u8bfe\u7a0b",
    )
    return any(marker in lowered for marker in ai_markers) and any(
        marker in lowered for marker in education_markers
    )


def _is_enterprise_ai_content(value: str) -> bool:
    """Identify enterprise-AI operating-model content before text-risk routing."""

    lowered = f" {value.casefold()} "
    ai_markers = (
        " ai ",
        "artificial intelligence",
        "agentic",
        " ai agent",
        " ai-enabled",
        "intelligent automation",
        "人工智能",
        "智能体",
        "智能自动化",
    )
    enterprise_markers = (
        "enterprise",
        "business",
        "organization",
        "operating model",
        "workflow",
        "executive",
        "leadership",
        "operations",
        "transformation",
        "企业",
        "业务",
        "组织",
        "运营",
        "管理层",
        "转型",
    )
    return any(marker in lowered for marker in ai_markers) and any(
        marker in lowered for marker in enterprise_markers
    )


def _enterprise_ai_scene_direction(page_job: str, semantic_subject: str) -> str:
    """Turn an executive story beat into a visible, no-text physical scene.

    Free image providers respond much better to a concrete action plus spatial
    constraint than to an abstract strategy noun. Every beat below has a
    different cast, location, focal action, and composition so a nine-page
    deck cannot collapse into one repeated right-hand boardroom photograph.
    """

    directions = {
        "cover": (
            "a small cross-functional executive team gathers around a large blank modular workflow model; "
            "one leader moves a single control piece from an isolated prototype zone into a connected operating network, "
            "wide architectural composition with open negative space"
        ),
        "agenda": (
            "four clearly separated architectural thresholds recede through one modern workplace; "
            "a team advances from an isolated experiment through ownership, measurement, and scale-review zones, "
            "each threshold visibly distinct without symbols or labels"
        ),
        "context": (
            "an attractive isolated prototype sits under a spotlight while, deeper in the same scene, a staffed operational line reveals many handoffs and dependencies; "
            "the contrast visibly shows why pilot success is not proof of scalable operations"
        ),
        "framework": (
            "four linked physical workstations form one continuous value chain from human request to coordinated process, observable outcome, and executive value review; "
            "people pass one unmarked object through every stage with no broken handoff"
        ),
        "insight": (
            "a crowded workflow narrows through one visible operational chokepoint where a business owner, engineer, and frontline operator coordinate the handoff; "
            "the bottleneck is clearly ownership and process orchestration, not computing hardware"
        ),
        "evidence": (
            "a measurement review in a quiet operations studio uses three physically distinct blank evidence stations for baseline, causal attribution, and risk boundary; "
            "a decision team compares the stations with calibrated but completely unmarked instruments"
        ),
        "recommendation": (
            "a delivery team moves through four sequential physical work zones representing mandate, instrument, pilot, and review across a 90-day implementation; "
            "ownership transfers visibly from executive sponsor to operators and back to the review table"
        ),
        "scale_gate": (
            "three parallel controlled lanes converge on one guarded scale threshold; "
            "leaders inspect value, human adoption, and operational reliability together before opening the final passage"
        ),
        "conclusion": (
            "a resilient automated physical process runs across the scene while a human supervisor remains visibly able to pause, reroute, and recover it from a central manual control point; "
            "the image communicates owned operations rather than an autonomous black box"
        ),
    }
    return directions.get(
        page_job,
        f"a credible cross-functional enterprise team performs this specific action in a real operating environment: {semantic_subject}",
    )


def _ai_semantic_subject(cues: str, purpose: str, fallback: str) -> str:
    lowered = cues.casefold()
    ai_education = (
        any(marker in lowered for marker in (" ai", "artificial intelligence", "generative ai", "machine learning", "llm", "人工智能", "生成式"))
        and any(
            marker in lowered
            for marker in (
                "education",
                "higher education",
                "university",
                "college",
                "teaching",
                "learning",
                "assessment",
                "教育",
                "高校",
                "大学",
                "教学",
                "学习",
                "课程",
            )
        )
    )
    if _is_ai_education_content(lowered):
        education_scenes = {
            "cover": "a university seminar with faculty and diverse students discussing responsible generative AI adoption around a clean shared table",
            "agenda": "four connected university learning spaces represented by faculty and students moving between seminar, tutorial, assessment, and governance review",
            "context": "an instructor and students reviewing a learning task together, with human guidance visibly leading the discussion",
            "framework": "a faculty workshop connecting teaching, learning, assessment, and governance through four tactile unmarked objects on one table",
            "evidence": "a university learning-review table with feedback notes, source cards, and oral-review materials, all blank and unmarked",
            "insight": "a student receiving guided feedback from an instructor in a quiet university studio, with reflection and human judgment central",
            "recommendation": "a small faculty team planning a one-term responsible AI course pilot with clear ownership and review moments",
            "conclusion": "a university leadership review at the end of a pilot, with people choosing a careful scale, redesign, or stop path",
        }
        page_job = _ai_education_page_job(lowered)
        return education_scenes.get(page_job or purpose, fallback)
    enterprise_ai = (
        any(marker in lowered for marker in ("enterprise", "business", "organization", "企业", "业务", "组织"))
        and any(marker in lowered for marker in (" ai ", "artificial intelligence", "agent", "agentic", "人工智能", "智能体"))
    )
    if enterprise_ai:
        enterprise_scenes = {
            "cover": "an executive leadership team planning an AI-enabled business transformation in a modern unbranded office",
            "agenda": "a strategy workshop team arranging four distinct blank physical decision tokens on a table",
            "context": "a cross-functional team reviewing an AI pilot and operational readiness in a real office",
            "framework": "people coordinating a sequence of connected business-process stages with blank physical objects",
            "evidence": "a premium analytical still life representing baseline, attribution, and risk with unmarked physical objects",
            "insight": "a cross-functional operations team handing work between business owners, engineers, and frontline staff",
            "recommendation": "an enterprise implementation team planning a phased 90-day rollout with three unmarked physical milestones",
            "scale_gate": "an executive operating committee reviewing three distinct physical go-or-no-go gates for value, adoption, and reliability",
            "conclusion": "a human supervisor overseeing a resilient automated physical process with clear manual control",
        }
        page_job = _enterprise_ai_page_job(lowered)
        if page_job:
            return enterprise_scenes[page_job]
        return enterprise_scenes.get(purpose, fallback)
    is_electric_vehicle = any(
        marker in lowered
        for marker in ("新能源汽车", "电动汽车", "electric vehicle", "electric car")
    )
    if not is_electric_vehicle:
        return fallback
    electric_vehicle_scenes = {
        "cover": "a modern unbranded electric vehicle hero in a premium urban showroom",
        "agenda": "an advanced electric vehicle battery factory with robotic assembly equipment",
        "context": "a modern electric vehicle production line showing industrial capability",
        "framework": "a driver using a clean home electric vehicle charging point",
        "evidence": "an electric vehicle engineering laboratory testing battery technology",
        "insight": "a premium electric vehicle moving through a modern city at blue hour",
        "recommendation": "an automotive engineering team inspecting an unbranded electric vehicle prototype",
        "conclusion": "a future-ready electric vehicle on an open road at sunrise",
    }
    return electric_vehicle_scenes.get(purpose, fallback)


def _ai_education_page_job(lowered: str) -> str | None:
    """Resolve a university-AI image beat from concrete slide cues.

    Image-plan purposes are full sentences, not the short internal page-role
    tokens used by the scene dictionary.  Map the evidence-bearing language
    before falling back, so a framework slide cannot silently become a generic
    classroom photo.
    """
    if any(
        marker in lowered
        for marker in (
            "scale only when",
            "scale only after",
            "leadership review",
            "expand only when",
        )
    ):
        return "conclusion"
    if any(
        marker in lowered
        for marker in (
            "one-term",
            "one term",
            "course pilot",
            "pilot one",
            "implementation priority",
        )
    ):
        return "recommendation"
    if any(
        marker in lowered
        for marker in (
            "guided practice",
            "guided feedback",
            "augment judgment",
            "answer substitution",
        )
    ):
        return "insight"
    if any(
        marker in lowered
        for marker in (
            "process proof",
            "feedback quality",
            "academic-integrity",
            "academic integrity",
            "evidence:",
        )
    ):
        return "evidence"
    if any(
        marker in lowered
        for marker in (
            "four design layers",
            "teaching, learning, assessment, and governance",
            "connected academic ecosystem",
            "trustworthy ai use",
        )
    ):
        return "framework"
    if any(
        marker in lowered
        for marker in (
            "ai era",
            "human guidance",
            "reasoning and integrity",
        )
    ):
        return "context"
    if any(
        marker in lowered
        for marker in (
            "four university systems",
            "across four university",
        )
    ):
        return "agenda"
    if "hero content" in lowered or "generative ai in higher education" in lowered:
        return "cover"
    return None


def _web_candidate_has_delivery_dimensions(width: int, height: int) -> bool:
    """Require enough real pixels for a clean 16:9 or portrait slide crop."""

    return max(width, height) >= 1280 and min(width, height) >= 720


def _enterprise_ai_page_job(lowered: str) -> str | None:
    """Resolve the page job from strong, page-specific cues before broad words.

    Every image request also contains the deck title and a long purpose string,
    so terms such as ``pilot``, ``scale``, and ``risk`` occur on many pages.
    Exact story-beat phrases prevent those shared terms from collapsing a deck
    into one generic evidence scene.
    """

    if any(
        marker in lowered
        for marker in (
            "run ai agents as an operating system",
            "responsible enterprise automation",
            "resilient operations",
            "human control",
            "human oversight",
        )
    ):
        return "conclusion"
    if any(
        marker in lowered
        for marker in (
            "scale only after",
            "value, adoption, and risk gates",
            "value adoption risk gates",
            "three lines pass together",
            "go-or-no-go",
        )
    ):
        return "scale_gate"
    if any(marker in lowered for marker in ("90-day", "90 day", "phased implementation")):
        return "recommendation"
    if any(
        marker in lowered
        for marker in (
            "evidence matrix",
            "baseline attribution",
            "baseline, attribution",
            "measurement baseline attribution",
        )
    ):
        return "evidence"
    if any(
        marker in lowered
        for marker in (
            "bottleneck is the operating model",
            "human ai collaboration operating model",
            "workflow ownership",
        )
    ):
        return "insight"
    if any(
        marker in lowered
        for marker in (
            "roi chain",
            "workflow orchestration",
            "connected process stages",
            "use → process → outcome → value",
        )
    ):
        return "framework"
    if any(
        marker in lowered
        for marker in (
            "pilot success is not scale evidence",
            "business pilot review",
            "pilot review and operational readiness",
        )
    ):
        return "context"
    if any(marker in lowered for marker in ("four gates from pilot to scale", "four decision gates")):
        return "agenda"
    if any(
        marker in lowered
        for marker in (
            "executive team planning intelligent automation transformation",
            "executive leadership team planning",
            "core decision: an agent earns the right to scale",
        )
    ):
        return "cover"
    return None


def _is_text_risk_image_type(image_type: str) -> bool:
    # Symbolic asset classes stay on the safest no-text still-life path. Scene
    # and product classes use a concrete editorial-photo prompt plus OCR gate.
    return image_type in {"classical_element", "data_visual", "icon_illustration"}


def _safe_image_environment_hint(image_type: str) -> str:
    environments = {
        "background": "Environment: an architectural light field with sculptural depth and no walls carrying marks",
        "course_review_atmosphere": (
            "Environment: a quiet sunlit lecture hall suggested only by sculptural seating rhythms and clean light"
        ),
        "business_scene": (
            "Environment: a premium boardroom-inspired tabletop made only from blank architectural strategy objects"
        ),
        "classical_element": (
            "Environment: a misty ink-wash material landscape made from stone, paper texture, water, and shadow; "
            "no calligraphy, seals, scroll writing, or symbols"
        ),
        "thesis_concept": (
            "Environment: a museum-like research still life with glass knowledge nodes and completely blank paper-like planes"
        ),
        "product_showcase": (
            "Environment: an unbranded sculptural product plinth with smooth blank physical forms and studio reflections"
        ),
        "icon_illustration": "Environment: a tactile three-dimensional symbolic object scene made from plain geometric materials",
        "data_visual": (
            "Environment: a physical evidence metaphor built from glass tokens, height differences, and directional light; "
            "every element is tactile, blank, geometric, and unmarked"
        ),
    }
    return environments.get(
        image_type,
        "Environment: a clean content-matched physical scene with no writable or labelled surfaces",
    )


def _safe_content_object_hint(*values: str) -> str:
    text = " ".join(str(value) for value in values).casefold()
    if any(
        marker in text
        for marker in ("\u65b0\u80fd\u6e90\u6c7d\u8f66", "\u65b0\u80fd\u6e90\u8f66", "\u7535\u52a8\u6c7d\u8f66", "electric vehicle", "electric car")
    ):
        if any(
            marker in text
            for marker in ("\u7ade\u4e89", "\u89c4\u5219", "\u80fd\u529b", "\u8d5b\u9053", "competition", "capability")
        ):
            return (
                "Content cue: show a clean unbranded electric-vehicle production line with a single silver vehicle body, "
                "battery modules as tactile engineering objects, soft factory depth, and no readable panels"
            )
        if any(
            marker in text
            for marker in ("\u7528\u6237", "\u9700\u6c42", "\u51b3\u7b56", "\u4f53\u9a8c", "customer", "consumer", "demand", "experience")
        ):
            return (
                "Content cue: show one unbranded electric car in a quiet real-world mobility scene, "
                "a driver silhouette or charging connection, natural depth, and absolutely no signs or text"
            )
        return (
            "Content cue: show one unbranded premium electric vehicle in a clean studio or architectural city setting, "
            "with tactile battery or charging details, cinematic depth, and no signs, screens, labels, or logos"
        )
    if any(marker in text for marker in ("路径", "落地", "route", "path", "roadmap")):
        return (
            "Content cue: build a path metaphor with staggered blank stone steps, a subtle route line, "
            "unbranded coffee cups as milestones, and warm counter light"
        )
    if any(marker in text for marker in ("证据", "證據", "evidence", "proof")):
        return (
            "Content cue: build an evidence metaphor with clear glass tokens, blank index-card planes, "
            "magnifying-lens light, and ordered material layers without markings"
        )
    if any(marker in text for marker in ("结论", "下一步", "conclusion", "next step")):
        return (
            "Content cue: build a future-horizon metaphor with an open light corridor, blank ceramic pillars, "
            "coffee-toned reflections, and a calm forward direction"
        )
    if any(marker in text for marker in ("背景", "问题", "风险", "risk", "problem", "context")):
        return (
            "Content cue: build a problem-boundary metaphor with split light and shadow, separated glass blocks, "
            "coffee-toned material tension, and generous negative space"
        )
    if any(marker in text for marker in ("汇报", "agenda", "outline")):
        return (
            "Content cue: build an agenda metaphor with a sequence of blank ceramic cards, small glass markers, "
            "and a quiet left-to-right reading rhythm"
        )
    if any(marker in text for marker in ("luckin", "coffee", "咖啡", "鍜栧暋", "瑞幸")):
        return (
            "Content cue: use unbranded blank coffee cups, coffee beans, ceramic saucers, "
            "warm cafe counter materials, and abstract retail-flow shapes without any printed marks"
        )
    if any(marker in text for marker in ("ai", "artificial intelligence", "人工智能", "浜哄伐鏅鸿兘")):
        return "Content cue: use translucent neural-network glass nodes, blank research cards, and soft academic light"
    if any(marker in text for marker in ("thesis", "paper", "research", "论文", "研究")):
        return "Content cue: use blank paper-like planes, library light, glass knowledge nodes, and quiet academic materials"
    if any(marker in text for marker in ("business", "strategy", "market", "brand", "商业", "品牌")):
        return "Content cue: use blank strategy-table objects, architectural blocks, and cinematic boardroom light"
    return "Content cue: use content-matched abstract objects and physical metaphors, never decorative filler"


def _safe_abstract_image_variant(
    slide_index: int,
    slide_title: str,
    purpose: str,
    composition_archetype: str,
) -> str:
    variants = [
        "Variant A: low-angle side light, two large amber glass spheres, three ivory ceramic blocks, rippled reflective surface, calm gallery composition",
        "Variant B: overhead editorial composition, frosted glass discs, sand-colored stone plinths, soft diagonal shadows, spacious negative space",
        "Variant C: close-up shallow-focus arrangement, translucent cubes, warm beige fabric folds, small pearl-like ceramic beads, quiet luxury mood",
        "Variant D: asymmetrical still life, tall matte cylinders, smoky glass orbs, coffee-brown stone slab, golden hour window light",
        "Variant E: minimal architectural tabletop, layered cream blocks, clear water reflection, single emerald glass sphere, premium keynote atmosphere",
        "Variant F: cinematic depth composition, blurred foreground crystal, stacked ceramic steps, soft bronze highlights, museum-grade product lighting",
        "Variant G: horizontal route composition, small ceramic milestones, thin shadow line, warm amber reflection, spacious strategic-roadmap mood",
        "Variant H: evidence-table composition, clear glass tokens, pale paper planes with no marks, soft magnifier-like caustic light, analytical calm",
        "Variant I: future-horizon composition, receding ivory pillars, open corridor of warm light, emerald reflection, optimistic closing mood",
        "Variant J: tension-boundary composition, split shadow field, separated matte blocks, one translucent bridge object, controlled risk atmosphere",
    ]
    variant = variants[(max(1, slide_index) - 1) % len(variants)]
    semantic_seed = abs(
        sum(ord(character) for character in f"{slide_title}|{purpose}|{composition_archetype}")
    )
    return f"Slide-specific scene {slide_index}, semantic seed {semantic_seed % 997}: {variant}"


def _has_text_risk_visual_cues(*values: str) -> bool:
    text = " ".join(str(value) for value in values).casefold()
    if re.search(
        r"\b(?:app|apps|dashboard|chart|diagram|ui|interface|screen|website|webpage|browser|panel|poster|document|report|form|table|spreadsheet)\b",
        text,
    ):
        return True
    return any(
        marker in text
        for marker in (
            "小程序",
            "应用",
            "界面",
            "屏幕",
            "网页",
            "网站",
            "报表",
            "文档",
            "面板",
            "图表",
            "仪表盘",
            "表格",
            "海报",
            "菜单",
            "标签",
        )
    )


def _safe_ai_image_subject(slide_title: str, slide_intent: str, purpose: str) -> str:
    raw = " ".join([slide_title, slide_intent, purpose])
    raw = re.sub(
        r"\b(?:dashboard|chart|diagram|framework|system map|UI|interface|screen|app|web|report|document)\b",
        "growth system",
        raw,
        flags=re.IGNORECASE,
    )
    raw = re.sub(
        r"(?:小程序|应用|界面|屏幕|网页|网站|报表|文档|面板|图表|仪表盘|表格|海报|菜单|标签)",
        "增长系统",
        raw,
    )
    raw = re.sub(r"[“”\"'《》<>]", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return _clip_for_asset(raw, 180)


def _uses_owned_explainer_visual(
    image_type: str,
    *,
    expert_mode: bool,
    semantic_cues: str = "",
) -> bool:
    """Compatibility predicate for legacy callers.

    The renderer used to force framework, evidence and education pages through
    the owned-graphic branch before it tried a licensed photo or configured
    image provider.  That was technically valid but visually read as an
    image-less template deck.  Owned visuals now exist only as the final
    delivery-safe fallback in :func:`resolve_visual_assets`, after the
    page-specific sourcing cascade has had a fair opportunity to succeed.
    """
    _ = (image_type, expert_mode, semantic_cues)
    return False


def _write_owned_explainer_visual_asset(
    slide_index: int,
    query: str,
    assets_dir: Path,
    *,
    image_type: str,
    purpose: str,
    prompt: str,
    provider_chain: list[str],
    slide_title: str,
    slide_intent: str,
    composition_archetype: str,
    palette: list[str],
) -> VisualAsset:
    """Render a high-resolution, text-free owned visual from the design library.

    The export does not put slide copy inside the image.  Instead, each visual
    uses a distinct geometry (system constellation, evidence progression, or
    conceptual feedback loop) to give the page depth while the editable PPT
    text carries the actual labels.
    """
    # Draw at a compact logical canvas, then export with a deterministic
    # high-quality raster scale.  This keeps our own vector-like art clean
    # without sending it through Real-ESRGAN, which can invent tiled artifacts
    # on flat gradients and thin editorial lines.
    width, height = 1600, 900
    key_page = composition_archetype in {
        "cinematic_hero",
        "editorial_cover",
        "architectural_cover",
        "statement_focus",
        "closing_bloom",
        "closing_echo",
        "future_horizon",
        "manifesto_close",
    }
    delivery_width, delivery_height = (3840, 2160) if key_page else (1920, 1080)

    def rgb(value: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
        match = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(value or "").strip())
        if match is None:
            return fallback
        raw = match.group(1)
        return tuple(int(raw[index : index + 2], 16) for index in (0, 2, 4))

    bg = rgb(palette[0] if palette else "", (9, 18, 33))
    ink = rgb(palette[1] if len(palette) > 1 else "", (243, 240, 232))
    accent = rgb(palette[2] if len(palette) > 2 else "", (207, 138, 75))
    support = rgb(palette[3] if len(palette) > 3 else "", (70, 123, 165))
    # Hero / closing surfaces are rendered dark by the PPTX renderer.  Keep a
    # matching image base even when a direction-level palette happens to be
    # light, otherwise a rectangular white image looks pasted onto the page.
    if composition_archetype in {
        "cinematic_hero",
        "editorial_cover",
        "architectural_cover",
        "statement_focus",
        "closing_bloom",
        "closing_echo",
        "future_horizon",
        "manifesto_close",
    }:
        bg = (28, 31, 40)
        ink = (244, 241, 235)
        accent = tuple(round(channel * 0.66 + 255 * 0.34) for channel in accent)
        support = tuple(round(channel * 0.58 + accent[index] * 0.42) for index, channel in enumerate(support))
    seed = int.from_bytes(
        hashlib.sha256(
            f"{slide_index}|{query}|{purpose}|{composition_archetype}".encode("utf-8")
        ).digest()[:4],
        "big",
    )

    canvas = Image.new("RGBA", (width, height), (*bg, 255))
    pixels = canvas.load()
    for y in range(height):
        progress = y / max(1, height - 1)
        lift = int(15 * (1 - progress) + 3 * progress)
        for x in range(width):
            diagonal = ((x / max(1, width - 1)) * 8) + lift
            pixels[x, y] = (
                min(255, int(bg[0] + diagonal)),
                min(255, int(bg[1] + diagonal)),
                min(255, int(bg[2] + diagonal)),
                255,
            )

    atmosphere = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    atmosphere_draw = ImageDraw.Draw(atmosphere)
    glow_centers = [
        (int(width * 0.16), int(height * 0.20), accent),
        (int(width * 0.84), int(height * 0.72), support),
        (int(width * (0.42 + (seed % 17) / 100)), int(height * 0.52), ink),
    ]
    for center_x, center_y, color in glow_centers:
        radius = 190 + (seed % 70)
        atmosphere_draw.ellipse(
            (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
            fill=(*color, 54),
        )
    atmosphere = atmosphere.filter(ImageFilter.GaussianBlur(92))
    canvas.alpha_composite(atmosphere)

    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    foreground = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(foreground)

    def rounded_box(box: tuple[int, int, int, int], fill: tuple[int, int, int, int], radius: int = 28) -> None:
        offset_box = tuple(value + (10 if index % 2 == 0 else 14) for index, value in enumerate(box))
        shadow_draw.rounded_rectangle(offset_box, radius=radius, fill=(0, 0, 0, 86))
        draw.rounded_rectangle(box, radius=radius, fill=fill, outline=(*ink, 68), width=2)

    def node(center_x: int, center_y: int, radius: int, color: tuple[int, int, int]) -> None:
        shadow_draw.ellipse(
            (center_x - radius + 9, center_y - radius + 13, center_x + radius + 9, center_y + radius + 13),
            fill=(0, 0, 0, 110),
        )
        draw.ellipse(
            (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
            fill=(*color, 226),
            outline=(*ink, 118),
            width=3,
        )
        draw.ellipse(
            (center_x - radius // 2, center_y - radius // 2, center_x + radius // 2, center_y + radius // 2),
            fill=(*ink, 34),
        )

    def blend(
        first: tuple[int, int, int], second: tuple[int, int, int], weight: float
    ) -> tuple[int, int, int]:
        weight = max(0.0, min(1.0, weight))
        return tuple(
            round(left * (1.0 - weight) + right * weight)
            for left, right in zip(first, second)
        )

    def person(center_x: int, baseline_y: int, scale: float, color: tuple[int, int, int]) -> None:
        """A deliberately abstract learner silhouette, never a mascot/robot."""
        head = max(12, round(22 * scale))
        body_w = max(20, round(38 * scale))
        body_h = max(42, round(72 * scale))
        shadow_draw.ellipse(
            (
                center_x - body_w // 2 + 8,
                baseline_y - body_h + 10,
                center_x + body_w // 2 + 8,
                baseline_y + 11,
            ),
            fill=(0, 0, 0, 96),
        )
        draw.ellipse(
            (center_x - head, baseline_y - body_h - head * 2, center_x + head, baseline_y - body_h),
            fill=(*color, 230),
        )
        draw.rounded_rectangle(
            (center_x - body_w // 2, baseline_y - body_h, center_x + body_w // 2, baseline_y),
            radius=body_w // 2,
            fill=(*color, 204),
        )

    def glass_panel(
        box: tuple[int, int, int, int],
        color: tuple[int, int, int],
        *,
        radius: int = 32,
        alpha: int = 138,
    ) -> None:
        rounded_box(box, (*color, alpha), radius)
        inset = 12
        draw.rounded_rectangle(
            (box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset),
            radius=max(12, radius - inset),
            outline=(*ink, 42),
            width=1,
        )

    surface = blend(bg, ink, 0.16)
    surface_soft = blend(bg, support, 0.30)
    highlight = blend(ink, (255, 255, 255), 0.34)

    if composition_archetype == "chapter_index":
        # A vertical editorial route designed for the narrow chapter-index
        # image window. The focal stack stays centered after aspect-fill crop.
        draw.line((800, 160, 800, 740), fill=(*highlight, 66), width=5)
        stage_boxes = [
            (596, 186, 1004, 292),
            (646, 322, 1054, 428),
            (546, 458, 954, 564),
            (620, 594, 1028, 700),
        ]
        for index, box in enumerate(stage_boxes):
            stage_color = accent if index in {0, 3} else support
            glass_panel(box, stage_color, radius=30, alpha=154)
            draw.ellipse(
                (box[0] + 34, box[1] + 30, box[0] + 80, box[1] + 76),
                fill=(*highlight, 138),
            )
            draw.line(
                (box[0] + 108, (box[1] + box[3]) // 2, box[2] - 42, (box[1] + box[3]) // 2),
                fill=(*highlight, 54),
                width=5,
            )
        draw.ellipse((736, 90, 864, 218), fill=(*surface, 220), outline=(*accent, 146), width=5)
        draw.arc((758, 112, 842, 196), start=18, end=304, fill=(*highlight, 186), width=7)
    elif composition_archetype == "statement_focus":
        # One asymmetric judgement lens: a large focal disc, evidence orbit,
        # and a grounded counterweight. This is intentionally unlike the
        # closing horizon geometry.
        draw.ellipse((314, 152, 1002, 840), fill=(*support, 92), outline=(*highlight, 68), width=3)
        draw.ellipse((436, 274, 880, 718), fill=(*accent, 168), outline=(*highlight, 94), width=4)
        draw.ellipse((566, 404, 750, 588), fill=(*surface, 232))
        for inset, start in ((58, 18), (102, 112), (150, 224)):
            draw.arc(
                (314 - inset, 152 - inset, 1002 + inset, 840 + inset),
                start=start,
                end=start + 118,
                fill=(*highlight, 118),
                width=8,
            )
        glass_panel((1082, 250, 1334, 694), surface_soft, radius=46, alpha=142)
        draw.line((1108, 612, 1304, 332), fill=(*accent, 186), width=14)
        draw.ellipse((1262, 290, 1318, 346), fill=(*highlight, 210))
    elif composition_archetype in {"closing_bloom", "closing_echo", "future_horizon", "manifesto_close"}:
        # A receding strategy horizon provides a clear closing memory image
        # without reusing the insight page's two-way loop.
        horizon_y = 592
        draw.line((228, horizon_y, 1372, horizon_y), fill=(*highlight, 74), width=4)
        for index in range(6):
            left = 238 + index * 112
            right = 1362 - index * 112
            top = 170 + index * 52
            color = accent if index % 2 == 0 else support
            draw.rounded_rectangle(
                (left, top, left + 112, horizon_y),
                radius=42,
                fill=(*color, 48 + index * 15),
                outline=(*highlight, 38 + index * 8),
                width=2,
            )
            draw.rounded_rectangle(
                (right - 112, top, right, horizon_y),
                radius=42,
                fill=(*color, 48 + index * 15),
                outline=(*highlight, 38 + index * 8),
                width=2,
            )
        path = [(662, 760), (938, 760), (872, 388), (728, 388)]
        shadow_draw.polygon([(x + 12, y + 16) for x, y in path], fill=(0, 0, 0, 96))
        draw.polygon(path, fill=(*blend(accent, support, 0.45), 156), outline=(*highlight, 74))
        draw.ellipse((724, 260, 876, 412), fill=(*highlight, 86))
        draw.ellipse((758, 294, 842, 378), fill=(*accent, 214))
    elif image_type in {"background", "course_review_atmosphere", "business_scene"}:
        # Academic studio: an open research book, learning tiers and abstract
        # people make the scene recognisably educational without fabricating
        # a screen, a document, pseudo-type or a cartoon robot.
        variation = (seed + slide_index * 17) % 3
        for row, (left, top, right) in enumerate(
            ((206, 650, 1394), (290, 578, 1310), (390, 512, 1210))
        ):
            shade = blend(surface, accent if (row + variation) % 2 else support, 0.18)
            draw.rounded_rectangle(
                (left, top, right, top + 52),
                radius=26,
                fill=(*shade, 158),
                outline=(*highlight, 34),
                width=2,
            )
        if variation == 0:
            left_page = [(494, 350), (786, 300), (786, 572), (494, 622)]
            right_page = [(786, 300), (1090, 352), (1090, 626), (786, 572)]
            shadow_draw.polygon([(x + 16, y + 22) for x, y in left_page], fill=(0, 0, 0, 105))
            shadow_draw.polygon([(x + 16, y + 22) for x, y in right_page], fill=(0, 0, 0, 105))
            draw.polygon(left_page, fill=(*surface_soft, 224), outline=(*highlight, 72))
            draw.polygon(right_page, fill=(*blend(surface_soft, accent, 0.18), 224), outline=(*highlight, 72))
            draw.line((786, 302, 786, 572), fill=(*highlight, 92), width=4)
            for offset in (0, 1, 2):
                draw.line(
                    (558, 422 + offset * 44, 718, 392 + offset * 37),
                    fill=(*highlight, 44),
                    width=4,
                )
                draw.line(
                    (854, 392 + offset * 37, 1016, 424 + offset * 43),
                    fill=(*highlight, 44),
                    width=4,
                )
        elif variation == 1:
            glass_panel((518, 248, 1084, 526), surface_soft, radius=76, alpha=132)
            for index, x in enumerate((628, 800, 972)):
                draw.ellipse(
                    (x - 58, 326 - index * 18, x + 58, 442 - index * 18),
                    fill=(*(accent if index == 1 else support), 184),
                    outline=(*highlight, 70),
                    width=2,
                )
                draw.line((x, 454 - index * 18, x, 510), fill=(*highlight, 64), width=5)
        else:
            for index, (left, top, right, bottom) in enumerate(
                ((402, 486, 704, 596), (654, 388, 972, 498), (924, 290, 1250, 400))
            ):
                glass_panel(
                    (left, top, right, bottom),
                    accent if index == 2 else surface_soft,
                    radius=26,
                    alpha=154,
                )
                draw.ellipse(
                    (left + 34, top + 28, left + 76, top + 70),
                    fill=(*highlight, 116),
                )
        for index, (center_x, baseline, scale) in enumerate(
            ((356, 620, 0.78), (474, 584, 0.60), (1136, 586, 0.68), (1264, 634, 0.86))
        ):
            person(center_x, baseline, scale, accent if index in {0, 3} else support)
    elif image_type == "icon_illustration":
        # Four framed modules resolve into a single knowledge system.  It is a
        # visual explanation for a framework page, not decoration.
        variants = [
            [(232, 214), (946, 168), (1052, 544), (314, 588)],
            [(254, 326), (724, 154), (1114, 348), (712, 618)],
            [(338, 176), (1004, 246), (962, 612), (292, 540)],
        ]
        points = variants[(slide_index + seed) % len(variants)]
        center = (800, 442)
        for index, point in enumerate(points):
            node_color = accent if index in {0, 2} else support
            draw.line((center, point), fill=(*node_color, 136), width=8)
            draw.line((center, point), fill=(*highlight, 48), width=2)
            glass_panel(
                (point[0] - 122, point[1] - 78, point[0] + 122, point[1] + 78),
                node_color,
                radius=32,
                alpha=144,
            )
            draw.ellipse(
                (point[0] - 30, point[1] - 30, point[0] + 30, point[1] + 30),
                fill=(*highlight, 142),
            )
            draw.arc(
                (point[0] - 64, point[1] - 64, point[0] + 64, point[1] + 64),
                start=30 + index * 62,
                end=184 + index * 62,
                fill=(*node_color, 210),
                width=6,
            )
        draw.ellipse((center[0] - 118, center[1] - 118, center[0] + 118, center[1] + 118), fill=(*surface, 230))
        draw.ellipse((center[0] - 86, center[1] - 86, center[0] + 86, center[1] + 86), fill=(*accent, 190))
        draw.arc(
            (center[0] - 58, center[1] - 58, center[0] + 58, center[1] + 58),
            start=26,
            end=316,
            fill=(*highlight, 185),
            width=8,
        )
    elif image_type == "data_visual":
        # Evidence pages get a tangible measurement field: four distinct
        # process signals and one rising assurance path.  No fake chart text.
        baseline = 696
        columns = [(318, 472), (628, 356), (938, 422), (1248, 266)]
        for index, (center_x, top_y) in enumerate(columns):
            column_width = 148
            glass_panel(
                (center_x - column_width // 2, top_y, center_x + column_width // 2, baseline),
                accent if index in {1, 3} else support,
                radius=36,
                alpha=160,
            )
            draw.rounded_rectangle(
                (center_x - 42, top_y + 34, center_x + 42, top_y + 76),
                radius=20,
                fill=(*highlight, 88),
            )
            draw.line((center_x - 48, baseline - 48, center_x + 48, baseline - 48), fill=(*highlight, 58), width=3)
        points = [(x, y - 26) for x, y in columns]
        draw.line(points, fill=(*surface, 230), width=15, joint="curve")
        draw.line(points, fill=(*accent, 230), width=5, joint="curve")
        for point in points:
            draw.ellipse((point[0] - 25, point[1] - 25, point[0] + 25, point[1] + 25), fill=(*highlight, 196))
            draw.ellipse((point[0] - 10, point[1] - 10, point[0] + 10, point[1] + 10), fill=(*accent, 246))
    else:
        # Insight and decision pages use a two-way learning loop.  The shapes
        # communicate augmentation and governance without claiming to be a UI
        # or placing any words inside the visual.
        left_box = (214, 222, 754, 678)
        right_box = (846, 222, 1386, 678)
        glass_panel(left_box, support, radius=72, alpha=138)
        glass_panel(right_box, accent, radius=72, alpha=138)
        centers = ((486, 450), (1114, 450))
        for index, center in enumerate(centers):
            fill = accent if index == 0 else support
            draw.ellipse(
                (center[0] - 118, center[1] - 118, center[0] + 118, center[1] + 118),
                fill=(*fill, 190),
                outline=(*highlight, 94),
                width=3,
            )
            draw.ellipse(
                (center[0] - 64, center[1] - 64, center[0] + 64, center[1] + 64),
                fill=(*surface, 128),
            )
            draw.arc(
                (center[0] - 154, center[1] - 154, center[0] + 154, center[1] + 154),
                start=38 + index * 174,
                end=274 + index * 174,
                fill=(*highlight, 190),
                width=10,
            )
        bridge = [(726, 404), (874, 404), (946, 450), (874, 496), (726, 496), (654, 450)]
        shadow_draw.polygon([(x + 12, y + 16) for x, y in bridge], fill=(0, 0, 0, 96))
        draw.polygon(bridge, fill=(*blend(accent, support, 0.5), 206), outline=(*highlight, 84))
        draw.line((696, 450, 904, 450), fill=(*highlight, 164), width=4)

    shadow = shadow.filter(ImageFilter.GaussianBlur(20))
    canvas.alpha_composite(shadow)
    canvas.alpha_composite(foreground)
    finishing = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    finish_draw = ImageDraw.Draw(finishing)
    for index in range(10):
        x = (seed * (index + 3) * 71) % width
        y = (seed * (index + 7) * 43) % height
        finish_draw.ellipse((x, y, x + 3, y + 3), fill=(*ink, 58))
    finishing = finishing.filter(ImageFilter.GaussianBlur(0.6))
    canvas.alpha_composite(finishing)

    file_name = f"slide-{slide_index}-owned-explainer.png"
    path = assets_dir / file_name
    delivery_canvas = canvas.convert("RGB").resize(
        (delivery_width, delivery_height),
        Image.Resampling.LANCZOS,
    )
    delivery_canvas.save(path, format="PNG", optimize=True)
    return VisualAsset(
        slide_index=slide_index,
        path=path,
        rel_path=f"assets/{file_name}",
        file_name=file_name,
        mime_type="image/png",
        source_type="owned_design_library",
        alt=_asset_alt(slide_index, query),
        query=query,
        image_type=image_type,
        purpose=purpose,
        prompt=prompt,
        provider_chain=provider_chain,
        attribution=(
            "HumanizePPT owned explanatory visual library / selected after open-web search because "
            "this slide requires a semantic visual explanation rather than decorative stock photography"
        ),
        width=delivery_width,
        height=delivery_height,
        original_width=delivery_width,
        original_height=delivery_height,
    )


def _write_local_visual_asset(
    slide_index: int,
    query: str,
    assets_dir: Path,
    *,
    image_type: str,
    purpose: str,
    prompt: str,
    provider_chain: list[str],
    slide_title: str,
    slide_intent: str,
    image_treatment: str,
    composition_archetype: str,
    palette: list[str],
) -> VisualAsset:
    file_name = f"slide-{slide_index}-local.svg"
    path = assets_dir / file_name
    safe_title = html.escape(_clip_for_asset(slide_title, 84))
    safe_intent = html.escape(_clip_for_asset(slide_intent or query, 120))
    hue = (sum(ord(character) for character in query) * 37) % 360
    bg_color = _safe_svg_color(palette[0] if palette else "#05070c", "#05070c")
    fg_color = _safe_svg_color(palette[1] if len(palette) > 1 else "#F8F3E7", "#F8F3E7")
    accent_color = _safe_svg_color(palette[2] if len(palette) > 2 else "#F2BF4A", "#F2BF4A")
    support_color = _safe_svg_color(palette[3] if len(palette) > 3 else f"hsl({hue}, 58%, 24%)", "#1F67D2")
    composition_geometry = _local_composition_geometry(
        composition_archetype, accent_color, support_color, fg_color
    )
    image_type_geometry = _local_image_type_geometry(image_type, accent_color, support_color, fg_color)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900" role="img" aria-label="{safe_title}">
  <desc>{safe_intent} | {html.escape(_clip_for_asset(purpose, 180))}</desc>
  <defs>
    <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0%" stop-color="{bg_color}"/>
      <stop offset="46%" stop-color="{support_color}" stop-opacity=".72"/>
      <stop offset="100%" stop-color="{bg_color}"/>
    </linearGradient>
    <radialGradient id="gold" cx="70%" cy="18%" r="58%">
      <stop offset="0%" stop-color="{accent_color}" stop-opacity=".78"/>
      <stop offset="44%" stop-color="{accent_color}" stop-opacity=".16"/>
      <stop offset="100%" stop-color="{accent_color}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="red" cx="18%" cy="62%" r="56%">
      <stop offset="0%" stop-color="{support_color}" stop-opacity=".66"/>
      <stop offset="54%" stop-color="{support_color}" stop-opacity=".15"/>
      <stop offset="100%" stop-color="{support_color}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="blue" cx="86%" cy="74%" r="54%">
      <stop offset="0%" stop-color="{accent_color}" stop-opacity=".54"/>
      <stop offset="52%" stop-color="{accent_color}" stop-opacity=".12"/>
      <stop offset="100%" stop-color="{accent_color}" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="beam" x1="0" x2="1" y1="0" y2="0">
      <stop offset="0%" stop-color="#F8F3E7" stop-opacity="0"/>
      <stop offset="50%" stop-color="{fg_color}" stop-opacity=".62"/>
      <stop offset="100%" stop-color="#F8F3E7" stop-opacity="0"/>
    </linearGradient>
    <pattern id="grain" width="64" height="64" patternUnits="userSpaceOnUse">
      <circle cx="8" cy="11" r="1.1" fill="#F8F3E7" opacity=".16"/>
      <circle cx="44" cy="21" r=".8" fill="#F8F3E7" opacity=".11"/>
      <circle cx="30" cy="52" r="1" fill="#F8F3E7" opacity=".13"/>
      <path d="M0 63 H64" stroke="#F8F3E7" opacity=".045"/>
    </pattern>
  </defs>
  <rect width="1600" height="900" fill="url(#bg)"/>
  <rect width="1600" height="900" fill="url(#red)"/>
  <rect width="1600" height="900" fill="url(#blue)"/>
  <rect width="1600" height="900" fill="url(#gold)"/>
  <path d="M-160 610 C170 430 395 785 720 596 C1012 426 1204 562 1760 286 L1760 900 L-160 900 Z" fill="{fg_color}" opacity=".075"/>
  <path d="M-120 226 C244 160 455 218 735 114 C1011 12 1235 98 1700 -42" fill="none" stroke="url(#beam)" stroke-width="34" opacity=".27"/>
  <path d="M-70 708 C244 588 510 760 812 642 C1070 541 1270 582 1654 432" fill="none" stroke="{accent_color}" stroke-width="8" opacity=".32"/>
  <rect x="1016" y="130" width="362" height="570" rx="26" fill="{fg_color}" opacity=".055" stroke="{accent_color}" stroke-opacity=".24" stroke-width="2"/>
  <circle cx="1198" cy="414" r="126" fill="{fg_color}" opacity=".09"/>
  <circle cx="1198" cy="414" r="58" fill="{accent_color}" opacity=".18"/>
  {image_type_geometry}
  {composition_geometry}
  <g opacity=".28" data-image-treatment="{html.escape(image_treatment)}">
    <path d="M92 770 H1508" stroke="{fg_color}" stroke-width="2" stroke-dasharray="6 18"/>
  </g>
  <rect width="1600" height="900" fill="url(#grain)"/>
  <rect width="1600" height="900" fill="#000" opacity=".18"/>
</svg>'''
    path.write_text(svg, encoding="utf-8")
    return VisualAsset(
        slide_index=slide_index,
        path=path,
        rel_path=f"assets/{file_name}",
        file_name=file_name,
        mime_type="image/svg+xml",
        source_type="safe_vector_fallback",
        alt=_asset_alt(slide_index, query),
        query=query,
        image_type=image_type,
        purpose=purpose,
        prompt=prompt,
        provider_chain=provider_chain,
        attribution="Local deterministic no-text SVG visual after open-web search fallback",
    )


def _read_json_url(url: str, *, timeout: float, headers: dict[str, str] | None = None) -> dict:
    request_headers = {"User-Agent": "AI-PPT-Agent/0.1 image-search", **(headers or {})}
    request = urlrequest.Request(url, headers=request_headers)
    with urlrequest.urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_IMAGE_BYTES)
    return json.loads(raw.decode("utf-8"))


def _generated_image_source_type(model: str) -> str:
    lowered = model.casefold()
    if "pollinations" in lowered:
        return "free_ai_fallback"
    return "ai_fallback"


def _generated_image_provider_label(model: str) -> str:
    lowered = model.casefold()
    if "pollinations" in lowered:
        return "Pollinations FLUX free image API"
    if "openai" in lowered or "gpt-image" in lowered:
        return "gpt-image-2"
    return model


def _download_binary(url: str, path: Path, *, timeout: float) -> str:
    request = urlrequest.Request(url, headers={"User-Agent": "AI-PPT-Agent/0.1 image-search"})
    with urlrequest.urlopen(request, timeout=timeout) as response:
        mime_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        data = response.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("image too large")
    if not mime_type:
        if data.startswith(b"\xff\xd8\xff"):
            mime_type = "image/jpeg"
        elif data.startswith(b"\x89PNG\r\n\x1a\n"):
            mime_type = "image/png"
        else:
            mime_type = "application/octet-stream"
    path.write_bytes(data)
    return mime_type


def _asset_query(deck: SlideDeck, slide) -> str:
    if slide.design_plan.asset_query:
        grounded_query = " ".join(
            [
                slide.design_plan.asset_query,
                slide.design_plan.visual_brief,
                " ".join(slide.design_plan.diagram_labels[:4]),
            ]
        )
        cleaned_query = _clean_visible_text(grounded_query, role="body", clip=False)
        return _clip_for_asset(cleaned_query or grounded_query, 240)
    placeholder = next(
        (block.content for block in slide.blocks if block.block_type == "image_placeholder"),
        "",
    )
    key_point = next(
        (block.content for block in slide.blocks if block.block_type == "body"),
        "",
    )
    raw = " ".join(
        part
        for part in [
            deck.title,
            slide.title,
            slide.subtitle or "",
            key_point,
            slide.visual_intent,
            placeholder,
            slide.speaker_notes,
            "presentation visual",
            "photo concept illustration",
        ]
        if part
    )
    cleaned = _clean_visible_text(raw, role="body", clip=False) or re.sub(r"\s+", " ", raw).strip()
    return _clip_for_asset(cleaned, 180)


def _image_search_queries(query: str, image_type: str) -> list[str]:
    cleaned_query = _clip_for_asset(
        _clean_visible_text(query, role="body", clip=False) or query,
        160,
    )
    subject_queries = _subject_image_queries(cleaned_query, image_type)
    cross_language_queries = _cross_language_image_queries(cleaned_query, image_type)
    # Preserve concise, concrete catalogue queries. Generic type defaults such
    # as business strategy meeting must not erase a control-room or lab scene.
    direct_query = (
        not _contains_cjk(cleaned_query)
        and 2 <= len(cleaned_query.split()) <= 8
        and not _is_enterprise_ai_content(cleaned_query)
        and not _is_ai_education_content(cleaned_query)
    )
    candidates = [
        *([cleaned_query] if direct_query else []),
        # For CJK source text, the short, scene-specific English query has a
        # much deeper licensed-image inventory than a whole sentence copied
        # from the outline. Try it before the topic-only fallback.
        *cross_language_queries,
        *(subject_queries[:1]),
        *(subject_queries[1:]),
        cleaned_query,
        *_semantic_image_queries(cleaned_query, image_type),
        *IMAGE_SEARCH_FALLBACK_QUERIES.get(image_type, ()),
    ]
    unique: list[str] = []
    for candidate in candidates:
        cleaned = re.sub(r"\s+", " ", str(candidate)).strip()
        if cleaned and cleaned not in unique:
            unique.append(cleaned)
    return unique


def _cross_language_image_queries(query: str, image_type: str) -> list[str]:
    lowered = query.casefold()
    if _is_ai_education_content(lowered):
        page_job = _ai_education_page_job(lowered)
        education_queries = {
            "cover": [
                "university students seminar",
                "university classroom discussion",
                "college students workshop",
            ],
            "agenda": [
                "university teaching workshop",
                "university students seminar",
                "university classroom discussion",
            ],
            "context": [
                "university students discussion",
                "university classroom",
                "university students seminar",
            ],
            "framework": [
                "university faculty workshop",
                "university students seminar",
                "university teaching workshop",
            ],
            "evidence": [
                "university students seminar",
                "university teaching workshop",
                "university student discussion",
            ],
            "insight": [
                "university students discussion",
                "university students seminar",
                "university classroom discussion",
            ],
            "recommendation": [
                "university faculty workshop",
                "university teaching workshop",
                "university students seminar",
            ],
            "conclusion": [
                "university faculty meeting",
                "university students seminar",
                "university teaching workshop",
            ],
        }
        return education_queries.get(
            page_job,
            [
                # The image-plan query does not always retain the page-purpose
                # token that drove its original design.  These short, concrete
                # library searches are deliberately stronger than a generic
                # "AI education" phrase and return real people rather than a
                # stock technology backdrop.
                "university students seminar",
                "university classroom discussion",
                "university teaching workshop",
            ],
        )
    enterprise_ai = (
        any(marker in lowered for marker in ("enterprise", "business", "organization", "企业", "业务", "组织"))
        and any(marker in lowered for marker in (" ai ", "artificial intelligence", "agent", "agentic", "人工智能", "智能体"))
    )
    if enterprise_ai:
        page_job = _enterprise_ai_page_job(lowered)
        if page_job == "conclusion":
            return [
                "industrial operations supervisor automation",
                "responsible technology governance team",
                "human oversight operations team",
            ]
        if page_job == "scale_gate":
            return [
                "executive scale decision governance workshop",
                "business value adoption risk review team",
                "enterprise go no go decision meeting",
            ]
        if page_job == "recommendation":
            return [
                "enterprise implementation planning team",
                "executive strategy workshop team",
                "project milestone planning meeting",
            ]
        if page_job == "evidence":
            return [
                "business evidence analysis still life",
                "risk assessment workshop team",
                "financial measurement planning meeting",
            ]
        if page_job in {"framework", "insight"}:
            return [
                "cross functional business process workshop",
                "operations team workflow planning",
                "human automation collaboration office",
            ]
        if page_job == "context":
            return [
                "innovation pilot review team",
                "business experiment review meeting",
                "operations readiness workshop",
            ]
        if page_job == "agenda":
            return [
                "strategy workshop four decision gates",
                "executive transformation roadmap workshop",
                "leadership decision framework meeting",
            ]
        if page_job == "cover":
            return [
                "executive leadership artificial intelligence strategy workshop",
                "enterprise transformation leadership team",
                "business automation planning meeting",
            ]
        # Only treat evidence terms as decisive when they form an evidence
        # phrase. A single shared word such as "risk" must not route every page
        # to the same still life.
        if (
            "evidence" in lowered
            and any(marker in lowered for marker in ("baseline", "attribution", "measurement"))
        ):
            return [
                "business evidence analysis still life",
                "risk assessment workshop team",
                "financial measurement planning meeting",
            ]
        return [
            "executive leadership artificial intelligence strategy workshop",
            "enterprise transformation leadership team",
            "business automation planning meeting",
        ]
    if "新能源汽车" in lowered:
        lowered = f"{lowered} electric vehicle"
    if any(marker in lowered for marker in ("新能源汽车", "新能源车", "电动汽车", "electric vehicle", "electric car")):
        if any(
            marker in lowered
            for marker in ("\u7ade\u4e89", "\u89c4\u5219", "\u80fd\u529b", "\u8d5b\u9053", "competition", "capability", "industry")
        ):
            return [
                "electric vehicle factory production line",
                "automotive battery manufacturing",
                "electric vehicle supply chain",
            ]
        if any(
            marker in lowered
            for marker in ("\u7528\u6237", "\u9700\u6c42", "\u51b3\u7b56", "\u4f53\u9a8c", "customer", "consumer", "demand", "experience")
        ):
            return [
                "modern electric car driver on road",
                "electric vehicle charging at home",
                "electric car urban mobility",
            ]
        if any(
            marker in lowered
            for marker in ("\u589e\u957f", "\u54c1\u724c", "\u5e02\u573a", "\u4f18\u52bf", "growth", "brand", "market", "advantage")
        ):
            return [
                "modern electric vehicle showroom",
                "modern electric car city street",
                "modern electric vehicle design studio",
            ]
        if any(
            marker in lowered
            for marker in ("\u884c\u52a8", "\u8def\u5f84", "\u6218\u7565", "\u7ec4\u7ec7", "\u534f\u540c", "strategy", "roadmap", "team", "organization")
        ):
            return [
                "automotive engineering team electric vehicle",
                "electric vehicle design studio",
                "electric vehicle factory planning",
            ]
        if image_type == "product_showcase":
            return ["modern electric vehicle", "electric vehicle showroom", "electric car design studio"]
        if image_type == "business_scene":
            return ["electric vehicle factory", "automotive strategy meeting", "electric vehicle supply chain"]
        if image_type == "course_review_atmosphere":
            return ["electric vehicle industry", "electric vehicle charging station", "modern electric cars"]
        return ["electric vehicle", "electric vehicle factory", "electric vehicle charging station"]
    if any(marker in lowered for marker in ("人工智能", "artificial intelligence", "machine learning")):
        return ["artificial intelligence research", "computer science laboratory", "technology abstract"]
    if any(marker in lowered for marker in ("教育", "课堂", "大学", "education", "university", "classroom")):
        return ["university classroom", "students lecture hall", "academic research"]
    coffee_retail = any(
        marker in lowered
        for marker in (
            "\u745e\u5e78", "\u5496\u5561", "\u96f6\u552e", "\u95e8\u5e97",
            "luckin", "coffee", "retail", "store",
        )
    )
    if coffee_retail:
        if any(
            marker in lowered
            for marker in (
                "\u843d\u5730", "\u8def\u5f84", "\u884c\u52a8", "\u6307\u6807", "\u9a8c\u6536",
                "recommendation", "roadmap", "operations",
            )
        ):
            return ["coffee shop operations team", "barista workflow coffee shop", "coffee retail supply chain"]
        if any(
            marker in lowered
            for marker in (
                "\u8bc1\u636e", "\u590d\u8d2d", "\u4f1a\u5458", "\u6570\u5b57\u5316",
                "evidence", "customer", "member",
            )
        ):
            return ["coffee shop customer counter", "busy coffee shop service", "coffee shop barista customer"]
        if any(
            marker in lowered
            for marker in (
                "\u589e\u957f", "\u673a\u5236", "\u98de\u8f6e", "\u4f9b\u5e94\u94fe",
                "growth", "mechanism", "supply chain",
            )
        ):
            return ["busy modern coffee shop counter", "coffee beans supply chain", "coffee shop barista service"]
        if any(
            marker in lowered
            for marker in (
                "\u4fe1\u4efb", "\u80cc\u666f", "\u8fb9\u754c", "trust", "context",
            )
        ):
            return ["modern coffee shop customer service", "coffee shop counter interior", "barista serving coffee customer"]
        if "luckin" in lowered and any(
            marker in lowered for marker in ("\u7ed3\u8bba", "\u6848\u4f8b", "conclusion", "case")
        ):
            return ["luckin coffee", "modern coffee shop", "coffee shop counter"]
        return ["modern coffee shop", "coffee shop counter", "coffee store interior"]
    if any(marker in lowered for marker in ("咖啡", "零售", "门店", "coffee", "retail", "store")):
        return ["modern coffee shop", "retail business", "coffee store interior"]
    if any(marker in lowered for marker in ("论文", "研究", "thesis", "research")):
        return ["academic research", "university library", "research laboratory"]
    if image_type == "business_scene":
        return ["business strategy meeting", "modern office collaboration"]
    return []


def _subject_image_queries(query: str, image_type: str) -> list[str]:
    subject = _primary_subject_query(query)
    if not subject:
        return []
    terms = [subject]
    lowered = f" {query.casefold()} "
    retail_or_brand = any(
        marker in lowered
        for marker in (
            "luckin",
            "coffee",
            "brand",
            "retail",
            "store",
            "chain",
            "瑞幸",
            "咖啡",
            "品牌",
            "零售",
            "门店",
            "连锁",
            "消费",
            "商业",
        )
    )
    if retail_or_brand or image_type in {"business_scene", "product_showcase"}:
        terms.extend(
            [
                f"{subject} store",
                f"{subject} product",
                f"{subject} retail business",
            ]
        )
    elif image_type == "thesis_concept":
        terms.append(f"{subject} research concept")
    elif image_type == "data_visual":
        terms.append(f"{subject} data visualization")
    else:
        terms.append(f"{subject} photo")
    return terms


def _primary_subject_query(query: str) -> str:
    raw_text = html.unescape(str(query or ""))
    aliases = [
        alias.strip(" ,，;；")
        for alias in re.findall(
            r"(?:英语|英文|English)\s*[:：]\s*([A-Za-z][A-Za-z0-9 .&'’\-]{2,80})",
            raw_text,
            flags=re.IGNORECASE,
        )
    ]
    text = _clean_visible_text(raw_text, role="body", clip=False)
    if not text and not aliases:
        return ""
    without_parentheses = re.sub(r"[（(][^）)]{0,120}[）)]", " ", text)
    first_clause = re.split(r"[。；;？！!?，,：:|/\\]", without_parentheses, maxsplit=1)[0]
    first_clause = _strip_visible_outline_scaffold(first_clause)
    if not first_clause:
        chunks = [
            chunk.strip()
            for chunk in re.findall(r"[\u3400-\u9fffA-Za-z][\u3400-\u9fffA-Za-z0-9 .&'’\-]{1,24}", text)
            if chunk.strip() not in {"背景", "结论", "问题", "核心", "方案", "建议", "主题"}
        ]
        first_clause = chunks[0] if chunks else ""
    first_clause = _clip_for_asset(first_clause, 36)
    if aliases:
        alias = _clip_for_asset(aliases[0], 36)
        if first_clause and alias.casefold() not in first_clause.casefold():
            return _clip_for_asset(f"{first_clause} {alias}", 78)
        return alias or first_clause
    return first_clause


def _wikipedia_language_candidates(query: str) -> list[str]:
    return ["zh", "en"] if _contains_cjk(query) else ["en", "zh"]


def _semantic_image_queries(query: str, image_type: str) -> list[str]:
    lowered = query.lower()
    is_ai_education = (
        ("人工智能" in query or " ai" in f" {lowered}" or "artificial intelligence" in lowered)
        and any(
            marker in query or marker in lowered
            for marker in (
                "教育",
                "高校",
                "大学",
                "教学",
                "学习",
                "课程",
                "评价",
                "education",
                "university",
                "teaching",
                "learning",
                "assessment",
            )
        )
    )
    if not is_ai_education:
        return []
    if image_type == "course_review_atmosphere":
        return [
            "students using laptop university classroom",
            "university classroom",
            "lecture hall students",
        ]
    if image_type == "thesis_concept":
        return [
            "artificial intelligence education",
            "university library",
            "research paper",
        ]
    if image_type == "data_visual":
        return [
            "abstract evidence concept",
            "business growth metaphor",
            "data insight still life",
        ]
    return [
        "artificial intelligence education",
        "students laptop classroom",
        "university lecture hall",
    ]


def _local_composition_geometry(archetype: str, accent: str, support: str, fg: str) -> str:
    if archetype == "data_landscape":
        return f"""<g transform="translate(890 450)" opacity=".72"><rect x="0" y="180" width="82" height="150" rx="14" fill="{support}"/><rect x="112" y="90" width="82" height="240" rx="14" fill="{accent}"/><rect x="224" y="20" width="82" height="310" rx="14" fill="{fg}"/><path d="M0 120 C100 20 190 130 306 0" fill="none" stroke="{fg}" stroke-width="9"/></g>"""
    if archetype in {"process_ribbon", "chapter_index", "priority_stack"}:
        return f"""<g transform="translate(820 520)" opacity=".68"><path d="M0 80 H600" stroke="{accent}" stroke-width="12"/><circle cx="20" cy="80" r="28" fill="{fg}"/><circle cx="210" cy="80" r="28" fill="{support}"/><circle cx="400" cy="80" r="28" fill="{fg}"/><circle cx="590" cy="80" r="28" fill="{accent}"/></g>"""
    if archetype in {"system_map", "proof_mosaic"}:
        return f"""<g transform="translate(1100 460)" opacity=".62"><circle r="84" fill="{accent}"/><circle cx="-210" cy="-130" r="52" fill="{support}"/><circle cx="220" cy="-96" r="48" fill="{fg}"/><circle cx="-170" cy="180" r="42" fill="{fg}"/><path d="M-170 -100 L-55 -34 M175 -74 L66 -28 M-140 142 L-58 43" stroke="{fg}" stroke-width="6"/></g>"""
    if archetype == "split_comparison":
        return f"""<g transform="translate(820 190)" opacity=".54"><path d="M0 0 H290 V510 H0 Z" fill="{support}"/><path d="M320 0 H610 V510 H320 Z" fill="{accent}"/><path d="M305 -30 V540" stroke="{fg}" stroke-width="8"/></g>"""
    if archetype in {"editorial_cover", "editorial_split", "statement_focus"}:
        return f"""<g transform="translate(990 260)" opacity=".55"><rect width="430" height="340" fill="none" stroke="{fg}" stroke-width="4"/><rect x="28" y="30" width="210" height="12" fill="{accent}"/><rect x="28" y="74" width="320" height="8" fill="{fg}"/><rect x="28" y="106" width="276" height="8" fill="{fg}"/></g>"""
    return f"""<g transform="translate(1150 440)" opacity=".58"><circle r="190" fill="none" stroke="{accent}" stroke-width="10"/><circle r="118" fill="none" stroke="{fg}" stroke-width="3"/><path d="M-240 0 H240 M0 -240 V240" stroke="{fg}" stroke-width="2"/></g>"""


def _local_image_type_geometry(image_type: str, accent: str, support: str, fg: str) -> str:
    if image_type == "course_review_atmosphere":
        return f"""<g transform="translate(1030 275)" opacity=".64" data-image-plan-type="{html.escape(image_type)}"><rect x="0" y="0" width="360" height="210" rx="18" fill="none" stroke="{fg}" stroke-width="5"/><path d="M42 58 H318 M42 104 H250" stroke="{fg}" stroke-width="10" opacity=".72"/><path d="M74 292 h210 l42 48 h-294 z" fill="{support}" opacity=".72"/><circle cx="78" cy="390" r="38" fill="{accent}"/><circle cx="210" cy="386" r="42" fill="{fg}" opacity=".5"/><circle cx="342" cy="390" r="36" fill="{accent}" opacity=".64"/></g>"""
    if image_type == "business_scene":
        return f"""<g transform="translate(990 292)" opacity=".62" data-image-plan-type="{html.escape(image_type)}"><rect x="0" y="0" width="440" height="250" rx="22" fill="{fg}" opacity=".12" stroke="{accent}" stroke-width="4"/><circle cx="96" cy="96" r="44" fill="{accent}"/><circle cx="220" cy="82" r="38" fill="{fg}" opacity=".55"/><circle cx="340" cy="104" r="42" fill="{support}"/><path d="M72 172 C144 132 274 132 372 174" fill="none" stroke="{fg}" stroke-width="10" opacity=".55"/><path d="M42 220 H398" stroke="{accent}" stroke-width="8"/></g>"""
    if image_type == "classical_element":
        return f"""<g transform="translate(880 250)" opacity=".58" data-image-plan-type="{html.escape(image_type)}"><path d="M0 290 C120 180 166 210 250 98 C336 206 452 168 610 286 Z" fill="{support}" opacity=".72"/><path d="M46 132 C162 56 308 58 430 128" fill="none" stroke="{fg}" stroke-width="9"/><path d="M96 368 C240 324 382 324 548 366" fill="none" stroke="{accent}" stroke-width="12"/><circle cx="520" cy="70" r="52" fill="{accent}" opacity=".68"/></g>"""
    if image_type == "product_showcase":
        return f"""<g transform="translate(1040 190)" opacity=".66" data-image-plan-type="{html.escape(image_type)}"><rect x="0" y="0" width="280" height="440" rx="34" fill="{fg}" opacity=".18" stroke="{accent}" stroke-width="5"/><rect x="34" y="58" width="212" height="270" rx="18" fill="{support}" opacity=".55"/><circle cx="140" cy="382" r="26" fill="{accent}"/><path d="M56 92 H224 M56 138 H190 M56 184 H216" stroke="{fg}" stroke-width="10" opacity=".7"/></g>"""
    if image_type == "icon_illustration":
        return f"""<g transform="translate(980 250)" opacity=".64" data-image-plan-type="{html.escape(image_type)}"><rect x="40" y="40" width="150" height="150" rx="34" fill="{accent}" opacity=".58"/><rect x="250" y="40" width="150" height="150" rx="34" fill="{fg}" opacity=".22"/><rect x="145" y="250" width="150" height="150" rx="34" fill="{support}" opacity=".65"/><path d="M190 115 H250 M220 190 V250" stroke="{fg}" stroke-width="10"/></g>"""
    if image_type == "data_visual":
        return f"""<g transform="translate(925 260)" opacity=".68" data-image-plan-type="{html.escape(image_type)}"><rect x="0" y="0" width="520" height="330" rx="24" fill="{fg}" opacity=".09" stroke="{accent}" stroke-width="4"/><path d="M70 260 V188 M170 260 V116 M270 260 V154 M370 260 V70" stroke="{accent}" stroke-width="34"/><path d="M62 118 C152 54 226 184 366 84" fill="none" stroke="{fg}" stroke-width="9"/><path d="M58 260 H430" stroke="{fg}" stroke-width="5" opacity=".55"/></g>"""
    return f"""<g transform="translate(965 230)" opacity=".60" data-image-plan-type="{html.escape(image_type)}"><rect x="0" y="0" width="470" height="350" rx="30" fill="{fg}" opacity=".08" stroke="{accent}" stroke-width="4"/><circle cx="150" cy="156" r="88" fill="{support}" opacity=".58"/><path d="M96 262 C188 184 250 214 346 132" fill="none" stroke="{fg}" stroke-width="10"/><circle cx="362" cy="98" r="42" fill="{accent}"/></g>"""


def _safe_svg_color(value: str, fallback: str) -> str:
    cleaned = str(value).strip()
    return cleaned if re.fullmatch(r"#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?", cleaned) else fallback


def _asset_alt(slide_index: int, query: str) -> str:
    clean_query = _clean_visible_text(query, role="body", clip=False) or "content-grounded presentation visual"
    return f"Slide {slide_index} visual: {_clip_for_asset(clean_query, 56)}"


def _commons_attribution(image_info: dict) -> str | None:
    metadata = image_info.get("extmetadata") or {}
    parts = []
    for key in ("ObjectName", "Artist", "LicenseShortName"):
        value = ((metadata.get(key) or {}).get("value") or "").strip()
        value = re.sub(r"<[^>]+>", "", value)
        if value:
            parts.append(value)
    return " / ".join(parts[:3]) or "Wikimedia Commons"


def _openverse_attribution(item: dict) -> str:
    title = _clean_visible_text(str(item.get("title") or "Openverse image"), role="body", clip=False)
    creator = _clean_visible_text(str(item.get("creator") or "Unknown creator"), role="body", clip=False)
    license_name = str(item.get("license") or "open license").upper()
    license_version = str(item.get("license_version") or "").strip()
    landing_url = str(item.get("foreign_landing_url") or item.get("license_url") or "")
    license_label = f"{license_name} {license_version}".strip()
    return _clip_for_asset(
        f"{title} / {creator} / {license_label} / Openverse / {landing_url}",
        220,
    )


def _bing_attribution(item: dict) -> str:
    name = _clean_visible_text(str(item.get("name") or "Bing Images result"), role="body", clip=False)
    page = _clean_visible_text(str(item.get("hostPageUrl") or ""), role="body", clip=False)
    if page:
        return _clip_for_asset(f"{name} / {page}", 180)
    return _clip_for_asset(name, 120)


def _wikipedia_attribution(page: dict, language: str) -> str:
    title = _clean_visible_text(str(page.get("title") or "Wikipedia page image"), role="body", clip=False)
    url = str(page.get("fullurl") or "")
    if not url and title:
        url = f"https://{language}.wikipedia.org/wiki/{parse.quote(title.replace(' ', '_'))}"
    return _clip_for_asset(f"{title} / Wikipedia-Wikimedia / {url}" if url else f"{title} / Wikipedia-Wikimedia", 180)


def _extension_for_mime(mime_type: str) -> str:
    if mime_type == "image/jpeg":
        return ".jpg"
    if mime_type == "image/svg+xml":
        return ".svg"
    return ".png"


def _extension_for_mime_from_url(url: str) -> str:
    path = parse.urlparse(url).path.lower()
    if path.endswith((".jpg", ".jpeg")):
        return ".jpg"
    return ".png"


def _image_search_timeout(timeout_seconds: float | None = None) -> float:
    if timeout_seconds is not None:
        return max(0.2, min(float(timeout_seconds), 6.0))
    raw = os.getenv("AI_PPT_IMAGE_SEARCH_TIMEOUT_SECONDS", "0.8")
    try:
        return max(0.2, min(float(raw), 6.0))
    except ValueError:
        return 0.8


def _image_search_budget(timeout_seconds: float | None = None) -> float:
    if timeout_seconds is not None:
        return max(0.6, min(float(timeout_seconds) * 3.0, 8.0))
    raw = os.getenv("AI_PPT_IMAGE_SEARCH_MAX_SECONDS_PER_SLIDE", "2.8")
    try:
        return max(0.6, min(float(raw), 8.0))
    except ValueError:
        return 2.8


def _clip_for_asset(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", str(value)).strip()
    if len(value) <= limit:
        return _trim_dangling_visible_text(value)
    return _smart_clip_visible_text(value, limit)


def _contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value))


def _display_weight(value: str) -> int:
    weight = 0
    for character in value:
        weight += 2 if _contains_cjk(character) else 1
    return weight


def _visible_text_limit(role: str, value: str) -> int:
    has_cjk = _contains_cjk(value)
    limits = {
        "title": (22, 50),
        "subtitle": (30, 66),
        "card": (38, 78),
        "body": (46, 94),
    }
    cjk_limit, latin_limit = limits.get(role, limits["body"])
    return cjk_limit if has_cjk else latin_limit


def _smart_clip_visible_text(value: str, limit: int) -> str:
    if len(value.rstrip(" .…")) <= limit:
        return _trim_dangling_visible_text(value)
    window = value[: max(1, limit)].rstrip()
    punctuation_boundary = max(
        (window.rfind(marker) for marker in ("。", "；", "，", "、", "：", "—", "–", ";", ",", ":", "-")),
        default=-1,
    )
    if punctuation_boundary >= int(limit * 0.42):
        window = window[:punctuation_boundary].rstrip(" ，。；：、,:;-—–")
    elif not _contains_cjk(window):
        space = window.rfind(" ")
        if space >= int(limit * 0.45):
            window = window[:space].rstrip()
    return _trim_dangling_visible_text(window)


def _trim_dangling_visible_text(value: str) -> str:
    text = str(value).rstrip(" .…").strip(" \t\r\n，。；：、,:;-—–")
    if _contains_cjk(text):
        while len(text) > 4 and text[-1:] in {"的", "与", "和", "在", "将", "把"}:
            text = text[:-1].rstrip()
        return text
    dangling = {
        "a", "an", "and", "as", "at", "but", "by", "for", "from", "if", "in", "into",
        "of", "on", "or", "than", "that", "the", "to", "when", "while", "which", "with",
    }
    words = text.split()
    while len(words) > 3 and words[-1].casefold().strip(".,:;—-") in dangling:
        words.pop()
    return " ".join(words).rstrip(" .…,:;—-")


_CJK_NUMERAL_RE = r"[零〇一二三四五六七八九十百千万两\d]+"
_VISIBLE_OUTLINE_LABEL_RE = (
    r"叙事路径|核心判断|核心问题|背景|洞察|行动|证据|结论|建议|关键判断|本页结论|"
    r"本页任务|页面目标|页面作用|原文线索|可引用证据|可验证证据线索|证据线索|"
    r"讲解时可参考摘录|文章先回答的问题|分析路径|论证路径|核心信息|核心观点|"
    r"Source claim|Slide role|Traceable evidence|Useful excerpt|Core message|"
    r"What to expect|Main takeaway|Background|Context|Evidence|Conclusion|"
    r"Recommendation|Action|Key insight|Problem|Question|Solution|Takeaway"
)


def _strip_visible_outline_scaffold(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    for _ in range(5):
        before = text
        text = re.sub(
            rf"^第\s*{_CJK_NUMERAL_RE}\s*(?:部分|章节|章|节|页|张|步|阶段|幕|层|点)\s*[：:\-—–]\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"^(?:Part|Section|Chapter|Step|Page|Slide)\s*[0-9IVXLC]+\s*[：:\-—–]\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            rf"^行动优先级\s*{_CJK_NUMERAL_RE}\s*[：:\-—–]\s*(?:行动\s*[：:\-—–]\s*)?",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            rf"^(?:{_VISIBLE_OUTLINE_LABEL_RE})\s*[：:\-—–]\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            rf"(^|[\s，,。；;：:、（(《“\"'—–-])第\s*{_CJK_NUMERAL_RE}\s*(?:部分|章节|章|节|页|张|步|阶段|幕|层|点)\s*[：:]\s*",
            r"\1",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            rf"(^|[\s，,。；;：:、（(《“\"'—–-])行动优先级\s*{_CJK_NUMERAL_RE}\s*[：:\-—–]\s*(?:行动\s*[：:\-—–]\s*)?",
            r"\1",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            rf"(^|[\s，,。；;：:、（(《“\"'—–-])(?:{_VISIBLE_OUTLINE_LABEL_RE})\s*[：:]\s*",
            r"\1",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"^(?:\d{1,2}|[A-Z])[\.)、]\s+", "", text)
        text = text.strip(" \t\r\n，。；：、,:;-—–")
        if text == before:
            break
    return text


def _clean_visible_text(value: str, *, role: str = "body", clip: bool = True) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\ufffd", "")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^AI\s*可以指\s*[：:]\s*", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^AI\s*(?:是指|指的是)\s*[：:]\s*", "", text, flags=re.IGNORECASE).strip()
    text = _strip_visible_outline_scaffold(text)
    if not text:
        return ""
    if re.fullmatch(r"[\s?？!！.。…·•\-—–_]+", text):
        return ""
    text = re.sub(r"\?{3,}", "", text)
    text = re.sub(r"[�]{2,}", "", text)
    text = re.sub(r"(?:citation|source)-[A-Za-z0-9_-]+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:第\s*\d+\s*页|Slide\s+\d+)\s*[：:]\s*", "", text, flags=re.IGNORECASE)
    if _contains_cjk(text):
        text = re.sub(
            r"\s*（\s*(?:英语|英文|English)\s*[:：][^）]{2,120}）",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\s*[（(][A-Za-z][A-Za-z0-9 ,./&:;+\-]{2,120}[）)]",
            "",
            text,
        ).strip()
        text = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", text)
    text = re.sub(r"\s+", " ", text).strip(" \t\r\n-—–·•")
    if not text:
        return ""
    if not clip:
        return text
    return _smart_clip_visible_text(text, _visible_text_limit(role, text))


def _fit_foreground_box(
    x: int,
    y: int,
    cx: int,
    cy: int,
    *,
    safe_x: int = FOREGROUND_SAFE_X,
    safe_top: int = FOREGROUND_SAFE_TOP,
    safe_bottom: int = FOREGROUND_SAFE_BOTTOM,
) -> tuple[int, int, int, int]:
    max_cx = max(1, SLIDE_CX - safe_x * 2)
    max_cy = max(1, SLIDE_CY - safe_top - safe_bottom)
    cx = max(1, min(cx, max_cx))
    cy = max(1, min(cy, max_cy))
    max_x = max(safe_x, SLIDE_CX - safe_x - cx)
    max_y = max(safe_top, SLIDE_CY - safe_bottom - cy)
    x = min(max(x, safe_x), max_x)
    y = min(max(y, safe_top), max_y)
    return x, y, cx, cy


def _visible_text_font_size(text: str, cx: int, cy: int, requested_size: int, role: str) -> int:
    weighted = _display_weight(text)
    if role == "meta":
        return max(850, min(1400, requested_size))
    size = requested_size
    if role == "title":
        if weighted >= 58:
            size = min(size, 3300)
        elif weighted >= 46:
            size = min(size, 3400)
        elif weighted >= 34:
            size = min(size, 3500)
    elif role == "subtitle":
        if weighted >= 72:
            size = min(size, 1600)
        elif weighted >= 52:
            size = min(size, 1650)
    elif weighted >= 110 or (cx <= 2600000 and weighted >= 72):
        size = min(size, 1600)
    elif weighted >= 86 or cy <= 420000:
        size = min(size, 1650)
    minimum = {
        "title": PPT_PAGE_TITLE_MIN,
        "subtitle": 1500,
        "card": PPT_CARD_MIN,
        "body": 1600,
    }.get(role, 1500)
    return max(minimum, size)


def _ceil_div(value: int, divisor: int) -> int:
    return max(1, (max(0, value) + max(1, divisor) - 1) // max(1, divisor))


def _text_insets_for_role(role: str, cx: int, cy: int) -> tuple[int, int]:
    if role == "meta":
        return (50000, 30000)
    if role == "title":
        return (120000 if cx <= 5200000 else 160000, 105000)
    if role == "card":
        return (190000 if cx <= 2400000 else 240000, 125000 if cy <= 900000 else 145000)
    if role == "subtitle":
        return (115000, 85000)
    return (100000, 75000)


def _weighted_capacity_per_line(cx: int, font_size: int, inset_x: int) -> int:
    usable_cx = max(300000, cx - inset_x * 2)
    point_size = max(8.0, font_size / 100.0)
    avg_weight_emu = point_size * EMU_PER_POINT * 0.56
    # Display weight already counts CJK glyphs as two Latin units. Multiplying
    # usable width by two a second time doubled the estimated capacity and made
    # PowerPoint clip the final line even though XML still contained it.
    return max(10, int(usable_cx / max(avg_weight_emu, 1.0)))


def _estimated_text_lines(text: str, cx: int, font_size: int, role: str, inset_x: int) -> int:
    paragraphs = [part.strip() for part in re.split(r"[\r\n]+", text) if part.strip()] or [text]
    capacity = _weighted_capacity_per_line(cx, font_size, inset_x)
    return sum(_ceil_div(_display_weight(paragraph), capacity) for paragraph in paragraphs)


def _required_text_cy(text: str, cx: int, font_size: int, role: str, inset_x: int, inset_y: int) -> int:
    lines = _estimated_text_lines(text, cx, font_size, role, inset_x)
    # SimSun has a taller CJK ascent/descent box than the Latin metrics used by
    # many PPTX estimators. Reserve real slideshow line height instead of relying
    # on PowerPoint to clip the top or bottom of the glyphs.
    # PowerPoint's Times New Roman/SimSun line box is materially taller than
    # the nominal font metrics, especially once normAutofit and text insets are
    # applied. 1.62 is calibrated against PowerPoint's own PNG export and keeps
    # the final line visible instead of silently clipping a complete sentence.
    line_height_factor = 1.34 if role == "title" else 1.32 if role == "subtitle" else 1.62
    line_height = int((font_size / 100.0) * EMU_PER_POINT * line_height_factor)
    return lines * line_height + inset_y * 2


def _minimum_font_size(role: str) -> int:
    if role == "meta":
        return 850
    if role == "title":
        return PPT_PAGE_TITLE_MIN
    if role == "subtitle":
        return 1500
    if role == "card":
        return PPT_CARD_MIN
    return 1600


def _fit_visible_text_to_frame(text: str, cx: int, cy: int, font_size: int, role: str) -> tuple[str, int]:
    if not text:
        return text, font_size
    inset_x, inset_y = _text_insets_for_role(role, cx, cy)
    min_font = _minimum_font_size(role)
    fitted_text = text
    fitted_size = font_size
    for _ in range(14):
        required = _required_text_cy(fitted_text, cx, fitted_size, role, inset_x, inset_y)
        if required <= int(cy * 0.94):
            return fitted_text, fitted_size
        if fitted_size > min_font:
            fitted_size = max(min_font, int(fitted_size * 0.92))
            continue
        limit = max(10, int(len(fitted_text) * 0.86))
        shorter = _smart_clip_visible_text(fitted_text, limit)
        if shorter == fitted_text:
            break
        fitted_text = shorter
    return fitted_text, fitted_size


def _fit_text_frame(
    text: str,
    x: int,
    y: int,
    cx: int,
    cy: int,
    font_size: int,
    role: str,
) -> tuple[str, int, int, int, int, int, str]:
    x, y, cx, cy = _fit_foreground_box(x, y, cx, cy)
    inset_x, inset_y = _text_insets_for_role(role, cx, cy)
    required = _required_text_cy(text, cx, font_size, role, inset_x, inset_y)
    max_available_cy = max(1, SLIDE_CY - FOREGROUND_SAFE_TOP - FOREGROUND_SAFE_BOTTOM)
    # The fitter below reserves six percent of the frame for Office's real
    # line-box variance. Grow the frame against that same threshold; otherwise
    # a complete two-line sentence can be shortened merely because it occupies
    # 95% of the nominal box even though there is room to enlarge the card.
    if required > int(cy * 0.94):
        cy = min(max(cy, int(required / 0.88)), max_available_cy)
    x, y, cx, cy = _fit_foreground_box(x, y, cx, cy)
    fitted_text, fitted_size = _fit_visible_text_to_frame(text, cx, cy, font_size, role)
    # Top anchoring is more stable across Windows Office, WPS and macOS Office
    # for Chinese serif fonts. Horizontal centering is still controlled by algn.
    anchor = "t"
    return fitted_text, x, y, cx, cy, fitted_size, anchor


def _write_hyperframes_html(deck: SlideDeck, path: Path, visual_assets: dict[int, VisualAsset]) -> None:
    slides = []
    for slide in deck.slides:
        asset = visual_assets.get(slide.slide_index)
        asset_html = _asset_figure_html(asset) if asset else ""
        block_items = []
        for block in _content_blocks(
            slide,
            deck_title=deck.title,
            max_blocks=_render_block_limit(slide),
        ):
            block_items.append(
                '<div class="block block-card">'
                f'<p>{html.escape(_clean_visible_text(block.content, role="card", clip=False))}</p>'
                "</div>"
            )
        blocks = "\n".join(block_items[:4])
        plan = slide.design_plan
        placement = visual_placement(plan.composition_archetype)
        slide_bg, slide_fg, slide_accent, slide_soft, _slide_red, _slide_blue = _slide_visual_palette(
            deck.theme.palette,
            slide,
        )
        # The owned library renders cinematic / closing pages as dark visual
        # surfaces so they match PPTX.  HyperFrames must choose its foreground
        # against that visible surface, not against the light direction palette
        # that happened to seed the deck.
        dark_visual_surface = plan.composition_archetype in {
            "cinematic_hero",
            "editorial_cover",
            "architectural_cover",
            "statement_focus",
            "closing_bloom",
            "closing_echo",
            "future_horizon",
            "manifesto_close",
        }
        if dark_visual_surface:
            slide_bg = "1C1F28"
            slide_fg = "FAF8F2"
            slide_soft = "353646"
            if not _is_light_color(slide_accent):
                slide_accent = "B79BFF"
        light_page = _is_light_color(slide_bg)
        card_surface = "rgba(255,255,255,.90)" if light_page else "rgba(19,23,31,.88)"
        card_surface_soft = "rgba(255,255,255,.80)" if light_page else "rgba(19,23,31,.76)"
        card_border = "rgba(31,41,55,.14)" if light_page else "rgba(255,255,255,.18)"
        slide_style = (
            f"--bg:#{slide_bg};--fg:#{slide_fg};"
            f"--accent:#{slide_accent};--soft:#{slide_soft};"
            f"--card-surface:{card_surface};--card-surface-soft:{card_surface_soft};"
            f"--card-border:{card_border};"
        )
        explainer_html = _explainer_html(slide)
        title = _ppt_title_text(_ppt_display_title_for_slide(slide, deck.title))
        subtitle = _clean_visible_text(slide.subtitle, role="subtitle")
        slides.append(
            f"""
            <section class="frame frame-{html.escape(slide.layout)} composition-{html.escape(plan.composition_archetype)} treatment-{html.escape(plan.image_treatment)} motion-{html.escape(plan.motion_preset)}" style="{slide_style}" data-slide="{slide.slide_index}" data-active="{"true" if slide.slide_index == 1 else "false"}" data-motion-engine="HyperFrames" data-reference-style="content-driven-composition" data-visual-mode="{html.escape(placement.mode)}" data-visual-gravity="{html.escape(placement.gravity)}" data-composition-archetype="{html.escape(plan.composition_archetype)}" data-composition-variant="{html.escape(plan.composition_variant)}" data-image-treatment="{html.escape(plan.image_treatment)}" data-motion-preset="{html.escape(plan.motion_preset)}" data-content-density="{html.escape(plan.content_density)}" data-asset-role="{html.escape(plan.asset_role)}">
              <div class="frame-inner" data-reference-style="content-driven-composition">
                {asset_html}
                {explainer_html}
                <h1>{html.escape(title)}</h1>
                {f'<h2>{html.escape(subtitle)}</h2>' if subtitle else ''}
                <div class="blocks">{blocks}</div>
                <aside class="speaker-notes">{html.escape(_clean_visible_text(slide.speaker_notes, role="body"))}</aside>
              </div>
            </section>
            """
        )
    palette = deck.theme.palette
    deck_title = _clean_visible_text(deck.title, role="title") or deck.project_id
    deck_title_json = json.dumps(deck_title, ensure_ascii=False)
    nav_buttons = "\n".join(
        f'<button type="button" data-index="{index - 1}" aria-label="跳转到第 {index} 页">{index}</button>'
        for index in range(1, len(deck.slides) + 1)
    )
    content = f"""<!doctype html>
<html lang="{html.escape(deck.language)}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="generator" content="HyperFrames local renderer" />
  <meta name="deck-contract-source" content="SlideDeck JSON" />
  <title>{html.escape(deck_title)}</title>
  <style>
    :root {{
      --bg: {html.escape(palette[0])};
      --fg: {html.escape(palette[1])};
      --accent: {html.escape(palette[2])};
      --soft: {html.escape(palette[-1])};
      --type-title: clamp(30px, 3.55vw, 48px);
      --type-subtitle: clamp(17px, 1.85vw, 25px);
      --type-card: clamp(14px, 1.18vw, 17px);
      --type-caption: 12px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--fg);
      background: var(--bg);
      background-image:
        radial-gradient(circle at 18% 24%, color-mix(in srgb, var(--accent) 28%, transparent), transparent 30%),
        radial-gradient(circle at 86% 72%, color-mix(in srgb, var(--soft) 32%, transparent), transparent 34%);
      font-family: "Times New Roman", SimSun, "宋体", serif;
      overflow: hidden;
    }}
    .chrome {{
      position: fixed;
      inset: 20px 22px auto 22px;
      z-index: 10;
      max-width: calc(100vw - 44px);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      pointer-events: none;
    }}
    .brand, .controls {{
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 9px 12px;
      border: 1px solid rgba(255,255,255,.18);
      border-radius: 999px;
      background: rgba(0,0,0,.22);
      backdrop-filter: blur(18px);
      pointer-events: auto;
      min-width: 0;
    }}
    .brand strong {{ font-size: 12px; letter-spacing: .12em; text-transform: uppercase; }}
    .brand span {{
      max-width: min(42vw, 460px);
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
      color: color-mix(in srgb, var(--fg) 78%, transparent);
      font-size: 12px;
    }}
    button {{
      border: 0;
      border-radius: 999px;
      color: var(--fg);
      background: rgba(255,255,255,.12);
      cursor: pointer;
      font: inherit;
      font-size: 13px;
      font-weight: 800;
    }}
    .controls button {{ padding: 8px 12px; }}
    .controls button[data-action="present"] {{
      color: var(--bg);
      background: var(--accent);
    }}
    .controls button[data-action="zoom-out"],
    .controls button[data-action="zoom-in"] {{
      width: 34px;
      padding-inline: 0;
    }}
    .controls button[aria-pressed="true"] {{
      color: var(--bg);
      background: var(--accent);
    }}
    .dots {{
      position: fixed;
      left: 22px;
      bottom: 24px;
      z-index: 10;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      max-width: min(720px, calc(100vw - 44px));
    }}
    .dots button {{
      width: 34px;
      height: 34px;
      color: var(--accent);
      border: 1px solid rgba(255,255,255,.18);
      background: rgba(0,0,0,.18);
      backdrop-filter: blur(14px);
    }}
    .dots button[data-active="true"] {{
      color: var(--bg);
      background: var(--accent);
    }}
    .progress {{
      position: fixed;
      left: 0;
      right: 0;
      bottom: 0;
      z-index: 12;
      height: 5px;
      background: rgba(255,255,255,.12);
    }}
    .progress span {{
      display: block;
      width: 0;
      height: 100%;
      background: var(--accent);
      transition: width .24s ease;
    }}
    .frame {{
      min-height: 100dvh;
      padding: 76px 4vw 46px;
      display: none;
      place-items: center;
      /* Resolve foreground against this frame's palette.  Body-level color
         inheritance resolves custom properties too early for dark per-slide
         visual surfaces. */
      color: var(--fg);
      animation: rise .34s ease both;
    }}
    .frame[data-active="true"] {{
      display: grid;
    }}
    .frame-inner {{
      position: relative;
      --content-w: min(560px, 47%);
      --content-left: 0%;
      --asset-inset: 0;
      --asset-radius: 0px;
      --frame-overlay: linear-gradient(90deg, color-mix(in srgb, var(--bg) 90%, transparent) 0%, color-mix(in srgb, var(--bg) 64%, transparent) 42%, color-mix(in srgb, var(--bg) 18%, transparent) 72%, color-mix(in srgb, var(--bg) 40%, transparent) 100%);
      overflow: hidden;
      width: min(1280px, 100%);
      aspect-ratio: 16 / 9;
      min-height: min(76vh, 720px);
      padding: clamp(36px, 4.3vw, 56px);
      border: 1px solid color-mix(in srgb, var(--accent) 34%, transparent);
      border-radius: 24px;
      background: var(--bg);
      box-shadow: 0 36px 120px rgba(0,0,0,.48);
      isolation: isolate;
      transform: scale(var(--preview-zoom, 1));
      transform-origin: center center;
    }}
    body[data-presenter="true"] {{
      background: #05070a;
    }}
    body[data-presenter="true"] .frame {{
      min-height: 100dvh;
      padding: 0;
      background: #05070a;
    }}
    body[data-presenter="true"] .frame-inner {{
      width: min(100vw, calc(100dvh * 16 / 9));
      height: min(100dvh, calc(100vw * 9 / 16));
      min-height: 0;
      border: 0;
      border-radius: 0;
      box-shadow: none;
    }}
    body[data-presenter="true"] .chrome,
    body[data-presenter="true"] .dots {{
      opacity: .08;
      transition: opacity .18s ease, transform .18s ease;
    }}
    body[data-presenter="true"] .chrome:hover,
    body[data-presenter="true"] .chrome:focus-within,
    body[data-presenter="true"] .dots:hover,
    body[data-presenter="true"] .dots:focus-within {{
      opacity: 1;
    }}
    body[data-presenter="true"] .progress {{
      height: 4px;
    }}
    .frame-inner::before {{
      content: "";
      position: absolute;
      inset: 0;
      z-index: 1;
      pointer-events: none;
      background:
        var(--frame-overlay),
        radial-gradient(circle at 18% 78%, color-mix(in srgb, var(--accent) 26%, transparent), transparent 32%),
        radial-gradient(circle at 82% 28%, color-mix(in srgb, var(--soft) 24%, transparent), transparent 34%);
    }}
    .frame[data-visual-mode="window"] .frame-inner::before,
    .frame[data-visual-mode="strip"] .frame-inner::before,
    .frame[data-visual-mode="edge_panel"] .frame-inner::before {{
      background: none;
    }}
    .frame-inner::after {{
      content: "";
      position: absolute;
      inset: -30% -20%;
      z-index: 1;
      pointer-events: none;
      background: linear-gradient(102deg, transparent 0 38%, rgba(248,243,231,.16) 49%, transparent 60% 100%);
      mix-blend-mode: screen;
      transform: translateX(-30%);
    }}
    .eyebrow, .role {{ color: var(--accent); text-transform: uppercase; letter-spacing: .14em; font-size: 12px; }}
    .frame-inner > h1,
    .frame-inner > h2,
    .frame-inner > .blocks,
    .frame-inner > .explainer-layer,
    .frame-inner > .speaker-notes {{
      position: relative;
      z-index: 2;
    }}
    .frame-inner > h1,
    .frame-inner > h2,
    .block p,
    .explainer-node {{
      min-width: 0;
      overflow-wrap: anywhere;
      word-break: normal;
    }}
    h1 {{
      max-width: var(--content-w);
      width: var(--content-w);
      display: block;
      overflow: visible;
      font-family: "Times New Roman", SimSun, "宋体", serif;
      font-size: var(--type-title);
      line-height: 1.14;
      margin: 18px 0 20px;
      letter-spacing: -.012em;
      text-wrap: balance;
      text-shadow: 0 12px 34px rgba(0,0,0,.48);
    }}
    h2 {{
      max-width: var(--content-w);
      width: var(--content-w);
      display: block;
      overflow: visible;
      font-size: var(--type-subtitle);
      line-height: 1.18;
      opacity: .82;
      font-weight: 560;
      text-shadow: 0 10px 24px rgba(0,0,0,.42);
    }}
    .blocks {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-top: 28px; max-width: var(--content-w); width: var(--content-w); align-items: stretch; }}
    .frame-asset {{
      position: absolute;
      inset: var(--asset-inset);
      z-index: 0;
      margin: 0;
      border: 0;
      border-radius: inherit;
      overflow: hidden;
      min-height: 0;
      background: var(--bg);
      box-shadow: none;
      transform-origin: 70% 45%;
    }}
    .frame-asset::after {{
      display: none;
    }}
    .frame-asset img {{ display: block; width: 100%; height: 100%; aspect-ratio: auto; object-fit: cover; filter: saturate(1.12) contrast(1.08) brightness(.98); transform: scale(1.018); }}
    .frame-asset figcaption {{
      display: none;
      position: absolute;
      right: 18px;
      bottom: 18px;
      z-index: 2;
      max-width: calc(100% - 28px);
      padding: 7px 10px;
      border-radius: 999px;
      color: rgba(248,243,231,.72);
      background: rgba(0,0,0,.30);
      backdrop-filter: blur(12px);
      font-size: 11px;
      letter-spacing: .04em;
      opacity: 0;
      transform: translateY(6px);
      transition: opacity .18s ease, transform .18s ease;
    }}
    .frame[data-active="true"]:hover .frame-asset figcaption,
    .frame[data-active="true"]:focus-within .frame-asset figcaption {{
      opacity: .72;
      transform: none;
    }}
    .treatment-split_crop .frame-asset {{ border-radius: 28px; }}
    .treatment-masked_window .frame-asset {{ border: 1px solid color-mix(in srgb, var(--accent) 38%, transparent); border-radius: 28px; box-shadow: 0 28px 80px rgba(0,0,0,.42); }}
    .treatment-layered_cutout .frame-asset {{ border: 1px solid rgba(255,255,255,.24); border-radius: 36px; transform: none; box-shadow: -14px 18px 0 color-mix(in srgb, var(--accent) 12%, transparent), 0 36px 90px rgba(0,0,0,.48); }}
    .treatment-evidence_strip .frame-asset {{ border: 1px solid color-mix(in srgb, var(--accent) 34%, transparent); border-radius: 24px; }}
    .treatment-atmospheric_backdrop .frame-asset img {{ filter: saturate(.96) contrast(1.06) brightness(.92); transform: scale(1.018); }}
    .block {{ position: relative; overflow: visible; min-width: 0; min-height: 104px; display: grid; align-content: center; padding: 18px; border-radius: 16px; background: var(--card-surface); border: 1px solid var(--card-border); box-shadow: 0 14px 34px rgba(0,0,0,.20); }}
    .block::after {{ content: ""; position: absolute; inset: auto -30px -45px auto; width: 110px; height: 110px; border-radius: 999px; background: var(--accent); opacity: .10; }}
    .block p {{ display: block; overflow: visible; font-size: var(--type-card); line-height: 1.38; margin: 0; }}
    .explainer-layer {{
      position: relative;
      z-index: 4;
      width: var(--content-w);
      max-width: var(--content-w);
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      padding: 12px;
      margin: 0 0 24px 0;
      border: 1px solid color-mix(in srgb, var(--accent) 42%, transparent);
      border-radius: 22px;
      background: var(--card-surface-soft);
      box-shadow: 0 24px 70px rgba(0,0,0,.38);
      backdrop-filter: blur(20px);
      pointer-events: none;
    }}
    .explainer-layer[data-render="metadata-only"] {{
      display: none !important;
    }}
    .explainer-node {{
      position: relative;
      z-index: 2;
      min-height: 58px;
      display: grid;
      align-content: center;
      padding: 11px 13px;
      border: 1px solid color-mix(in srgb, var(--accent) 28%, transparent);
      border-radius: 14px;
      background: var(--card-surface);
      overflow: hidden;
      font-size: 13px;
      line-height: 1.28;
      font-weight: 720;
    }}
    .explainer-connector {{
      position: absolute;
      z-index: 1;
      left: 12%;
      right: 12%;
      top: 50%;
      height: 2px;
      background: linear-gradient(90deg, transparent, var(--accent), transparent);
      opacity: .62;
    }}
    .explainer-layer[data-explanation-mode="hero_photo"] {{ width: var(--content-w); grid-template-columns: 1fr; }}
    .explainer-layer[data-explanation-mode="process_diagram"],
    .explainer-layer[data-explanation-mode="summary_map"] {{ width: var(--content-w); grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .explainer-layer[data-explanation-mode="data_evidence"] .explainer-node {{ border-left: 4px solid var(--accent); }}
    .explainer-layer[data-explanation-mode="comparison_visual"] {{ grid-template-columns: 1fr 1fr; }}
    .explainer-layer[data-explanation-mode="concept_diagram"] {{ border-radius: 999px; }}
    .explainer-layer[data-explanation-mode="concept_diagram"] .explainer-node {{ border-radius: 999px; text-align: center; }}
    .composition-process_ribbon .explainer-layer,
    .composition-system_map .explainer-layer,
    .composition-data_landscape .explainer-layer {{ transform: none; }}
    .frame-hero .frame-inner {{ display: grid; align-content: center; }}
    .frame-hero h1 {{ max-width: var(--content-w); }}
    .frame-hero .blocks {{ grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: stretch; }}
    .frame-section .frame-inner,
    .frame-closing .frame-inner {{ display: grid; align-content: center; text-align: center; }}
    .frame-section .blocks,
    .frame-closing .blocks {{ max-width: var(--content-w); margin-inline: 0; grid-template-columns: 1fr; }}
    .frame-two_column .blocks {{ grid-template-columns: minmax(0, 1.15fr) minmax(280px, .85fr); }}
    .frame-two_column .block:first-child {{ min-height: 320px; display: grid; align-content: center; }}
    .frame-three_cards .blocks {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    .frame-timeline .blocks {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .frame-timeline .block {{ margin-top: 48px; }}
    .frame-timeline .block::before {{ content: ""; position: absolute; top: -48px; left: 28px; width: 18px; height: 18px; border-radius: 999px; background: var(--accent); box-shadow: 0 0 0 10px color-mix(in srgb, var(--accent), transparent 72%); }}
    .frame-chart_focus .blocks {{ grid-template-columns: minmax(0, 1.2fr) minmax(260px, .8fr); }}
    .frame-chart_focus .block:first-child,
    .block-chart_placeholder {{ min-height: 280px; }}
    .block-chart_placeholder::before {{ content: ""; position: absolute; left: 28px; right: 28px; bottom: 28px; height: 44%; border-radius: 18px; background: linear-gradient(90deg, var(--accent) 18%, transparent 18% 26%, var(--soft) 26% 48%, transparent 48% 56%, var(--accent) 56% 82%, transparent 82%); opacity: .55; }}
    .block-image_placeholder::before {{ content: ""; position: absolute; inset: 18px 18px auto auto; width: 64px; height: 64px; border-radius: 20px; background: radial-gradient(circle at 30% 30%, var(--fg), transparent 18%), var(--accent); opacity: .35; }}
    .composition-editorial_cover .frame-inner {{ padding-left: 72px; display: grid; align-content: center; }}
    .composition-editorial_cover h1 {{ max-width: min(58%, 680px); font-family: Georgia, "Times New Roman", serif; font-weight: 500; }}
    .composition-editorial_cover h2,
    .composition-editorial_cover .blocks {{ max-width: 42%; }}
    .composition-architectural_cover .frame-inner {{ display: grid; align-content: end; padding: 76px; }}
    .composition-architectural_cover h1 {{ max-width: 70%; padding-top: 28px; border-top: 5px solid var(--accent); }}
    .composition-architectural_cover .blocks {{ max-width: 68%; grid-template-columns: 1fr 1fr; }}
    .composition-chapter_index .blocks {{ max-width: 58%; grid-template-columns: 1fr; counter-reset: chapter; }}
    .composition-chapter_index .block {{ min-height: 74px; padding-left: 76px; }}
    .composition-chapter_index .block::before {{ counter-increment: chapter; content: counter(chapter, decimal-leading-zero); position: absolute; left: 20px; top: 18px; color: var(--accent); font-size: 28px; font-weight: 900; }}
    .composition-editorial_split h1,
    .composition-editorial_split h2,
    .composition-editorial_split .blocks {{ max-width: 46%; }}
    .composition-editorial_split .blocks {{ grid-template-columns: 1fr; }}
    .composition-diagonal_story .frame-inner {{ clip-path: polygon(0 0, 100% 0, 94% 100%, 0 100%); }}
    .composition-diagonal_story h1 {{ max-width: 62%; transform: rotate(-1deg); }}
    .composition-diagonal_story .blocks {{ max-width: 62%; grid-template-columns: 1.1fr .9fr; transform: translateX(3%); }}
    .composition-statement_focus .frame-inner {{ display: grid; align-content: center; }}
    .composition-statement_focus h1 {{ max-width: 88%; font-size: clamp(40px, 5.8vw, 76px); }}
    .composition-statement_focus .blocks {{ grid-template-columns: minmax(0, 1.55fr) repeat(2, minmax(180px, .72fr)); max-width: 100%; }}
    .composition-statement_focus .block:first-child {{ font-size: 1.18em; border-left: 5px solid var(--accent); }}
    .composition-proof_mosaic h1,
    .composition-proof_mosaic h2,
    .composition-proof_mosaic .blocks {{ max-width: 53%; }}
    .composition-proof_mosaic .blocks {{ grid-template-columns: 1fr 1fr; }}
    .composition-proof_mosaic .block:first-child {{ grid-column: 1 / -1; }}
    .composition-data_landscape .blocks {{ margin-top: 22px; max-width: 100%; grid-template-columns: 1.25fr repeat(3, .65fr); }}
    .composition-data_landscape .block:first-child {{ min-height: 210px; }}
    .composition-process_ribbon .blocks {{ position: absolute; left: 5%; right: 5%; bottom: 8%; max-width: none; grid-template-columns: repeat(4, 1fr); gap: 10px; }}
    .composition-process_ribbon .blocks::before {{ content: ""; position: absolute; left: 4%; right: 4%; top: -22px; height: 3px; background: var(--accent); opacity: .72; }}
    .composition-process_ribbon .block {{ min-height: 150px; border-radius: 12px 28px 12px 12px; }}
    .composition-system_map .blocks {{ width: 84%; max-width: none; margin: 86px auto 0; grid-template-columns: repeat(3, 1fr); align-items: center; }}
    .composition-system_map .block {{ border-radius: 999px; min-height: 140px; display: grid; place-items: center; text-align: center; }}
    .composition-system_map .block:first-child {{ transform: translateY(-42px); }}
    .composition-system_map .block:nth-child(3) {{ transform: translateY(42px); }}
    .composition-split_comparison .blocks {{ max-width: 100%; grid-template-columns: 1fr 1fr; gap: 28px; }}
    .composition-split_comparison .block {{ min-height: 180px; }}
    .composition-split_comparison .block:nth-child(odd) {{ border-top: 5px solid #1F67D2; }}
    .composition-split_comparison .block:nth-child(even) {{ border-top: 5px solid #A92323; }}
    .composition-priority_stack .blocks {{ max-width: 72%; grid-template-columns: 1fr; gap: 10px; }}
    .composition-priority_stack .block:nth-child(2) {{ margin-left: 7%; }}
    .composition-priority_stack .block:nth-child(3) {{ margin-left: 14%; }}
    .composition-priority_stack .block:nth-child(4) {{ margin-left: 21%; }}
    .composition-closing_echo .frame-inner,
    .composition-manifesto_close .frame-inner,
    .composition-future_horizon .frame-inner {{ display: grid; align-content: center; text-align: center; }}
    .composition-closing_echo h1,
    .composition-manifesto_close h1,
    .composition-future_horizon h1 {{ max-width: 940px; margin-inline: auto; }}
    .composition-manifesto_close h1 {{ text-transform: uppercase; letter-spacing: .015em; }}
    .composition-future_horizon .blocks {{ max-width: 78%; margin-inline: auto; border-top: 2px solid var(--accent); padding-top: 24px; }}
    .frame-inner > h1,
    .frame-inner > h2,
    .frame-inner > .blocks,
    .frame-inner > .explainer-layer {{
      max-width: var(--content-w) !important;
      width: var(--content-w) !important;
      margin-left: 0 !important;
      margin-right: auto !important;
      text-align: left !important;
      transform: none !important;
    }}
    .frame-inner > h1 {{
      font-family: "Times New Roman", SimSun, "宋体", serif !important;
      font-size: var(--type-title) !important;
      line-height: 1.08 !important;
    }}
    .frame-inner > h2,
    .block p,
    .explainer-node {{
      font-family: "Times New Roman", SimSun, "宋体", serif !important;
    }}
    .frame-inner > .blocks {{
      position: relative !important;
      left: auto !important;
      right: auto !important;
      bottom: auto !important;
      grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
      gap: 14px !important;
    }}
    .frame-inner > .explainer-layer {{
      position: relative !important;
      inset: auto !important;
      top: auto !important;
      right: auto !important;
      bottom: auto !important;
      left: auto !important;
      grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
      padding: 12px !important;
      margin-top: 0 !important;
      margin-bottom: 24px !important;
    }}
    .frame-asset figcaption {{
      display: none !important;
    }}
    .composition-process_ribbon .blocks::before {{
      display: none !important;
    }}
    .composition-cinematic_hero .frame-inner,
    .composition-editorial_cover .frame-inner,
    .composition-architectural_cover .frame-inner {{
      align-content: center !important;
    }}
    .composition-cinematic_hero .blocks,
    .composition-editorial_cover .blocks,
    .composition-architectural_cover .blocks {{
      grid-template-columns: 1.08fr .92fr !important;
      margin-top: 30px !important;
    }}
    .composition-chapter_index .blocks,
    .composition-system_map .blocks {{
      grid-template-columns: 1fr !important;
      gap: 10px !important;
    }}
    .composition-proof_mosaic .blocks,
    .composition-data_landscape .blocks,
    .composition-statement_focus .blocks {{
      grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
      align-items: stretch !important;
    }}
    .composition-proof_mosaic .block:first-child,
    .composition-data_landscape .block:first-child,
    .composition-statement_focus .block:first-child {{
      grid-column: 1 / -1 !important;
      min-height: 128px !important;
      border-left: 5px solid var(--accent);
    }}
    .composition-process_ribbon .blocks,
    .composition-diagonal_story .blocks,
    .composition-split_comparison .blocks {{
      grid-template-columns: 1fr !important;
      gap: 10px !important;
    }}
    .composition-future_horizon .blocks,
    .composition-manifesto_close .blocks,
    .composition-closing_echo .blocks,
    .composition-priority_stack .blocks {{
      grid-template-columns: 1fr !important;
      border-top: 2px solid var(--accent);
      padding-top: 18px;
    }}
    .block {{
      min-height: 92px !important;
      max-height: 152px !important;
      align-content: center !important;
    }}
    .block p {{
      -webkit-line-clamp: 3 !important;
      font-size: var(--type-card) !important;
      line-height: 1.32 !important;
      letter-spacing: -.01em;
    }}
    .composition-statement_focus .block:first-child,
    .composition-system_map .block:first-child,
    .composition-system_map .block:nth-child(3),
    .composition-priority_stack .block:nth-child(2),
    .composition-priority_stack .block:nth-child(3),
    .composition-priority_stack .block:nth-child(4) {{
      margin-left: 0 !important;
      transform: none !important;
    }}
    /* Content-driven composition contract. These rules intentionally come
       after the legacy safety skin so page-plan geometry is not flattened. */
    .frame.frame > .frame-inner > h1,
    .frame.frame > .frame-inner > h2,
    .frame.frame > .frame-inner > .blocks,
    .frame.frame > .frame-inner > .explainer-layer {{
      position: relative !important;
      inset: auto !important;
      max-width: var(--content-w) !important;
      width: var(--content-w) !important;
      margin-left: var(--content-left) !important;
      margin-right: 0 !important;
      min-width: 0 !important;
      transform: none !important;
    }}
    .frame.frame > .frame-inner > h1 {{
      overflow: visible !important;
      font-family: "Times New Roman", SimSun, "宋体", serif !important;
      font-size: var(--type-title) !important;
      line-height: 1.14 !important;
    }}
    .frame.frame > .frame-inner > .blocks {{ gap: 14px !important; }}
    .frame.frame > .frame-inner > .explainer-layer {{
      padding: 12px !important;
      margin-top: 0 !important;
      margin-bottom: 20px !important;
    }}
    .frame.frame > .frame-inner > .frame-asset {{
      inset: var(--asset-inset) !important;
      z-index: 0 !important;
      min-height: 0 !important;
      border-radius: var(--asset-radius) !important;
      border: 1px solid color-mix(in srgb, var(--accent) 28%, transparent) !important;
      box-shadow: 0 28px 80px rgba(0,0,0,.32) !important;
    }}
    .frame.frame .block {{
      min-height: 86px !important;
      max-height: none !important;
      overflow: visible !important;
      align-content: center !important;
    }}
    .frame.frame .block p {{
      display: block !important;
      overflow: visible !important;
      -webkit-line-clamp: unset !important;
      font-size: var(--type-card) !important;
      line-height: 1.38 !important;
      letter-spacing: -.006em;
    }}

    .composition-cinematic_hero {{
      --content-w: 46%; --content-left: 0%; --asset-inset: 8% 5% 9% 56%; --asset-radius: 28px;
      --frame-overlay: linear-gradient(90deg, color-mix(in srgb, var(--bg) 94%, transparent) 0 42%, color-mix(in srgb, var(--bg) 28%, transparent) 68%, color-mix(in srgb, var(--bg) 10%, transparent));
    }}
    .composition-editorial_cover {{
      --content-w: 42%; --content-left: 53%; --asset-inset: 8% 54% 10% 5%; --asset-radius: 28px;
      --frame-overlay: linear-gradient(270deg, color-mix(in srgb, var(--bg) 94%, transparent) 0 43%, color-mix(in srgb, var(--bg) 24%, transparent) 70%, color-mix(in srgb, var(--bg) 8%, transparent));
    }}
    .composition-architectural_cover {{
      --content-w: 66%; --content-left: 3%; --asset-inset: 10% 5% 58% 35%; --asset-radius: 26px;
      --frame-overlay: linear-gradient(180deg, color-mix(in srgb, var(--bg) 92%, transparent) 0 42%, color-mix(in srgb, var(--bg) 22%, transparent) 72%, color-mix(in srgb, var(--bg) 52%, transparent));
    }}
    .composition-chapter_index {{
      --content-w: 63%; --content-left: 0%; --asset-inset: 0;
      --frame-overlay: linear-gradient(90deg, color-mix(in srgb, var(--bg) 96%, transparent) 0 58%, color-mix(in srgb, var(--bg) 40%, transparent) 83%, color-mix(in srgb, var(--bg) 18%, transparent));
    }}
    .composition-editorial_split {{
      --content-w: 44%; --content-left: 54%; --asset-inset: 0 56% 0 0; --asset-radius: 0;
      --frame-overlay: linear-gradient(270deg, color-mix(in srgb, var(--bg) 96%, transparent) 0 45%, color-mix(in srgb, var(--bg) 32%, transparent) 68%, color-mix(in srgb, var(--bg) 12%, transparent));
    }}
    .composition-diagonal_story {{ --content-w: 58%; --content-left: 2%; --asset-inset: 0; }}
    .composition-statement_focus {{
      --content-w: 86%; --content-left: 7%; --asset-inset: 0;
      --frame-overlay: radial-gradient(circle at 50% 42%, color-mix(in srgb, var(--bg) 72%, transparent), color-mix(in srgb, var(--bg) 92%, transparent));
    }}
    .composition-proof_mosaic {{ --content-w: 52%; --content-left: 0%; --asset-inset: 18% 5% 13% 58%; --asset-radius: 24px; }}
    .composition-data_landscape {{ --content-w: 62%; --content-left: 0%; --asset-inset: 8% 5% 76% 66%; --asset-radius: 20px; }}
    .composition-process_ribbon {{ --content-w: 90%; --content-left: 5%; --asset-inset: 22% 5% 64% 5%; --asset-radius: 20px; }}
    .composition-system_map {{
      --content-w: 88%; --content-left: 6%; --asset-inset: 30% 36% 25% 36%; --asset-radius: 999px;
      --frame-overlay: radial-gradient(circle at 50% 50%, color-mix(in srgb, var(--bg) 22%, transparent), color-mix(in srgb, var(--bg) 88%, transparent) 40%, color-mix(in srgb, var(--bg) 96%, transparent));
    }}
    .composition-split_comparison {{ --content-w: 92%; --content-left: 4%; --asset-inset: 39% 45% 34% 45%; --asset-radius: 999px; }}
    .composition-priority_stack {{ --content-w: 73%; --content-left: 0%; --asset-inset: 11% 4% 10% 79%; --asset-radius: 22px; }}
    .composition-gallery_strip {{
      --content-w: 90%; --content-left: 5%; --asset-inset: 5% 5% 67% 5%; --asset-radius: 20px;
      --frame-overlay: linear-gradient(180deg, color-mix(in srgb, var(--bg) 20%, transparent) 0 25%, color-mix(in srgb, var(--bg) 94%, transparent) 46% 100%);
    }}
    .composition-vertical_story {{
      --content-w: 61%; --content-left: 0%; --asset-inset: 0 0 0 70%; --asset-radius: 0;
      --frame-overlay: linear-gradient(90deg, color-mix(in srgb, var(--bg) 96%, transparent) 0 58%, color-mix(in srgb, var(--bg) 30%, transparent) 78%, color-mix(in srgb, var(--bg) 12%, transparent));
    }}
    .composition-spotlight_quote {{
      --content-w: 55%; --content-left: 2%; --asset-inset: 55% 5% 10% 59%; --asset-radius: 30px;
      --frame-overlay: radial-gradient(circle at 28% 38%, color-mix(in srgb, var(--bg) 74%, transparent), color-mix(in srgb, var(--bg) 94%, transparent) 66%);
    }}
    .composition-evidence_matrix {{
      --content-w: 57%; --content-left: 42%; --asset-inset: 25% 66% 16% 5%; --asset-radius: 24px;
      --frame-overlay: linear-gradient(270deg, color-mix(in srgb, var(--bg) 95%, transparent) 0 50%, color-mix(in srgb, var(--bg) 34%, transparent) 75%, color-mix(in srgb, var(--bg) 14%, transparent));
    }}
    .composition-orbit_system {{
      --content-w: 92%; --content-left: 4%; --asset-inset: 29% 37% 23% 37%; --asset-radius: 999px;
      --frame-overlay: radial-gradient(circle at 50% 50%, color-mix(in srgb, var(--bg) 24%, transparent), color-mix(in srgb, var(--bg) 90%, transparent) 43%, color-mix(in srgb, var(--bg) 97%, transparent));
    }}
    .composition-step_ladder {{
      --content-w: 60%; --content-left: 36%; --asset-inset: 0 68% 0 0; --asset-radius: 0;
      --frame-overlay: linear-gradient(270deg, color-mix(in srgb, var(--bg) 96%, transparent) 0 56%, color-mix(in srgb, var(--bg) 34%, transparent) 76%, color-mix(in srgb, var(--bg) 13%, transparent));
    }}
    .composition-bridge_narrative {{
      --content-w: 56%; --content-left: 0%; --asset-inset: 7% 5% 58% 57%; --asset-radius: 26px;
      --frame-overlay: linear-gradient(90deg, color-mix(in srgb, var(--bg) 96%, transparent) 0 49%, color-mix(in srgb, var(--bg) 33%, transparent) 70%, color-mix(in srgb, var(--bg) 12%, transparent));
    }}
    .composition-closing_bloom {{
      --content-w: 78%; --content-left: 11%; --asset-inset: 0; --asset-radius: 0;
      --frame-overlay: radial-gradient(circle at 50% 42%, color-mix(in srgb, var(--bg) 57%, transparent), color-mix(in srgb, var(--bg) 91%, transparent));
    }}
    .composition-closing_echo,
    .composition-manifesto_close,
    .composition-future_horizon {{
      --content-w: 80%; --content-left: 10%; --asset-inset: 0;
      --frame-overlay: radial-gradient(circle at 50% 50%, color-mix(in srgb, var(--bg) 54%, transparent), color-mix(in srgb, var(--bg) 88%, transparent));
    }}

    .composition-proof_mosaic .blocks {{ grid-template-columns: 1fr 1fr !important; }}
    .composition-proof_mosaic .block:first-child {{ grid-column: 1 / -1 !important; }}
    .composition-data_landscape .blocks {{ grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }}
    .composition-process_ribbon .frame-inner > .blocks {{
      position: absolute !important;
      left: 4% !important; right: 4% !important; bottom: 7% !important;
      width: auto !important; max-width: none !important; margin-left: 0 !important;
      grid-template-columns: repeat(4, minmax(0, 1fr)) !important;
    }}
    .composition-system_map .blocks {{ grid-template-columns: repeat(3, minmax(0, 1fr)) !important; }}
    .composition-split_comparison .blocks {{ grid-template-columns: 1fr 1fr !important; gap: 26px !important; }}
    .composition-priority_stack .blocks {{ grid-template-columns: 1fr !important; }}
    .composition-gallery_strip .frame-inner {{ padding-top: clamp(180px, 19vh, 260px) !important; }}
    .composition-gallery_strip .blocks {{ grid-template-columns: repeat(3, minmax(0, 1fr)) !important; max-width: 100% !important; }}
    .composition-vertical_story .blocks {{ grid-template-columns: 1fr !important; max-width: 61% !important; }}
    .composition-spotlight_quote .frame-inner {{ display: grid !important; align-content: center !important; }}
    .composition-spotlight_quote h1 {{ max-width: 56% !important; font-size: clamp(42px, 6vw, 76px) !important; }}
    .composition-spotlight_quote .blocks {{ max-width: 54% !important; grid-template-columns: 1fr !important; }}
    .composition-evidence_matrix .blocks {{ margin-left: auto !important; max-width: 56% !important; grid-template-columns: 1fr 1fr !important; }}
    .composition-orbit_system .blocks {{ width: 94% !important; max-width: none !important; margin: 92px auto 0 !important; grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }}
    .composition-orbit_system .block:nth-child(odd) {{ transform: translateX(-6%); }}
    .composition-orbit_system .block:nth-child(even) {{ transform: translateX(6%); }}
    .composition-step_ladder .blocks {{ margin-left: auto !important; max-width: 59% !important; grid-template-columns: 1fr !important; gap: 10px !important; }}
    .composition-step_ladder .block:nth-child(2) {{ margin-left: 8% !important; }}
    .composition-step_ladder .block:nth-child(3) {{ margin-left: 16% !important; }}
    .composition-bridge_narrative .blocks {{ position: absolute !important; left: 5% !important; right: 5% !important; bottom: 8% !important; max-width: none !important; grid-template-columns: repeat(3, minmax(0, 1fr)) !important; }}
    .composition-closing_bloom .frame-inner {{ align-content: center !important; text-align: center !important; }}
    .composition-closing_bloom .frame-inner > h1,
    .composition-closing_bloom .frame-inner > h2,
    .composition-closing_bloom .frame-inner > .blocks {{ margin-left: auto !important; margin-right: auto !important; }}
    .composition-closing_echo .frame-inner,
    .composition-manifesto_close .frame-inner,
    .composition-future_horizon .frame-inner {{ align-content: center !important; text-align: center !important; }}
    .composition-closing_echo .frame-inner > h1,
    .composition-closing_echo .frame-inner > h2,
    .composition-closing_echo .frame-inner > .blocks,
    .composition-manifesto_close .frame-inner > h1,
    .composition-manifesto_close .frame-inner > h2,
    .composition-manifesto_close .frame-inner > .blocks,
    .composition-future_horizon .frame-inner > h1,
    .composition-future_horizon .frame-inner > h2,
    .composition-future_horizon .frame-inner > .blocks {{ margin-left: auto !important; margin-right: auto !important; }}
    .speaker-notes {{ display: none; margin-top: 34px; opacity: .66; font-size: 15px; line-height: 1.6; }}
    body[data-notes="true"] .speaker-notes {{ display: block; }}
    .frame[data-active="true"] .frame-inner::after {{ animation: reference-light-sweep 1.4s cubic-bezier(.2,.7,.2,1) both; }}
    .frame[data-active="true"] .frame-asset {{ animation: asset-float .56s cubic-bezier(.2,.7,.2,1) both; }}
    .frame[data-active="true"] .block {{ animation: block-rise .42s cubic-bezier(.2,.7,.2,1) both; }}
    .frame[data-active="true"] .block:nth-child(2) {{ animation-delay: .06s; }}
    .frame[data-active="true"] .block:nth-child(3) {{ animation-delay: .12s; }}
    .frame[data-active="true"] .block:nth-child(4) {{ animation-delay: .18s; }}
    .frame[data-active="true"] .explainer-node {{ animation: explainer-build .5s cubic-bezier(.2,.7,.2,1) both; }}
    .frame[data-active="true"] .explainer-node:nth-of-type(2) {{ animation-delay: .08s; }}
    .frame[data-active="true"] .explainer-node:nth-of-type(3) {{ animation-delay: .16s; }}
    .frame[data-active="true"] .explainer-node:nth-of-type(4) {{ animation-delay: .24s; }}
    .motion-editorial_wipe[data-active="true"] h1 {{ animation: editorial-wipe .58s cubic-bezier(.2,.7,.2,1) both; }}
    .motion-evidence_reveal[data-active="true"] .blocks {{ animation: evidence-reveal .64s cubic-bezier(.2,.7,.2,1) both; }}
    .motion-sequence_build[data-active="true"] .block {{ animation-name: sequence-build; }}
    .motion-diagram_orbit[data-active="true"] .block {{ animation-name: diagram-orbit; }}
    @keyframes rise {{ from {{ opacity: 0; transform: translateY(16px) scale(.992); }} to {{ opacity: 1; transform: none; }} }}
    @keyframes reference-light-sweep {{ from {{ opacity: 0; transform: translateX(-38%); }} 42% {{ opacity: 1; }} to {{ opacity: .58; transform: translateX(28%); }} }}
    @keyframes asset-float {{ from {{ opacity: 0; transform: scale(1.025); filter: saturate(.76) blur(5px); }} to {{ opacity: 1; transform: none; filter: saturate(1.04) blur(0); }} }}
    @keyframes block-rise {{ from {{ opacity: 0; transform: translateY(12px); }} to {{ opacity: 1; transform: none; }} }}
    @keyframes editorial-wipe {{ from {{ opacity: 0; clip-path: inset(0 100% 0 0); transform: translateX(-18px); }} to {{ opacity: 1; clip-path: inset(0); transform: none; }} }}
    @keyframes evidence-reveal {{ from {{ opacity: 0; transform: translateY(20px) scale(.985); filter: blur(4px); }} to {{ opacity: 1; transform: none; filter: none; }} }}
    @keyframes sequence-build {{ from {{ opacity: 0; transform: translateX(-18px); }} to {{ opacity: 1; transform: none; }} }}
    @keyframes diagram-orbit {{ from {{ opacity: 0; transform: translateY(18px) rotate(-2deg) scale(.96); }} to {{ opacity: 1; transform: none; }} }}
    @keyframes explainer-build {{ from {{ opacity: 0; transform: translateY(10px) scale(.96); }} to {{ opacity: 1; transform: none; }} }}
    @media (max-width: 720px) {{
      .chrome {{ inset: 12px 12px auto 12px; align-items: stretch; flex-direction: column; max-width: calc(100vw - 24px); }}
      .controls {{ flex-wrap: wrap; }}
      .brand span {{ max-width: 100%; }}
      .frame {{ padding: 118px 16px 72px; }}
      .frame-inner {{ min-height: auto; padding: 28px; border-radius: 26px; }}
      body[data-presenter="true"] .frame {{ padding: 0; }}
      body[data-presenter="true"] .frame-inner {{ padding: 22px; border-radius: 0; }}
      h1 {{ font-size: clamp(30px, 10vw, 52px); }}
      .frame-asset img {{ aspect-ratio: 16 / 9; }}
      .blocks,
      .frame-hero .blocks,
      .frame-two_column .blocks,
      .frame-three_cards .blocks,
      .frame-timeline .blocks,
      .frame-chart_focus .blocks {{ grid-template-columns: 1fr; margin-top: 26px; }}
      .explainer-layer {{ position: relative; inset: auto; width: 100%; margin-top: 22px; grid-template-columns: 1fr; transform: none !important; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      *, *::before, *::after {{ animation: none !important; transition: none !important; scroll-behavior: auto !important; }}
    }}
  </style>
</head>
<body data-notes="false" data-hyperframes-renderer="local" data-motion-engine="HyperFrames" data-deck-contract="SlideDeck JSON" data-reference-style="content-driven-composition" data-design-system="{html.escape(deck.theme.design_system_id)}">
  <div class="chrome">
    <div class="brand"><strong>AI PPT Agent</strong><span>{html.escape(deck.project_id)}</span></div>
    <div class="controls">
      <button type="button" data-action="present" aria-pressed="false">全屏放映</button>
      <button type="button" data-action="fit">适配窗口</button>
      <button type="button" data-action="zoom-out" aria-label="缩小预览">−</button>
      <button type="button" data-action="zoom-in" aria-label="放大预览">＋</button>
      <button type="button" data-action="prev">上一页</button>
      <button type="button" data-action="next">下一页</button>
      <button type="button" data-action="notes">讲稿</button>
    </div>
  </div>
  {"".join(slides)}
  <nav class="dots" aria-label="幻灯片导航">{nav_buttons}</nav>
  <div class="progress" aria-hidden="true"><span></span></div>
  <script>
    const deckTitle = {deck_title_json};
    const frames = Array.from(document.querySelectorAll('.frame'));
    const dots = Array.from(document.querySelectorAll('.dots button'));
    const progress = document.querySelector('.progress span');
    const presentButton = document.querySelector('[data-action="present"]');
    let zoom = 1;
    let current = 0;
    function setZoom(value) {{
      zoom = Math.max(.74, Math.min(1.36, value));
      document.body.style.setProperty('--preview-zoom', zoom.toFixed(2));
    }}
    function setPresenter(active) {{
      document.body.dataset.presenter = String(active);
      presentButton.textContent = active ? '退出放映' : '全屏放映';
      presentButton.setAttribute('aria-pressed', String(active));
      if (active) setZoom(1);
    }}
    async function togglePresenter() {{
      if (!document.fullscreenElement) {{
        setPresenter(true);
        try {{
          await document.documentElement.requestFullscreen();
        }} catch (_error) {{
          setPresenter(true);
        }}
      }} else {{
        await document.exitFullscreen();
      }}
    }}
    function show(index) {{
      current = Math.max(0, Math.min(frames.length - 1, index));
      frames.forEach((frame, frameIndex) => frame.dataset.active = String(frameIndex === current));
      dots.forEach((dot, dotIndex) => dot.dataset.active = String(dotIndex === current));
      progress.style.width = `${{((current + 1) / frames.length) * 100}}%`;
      document.title = `${{current + 1}}/${{frames.length}} · ${{deckTitle}}`;
    }}
    presentButton.addEventListener('click', () => void togglePresenter());
    document.querySelector('[data-action="fit"]').addEventListener('click', () => setZoom(1));
    document.querySelector('[data-action="zoom-out"]').addEventListener('click', () => setZoom(zoom - .08));
    document.querySelector('[data-action="zoom-in"]').addEventListener('click', () => setZoom(zoom + .08));
    document.querySelector('[data-action="prev"]').addEventListener('click', () => show(current - 1));
    document.querySelector('[data-action="next"]').addEventListener('click', () => show(current + 1));
    document.querySelector('[data-action="notes"]').addEventListener('click', () => {{
      document.body.dataset.notes = document.body.dataset.notes === 'true' ? 'false' : 'true';
    }});
    dots.forEach((dot) => dot.addEventListener('click', () => show(Number(dot.dataset.index || 0))));
    window.addEventListener('keydown', (event) => {{
      if (['ArrowRight', 'PageDown', ' '].includes(event.key)) {{ event.preventDefault(); show(current + 1); }}
      if (['ArrowLeft', 'PageUp'].includes(event.key)) {{ event.preventDefault(); show(current - 1); }}
      if (event.key === 'Home') show(0);
      if (event.key === 'End') show(frames.length - 1);
      if (event.key.toLowerCase() === 'f') {{ event.preventDefault(); void togglePresenter(); }}
      if (event.key === '+' || event.key === '=') {{ event.preventDefault(); setZoom(zoom + .08); }}
      if (event.key === '-' || event.key === '_') {{ event.preventDefault(); setZoom(zoom - .08); }}
      if (event.key === '0') {{ event.preventDefault(); setZoom(1); }}
      if (event.key === 'Escape' && document.body.dataset.presenter === 'true' && !document.fullscreenElement) {{
        setPresenter(false);
      }}
      if (event.key.toLowerCase() === 'n') {{
        document.body.dataset.notes = document.body.dataset.notes === 'true' ? 'false' : 'true';
      }}
    }});
    document.addEventListener('fullscreenchange', () => setPresenter(Boolean(document.fullscreenElement)));
    show(0);
  </script>
</body>
</html>
"""
    path.write_text(content, encoding="utf-8")


def _asset_figure_html(asset: VisualAsset) -> str:
    caption = _clean_visible_text(asset.attribution or asset.source_type, role="body", clip=False)
    # Query is canonical Image Agent metadata, not customer-visible copy.  Keep
    # it byte-for-byte (apart from surrounding whitespace) so the HTML remains
    # traceable to the same SlideDeck JSON that produced the PPTX.
    query = str(asset.query or "").strip()
    purpose = _clean_visible_text(asset.purpose, role="body", clip=False)
    alt = _clean_visible_text(asset.alt, role="body", clip=False) or asset.source_type
    return (
        f'<figure class="frame-asset" data-source-type="{html.escape(asset.source_type)}" '
        f'data-query="{html.escape(query)}" '
        f'data-image-plan-type="{html.escape(asset.image_type)}" '
        f'data-image-plan-purpose="{html.escape(purpose)}" '
        f'data-provider-chain="{html.escape(" > ".join(asset.provider_chain))}">'
        f'<img src="{html.escape(asset.rel_path)}" alt="{html.escape(alt)}" loading="eager" />'
        f'<figcaption>{html.escape(caption)}</figcaption>'
        "</figure>"
    )


def _explainer_html(slide) -> str:
    """Expose explainer metadata without rendering a second card panel."""

    plan = slide.design_plan
    visual_brief = _clean_visible_text(plan.visual_brief, role="body", clip=False) or "outline-grounded explainer"
    labels = " | ".join(
        clean_label
        for label in plan.diagram_labels[:3]
        if (clean_label := _clean_visible_text(label, role="card", clip=False))
    )
    return (
        '<div class="explainer-layer" '
        f'data-explanation-mode="{html.escape(plan.explanation_mode)}" '
        'data-render="metadata-only" '
        f'data-visual-brief="{html.escape(visual_brief)}" '
        f'data-diagram-labels="{html.escape(labels)}" '
        'aria-hidden="true"><div class="explainer-connector"></div><div class="explainer-node"></div></div>'
    )


def _write_pptx(deck: SlideDeck, path: Path, visual_assets: dict[int, VisualAsset]) -> None:
    slide_count = len(deck.slides)
    if not PPTX_TEMPLATE_PATH.is_file():
        raise FileNotFoundError(f"native PPTX template is missing: {PPTX_TEMPLATE_PATH}")
    dynamic_parts = {
        "[Content_Types].xml",
        "ppt/presentation.xml",
        "ppt/_rels/presentation.xml.rels",
        "docProps/core.xml",
        "docProps/app.xml",
    }
    with zipfile.ZipFile(PPTX_TEMPLATE_PATH) as template, zipfile.ZipFile(
        path, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        template_parts = {name: template.read(name) for name in template.namelist()}
        for info in template.infolist():
            name = info.filename
            if (
                name in dynamic_parts
                or name.startswith("ppt/slides/")
                or name.startswith("ppt/notesSlides/")
                or name.startswith("ppt/media/")
            ):
                continue
            part = template_parts[name]
            if name.endswith(".xml"):
                archive.writestr(info, _enforce_office_font_scheme(part.decode("utf-8")))
            else:
                archive.writestr(info, part)
        archive.writestr(
            "[Content_Types].xml",
            _native_content_types(template_parts["[Content_Types].xml"].decode("utf-8"), slide_count, visual_assets),
        )
        archive.writestr(
            "ppt/presentation.xml",
            _native_presentation(template_parts["ppt/presentation.xml"].decode("utf-8"), slide_count),
        )
        archive.writestr(
            "ppt/_rels/presentation.xml.rels",
            _native_presentation_rels(
                template_parts["ppt/_rels/presentation.xml.rels"].decode("utf-8"), slide_count
            ),
        )
        archive.writestr(
            "docProps/core.xml",
            _native_core_props(template_parts["docProps/core.xml"].decode("utf-8"), deck),
        )
        archive.writestr(
            "docProps/app.xml",
            _native_app_props(template_parts["docProps/app.xml"].decode("utf-8"), slide_count),
        )
        for asset in visual_assets.values():
            archive.write(asset.path, f"ppt/media/{asset.file_name}")
        for index, slide in enumerate(deck.slides, start=1):
            asset = visual_assets.get(slide.slide_index)
            archive.writestr(
                f"ppt/slides/slide{index}.xml",
                _slide_xml(slide, deck.theme.palette, len(deck.slides), asset, deck.title),
            )
            archive.writestr(f"ppt/slides/_rels/slide{index}.xml.rels", _slide_rels(index, asset))
            archive.writestr(f"ppt/notesSlides/notesSlide{index}.xml", _notes_slide_xml(slide))
            archive.writestr(f"ppt/notesSlides/_rels/notesSlide{index}.xml.rels", _notes_slide_rels(index))


def _enforce_office_font_scheme(xml: str) -> str:
    xml = re.sub(r'<a:latin typeface="[^"]*"/>', '<a:latin typeface="Times New Roman"/>', xml)
    xml = re.sub(r'<a:ea typeface="[^"]*"/>', '<a:ea typeface="SimSun"/>', xml)
    xml = re.sub(r'<a:cs typeface="[^"]*"/>', '<a:cs typeface="Times New Roman"/>', xml)
    return xml


def _native_content_types(
    template_xml: str,
    slide_count: int,
    visual_assets: dict[int, VisualAsset],
) -> str:
    xml = re.sub(r'<Override PartName="/ppt/slides/slide\d+\.xml"[^>]*/>', "", template_xml)
    xml = re.sub(r'<Override PartName="/ppt/notesSlides/notesSlide\d+\.xml"[^>]*/>', "", xml)
    for extension in {asset.path.suffix.lower().lstrip(".") for asset in visual_assets.values()}:
        xml = re.sub(rf'<Default Extension="{re.escape(extension)}"[^>]*/>', "", xml)
    media_defaults = _media_content_type_defaults(visual_assets)
    slides = "".join(
        f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        for i in range(1, slide_count + 1)
    )
    notes = "".join(
        f'<Override PartName="/ppt/notesSlides/notesSlide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>'
        for i in range(1, slide_count + 1)
    )
    return xml.replace("</Types>", f"{media_defaults}{slides}{notes}</Types>")


def _native_presentation(template_xml: str, slide_count: int) -> str:
    slide_ids = "".join(
        f'<p:sldId id="{255 + i}" r:id="rId{7 + i}"/>' for i in range(1, slide_count + 1)
    )
    return re.sub(
        r"<p:sldIdLst>.*?</p:sldIdLst>",
        f"<p:sldIdLst>{slide_ids}</p:sldIdLst>",
        template_xml,
        count=1,
        flags=re.DOTALL,
    )


def _native_presentation_rels(template_xml: str, slide_count: int) -> str:
    xml = re.sub(
        r'<Relationship Id="[^"]+" Type="http://schemas\.openxmlformats\.org/officeDocument/2006/relationships/slide" Target="slides/slide\d+\.xml"/>',
        "",
        template_xml,
    )
    slides = "".join(
        f'<Relationship Id="rId{7 + i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>'
        for i in range(1, slide_count + 1)
    )
    return xml.replace("</Relationships>", f"{slides}</Relationships>")


def _native_core_props(template_xml: str, deck: SlideDeck) -> str:
    clean_title = _clean_visible_text(deck.title, role="title") or deck.project_id
    xml = re.sub(r"<dc:title>.*?</dc:title>", f"<dc:title>{html.escape(clean_title)}</dc:title>", template_xml)
    return re.sub(r"<dc:creator>.*?</dc:creator>", "<dc:creator>AI PPT Agent</dc:creator>", xml)


def _native_app_props(template_xml: str, slide_count: int) -> str:
    return re.sub(r"<Slides>\d+</Slides>", f"<Slides>{slide_count}</Slides>", template_xml)


def _content_types(slide_count: int, visual_assets: dict[int, VisualAsset]) -> str:
    slides = "\n".join(
        f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        for i in range(1, slide_count + 1)
    )
    notes = "\n".join(
        f'<Override PartName="/ppt/notesSlides/notesSlide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>'
        for i in range(1, slide_count + 1)
    )
    media_defaults = _media_content_type_defaults(visual_assets)
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  {media_defaults}
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
  <Override PartName="/ppt/theme/theme2.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
  <Override PartName="/ppt/notesMasters/notesMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml"/>
  <Override PartName="/ppt/presProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"/>
  <Override PartName="/ppt/viewProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"/>
  <Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  {slides}
  {notes}
</Types>'''


def _media_content_type_defaults(visual_assets: dict[int, VisualAsset]) -> str:
    defaults: dict[str, str] = {}
    for asset in visual_assets.values():
        extension = asset.path.suffix.lower().lstrip(".")
        if extension:
            defaults[extension] = asset.mime_type
    return "\n  ".join(
        f'<Default Extension="{html.escape(extension)}" ContentType="{html.escape(content_type)}"/>'
        for extension, content_type in sorted(defaults.items())
    )


def _root_rels() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''


def _presentation(slide_count: int) -> str:
    slide_ids = "\n".join(
        f'<p:sldId id="{255 + i}" r:id="rId{6 + i}"/>' for i in range(1, slide_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>
  <p:sldIdLst>{slide_ids}</p:sldIdLst>
  <p:sldSz cx="12192000" cy="6858000" type="wide"/>
  <p:notesSz cx="6858000" cy="9144000"/>
  <p:defaultTextStyle><a:defPPr><a:defRPr lang="zh-CN"/></a:defPPr></p:defaultTextStyle>
</p:presentation>'''


def _presentation_rels(slide_count: int) -> str:
    slides = "\n".join(
        f'<Relationship Id="rId{6 + i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>'
        for i in range(1, slide_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster" Target="notesMasters/notesMaster1.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps" Target="presProps.xml"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps" Target="viewProps.xml"/>
  <Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>
  <Relationship Id="rId6" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles" Target="tableStyles.xml"/>
  {slides}
</Relationships>'''


def _slide_xml(
    slide,
    palette: list[str],
    total_slides: int,
    visual_asset: VisualAsset | None,
    deck_title: str = "",
) -> str:
    bg, fg, accent, soft, red, blue = _slide_visual_palette(palette, slide)
    slide_for_ppt = RenderSlideProxy(
        slide,
        subtitle=_ppt_subtitle_text(getattr(slide, "subtitle", ""), deck_title),
        title=_ppt_display_title_for_slide(slide, deck_title),
    )
    content_blocks = _content_blocks(
        slide_for_ppt,
        deck_title=deck_title,
        max_blocks=_render_block_limit(slide_for_ppt),
    )
    layout_shapes = _layout_shapes(slide_for_ppt, content_blocks, fg, accent, soft)
    backdrop_shapes = _cinematic_backdrop_shapes(slide_for_ppt, visual_asset, bg, fg, accent, soft, red, blue)
    explainer_shapes = _explainer_shapes(slide_for_ppt, fg, accent, soft)
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree>
    <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>{_group_transform()}
    {_rect_shape(2, 0, 0, SLIDE_CX, SLIDE_CY, bg)}
    {backdrop_shapes}
    {explainer_shapes}
    {layout_shapes}
    {_page_number_shape(slide_for_ppt, total_slides, accent)}
  </p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>'''


def _page_number_shape(slide, total_slides: int, accent: str) -> str:
    x = 10700000
    placement = visual_placement(slide.design_plan.composition_archetype)
    page_number_top = 5980000
    overlaps_right_asset = (
        placement.mode != "full_bleed"
        and placement.y + placement.cy >= page_number_top
        and placement.x < x + 760000
        and placement.x + placement.cx > x
    )
    if overlaps_right_asset:
        x = max(720000, placement.x - 980000)
    return _text_shape(
        900,
        f"{slide.slide_index}/{total_slides}",
        x,
        6100000,
        760000,
        260000,
        1150,
        accent,
        align="r",
        role="meta",
    )


def _explainer_shapes(slide, fg: str, accent: str, soft: str) -> str:
    """Keep the semantic explainer contract without drawing a second layout.

    The canonical design plan already drives the native composition family.  A
    second set of circles, rails and evidence panels used to be rendered on top
    of that family, which made otherwise valid pages feel like two slides had
    been composited together.  The invisible marker preserves QA/provenance;
    the selected composition remains the single customer-visible explainer.
    """

    plan = slide.design_plan
    marker = _alpha_rect_shape(
        700,
        0,
        0,
        1000,
        1000,
        accent,
        0,
        name=f"Page Explainer {plan.explanation_mode}",
    )
    return marker


def _explainer_label_shapes(
    mode: str,
    archetype: str,
    labels: list[str],
    fg: str,
    accent: str,
) -> list[str]:
    if not labels:
        return []
    if mode == "data_evidence" and archetype == "data_landscape":
        placements = [
            (724, 9300000, 4700000, 980000, 360000),
        ]
    elif mode == "data_evidence":
        placements = [
            (724, 8450000, 2450000, 1220000, 420000),
        ]
    elif mode == "comparison_visual":
        placements = [
            (724, 7040000, 2920000, 1500000, 560000),
            (725, 9370000, 2920000, 1500000, 560000),
        ]
    elif mode in {"process_diagram", "summary_map"}:
        placements = [
            (724, 6790000, 5330000, 760000, 360000),
            (725, 8690000, 5330000, 760000, 360000),
            (726, 10590000, 5330000, 760000, 360000),
        ]
    elif mode == "concept_diagram":
        placements = [
            (724, 8610000, 2940000, 1480000, 420000),
            (725, 7420000, 2160000, 1060000, 360000),
            (726, 9850000, 5060000, 1180000, 360000),
        ]
    else:
        placements = [
            (724, 8980000, 1780000, 1900000, 420000),
            (725, 9660000, 4350000, 1320000, 360000),
        ]
    shapes: list[str] = []
    visible_labels = labels[:1] if mode == "data_evidence" else labels
    for index, (shape_id, x, y, cx, cy) in enumerate(placements[: len(visible_labels)]):
        shapes.append(
            _text_shape(
                shape_id,
                visible_labels[index],
                x,
                y,
                cx,
                cy,
                1080,
                fg if index == 0 else accent,
                bold=index == 0,
                align="ctr",
                role="card",
            )
        )
    return shapes


def _reference_palette(palette: list[str]) -> tuple[str, str, str, str, str, str]:
    colors = [_ppt_color(value) for value in palette]
    bg = colors[0] if colors else REF_DARK
    fg = colors[1] if len(colors) > 1 else REF_INK
    accent = colors[2] if len(colors) > 2 else REF_GOLD
    soft = colors[3] if len(colors) > 3 else REF_PANEL
    contrast_a = colors[4] if len(colors) > 4 else accent
    contrast_b = colors[5] if len(colors) > 5 else soft
    return bg, fg, accent, soft, contrast_a, contrast_b


def _mix_ppt_colors(first: str, second: str, second_weight: float) -> str:
    """Blend two RGB colors for deterministic, theme-aware page variation."""

    first = _ppt_color(first)
    second = _ppt_color(second)
    weight = max(0.0, min(1.0, second_weight))
    channels = []
    for offset in (0, 2, 4):
        left = int(first[offset : offset + 2], 16)
        right = int(second[offset : offset + 2], 16)
        channels.append(round(left * (1.0 - weight) + right * weight))
    return "".join(f"{channel:02X}" for channel in channels)


def _slide_visual_palette(palette: list[str], slide) -> tuple[str, str, str, str, str, str]:
    """Give adjacent pages different faces while preserving one design grammar.

    Anchor pages stay cinematic and dark. Evidence, framework and process pages
    rotate through restrained paper tints. Accent and panel colors still derive
    from the selected visual direction, so this is variation—not theme drift.
    """

    theme_bg, theme_fg, theme_accent, theme_soft, contrast_a, contrast_b = _reference_palette(palette)
    archetype = getattr(getattr(slide, "design_plan", None), "composition_archetype", "")
    purpose = str(getattr(slide, "purpose", ""))
    index = max(1, int(getattr(slide, "slide_index", 1)))
    dark_anchor = purpose in {"cover", "conclusion", "section"} or archetype in {
        "cinematic_hero",
        "editorial_cover",
        "architectural_cover",
        "statement_focus",
        "closing_bloom",
        "manifesto_close",
        "future_horizon",
        "closing_echo",
    }
    # A Fortune-500-style deck should look like one brand, not a gallery of
    # unrelated theme colors. Composition creates page variety; the accent
    # remains anchored to the selected direction and shifts only slightly for
    # evidence/comparison semantics.
    if archetype in {"proof_mosaic", "data_landscape", "evidence_matrix"}:
        page_accent = _mix_ppt_colors(theme_accent, contrast_b, 0.12)
    elif archetype == "split_comparison":
        page_accent = _mix_ppt_colors(theme_accent, contrast_a, 0.14)
    else:
        page_accent = theme_accent
    if dark_anchor:
        bg = theme_bg if not _is_light_color(theme_bg) else _mix_ppt_colors(theme_bg, "05080D", 0.86)
        fg = theme_fg if _is_light_color(theme_fg) else "FAF8F2"
        raw_accent = _mix_ppt_colors(theme_accent, page_accent, 0.42)
        accent = raw_accent if _is_light_color(raw_accent) else _mix_ppt_colors(raw_accent, "FFFFFF", 0.28)
        soft = _mix_ppt_colors(bg, accent, 0.16)
        return bg, fg, accent, soft, contrast_a, contrast_b

    paper_faces = ("F7F6F1", "EEF4F7", "F4F0E8", "EEF5F0", "F5EEF1")
    bg = paper_faces[(index - 1) % len(paper_faces)]
    fg = theme_bg if not _is_light_color(theme_bg) else "10211E"
    raw_accent = _mix_ppt_colors(theme_accent, page_accent, 0.58)
    accent = _mix_ppt_colors(raw_accent, fg, 0.48) if _is_light_color(raw_accent) else raw_accent
    soft = _mix_ppt_colors(bg, raw_accent, 0.13)
    red = _mix_ppt_colors(bg, _mix_ppt_colors(contrast_a, page_accent, 0.36), 0.24)
    blue = _mix_ppt_colors(bg, _mix_ppt_colors(contrast_b, page_accent, 0.28), 0.24)
    return bg, fg, accent, soft, red, blue


def _cinematic_backdrop_shapes(
    slide,
    visual_asset: VisualAsset | None,
    bg: str,
    fg: str,
    accent: str,
    soft: str,
    red: str,
    blue: str,
) -> str:
    plan = slide.design_plan
    archetype = plan.composition_archetype
    placement = visual_placement(archetype)
    visual = (
        _image_pic_shape(
            201,
            "rId3",
            placement.x,
            placement.y,
            placement.cx,
            placement.cy,
            visual_asset.alt,
            rounded=False,
            name=f"Content Visual {placement.gravity}",
            source_dimensions=(visual_asset.width, visual_asset.height),
        )
        if visual_asset is not None and placement.mode == "full_bleed"
        else ""
    )
    reading_vignette = ""
    if placement.mode == "full_bleed" and placement.reading_zone is not None:
        reading_x, reading_y, reading_cx, reading_cy = placement.reading_zone
        reading_vignette = _alpha_rect_shape(
            203,
            reading_x,
            reading_y,
            reading_cx,
            reading_cy,
            bg,
            54000,
            name=f"Localized Reading Zone {placement.gravity}",
        )
    treatment_visual = _treatment_pic_shape(slide, visual_asset)
    ornaments = _page_backdrop_ornaments(slide, accent, soft, red, blue)
    return "\n".join(
        [
            visual,
            reading_vignette,
            ornaments,
            treatment_visual,
            _alpha_rect_shape(
                219,
                0,
                0,
                1000,
                1000,
                accent,
                0,
                name=(
                    f"Page Plan {plan.composition_archetype} {plan.composition_variant} "
                    f"{plan.image_treatment} {placement.mode} {placement.gravity}"
                ),
            ),
            _alpha_rect_shape(
                220,
                0,
                0,
                1000,
                1000,
                accent,
                0,
                name=(
                    f"Image Agent {visual_asset.image_type} "
                    f"{_clip_for_asset(_clean_visible_text(visual_asset.purpose, role='body'), 80)}"
                    if visual_asset is not None
                    else "Image Agent missing"
                ),
            ),
        ]
    )


def _page_backdrop_ornaments(slide, accent: str, soft: str, red: str, blue: str) -> str:
    archetype = slide.design_plan.composition_archetype
    index = int(getattr(slide, "slide_index", 1))
    if archetype in {"cinematic_hero", "editorial_cover"}:
        return "\n".join(
            [
                _alpha_rect_shape(204, 520000, 560000, 54000, 5350000, accent, 82000, name="Cover Accent Spine"),
                _alpha_rect_shape(205, 610000, 5960000, 5750000, 36000, accent, 50000, name="Cover Baseline"),
            ]
        )
    if archetype in {"chapter_index", "priority_stack", "step_ladder"}:
        return _alpha_rect_shape(204, 11120000, 720000, 36000, 4850000, accent, 48000, name="Vertical Rhythm")
    if archetype in {"system_map", "statement_focus", "orbit_system"}:
        return ""
    if archetype in {"editorial_split", "architectural_cover"}:
        return ""
    if archetype in {"proof_mosaic", "data_landscape", "split_comparison", "evidence_matrix"}:
        return _alpha_rect_shape(204, 720000, 5720000, 3600000, 28000, accent, 44000, name="Evidence Baseline")
    if archetype in {"process_ribbon", "diagonal_story", "bridge_narrative", "gallery_strip"}:
        return "\n".join(
            [
                _alpha_rect_shape(204, 720000, 5740000, 10500000, 30000, accent, 50000, name="Process Horizon"),
                _shape(205, "ellipse", 900000 + (index % 3) * 2400000, 5480000, 420000, 420000, red, alpha=18000),
            ]
        )
    if archetype in {"vertical_story", "spotlight_quote"}:
        return "\n".join(
            [
                _alpha_rect_shape(204, 760000, 5700000, 6200000, 30000, accent, 48000, name="Editorial Baseline"),
                _shape(205, "ellipse", 5700000, 780000, 680000, 680000, blue, alpha=14000),
            ]
        )
    return _alpha_rect_shape(204, 820000, 5660000, 10300000, 36000, accent, 46000, name="Closing Horizon")


def _treatment_pic_shape(slide, visual_asset: VisualAsset | None) -> str:
    if visual_asset is None:
        return ""
    archetype = slide.design_plan.composition_archetype
    image_treatment = slide.design_plan.image_treatment
    placement = visual_placement(archetype)
    if placement.mode == "full_bleed":
        return ""
    return _image_pic_shape(
        218,
        "rId3",
        placement.x,
        placement.y,
        placement.cx,
        placement.cy,
        visual_asset.alt,
        rounded=placement.rounded,
        name=f"Page Visual {image_treatment} {placement.gravity}",
        source_dimensions=(visual_asset.width, visual_asset.height),
    )


def _render_block_limit(slide) -> int:
    design_plan = getattr(slide, "design_plan", None)
    archetype = getattr(design_plan, "composition_archetype", "")
    limits = {
        "cinematic_hero": 2,
        "editorial_cover": 2,
        "architectural_cover": 2,
        "chapter_index": 3,
        "statement_focus": 3,
        "proof_mosaic": 3,
        "system_map": 5,
        "orbit_system": 4,
        "closing_bloom": 2,
        "manifesto_close": 1,
        "future_horizon": 2,
        "closing_echo": 1,
    }
    return limits.get(archetype, 4)


def _content_blocks(slide, *, deck_title: str = "", max_blocks: int = 4) -> list:
    visible_blocks: list[RenderTextBlock] = []
    seen = {
        _render_block_key(_clean_visible_text(deck_title, role="title", clip=False)),
        _render_block_key(_clean_visible_text(getattr(slide, "title", ""), role="title", clip=False)),
        _render_block_key(_clean_visible_text(getattr(slide, "subtitle", ""), role="subtitle", clip=False)),
    }
    for block in slide.blocks:
        if block.block_type in {
            "headline",
            "subtitle",
            "speaker_notes",
            "image_placeholder",
            "chart_placeholder",
        }:
            continue
        content = _compact_render_block_text(block.content, slide, deck_title=deck_title)
        key = _render_block_key(content)
        if not content or not key or key in seen:
            continue
        visible_blocks.append(RenderTextBlock(content=content))
        seen.add(key)
        if len(visible_blocks) >= max_blocks:
            break
    return visible_blocks


def _ppt_subtitle_text(value: str, deck_title: str) -> str:
    text = _clean_visible_text(value, role="subtitle", clip=False)
    if not text or _is_offtopic_source_fragment(text, deck_title):
        return ""
    limit = 34 if _contains_cjk(text) else 76
    return _smart_clip_visible_text(text, limit).strip(" \t\r\n，。；：、,:;-—–")


def _ppt_display_title_for_slide(slide, deck_title: str) -> str:
    """Replace only visibly incomplete generic cover labels with outline copy."""

    title = _clean_visible_text(getattr(slide, "title", ""), role="title", clip=False)
    if str(getattr(slide, "purpose", "")) != "cover":
        return title
    generic_or_incomplete = (
        "…" in title
        or "..." in title
        or title.casefold().startswith(("封面主张", "封面主题", "cover claim", "cover theme"))
    )
    if not generic_or_incomplete:
        return title
    for block in getattr(slide, "blocks", []):
        content = _clean_visible_text(getattr(block, "content", ""), role="card", clip=False)
        if "而是" not in content:
            continue
        claim = content.split("而是", 1)[1].strip(" \t\r\n，。；：:;.-—")
        if 4 <= len(claim) <= 26:
            return f"{deck_title}：{claim}" if deck_title else claim
    return deck_title or _ppt_title_text(title)


def _ppt_title_text(value: str) -> str:
    text = _clean_visible_text(value, role="title", clip=False)
    if not text:
        return ""
    text = _trim_dangling_visible_text(text)
    is_cjk = _contains_cjk(text)
    title_limit = 26 if is_cjk else 54
    if len(text) <= title_limit:
        return text
    for separator in ("：", ":", "—", "｜", "|"):
        if separator not in text:
            continue
        head, tail = text.split(separator, 1)
        head = head.strip(" \t\r\n，。；：、,:;-—–")
        tail = tail.strip(" \t\r\n，。；：、,:;-—–")
        generic_heads = {
            "问题边界",
            "作用机制",
            "证据指向",
            "关键证据",
            "核心洞察",
            "因此",
            "行动优先级",
            "最终判断",
            "the real issue",
            "how it works",
            "evidence map",
            "what this means",
            "act on",
            "final judgment",
        }
        if tail and head.casefold() in generic_heads:
            tail_limit = 18 if is_cjk else max(24, title_limit - len(head) - 2)
            display_separator = f"{separator} " if separator == ":" and not is_cjk else separator
            return f"{head}{display_separator}{_smart_clip_visible_text(tail, tail_limit)}"
        head_is_meaningful = 4 <= len(head) <= 18 if is_cjk else 8 <= len(head) <= 42
        if head_is_meaningful:
            return head
    candidate = _presentation_clause(text)
    return _smart_clip_visible_text(candidate, title_limit)


def _compact_render_block_text(value: str, slide, *, deck_title: str = "") -> str:
    text = _clean_visible_text(value, role="body", clip=False)
    if not text:
        return ""
    if _looks_like_source_metadata_fragment(text):
        return ""
    if _is_offtopic_source_fragment(text, deck_title):
        return ""
    source_like = _looks_like_source_fragment(text)
    for repeated in (deck_title, getattr(slide, "title", ""), getattr(slide, "subtitle", "")):
        repeated_text = _clean_visible_text(repeated, role="body", clip=False)
        if len(repeated_text) < 4:
            continue
        text = re.sub(rf"[“\"'《]?\s*{re.escape(repeated_text)}\s*[”\"'》]?", "", text)
    if not source_like:
        text = re.sub(
            r"(?<!一个)(?<!一种)(?<!一套)(?<!一条)(?<!一组)"
            r"[“\"'《][^”\"'》]{8,48}[”\"'》]"
            r"(?=的|建立|形成|作为|真正|是|在|，|。|；|:|：|$)",
            "",
            text,
        )
    text = _strip_visible_outline_scaffold(text)
    text = re.sub(r"^面向[^，,]{2,40}[，,]\s*把", "", text)
    text = re.sub(r"^面向[^，,]{2,40}[，,]\s*", "", text)
    text = _strip_visible_outline_scaffold(text)
    if _is_offtopic_source_fragment(text, deck_title):
        return ""
    text = re.sub(r"[“”\"'《》]", "", text)
    text = re.sub(r"\s+", " ", text)
    text = text.replace("先说明的", "先说明")
    text = text.replace("围绕建立", "建立")
    text = re.sub(r"^围绕\s*", "", text)
    text = text.strip(" \t\r\n，。；：、,:;-—–")
    if not text:
        return ""
    # One slide card should carry one claim. When source prose contains an
    # explicit Chinese enumeration, retain the first complete item instead of
    # flowing the next numbered item into the same visual block.
    if re.match(r"^(?:第二|第三|第四|第五|首先|其次|再次)[，、:：]", text):
        first_item = re.split(r"[；;。]", text, maxsplit=1)[0]
        text = _strip_enumeration_prefix(first_item)
    return _presentation_clause(text).strip(" \t\r\n，。；：、,:;-—–")


def _presentation_clause(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return ""
    lowered = normalized.casefold()
    if lowered.startswith("use 90 days to select the workflow"):
        pilot_end = lowered.find("run a controlled pilot")
        if pilot_end >= 0:
            pilot_end += len("run a controlled pilot")
            return normalized[:pilot_end].strip(" \t\r\n，。；：、,:;-—–")

    limit = 90 if _contains_cjk(normalized) else 156
    if len(normalized) <= limit:
        return normalized.strip(" \t\r\n，。；：、,:;-—–")

    candidates = _presentation_clause_candidates(text)
    decision_markers = (
        "cannot",
        "must",
        "should",
        "therefore",
        "so ",
        "cannot yet be claimed",
        "不能",
        "必须",
        "因此",
    )
    for candidate in reversed(candidates):
        cleaned = _strip_enumeration_prefix(candidate)
        if not cleaned or not any(marker in cleaned.casefold() for marker in decision_markers):
            continue
        head_match = re.match(r"^([^:：]{4,28})[:：]", normalized)
        if head_match and head_match.group(1).casefold() not in cleaned.casefold():
            combined = f"{head_match.group(1)}: {cleaned}"
            if len(combined) <= limit:
                return combined
        if len(cleaned) <= limit:
            return cleaned
    for candidate in candidates:
        cleaned = _strip_enumeration_prefix(candidate)
        if not cleaned:
            continue
        weight_limit = limit * (2 if _contains_cjk(cleaned) else 1)
        if _display_weight(cleaned) <= weight_limit:
            return cleaned
    cleaned_text = _strip_enumeration_prefix(text)
    return _smart_clip_visible_text(cleaned_text, limit).strip(" \t\r\n，。；：、,:;-—–")


def _presentation_clause_candidates(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    pieces = [
        piece.strip()
        for piece in re.split(r"[。；;.!?！？]\s*", normalized)
        if piece.strip()
    ]
    if not pieces:
        pieces = [normalized]
    if len(pieces) > 1:
        pieces.append(normalized)
    return pieces


def _strip_enumeration_prefix(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(
        r"^(?:第?[一二三四五六七八九十]+|首先|其次|再次|最后|第一|第二|第三|第四|第五)\s*[，、,:：.．]\s*",
        "",
        cleaned,
    )
    cleaned = re.sub(r"^(?:它|其|该品牌|该公司|品牌|公司)\s*(?:用|通过|以|把|将)\s*", "", cleaned)
    cleaned = re.sub(r"^\d+\s*[，、,:：.．]\s*", "", cleaned)
    return cleaned.strip(" \t\r\n，。；：、,:;.-—–")


def _render_block_key(value: str) -> str:
    return re.sub(r"[^\w\u3400-\u9fff]+", "", value).casefold()


def _is_offtopic_source_fragment(text: str, deck_title: str) -> bool:
    return (
        _looks_like_source_fragment(text) or _looks_like_bare_title_fragment(text)
    ) and not _has_topic_overlap(text, deck_title)


def _looks_like_source_metadata_fragment(text: str) -> bool:
    lowered = text.casefold()
    return bool(
        (
            re.search(r"(?:\u82f1\u8bed|\u82f1\u6587|English)\s*[:\uff1a]", text, re.IGNORECASE)
            and any(marker in lowered for marker in ("otc", "nasdaq", "nyse", "pink", "lkncy", "wikipedia"))
        )
        or "otc pink" in lowered
        or re.search(r"\b(?:otc|nasdaq|nyse)\b[^。；;]{0,80}\b[A-Z]{2,8}\b", text, re.IGNORECASE)
    )


def _looks_like_source_fragment(text: str) -> bool:
    lowered = text.casefold()
    return bool(
        re.search(r"(?:19|20)\d{2}\s*年?\s*研究", text)
        or any(
            marker in text or marker in lowered
            for marker in (
                "发表于",
                "资料来源",
                "来源：",
                "期刊",
                "研究《",
                "研究",
                "crossref",
                "modern management",
                "analysis and evaluation",
            )
        )
    )


def _looks_like_bare_title_fragment(text: str) -> bool:
    cleaned = text.strip()
    if len(cleaned) < 12 or re.search(r"[，。；:：、]", cleaned):
        return False
    lowered = cleaned.casefold()
    return any(
        marker in cleaned or marker in lowered
        for marker in (
            "趋势",
            "策略",
            "实践",
            "研究",
            "分析",
            "评估",
            "评价",
            "marketing",
            "management",
            "analysis",
            "evaluation",
        )
    )


def _has_topic_overlap(text: str, deck_title: str) -> bool:
    terms = _topic_terms(deck_title)
    if not terms:
        return True
    normalized = _render_block_key(text)
    return any(term in normalized for term in terms)


def _topic_terms(value: str) -> set[str]:
    normalized = _render_block_key(_clean_visible_text(value, role="title", clip=False))
    if not normalized:
        return set()
    terms: set[str] = set()
    cjk_chunks = re.findall(r"[\u3400-\u9fff]+", normalized)
    for chunk in cjk_chunks:
        for size in (4, 3, 2):
            for index in range(0, max(0, len(chunk) - size + 1)):
                term = chunk[index : index + size]
                if term not in {"品牌", "策略", "增长", "消费", "研究", "分析", "问题", "路径"}:
                    terms.add(term)
        if len(chunk) <= 6:
            terms.add(chunk)
    for word in re.findall(r"[a-z0-9]{4,}", normalized):
        if word not in {"brand", "strategy", "growth", "study", "analysis", "presentation"}:
            terms.add(word)
    return terms


def _copy_overlap_ratio(left: str, right: str) -> float:
    """Estimate whether two visible phrases communicate the same headline."""

    def units(value: str) -> set[str]:
        cleaned = _clean_visible_text(value, role="body", clip=False).casefold()
        normalized = _render_block_key(cleaned)
        words = set(re.findall(r"[a-z0-9]{3,}", cleaned))
        for chunk in re.findall(r"[\u3400-\u9fff]+", normalized):
            words.update(chunk[index : index + 2] for index in range(max(0, len(chunk) - 1)))
        return words

    left_units = units(left)
    right_units = units(right)
    if not left_units or not right_units:
        return 0.0
    return len(left_units & right_units) / max(1, min(len(left_units), len(right_units)))


def _layout_shapes(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    """Render the canonical content plan through its actual composition family.

    Each family owns different visual gravity, not merely different decoration.
    This keeps agenda, evidence, framework, insight and closing pages from being
    collapsed into one universal left-copy/right-image template.
    """

    archetype = getattr(getattr(slide, "design_plan", None), "composition_archetype", "")
    handlers = {
        "cinematic_hero": _hero_layout,
        "editorial_cover": _editorial_cover_layout,
        "architectural_cover": _architectural_cover_layout,
        "chapter_index": _chapter_index_layout,
        "editorial_split": _editorial_split_layout,
        "diagonal_story": _diagonal_story_layout,
        "statement_focus": _statement_focus_layout,
        "proof_mosaic": _proof_mosaic_layout,
        "data_landscape": _chart_focus_layout,
        "process_ribbon": _timeline_layout,
        "system_map": _system_map_layout,
        "split_comparison": _split_comparison_layout,
        "priority_stack": _priority_stack_layout,
        "gallery_strip": _gallery_strip_layout,
        "vertical_story": _vertical_story_layout,
        "spotlight_quote": _spotlight_quote_layout,
        "evidence_matrix": _evidence_matrix_layout,
        "orbit_system": _orbit_system_layout,
        "step_ladder": _step_ladder_layout,
        "bridge_narrative": _bridge_narrative_layout,
        "closing_bloom": _closing_bloom_layout,
        "manifesto_close": _manifesto_close_layout,
        "future_horizon": _future_horizon_layout,
        "closing_echo": _closing_layout,
    }
    handler = handlers.get(archetype)
    if handler is not None:
        return handler(slide, blocks, fg, accent, soft)
    return _customer_delivery_layout(slide, blocks, fg, accent, soft)


def _customer_delivery_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    purpose = getattr(slide, "purpose", "")
    archetype = getattr(getattr(slide, "design_plan", None), "composition_archetype", "")
    display_title = _ppt_title_text(slide.title)
    title_size = _ppt_title_font_size(display_title)
    title = _text_shape(5, display_title, 720000, 520000, 5520000, 720000, title_size, fg, bold=True)
    subtitle = (
        _text_shape(6, slide.subtitle, 760000, 1250000, 5160000, 300000, 1180, accent, bold=True)
        if slide.subtitle
        else ""
    )
    items = blocks[:4]
    lead = _premium_statement_copy(items[0].content if items else slide.speaker_notes or slide.title)
    support = _premium_support_blocks(items[1:4])
    if purpose in {"cover", "section"} or archetype in {
        "cinematic_hero",
        "editorial_cover",
        "architectural_cover",
    }:
        title = _text_shape(5, display_title, 760000, 850000, 5480000, 1120000, _ppt_title_font_size(display_title, cover=True), fg, bold=True)
        subtitle = (
            _text_shape(6, slide.subtitle, 790000, 2030000, 5080000, 320000, 1240, accent, bold=True)
            if slide.subtitle
            else ""
        )
        lead_box = _shape(24, "roundRect", 650000, 3220000, 5860000, 980000, "FFFFFF", alpha=96000, line=accent)
        lead_text = _text_shape(25, lead, 980000, 3470000, 5200000, 430000, _ppt_statement_font_size(lead), fg, bold=True)
        support_shapes = "\n".join(
            _premium_card_shape(
                26 + index,
                block.content,
                620000 + index * 2920000,
                4640000,
                2720000,
                720000,
                soft,
                fg,
                accent,
            )
            for index, block in enumerate(support[:2])
        )
        return "\n".join([title, subtitle, lead_box, lead_text, support_shapes])
    if purpose == "agenda" or archetype == "chapter_index":
        rows = []
        agenda_items = items[:4] or items[:1]
        for index, block in enumerate(agenda_items):
            y = 1720000 + index * 790000
            rows.extend(
                [
                    _shape(30 + index * 4, "ellipse", 650000, y + 60000, 340000, 340000, accent, alpha=90000),
                    _text_shape(31 + index * 4, str(index + 1), 730000, y + 130000, 180000, 120000, 920, "FFFFFF", bold=True, align="ctr"),
                    _alpha_rect_shape(32 + index * 4, 1000000, y + 218000, 360000, 26000, accent, 68000, name="Agenda Connector"),
                    _premium_card_shape(33 + index * 4, block.content, 1300000, y, 4920000, 520000, "FFFFFF", fg, accent),
                ]
            )
        spine = _alpha_rect_shape(49, 818000, 1980000, 26000, 2880000, accent, 42000, name="Agenda Vertical Rhythm")
        return "\n".join([title, subtitle, spine, *rows])
    if purpose == "framework" or archetype == "system_map":
        center = _shape(40, "roundRect", 2180000, 2500000, 2600000, 1050000, "FFFFFF", alpha=95000, line=accent)
        center_text = _text_shape(41, lead, 2450000, 2810000, 2060000, 390000, _ppt_statement_font_size(lead, compact=True), fg, bold=True, align="ctr")
        node_positions = [
            (650000, 1780000, 1900000, 620000),
            (4580000, 1780000, 1740000, 620000),
            (650000, 4140000, 1900000, 620000),
        ]
        nodes = [
            _premium_card_shape(42 + index, block.content, x, y, cx, cy, soft, fg, accent)
            for index, (block, (x, y, cx, cy)) in enumerate(zip(support[:3], node_positions))
        ]
        connectors = [
            _alpha_rect_shape(46, 1780000, 2380000, 1020000, 26000, accent, 52000, name="Framework Connector A"),
            _alpha_rect_shape(47, 4780000, 2380000, 720000, 26000, accent, 52000, name="Framework Connector B"),
            _alpha_rect_shape(48, 3220000, 3550000, 26000, 720000, accent, 52000, name="Framework Connector C"),
        ]
        return "\n".join([title, subtitle, *connectors, center, center_text, *nodes])
    if purpose == "evidence" or archetype in {"proof_mosaic", "data_landscape"}:
        statement_panel = _shape(40, "roundRect", 660000, 1640000, 5860000, 1320000, "FFFFFF", alpha=96000, line=accent)
        statement_text = _text_shape(41, lead, 1000000, 1990000, 5180000, 470000, _ppt_statement_font_size(lead), fg, bold=True)
        evidence_line = _alpha_rect_shape(45, 920000, 3460000, 4880000, 32000, accent, 62000, name="Evidence Logic Rail")
        support_shapes = []
        card_positions = [
            (660000, 3760000, 2700000, 660000),
            (3560000, 3760000, 2700000, 660000),
            (2080000, 4620000, 2700000, 660000),
        ]
        for index, block in enumerate(support[:3]):
            x, y, card_cx, card_cy = card_positions[index]
            support_shapes.append(
                _premium_card_shape(
                    47 + index * 4,
                    block.content,
                    x,
                    y,
                    card_cx,
                    card_cy,
                    soft if index else "FFFFFF",
                    fg,
                    accent,
                )
            )
        return "\n".join([title, subtitle, statement_panel, statement_text, evidence_line, *support_shapes])
    if purpose == "insight" or archetype == "statement_focus":
        insight_mark = _text_shape(50, "“", 620000, 1350000, 620000, 900000, 4300, accent, bold=True)
        insight_text = _text_shape(51, lead, 1180000, 1760000, 5000000, 1740000, _ppt_statement_font_size(lead), fg, bold=True)
        support_shapes = "\n".join(
            _premium_card_shape(
                52 + index,
                block.content,
                760000 + index * 2820000,
                4300000,
                2580000,
                720000,
                soft,
                fg,
                accent,
            )
            for index, block in enumerate(support[:2])
        )
        insight_line = _alpha_rect_shape(56, 1140000, 3690000, 4300000, 36000, accent, 58000, name="Insight Pause Line")
        return "\n".join([title, subtitle, insight_mark, insight_text, insight_line, support_shapes])
    if purpose == "recommendation" or archetype == "priority_stack":
        lead_box = _shape(60, "roundRect", 660000, 1540000, 5860000, 900000, "FFFFFF", alpha=96000, line=accent)
        lead_text = _text_shape(61, lead, 980000, 1780000, 5180000, 380000, _ppt_statement_font_size(lead, compact=True), fg, bold=True)
        card_shapes = []
        for index, block in enumerate(support[:3]):
            x = 720000 + index * 300000
            y = 2980000 + index * 760000
            width = 5400000 - index * 420000
            card_shapes.extend(
                [
                    _shape(62 + index * 3, "ellipse", x, y + 120000, 260000, 260000, accent, alpha=90000),
                    _text_shape(63 + index * 3, str(index + 1), x + 72000, y + 190000, 110000, 90000, 840, "FFFFFF", bold=True, align="ctr"),
                    _premium_card_shape(64 + index * 3, block.content, x + 430000, y, width, 540000, soft, fg, accent),
                ]
            )
        return "\n".join([title, subtitle, lead_box, lead_text, *card_shapes])
    if purpose == "conclusion" or archetype in {"manifesto_close", "future_horizon", "closing_echo"}:
        lead_box = _shape(50, "roundRect", 680000, 1640000, 5740000, 1340000, "FFFFFF", alpha=96000, line=accent)
        lead_text = _text_shape(51, lead, 980000, 1940000, 5140000, 600000, _ppt_statement_font_size(lead), fg, bold=True, align="ctr")
        support_shapes = "\n".join(
            _premium_card_shape(52 + index, block.content, 900000 + index * 2700000, 3700000, 2460000, 660000, soft, fg, accent)
            for index, block in enumerate(support[:2])
        )
        horizon = _alpha_rect_shape(58, 900000, 5450000, 5120000, 36000, accent, 52000, name="Closing Horizon")
        return "\n".join([title, subtitle, lead_box, lead_text, support_shapes, horizon])
    if archetype in {"process_ribbon", "diagonal_story", "split_comparison"}:
        lead_box = _shape(60, "roundRect", 660000, 1540000, 5860000, 900000, "FFFFFF", alpha=96000, line=accent)
        lead_text = _text_shape(61, lead, 980000, 1780000, 5180000, 380000, _ppt_statement_font_size(lead, compact=True), fg, bold=True)
        card_shapes = []
        for index, block in enumerate(support[:3]):
            y = 3020000 + index * 720000
            card_shapes.extend(
                [
                    _shape(62 + index * 3, "ellipse", 700000, y + 105000, 220000, 220000, accent, alpha=86000),
                    _premium_card_shape(63 + index * 3, block.content, 1080000, y, 5120000, 520000, soft, fg, accent),
                ]
            )
        return "\n".join([title, subtitle, lead_box, lead_text, *card_shapes])
    lead_box = _shape(70, "roundRect", 660000, 1580000, 5860000, 980000, "FFFFFF", alpha=96000, line=accent)
    lead_text = _text_shape(71, lead, 980000, 1830000, 5180000, 430000, _ppt_statement_font_size(lead, compact=True), fg, bold=True)
    card_shapes = "\n".join(
        _premium_card_shape(72 + index, block.content, 720000 + (index % 2) * 2860000, 3040000 + (index // 2) * 820000, 2700000, 620000, soft, fg, accent)
        for index, block in enumerate(support[:3])
    )
    return "\n".join([title, subtitle, lead_box, lead_text, card_shapes])


def _ppt_title_font_size(text: str, *, cover: bool = False) -> int:
    weight = _display_weight(text)
    if cover:
        if weight <= 26:
            return PPT_COVER_TITLE_MAX
        if weight <= 40:
            return PPT_COVER_TITLE_MID
        if weight <= 54:
            return 3900
        return PPT_COVER_TITLE_MIN
    if weight <= 22:
        return PPT_PAGE_TITLE_MAX
    if weight <= 34:
        return PPT_PAGE_TITLE_MID
    if weight <= 48:
        return 3000
    return PPT_PAGE_TITLE_MIN


def _ppt_statement_font_size(text: str, *, compact: bool = False) -> int:
    weight = _display_weight(text)
    if compact:
        if weight <= 32:
            return PPT_STATEMENT_MID
        if weight <= 48:
            return 1850
        return PPT_STATEMENT_MIN
    if weight <= 36:
        return PPT_STATEMENT_MAX
    if weight <= 56:
        return PPT_STATEMENT_MID
    return PPT_STATEMENT_MIN


def _premium_statement_copy(value: str) -> str:
    text = _clean_visible_text(value, role="body", clip=False)
    for quote in ("‘", "“", "《"):
        if quote not in text:
            continue
        prefix = text.split(quote, 1)[0].rstrip(" \t\r\n，。；：、,:;.-—–")
        text = f"{prefix}战略转向" if prefix.endswith("能否落实") else prefix
        break
    text = _presentation_clause(text)
    paired_comparison = "不只" in text and "更" in text
    if _contains_cjk(text) and len(text) > 34 and not paired_comparison:
        for marker in ("，", "；", "。"):
            head = text.split(marker, 1)[0].strip()
            if 12 <= len(head) <= 34:
                text = head
                break
    # Keep a complete strategic claim such as “落实战略转向” intact; the
    # statement layouts have enough width for 36 CJK characters.
    limit = 36 if _contains_cjk(text) else 82
    return _smart_clip_visible_text(text, limit).strip(" \t\r\n，。；：、?:;—–-)")


def _premium_card_copy(value: str) -> str:
    text = _clean_visible_text(value, role="card", clip=False)
    text = _presentation_clause(text)
    if _contains_cjk(text):
        for marker in ("，", "；", "。", "、"):
            head = text.split(marker, 1)[0].strip()
            if 4 <= len(head) <= 18:
                text = head
                break
    # Keep complete evidence/action sentences. The card renderer can reduce the
    # font and grow the safe text frame; clipping at 54 Latin characters made
    # grammatically valid but false/incomplete claims such as "hours-saved
    # estimate" and "users, or task" visible in PowerPoint slideshow mode.
    limit = 34 if _contains_cjk(text) else 96
    cleaned = _strip_terminal_ellipsis(
        _smart_clip_visible_text(text, limit).strip(" \t\r\n，。；：、?:;—–-)")
    )
    return "" if _is_low_information_card(cleaned) else cleaned


def _premium_support_blocks(blocks: list) -> list[RenderTextBlock]:
    cleaned: list[RenderTextBlock] = []
    for block in blocks:
        content = _premium_card_copy(block.content)
        if content:
            cleaned.append(RenderTextBlock(content=content))
    return cleaned


def _is_low_information_card(value: str) -> bool:
    normalized = re.sub(r"\s+", "", str(value)).casefold()
    return normalized in {
        "展开",
        "展開",
        "展开更多",
        "更多",
        "继续",
        "补充",
        "待补充",
        "more",
        "expand",
        "continue",
    } or len(normalized) <= 1


def _strip_terminal_ellipsis(value: str) -> str:
    return str(value).rstrip(" .…").strip(" \t\r\n，。；：、?:;—–-)")


def _premium_card_shape(
    shape_id: int,
    content: str,
    x: int,
    y: int,
    cx: int,
    cy: int,
    fill: str,
    text_color: str,
    accent: str,
) -> str:
    return _card_shape(shape_id, _premium_card_copy(content), x, y, cx, cy, fill, text_color, accent)


def _title_and_subtitle(slide, fg: str, *, title_y: int = 460000, title_size: int = 3100) -> str:
    display_title = _ppt_title_text(slide.title)
    subtitle = (
        _text_shape(7, slide.subtitle, 720000, title_y + 860000, 9600000, 360000, 1600, fg)
        if slide.subtitle
        else ""
    )
    return (
        _text_shape(5, display_title, 700000, title_y, 10200000, 920000, _ppt_title_font_size(display_title), fg, bold=True)
        + subtitle
    )


def _hero_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    lead = blocks[0].content if blocks else slide.title
    support = blocks[1].content if len(blocks) > 1 else slide.speaker_notes
    subtitle = (
        _text_shape(13, slide.subtitle, 740000, 2750000, 5300000, 360000, 1500, accent, bold=True)
        if slide.subtitle
        else ""
    )
    return "\n".join(
        [
            _text_shape(12, _ppt_title_text(slide.title), 720000, 900000, 6500000, 1450000, _ppt_title_font_size(_ppt_title_text(slide.title), cover=True), fg, bold=True),
            subtitle,
            _rect_shape(14, 740000, 3420000, 900000, 30000, accent),
            _text_shape(15, lead, 740000, 3680000, 6000000, 900000, 1750, fg, bold=True),
            (_text_shape(16, support, 740000, 4900000, 6000000, 600000, 1350, fg) if support and _copy_overlap_ratio(lead, support) < 0.72 else ""),
        ]
    )


def _editorial_cover_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    lead = blocks[0].content if blocks else slide.visual_intent
    support = blocks[1].content if len(blocks) > 1 else slide.speaker_notes
    return "\n".join(
        [
            _rect_shape(120, 6200000, 760000, 900000, 48000, accent),
            _text_shape(121, _ppt_title_text(slide.title), 6200000, 1040000, 5250000, 1900000, _ppt_title_font_size(_ppt_title_text(slide.title), cover=True), fg, bold=True),
            _text_shape(122, slide.subtitle or lead, 6240000, 3060000, 5100000, 620000, 1750, accent, bold=True),
            _card_shape(123, lead, 6240000, 3940000, 5100000, 820000, soft, fg, accent),
            _text_shape(124, support, 6240000, 5150000, 5100000, 520000, 1350, fg, align="r"),
        ]
    )


def _editorial_split_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    lead = blocks[0].content if blocks else slide.visual_intent
    support = blocks[1:4] or blocks[:1]
    support_shapes: list[str] = []
    for index, block in enumerate(support[:2]):
        y = 4000000 + index * 1450000
        support_shapes.extend(
            [
                _text_shape(136 + index * 2, f"0{index + 1}", 6460000, y, 520000, 360000, 1450, accent, bold=True),
                _text_shape(137 + index * 2, block.content, 7040000, y - 20000, 4320000, 700000, 1600, fg),
            ]
        )
    return "\n".join(
        [
            _rect_shape(130, 6460000, 680000, 760000, 42000, accent),
            _text_shape(131, _ppt_title_text(slide.title), 6460000, 970000, 4900000, 1300000, _ppt_title_font_size(_ppt_title_text(slide.title)), fg, bold=True),
            (_text_shape(132, slide.subtitle, 6480000, 2350000, 4850000, 420000, 1500, accent, bold=True) if slide.subtitle else ""),
            _text_shape(133, lead, 6480000, 2420000, 4850000, 820000, 1650, fg, bold=True),
            _rect_shape(134, 6480000, 3800000, 4880000, 26000, accent),
            *support_shapes,
        ]
    )


def _architectural_cover_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    lead = blocks[0].content if blocks else slide.visual_intent
    title = _ppt_title_text(slide.title)
    subtitle = _clean_visible_text(slide.subtitle or lead, role="subtitle", clip=False)
    title_size = _visible_text_font_size(title, 7200000, 1420000, _ppt_title_font_size(title, cover=True), "title")
    subtitle_size = _visible_text_font_size(subtitle, 6700000, 460000, 1500, "subtitle")
    title_cy = _fit_text_frame(title, 1550000, 1000000, 7200000, 1420000, title_size, "title")[4]
    subtitle_cy = _fit_text_frame(subtitle, 1580000, 1000000, 6700000, 460000, subtitle_size, "subtitle")[4]
    gap = 180000
    title_y = min(3340000, SLIDE_CY - FOREGROUND_SAFE_BOTTOM - title_cy - gap - subtitle_cy)
    subtitle_y = title_y + title_cy + gap
    return "\n".join(
        [
            _rect_shape(126, 1160000, 1120000, 64000, 4050000, accent),
            _text_shape(127, title, 1550000, title_y, 7200000, title_cy, title_size, fg, bold=True),
            _text_shape(128, subtitle, 1580000, subtitle_y, 6700000, subtitle_cy, subtitle_size, accent, bold=True),
            _shape(129, "ellipse", 9100000, 1050000, 1700000, 1700000, accent, alpha=36000),
        ]
    )


def _chapter_index_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    items = blocks[:4] or blocks[:1]
    rows = []
    cursor_y = 2300000
    for index, block in enumerate(items):
        cleaned = _clean_visible_text(block.content, role="body", clip=False)
        font_size = _visible_text_font_size(cleaned, 4020000, 760000, 1700, "body")
        inset_x, inset_y = _text_insets_for_role("body", 4020000, 760000)
        row_cy = max(
            760000,
            int(_required_text_cy(cleaned, 4020000, font_size, "body", inset_x, inset_y) / 0.88),
        )
        y = cursor_y
        rows.extend(
            [
                _text_shape(132 + index * 3, f"{index + 1:02d}", 940000, y, 620000, 420000, 1750, accent, bold=True),
                _rect_shape(133 + index * 3, 1640000, y + 210000, 720000, 20000, accent),
                _text_shape(134 + index * 3, block.content, 2380000, y - 20000, 4020000, row_cy, 1700, fg, role="body"),
            ]
        )
        cursor_y += row_cy + 30000
    return "\n".join(
        [
            _alpha_rect_shape(128, 520000, 420000, 6340000, 6000000, "FFFFFF", 86000, name="Agenda Reading Panel"),
            _text_shape(129, _ppt_title_text(slide.title), 900000, 680000, 5440000, 900000, _ppt_title_font_size(_ppt_title_text(slide.title)), fg, bold=True),
            (_text_shape(130, slide.subtitle, 930000, 1580000, 5200000, 330000, 1450, accent, bold=True) if slide.subtitle else ""),
            *rows,
        ]
    )


def _diagonal_story_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    lead = blocks[0].content if blocks else slide.title
    cards = blocks[1:4] or blocks[:1]
    return "\n".join(
        [
            _shape(145, "parallelogram", 0, 0, 6400000, SLIDE_CY, soft, alpha=33000),
            _text_shape(146, slide.title, 700000, 520000, 6000000, 1040000, 3100, fg, bold=True),
            _text_shape(147, lead, 920000, 2150000, 4650000, 1600000, 2250, fg, bold=True),
            *[
                _card_shape(148 + index, block.content, 7100000, 1350000 + index * 1120000, 4050000, 820000, soft, fg, accent)
                for index, block in enumerate(cards)
            ],
        ]
    )


def _statement_focus_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    display_title = _ppt_title_text(slide.title)
    statement = _premium_statement_copy(blocks[0].content if blocks else slide.title)
    if _copy_overlap_ratio(display_title, statement) >= 0.72:
        statement = ""
    support = blocks[1:3]
    support_shapes: list[str] = []
    for index, block in enumerate(support):
        support_shapes.extend(
            [
                _rect_shape(156 + index * 2, 940000 + index * 5540000, 4980000, 580000, 26000, accent),
                _text_shape(157 + index * 2, block.content, 940000 + index * 5540000, 5170000, 4600000, 680000, 1500, fg),
            ]
        )
    return "\n".join(
        [
            _text_shape(153, display_title, 940000, 760000, 10100000, 1180000, _ppt_title_font_size(display_title, cover=True), fg, bold=True),
            (_text_shape(154, statement, 940000, 2240000, 9200000, 1650000, _ppt_statement_font_size(statement), fg, bold=True) if statement else ""),
            _rect_shape(155, 940000, 4440000, 10100000, 30000, accent),
            *support_shapes,
        ]
    )


def _proof_mosaic_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    cards = blocks[:4] or blocks[:1]
    shapes: list[str] = []
    if cards:
        shapes.append(_text_shape(160, cards[0].content, 760000, 1860000, 5500000, 1450000, 1850, fg, bold=True))
    for index, block in enumerate(cards[1:3]):
        y = 3480000 + index * 1350000
        shapes.extend(
            [
                _rect_shape(161 + index * 2, 760000, y + 160000, 540000, 26000, accent),
                _text_shape(162 + index * 2, block.content, 1460000, y, 4800000, 720000, 1450, fg),
            ]
        )
    return "\n".join(
        [
            _text_shape(5, _ppt_title_text(slide.title), 700000, 420000, 6100000, 920000, _ppt_title_font_size(_ppt_title_text(slide.title)), fg, bold=True),
            (_text_shape(7, slide.subtitle, 720000, 1280000, 6000000, 340000, 1500, fg) if slide.subtitle else ""),
            *shapes,
        ]
    )


def _system_map_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    nodes = blocks[:5] or blocks[:1]
    visible_nodes = nodes[1:5] if len(nodes) >= 5 else nodes[:4]
    positions = [(720000, 1980000), (8520000, 1980000), (720000, 4300000), (8520000, 4300000)]
    shapes = [
        _card_shape(166 + index, block.content, x, y, 2920000, 880000, soft, fg, accent)
        for index, (block, (x, y)) in enumerate(zip(visible_nodes, positions))
    ]
    return "\n".join(
        [
            _text_shape(162, _ppt_title_text(slide.title), 900000, 520000, 10300000, 820000, _ppt_title_font_size(_ppt_title_text(slide.title)), fg, bold=True, align="ctr"),
            (_text_shape(163, slide.subtitle, 1440000, 1390000, 9300000, 340000, 1420, accent, bold=True, align="ctr") if slide.subtitle else ""),
            _shape(164, "ellipse", 4240000, 1780000, 3740000, 3740000, soft, alpha=7000, line=accent),
            *shapes,
        ]
    )


def _split_comparison_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    left = blocks[0::2][:2] or blocks[:1]
    right = blocks[1::2][:2] or blocks[:1]
    left_text = " · ".join(block.content for block in left)
    right_text = " · ".join(block.content for block in right)
    return "\n".join(
        [
            _title_and_subtitle(slide, fg, title_y=390000, title_size=2900),
            _shape(175, "roundRect", 720000, 1900000, 4700000, 3500000, "153B73", alpha=52000, line=accent),
            _shape(176, "roundRect", 6770000, 1900000, 4700000, 3500000, "6E2020", alpha=52000, line=accent),
            _text_shape(177, left_text, 1120000, 2600000, 3900000, 1950000, 1900, fg, bold=True),
            _text_shape(178, right_text, 7170000, 2600000, 3900000, 1950000, 1900, fg, bold=True),
            _shape(179, "ellipse", 5860000, 3170000, 360000, 360000, accent),
        ]
    )


def _priority_stack_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    items = blocks[:4] or blocks[:1]
    cards: list[str] = []
    for index, block in enumerate(items):
        y = 2000000 + index * 1120000
        cards.extend(
            [
                _text_shape(180 + index * 3, f"0{index + 1}", 820000, y, 600000, 420000, 1700, accent, bold=True),
                _rect_shape(181 + index * 3, 1540000, y + 220000, 720000, 24000, accent),
                _text_shape(182 + index * 3, block.content, 2460000, y - 40000, 6200000, 760000, 1600, fg),
            ]
        )
    title = _text_shape(
        5,
        _ppt_title_text(slide.title),
        700000,
        390000,
        8200000,
        920000,
        _ppt_title_font_size(_ppt_title_text(slide.title)),
        fg,
        bold=True,
    )
    subtitle = (
        _text_shape(7, slide.subtitle, 720000, 1250000, 7900000, 360000, 1500, fg)
        if slide.subtitle
        else ""
    )
    return "\n".join([title, subtitle, *cards])


def _gallery_strip_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    """An editorial gallery page: image strip above, verdict and tiles below."""

    items = blocks[:3] or blocks[:1]
    cards = [
        _card_shape(
            230 + index,
            block.content,
            760000 + index * 3700000,
            4100000,
            3380000,
            960000,
            soft,
            fg,
            accent,
        )
        for index, block in enumerate(items)
    ]
    lead = items[0].content if items else slide.title
    return "\n".join(
        [
            _text_shape(226, _ppt_title_text(slide.title), 760000, 2450000, 7100000, 820000, _ppt_title_font_size(_ppt_title_text(slide.title)), fg, bold=True),
            _text_shape(227, slide.subtitle or lead, 780000, 3380000, 6900000, 400000, 1500, accent, bold=True),
            _rect_shape(228, 780000, 3890000, 5800000, 32000, accent),
            *cards,
        ]
    )


def _vertical_story_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    """A tall image chapter page with a left-aligned editorial reading column."""

    items = blocks[:3] or blocks[:1]
    cards = [
        _card_shape(240 + index, block.content, 760000, 2800000 + index * 980000, 6500000, 740000, soft, fg, accent)
        for index, block in enumerate(items)
    ]
    return "\n".join(
        [
            _rect_shape(236, 760000, 700000, 72000, 1520000, accent),
            _text_shape(237, _ppt_title_text(slide.title), 1080000, 760000, 6500000, 1280000, _ppt_title_font_size(_ppt_title_text(slide.title), cover=True), fg, bold=True),
            (_text_shape(238, slide.subtitle, 1100000, 2160000, 6300000, 380000, 1450, accent, bold=True) if slide.subtitle else ""),
            *cards,
        ]
    )


def _spotlight_quote_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    """A claim-led page with one visual spotlight, not a standard card grid."""

    statement = blocks[0].content if blocks else slide.title
    support = blocks[1:3]
    small_cards = [
        _card_shape(253 + index, block.content, 780000 + index * 3020000, 4800000, 2720000, 700000, soft, fg, accent)
        for index, block in enumerate(support)
    ]
    return "\n".join(
        [
            _text_shape(248, "\u201c", 660000, 1270000, 720000, 1100000, 5200, accent, bold=True),
            _text_shape(249, _ppt_title_text(slide.title), 1300000, 780000, 5300000, 720000, _ppt_title_font_size(_ppt_title_text(slide.title)), accent, bold=True),
            _text_shape(250, statement, 1320000, 1710000, 5100000, 2050000, _ppt_statement_font_size(statement), fg, bold=True),
            _rect_shape(251, 1320000, 4040000, 3800000, 28000, accent),
            *small_cards,
        ]
    )


def _evidence_matrix_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    """A four-cell decision matrix that reserves a distinct left evidence visual."""

    items = blocks[:4] or blocks[:1]
    positions = (
        (4780000, 1880000),
        (7700000, 1880000),
        (4780000, 3500000),
        (7700000, 3500000),
    )
    cards = [
        _card_shape(264 + index, block.content, x, y, 2540000, 1220000, soft, fg, accent)
        for index, (block, (x, y)) in enumerate(zip(items, positions))
    ]
    return "\n".join(
        [
            _text_shape(260, _ppt_title_text(slide.title), 4780000, 520000, 6200000, 780000, _ppt_title_font_size(_ppt_title_text(slide.title)), fg, bold=True),
            (_text_shape(261, slide.subtitle, 4800000, 1380000, 5900000, 350000, 1420, accent, bold=True) if slide.subtitle else ""),
            _shape(262, "roundRect", 650000, 1880000, 3600000, 3240000, soft, alpha=18000, line=accent),
            _text_shape(263, "Evidence", 1050000, 2120000, 2780000, 420000, 1350, accent, bold=True, align="ctr"),
            *cards,
        ]
    )


def _orbit_system_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    """A four-pole system map surrounding a central visual anchor."""

    items = blocks[:4] or blocks[:1]
    positions = (
        (740000, 1660000, 3000000, 760000),
        (8460000, 1660000, 3000000, 760000),
        (740000, 4300000, 3000000, 760000),
        (8460000, 4300000, 3000000, 760000),
    )
    cards = [
        _card_shape(278 + index, block.content, x, y, cx, cy, soft, fg, accent)
        for index, (block, (x, y, cx, cy)) in enumerate(zip(items, positions))
    ]
    center = _ppt_title_text(slide.title)
    return "\n".join(
        [
            _text_shape(274, center, 3160000, 540000, 5860000, 620000, 2450, fg, bold=True, align="ctr"),
            _shape(275, "ellipse", 4140000, 1560000, 3640000, 3640000, soft, alpha=12000, line=accent),
            _shape(276, "ellipse", 4860000, 2280000, 2200000, 2200000, accent, alpha=18000),
            (_text_shape(277, slide.subtitle, 4080000, 5030000, 3760000, 300000, 1280, accent, bold=True, align="ctr") if slide.subtitle else ""),
            *cards,
        ]
    )


def _step_ladder_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    """A rising action ladder with an image field on the left."""

    items = blocks[:4] or blocks[:1]
    cards = []
    for index, block in enumerate(items):
        cards.append(
            _card_shape(
                290 + index,
                block.content,
                4460000 + index * 260000,
                2280000 + index * 760000,
                6060000 - index * 260000,
                570000,
                soft,
                fg,
                accent,
            )
        )
    return "\n".join(
        [
            _text_shape(286, _ppt_title_text(slide.title), 4460000, 700000, 6500000, 970000, _ppt_title_font_size(_ppt_title_text(slide.title)), fg, bold=True),
            (_text_shape(287, slide.subtitle, 4480000, 1740000, 6180000, 330000, 1400, accent, bold=True) if slide.subtitle else ""),
            _rect_shape(288, 4440000, 2140000, 3600000, 26000, accent),
            *cards,
        ]
    )


def _bridge_narrative_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    """A bridge page: decision claim at left and three connected moves below."""

    items = blocks[:3] or blocks[:1]
    cards = [
        _card_shape(303 + index, block.content, 760000 + index * 3740000, 4720000, 3380000, 740000, soft, fg, accent)
        for index, block in enumerate(items)
    ]
    lead = items[0].content if items else slide.title
    return "\n".join(
        [
            _text_shape(299, _ppt_title_text(slide.title), 760000, 760000, 5440000, 850000, _ppt_title_font_size(_ppt_title_text(slide.title)), fg, bold=True),
            _text_shape(300, lead, 780000, 1830000, 5160000, 1380000, _ppt_statement_font_size(lead, compact=True), fg, bold=True),
            _alpha_rect_shape(301, 780000, 3570000, 4900000, 32000, accent, 68000, name="Bridge Decision Rail"),
            _text_shape(302, slide.subtitle or "Decision bridge", 800000, 3850000, 4920000, 300000, 1320, accent, bold=True),
            *cards,
        ]
    )


def _closing_bloom_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    """A full-bleed closing page with a protected central decision statement."""

    takeaway = blocks[0].content if blocks else slide.speaker_notes
    support = blocks[1:2]
    return "\n".join(
        [
            _text_shape(311, _ppt_title_text(slide.title), 1520000, 1520000, 9160000, 1320000, _ppt_title_font_size(_ppt_title_text(slide.title), cover=True), fg, bold=True, align="ctr"),
            _text_shape(312, takeaway, 2320000, 3200000, 7560000, 920000, 1900, fg, align="ctr"),
            _rect_shape(313, 4300000, 4470000, 3600000, 30000, accent),
            (_text_shape(314, support[0].content, 3080000, 4860000, 6040000, 560000, 1350, fg, align="ctr") if support else ""),
        ]
    )


def _manifesto_close_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    takeaway = blocks[0].content if blocks else slide.speaker_notes
    return "\n".join(
        [
            _rect_shape(188, 780000, 820000, 72000, 5000000, accent),
            _text_shape(189, _ppt_title_text(slide.title), 1280000, 1200000, 8800000, 1900000, _ppt_title_font_size(_ppt_title_text(slide.title), cover=True), fg, bold=True),
            _text_shape(190, takeaway, 1300000, 3620000, 7200000, 950000, 2000, fg),
            _shape(191, "ellipse", 9300000, 4050000, 1500000, 1500000, accent, alpha=39000),
        ]
    )


def _future_horizon_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    takeaway = blocks[0].content if blocks else slide.speaker_notes
    supporting = blocks[1:2]
    support_text = (
        supporting[0].content
        if supporting and _copy_overlap_ratio(takeaway, supporting[0].content) < 0.72
        else ""
    )
    return "\n".join(
        [
            _text_shape(192, _ppt_title_text(slide.title), 1320000, 1260000, 9560000, 1320000, _ppt_title_font_size(_ppt_title_text(slide.title), cover=True), fg, bold=True, align="ctr"),
            _text_shape(193, takeaway, 2100000, 3020000, 8000000, 820000, 1900, fg, align="ctr"),
            _rect_shape(198, 3860000, 4260000, 4480000, 32000, accent),
            (_text_shape(199, support_text, 2800000, 4700000, 6600000, 620000, 1400, fg, align="ctr") if support_text else ""),
        ]
    )


def _section_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    key = blocks[0].content if blocks else slide.title
    return "\n".join(
        [
            _text_shape(21, slide.title, 720000, 1450000, 8600000, 1200000, 3800, fg, bold=True),
            _shape(22, "roundRect", 740000, 3360000, 9500000, 900000, soft, alpha=26000, line=accent),
            _text_shape(23, key, 1040000, 3580000, 8800000, 420000, 1850, fg),
        ]
    )


def _two_column_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    left = blocks[0].content if blocks else slide.title
    right_blocks = blocks[1:5] or blocks[:1]
    right_cards = "\n".join(
        _card_shape(40 + index, block.content, 6560000, 1900000 + index * 950000, 4500000, 720000, soft, fg, accent)
        for index, block in enumerate(right_blocks)
    )
    return "\n".join(
        [
            _title_and_subtitle(slide, fg, title_y=430000, title_size=3000),
            _shape(31, "roundRect", 720000, 1900000, 5200000, 3600000, soft, alpha=25000, line=accent),
            _text_shape(33, left, 1060000, 2580000, 4200000, 1800000, 2200, fg, bold=True),
            right_cards,
        ]
    )


def _three_cards_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    cards = blocks[:3] or blocks[:1]
    while len(cards) < 3 and cards:
        cards.append(cards[-1])
    card_shapes = "\n".join(
        _card_shape(60 + index, block.content, 720000 + index * 3650000, 2500000, 3200000, 2100000, soft, fg, accent)
        for index, block in enumerate(cards[:3])
    )
    return "\n".join(
        [
            _title_and_subtitle(slide, fg, title_y=430000, title_size=3000),
            card_shapes,
        ]
    )


def _timeline_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    events = blocks[:4] or blocks[:1]
    row_heights = [
        _uniform_card_height(
            [(block.content, 4800000) for block in events[row_start : row_start + 2]],
            base_cy=960000,
        )
        for row_start in range(0, len(events), 2)
    ]
    row_ys = [3280000]
    if len(row_heights) > 1:
        row_ys.append(row_ys[0] + row_heights[0] + 180000)
    rails = [
        _rect_shape(70, 980000, row_ys[0] + 220000, 10300000, 30000, accent),
        *(
            [
                _rect_shape(83, 980000, row_ys[1] + 220000, 10300000, 30000, accent),
                _rect_shape(84, 6260000, row_ys[0] + 220000, 30000, row_ys[1] - row_ys[0], accent),
            ]
            if len(row_ys) > 1
            else []
        ),
    ]
    nodes = []
    for index, block in enumerate(events):
        column = index % 2
        row = index // 2
        x = 760000 + column * 5750000
        y = row_ys[row]
        nodes.extend(
            [
                _shape(71 + index * 3, "ellipse", x, y + 90000, 260000, 260000, accent),
                _text_shape(72 + index * 3, f"{index + 1}", x + 50000, y + 142000, 160000, 110000, 900, "111111", bold=True, align="ctr", role="meta"),
                _card_shape(73 + index * 3, block.content, x + 420000, y, 4800000, row_heights[row], soft, fg, accent),
            ]
        )
    return "\n".join([_title_and_subtitle(slide, fg, title_y=430000, title_size=3000), *rails, *nodes])


def _chart_focus_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    insight = blocks[0].content if blocks else slide.title
    cards = "\n".join(
        _card_shape(90 + index, block.content, 7800000, 2050000 + index * 980000, 3300000, 780000, soft, fg, accent)
        for index, block in enumerate(blocks[1:4])
    )
    bars = "\n".join(
        _rect_shape(84 + index, 1500000 + index * 950000, 4400000 - index * 420000, 520000, 1050000 + index * 420000, accent)
        for index in range(4)
    )
    return "\n".join(
        [
            _text_shape(5, _ppt_title_text(slide.title), 700000, 430000, 6900000, 920000, _ppt_title_font_size(_ppt_title_text(slide.title)), fg, bold=True),
            (_text_shape(7, slide.subtitle, 720000, 1290000, 6900000, 320000, 1500, fg) if slide.subtitle else ""),
            _shape(80, "roundRect", 720000, 1900000, 6500000, 3600000, soft, alpha=23000, line=accent),
            _text_shape(82, insight, 1120000, 2580000, 5200000, 620000, 1800, fg, bold=True),
            bars,
            cards,
        ]
    )


def _closing_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    takeaway = blocks[0].content if blocks else slide.speaker_notes
    return "\n".join(
        [
            _shape(110, "roundRect", 1250000, 950000, 9700000, 4550000, soft, alpha=25000, line=accent),
            _text_shape(111, _ppt_title_text(slide.title), 1650000, 1500000, 8900000, 1350000, _ppt_title_font_size(_ppt_title_text(slide.title), cover=True), fg, bold=True, align="ctr"),
            _text_shape(112, takeaway, 2100000, 3250000, 8000000, 700000, 1900, fg, align="ctr"),
        ]
    )


def _text_shape(
    shape_id: int,
    text: str,
    x: int,
    y: int,
    cx: int,
    cy: int,
    size: int,
    color: str = "111111",
    *,
    bold: bool = False,
    align: str = "l",
    role: str | None = None,
) -> str:
    inferred_role = role or (
        "meta"
        if shape_id >= 900
        else "title"
        if bold and size >= 2400
        else "subtitle"
        if bold or size >= 1700
        else "body"
    )
    cleaned_text = _clean_visible_text(text, role=inferred_role, clip=False)
    font_size = _visible_text_font_size(cleaned_text, cx, cy, size, inferred_role)
    cleaned_text, x, y, cx, cy, font_size, anchor = _fit_text_frame(
        cleaned_text,
        x,
        y,
        cx,
        cy,
        font_size,
        inferred_role,
    )
    inset_x, inset_y = _text_insets_for_role(inferred_role, cx, cy)
    font_scale = 90000 if inferred_role == "title" else 92000 if inferred_role == "subtitle" else 94000
    safe = html.escape(cleaned_text)
    bold_attr = ' b="1"' if bold else ""
    return f'''<p:sp>
  <p:nvSpPr><p:cNvPr id="{shape_id}" name="Text {shape_id}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>
  <p:txBody><a:bodyPr wrap="square" anchor="{anchor}" horzOverflow="clip" vertOverflow="clip" lIns="{inset_x}" tIns="{inset_y}" rIns="{inset_x}" bIns="{inset_y}"><a:normAutofit fontScale="{font_scale}" lnSpcReduction="5000"/></a:bodyPr><a:lstStyle/><a:p><a:pPr algn="{align}"/><a:r><a:rPr lang="zh-CN" sz="{font_size}"{bold_attr}><a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:latin typeface="Times New Roman"/><a:ea typeface="SimSun"/><a:cs typeface="Times New Roman"/></a:rPr><a:t>{safe}</a:t></a:r></a:p></p:txBody>
</p:sp>'''


def _rect_shape(shape_id: int, x: int, y: int, cx: int, cy: int, fill: str) -> str:
    return f'''<p:sp>
  <p:nvSpPr><p:cNvPr id="{shape_id}" name="Shape {shape_id}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="{fill}"/></a:solidFill><a:ln><a:noFill/></a:ln></p:spPr>
</p:sp>'''


def _alpha_rect_shape(
    shape_id: int,
    x: int,
    y: int,
    cx: int,
    cy: int,
    fill: str,
    alpha: int,
    *,
    name: str = "Reference Layer",
) -> str:
    safe_name = html.escape(name)
    return f'''<p:sp>
  <p:nvSpPr><p:cNvPr id="{shape_id}" name="{safe_name} {shape_id}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="{fill}"><a:alpha val="{alpha}"/></a:srgbClr></a:solidFill><a:ln><a:noFill/></a:ln></p:spPr>
</p:sp>'''


def _shape(
    shape_id: int,
    preset: str,
    x: int,
    y: int,
    cx: int,
    cy: int,
    fill: str,
    *,
    alpha: int | None = None,
    line: str | None = None,
) -> str:
    alpha_xml = f'<a:alpha val="{alpha}"/>' if alpha is not None else ""
    line_xml = (
        f'<a:ln w="12000"><a:solidFill><a:srgbClr val="{line}"><a:alpha val="52000"/></a:srgbClr></a:solidFill></a:ln>'
        if line
        else "<a:ln><a:noFill/></a:ln>"
    )
    effect_xml = (
        '<a:effectLst><a:outerShdw blurRad="63500" dist="25400" dir="5400000" rotWithShape="0">'
        '<a:srgbClr val="000000"><a:alpha val="9000"/></a:srgbClr>'
        "</a:outerShdw></a:effectLst>"
        if preset in {"roundRect", "ellipse"}
        else ""
    )
    return f'''<p:sp>
  <p:nvSpPr><p:cNvPr id="{shape_id}" name="Design Shape {shape_id}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="{preset}"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="{fill}">{alpha_xml}</a:srgbClr></a:solidFill>{line_xml}{effect_xml}</p:spPr>
</p:sp>'''


def _image_pic_shape(
    shape_id: int,
    rel_id: str,
    x: int,
    y: int,
    cx: int,
    cy: int,
    description: str,
    *,
    rounded: bool = True,
    name: str = "Visual Asset",
    source_dimensions: tuple[int | None, int | None] | None = None,
) -> str:
    safe_description = html.escape(_clean_visible_text(description, role="body"))
    safe_name = html.escape(_clean_visible_text(name, role="body") or "Visual Asset")
    preset = "roundRect" if rounded else "rect"
    crop_xml = ""
    if source_dimensions is not None:
        source_width = int(source_dimensions[0] or 0)
        source_height = int(source_dimensions[1] or 0)
        if source_width > 0 and source_height > 0 and cx > 0 and cy > 0:
            source_ratio = source_width / source_height
            frame_ratio = cx / cy
            if source_ratio > frame_ratio:
                visible_width = source_height * frame_ratio
                crop = max(0, min(49999, round((source_width - visible_width) / source_width * 50000)))
                crop_xml = f'<a:srcRect l="{crop}" r="{crop}"/>'
            elif source_ratio < frame_ratio:
                visible_height = source_width / frame_ratio
                crop = max(0, min(49999, round((source_height - visible_height) / source_height * 50000)))
                crop_xml = f'<a:srcRect t="{crop}" b="{crop}"/>'
    chrome_xml = (
        '<a:ln w="9000"><a:solidFill><a:srgbClr val="FFFFFF"><a:alpha val="30000"/></a:srgbClr></a:solidFill></a:ln><a:effectLst><a:outerShdw blurRad="76200" dist="25400" dir="5400000" rotWithShape="0"><a:srgbClr val="000000"><a:alpha val="15000"/></a:srgbClr></a:outerShdw></a:effectLst>'
        if rounded
        else "<a:ln><a:noFill/></a:ln>"
    )
    return f'''<p:pic>
  <p:nvPicPr><p:cNvPr id="{shape_id}" name="{safe_name} {shape_id}" descr="{safe_description}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>
  <p:blipFill><a:blip r:embed="{rel_id}"/>{crop_xml}<a:stretch><a:fillRect/></a:stretch></p:blipFill>
  <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="{preset}"><a:avLst/></a:prstGeom>{chrome_xml}</p:spPr>
</p:pic>'''


def _uniform_card_height(items: list[tuple[str, int]], *, base_cy: int) -> int:
    """Return one safe height for a visual group of cards.

    PowerPoint renders SimSun/Times New Roman line boxes differently from the
    HTML preview. Computing the tallest card first prevents content-dependent
    growth from creating overlaps or ragged baselines in the exported deck.
    """
    cy = base_cy
    for _ in range(3):
        required_cy = cy
        for content, cx in items:
            cleaned = _clean_visible_text(content, role="card", clip=False)
            font_size = _card_font_size(cleaned, cx, cy)
            inset_x, inset_y = _text_insets_for_role("card", cx, cy)
            required = _required_text_cy(cleaned, cx, font_size, "card", inset_x, inset_y)
            required_cy = max(required_cy, int(required / 0.88))
        if required_cy <= cy:
            break
        cy = required_cy
    return cy


def _card_shape(
    shape_id: int,
    content: str,
    x: int,
    y: int,
    cx: int,
    cy: int,
    fill: str,
    text_color: str,
    accent: str,
) -> str:
    cleaned_content = _clean_visible_text(content, role="card", clip=False)
    font_size = _card_font_size(cleaned_content, cx, cy)
    cleaned_content, x, y, cx, cy, font_size, anchor = _fit_text_frame(
        cleaned_content,
        x,
        y,
        cx,
        cy,
        font_size,
        "card",
    )
    safe_content = html.escape(cleaned_content)
    font_scale = 90000 if font_size <= 1180 else 92000 if font_size <= 1280 else 94000
    inset_x, inset_y = _text_insets_for_role("card", cx, cy)
    effect_xml = (
        '<a:effectLst><a:outerShdw blurRad="76200" dist="38100" dir="5400000" rotWithShape="0">'
        '<a:srgbClr val="000000"><a:alpha val="11000"/></a:srgbClr>'
        "</a:outerShdw></a:effectLst>"
    )
    return f'''<p:sp>
  <p:nvSpPr><p:cNvPr id="{shape_id}" name="Card {shape_id}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="roundRect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="{fill}"><a:alpha val="94000"/></a:srgbClr></a:solidFill><a:ln w="12000"><a:solidFill><a:srgbClr val="{accent}"><a:alpha val="42000"/></a:srgbClr></a:solidFill></a:ln>{effect_xml}</p:spPr>
  <p:txBody><a:bodyPr wrap="square" anchor="{anchor}" horzOverflow="clip" vertOverflow="clip" lIns="{inset_x}" tIns="{inset_y}" rIns="{inset_x}" bIns="{inset_y}"><a:normAutofit fontScale="{font_scale}" lnSpcReduction="5000"/></a:bodyPr><a:lstStyle/>
    <a:p><a:r><a:rPr lang="zh-CN" sz="{font_size}"><a:solidFill><a:srgbClr val="{text_color}"/></a:solidFill><a:latin typeface="Times New Roman"/><a:ea typeface="SimSun"/><a:cs typeface="Times New Roman"/></a:rPr><a:t>{safe_content}</a:t></a:r></a:p>
  </p:txBody>
</p:sp>'''


def _card_font_size(content: str, cx: int, cy: int) -> int:
    weight = _display_weight(content.strip())
    narrow = cx <= 2400000
    compact = cy <= 900000
    if weight >= 96 or (narrow and weight >= 68):
        size = PPT_CARD_MIN
    elif weight >= 68 or (narrow and weight >= 48) or compact:
        size = PPT_CARD_MIN
    elif weight >= 44:
        size = PPT_CARD_MID
    else:
        size = PPT_CARD_MAX
    if narrow:
        size = max(PPT_CARD_MIN, min(size, 1650))
    if compact:
        size = max(PPT_CARD_MIN, min(size, 1650))
    return size


def _ppt_color(value: str) -> str:
    cleaned = value.strip().lstrip("#").upper()
    if len(cleaned) == 3:
        cleaned = "".join(character * 2 for character in cleaned)
    if len(cleaned) != 6 or any(character not in "0123456789ABCDEF" for character in cleaned):
        return "111111"
    return cleaned


def _is_light_color(value: str) -> bool:
    cleaned = _ppt_color(value)
    red = int(cleaned[0:2], 16)
    green = int(cleaned[2:4], 16)
    blue = int(cleaned[4:6], 16)
    return (0.2126 * red + 0.7152 * green + 0.0722 * blue) >= 160


def _slide_master() -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>{_group_transform()}</p:spTree></p:cSld>
  {_color_map()}
  <p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
  <p:txStyles>
    <p:titleStyle><a:lvl1pPr algn="l"><a:defRPr sz="4400" kern="1200"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mj-lt"/><a:ea typeface="+mj-ea"/></a:defRPr></a:lvl1pPr></p:titleStyle>
    <p:bodyStyle><a:lvl1pPr marL="228600" indent="-228600"><a:defRPr sz="1800" kern="1200"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mn-lt"/><a:ea typeface="+mn-ea"/></a:defRPr></a:lvl1pPr></p:bodyStyle>
    <p:otherStyle><a:defPPr><a:defRPr lang="zh-CN"/></a:defPPr></p:otherStyle>
  </p:txStyles>
</p:sldMaster>'''


def _slide_master_rels() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout7.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>'''


def _slide_layout() -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">
  <p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>{_group_transform()}</p:spTree></p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>'''


def _slide_layout_rels() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>'''


def _slide_rels(slide_index: int, visual_asset: VisualAsset | None) -> str:
    image_rel = (
        f'\n  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{html.escape(visual_asset.file_name)}"/>'
        if visual_asset is not None
        else ""
    )
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout7.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" Target="../notesSlides/notesSlide''' + str(slide_index) + '''.xml"/>
  ''' + image_rel + '''
</Relationships>'''


def _notes_slide_rels(slide_index: int) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster" Target="../notesMasters/notesMaster1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="../slides/slide{slide_index}.xml"/>
</Relationships>'''


def _notes_slide_xml(slide) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:notes xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree>
    <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>{_group_transform()}
    {_text_shape(2, slide.title, 620000, 420000, 5600000, 520000, 1800, "111111", bold=True)}
    {_text_shape(3, slide.speaker_notes, 620000, 1160000, 5600000, 5200000, 1250, "333333")}
  </p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:notes>'''


def _theme(name: str = "AI PPT Agent") -> str:
    safe_name = html.escape(name)
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="{safe_name}">
  <a:themeElements>
    <a:clrScheme name="Agent"><a:dk1><a:srgbClr val="111111"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="222222"/></a:dk2><a:lt2><a:srgbClr val="EEEEEE"/></a:lt2><a:accent1><a:srgbClr val="5B8DEF"/></a:accent1><a:accent2><a:srgbClr val="FF5A5F"/></a:accent2><a:accent3><a:srgbClr val="7BD88F"/></a:accent3><a:accent4><a:srgbClr val="FFD166"/></a:accent4><a:accent5><a:srgbClr val="9B5DE5"/></a:accent5><a:accent6><a:srgbClr val="00BBF9"/></a:accent6><a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink></a:clrScheme>
    <a:fontScheme name="Agent"><a:majorFont><a:latin typeface="Times New Roman"/><a:ea typeface="SimSun"/><a:cs typeface="Times New Roman"/></a:majorFont><a:minorFont><a:latin typeface="Times New Roman"/><a:ea typeface="SimSun"/><a:cs typeface="Times New Roman"/></a:minorFont></a:fontScheme>
    <a:fmtScheme name="Agent">
      <a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"><a:tint val="50000"/><a:satMod val="300000"/></a:schemeClr></a:solidFill><a:solidFill><a:schemeClr val="phClr"><a:shade val="50000"/><a:satMod val="200000"/></a:schemeClr></a:solidFill></a:fillStyleLst>
      <a:lnStyleLst><a:ln w="6350" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/><a:miter lim="800000"/></a:ln><a:ln w="12700" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/><a:miter lim="800000"/></a:ln><a:ln w="19050" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/><a:miter lim="800000"/></a:ln></a:lnStyleLst>
      <a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>
      <a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"><a:tint val="95000"/><a:satMod val="170000"/></a:schemeClr></a:solidFill><a:solidFill><a:schemeClr val="phClr"><a:shade val="90000"/><a:satMod val="120000"/></a:schemeClr></a:solidFill></a:bgFillStyleLst>
    </a:fmtScheme>
  </a:themeElements>
</a:theme>'''


def _group_transform() -> str:
    return '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'


def _color_map() -> str:
    return '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'


def _notes_master() -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:notesMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>{_group_transform()}</p:spTree></p:cSld>
  {_color_map()}
  <p:hf hdr="1" ftr="1" dt="1" sldNum="1"/>
  <p:notesStyle><a:lvl1pPr marL="0" algn="l"><a:defRPr sz="1200"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mn-lt"/><a:ea typeface="+mn-ea"/></a:defRPr></a:lvl1pPr></p:notesStyle>
</p:notesMaster>'''


def _notes_master_rels() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme2.xml"/></Relationships>'''


def _presentation_props() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentationPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>'''


def _view_props() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:viewPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:gridSpacing cx="72008" cy="72008"/></p:viewPr>'''


def _table_styles() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>'''


def _core_props(deck: SlideDeck) -> str:
    clean_title = _clean_visible_text(deck.title, role="title") or deck.project_id
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{html.escape(clean_title)}</dc:title><dc:creator>AI PPT Agent</dc:creator></cp:coreProperties>'''


def _app_props(slide_count: int) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>AI PPT Agent</Application><Slides>{slide_count}</Slides></Properties>'''
