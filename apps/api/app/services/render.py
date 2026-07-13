from __future__ import annotations

import html
import hashlib
import json
import os
import re
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib import parse, request as urlrequest

from ai_ppt_contracts import RenderResult, SlideDeck
from app.ai.errors import ModelGatewayError
from app.ai.models import ImageRequest
from app.ai.protocols import ImageGateway


MAX_IMAGE_BYTES = 8 * 1024 * 1024
SLIDE_CX = 12192000
SLIDE_CY = 6858000
FOREGROUND_SAFE_X = 460000
FOREGROUND_SAFE_TOP = 340000
FOREGROUND_SAFE_BOTTOM = 430000
EMU_PER_POINT = 12700
PPT_COVER_TITLE_MAX = 3300
PPT_COVER_TITLE_MID = 3050
PPT_COVER_TITLE_MIN = 2550
PPT_PAGE_TITLE_MAX = 2900
PPT_PAGE_TITLE_MID = 2700
PPT_PAGE_TITLE_MIN = 2300
PPT_STATEMENT_MAX = 1780
PPT_STATEMENT_MID = 1620
PPT_STATEMENT_MIN = 1460
PPT_CARD_MAX = 1540
PPT_CARD_MID = 1380
PPT_CARD_MIN = 1220
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


@dataclass(frozen=True, slots=True)
class RenderTextBlock:
    content: str


class RenderSlideProxy:
    def __init__(self, slide, *, subtitle: str) -> None:
        self._slide = slide
        self.subtitle = subtitle

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
) -> dict[int, VisualAsset]:
    assets_dir = render_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    assets: dict[int, VisualAsset] = {}
    seen_image_hashes: set[str] = set()
    image_plan_by_slide = {item.slide: item for item in deck.image_plan}
    for slide in deck.slides:
        image_item = image_plan_by_slide[slide.slide_index]
        query = image_item.search_query
        asset = None
        if mode != "generate":
            asset = _read_cached_visual_asset(
                slide.slide_index,
                assets_dir,
                image_type=image_item.image_type,
                purpose=image_item.purpose,
                prompt=image_item.prompt,
                provider_chain=list(image_item.provider_chain),
            )
        if mode != "generate":
            asset = asset or _search_open_visual_asset(
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
        if asset is not None and _visual_asset_hash(asset.path) in seen_image_hashes:
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
            )
            if generated_asset is not None:
                asset = generated_asset
        if asset is None:
            asset = _write_local_visual_asset(
                slide.slide_index,
                query,
                assets_dir,
                image_type=image_item.image_type,
                purpose=image_item.purpose,
                prompt=image_item.prompt,
                provider_chain=list(image_item.provider_chain),
                slide_title=slide.title,
                slide_intent=slide.visual_intent,
                image_treatment=slide.design_plan.image_treatment,
                composition_archetype=slide.design_plan.composition_archetype,
                palette=deck.theme.palette,
            )
        _write_cached_visual_asset(asset, assets_dir)
        seen_image_hashes.add(_visual_asset_hash(asset.path))
        assets[slide.slide_index] = asset
    return assets


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
    if not file_name or "/" in file_name or "\\" in file_name:
        return None
    path = assets_dir / file_name
    if not path.is_file() or path.stat().st_size <= 0:
        return None
    return VisualAsset(
        slide_index=slide_index,
        path=path,
        rel_path=f"assets/{file_name}",
        file_name=file_name,
        mime_type=str(data.get("mimeType") or "image/png"),
        source_type=str(data.get("sourceType") or "cached_visual_asset"),
        alt=str(data.get("alt") or _asset_alt(slide_index, str(data.get("query") or ""))),
        query=str(data.get("query") or ""),
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
    }
    try:
        _asset_sidecar_path(assets_dir, asset.slide_index).write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
    except OSError:
        return


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
) -> VisualAsset | None:
    if not enabled or os.getenv("AI_PPT_IMAGE_SEARCH_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return None
    deadline = time.monotonic() + _image_search_budget(timeout_seconds)
    for candidate_query in _image_search_queries(query, image_type)[:4]:
        for searcher in (
            _search_bing_visual_asset,
            _search_wikipedia_page_visual_asset,
            _search_commons_visual_asset,
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
            )
            if asset is not None:
                return asset
    return None


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
                if actual_mime not in {"image/jpeg", "image/png"} or not path.is_file() or path.stat().st_size <= 0:
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
) -> VisualAsset | None:
    search_url = "https://commons.wikimedia.org/w/api.php?" + parse.urlencode(
        {
            "action": "query",
            "generator": "search",
            "gsrnamespace": "6",
            "gsrlimit": "4",
            "gsrsearch": query,
            "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata",
            "format": "json",
        }
    )
    try:
        payload = _read_json_url(search_url, timeout=_image_search_timeout(timeout_seconds))
        pages = (payload.get("query") or {}).get("pages") or {}
        for page in pages.values():
            for image_info in page.get("imageinfo") or []:
                mime_type = str(image_info.get("mime") or "")
                if mime_type not in {"image/jpeg", "image/png"}:
                    continue
                if int(image_info.get("size") or 0) > MAX_IMAGE_BYTES:
                    continue
                image_url = str(image_info.get("url") or "")
                if not image_url:
                    continue
                extension = _extension_for_mime(mime_type)
                file_name = f"slide-{slide_index}-commons{extension}"
                path = assets_dir / file_name
                actual_mime = _download_binary(image_url, path, timeout=_image_search_timeout(timeout_seconds))
                if actual_mime not in {"image/jpeg", "image/png"} or not path.is_file() or path.stat().st_size <= 0:
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
            image_url = str(item.get("contentUrl") or "")
            if not image_url.lower().startswith(("http://", "https://")):
                continue
            encoding = str(item.get("encodingFormat") or "").lower()
            extension = ".png" if encoding == "png" else ".jpg"
            file_name = f"slide-{slide_index}-bing{extension}"
            path = assets_dir / file_name
            actual_mime = _download_binary(image_url, path, timeout=_image_search_timeout(timeout_seconds))
            if actual_mime not in {"image/jpeg", "image/png"} or not path.is_file() or path.stat().st_size <= 0:
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
    extension = _extension_for_mime(generated.mime_type)
    file_name = f"slide-{slide_index}-ai{extension}"
    path = assets_dir / file_name
    path.write_bytes(generated.bytes)
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
    if _is_text_risk_image_type(image_type) or _has_text_risk_visual_cues(
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
        object_hint = _safe_content_object_hint(query, image_prompt, slide_title, slide_intent, purpose)
        return (
            "Create a premium 16:9 editorial macro photograph of an abstract still life. "
            f"{variant}. "
            f"{object_hint}. "
            "The scene is made only from blank translucent glass objects, matte ceramic forms, coffee-toned stone, soft fabric, water reflections, and warm light beams. "
            "All surfaces are plain, smooth, unmarked, pattern-free, brand-free, logo-free, label-free, and minimal. "
            "ABSOLUTELY NO visible text or writing, letters, numbers, brand marks, watermarks, menus, signage, labelled packaging, digital devices, data graphics, or pseudo-writing. "
            "Use shallow depth of field, layered foreground and background, cinematic shadows, and generous empty space. "
            f"Palette: {', '.join(palette)}. "
            "The visual supports the idea only through atmosphere, metaphor, material texture, light, and depth."
        )
    return (
        f"{image_prompt}. "
        "Create a premium 16:9 presentation visual for a slide. "
        "Use only the supplied user/source-grounded deck cues. "
        "ABSOLUTELY NO visible text, letters, numbers, UI screenshots, browser windows, logos, badges, watermarks, menus, or fake document pages. "
        "Do not create dashboards, charts with labels, app screens, web pages, interface panels, posters, signs, documents, book pages, product labels, packaging labels, menu boards, storefront signage, or any surface that could contain readable or pseudo-readable writing. "
        "If showing products or business scenes, use blank unbranded objects and clean physical metaphors only. "
        "Prefer content-supporting photography, abstract 3D objects, symbolic still-life scenes, natural materials, light, depth, and clean geometry. "
        "The image must be a clean content-supporting photograph/abstract scene with generous empty space. "
        f"Image type: {image_type}. Purpose: {purpose}. "
        f"Slide title: {slide_title}. Visual intent: {slide_intent}. "
        f"Asset role: {asset_role}. Page composition: {composition_archetype}. "
        f"Image treatment: {image_treatment}. "
        f"Selected art direction: {direction_name}. Palette: {', '.join(palette)}. "
        f"Image search query that failed or needs fallback: {query}. "
        "Style: cinematic but clean, professional, layered foreground/midground/background, "
        "clear negative space for PPT text, suitable for editable PowerPoint and dynamic HyperFrames HTML."
    )


def _is_text_risk_image_type(image_type: str) -> bool:
    return image_type in {"icon_illustration", "data_visual", "product_showcase"}


def _safe_content_object_hint(*values: str) -> str:
    text = " ".join(str(value) for value in values).casefold()
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
    candidates = [
        *_subject_image_queries(cleaned_query, image_type),
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
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


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
    if len(value) <= limit:
        return value
    window = value[: max(1, limit - 1)].rstrip()
    boundary = -1
    for marker in ("。", "；", "，", "、", "：", "—", "–", ";", ",", ":", "-", " "):
        candidate = window.rfind(marker)
        if candidate >= int(limit * 0.55):
            boundary = max(boundary, candidate)
    if boundary > 0:
        window = window[:boundary].rstrip(" ，。；：、,:;-—–")
    elif not _contains_cjk(window):
        space = window.rfind(" ")
        if space >= int(limit * 0.45):
            window = window[:space].rstrip()
    return window.rstrip("…") + "…"


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
    text = re.sub(r"^AI\s*鍙\S{0,8}\s*[锛：:]\s*", "", text, flags=re.IGNORECASE).strip()
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
    size = requested_size
    if role == "title":
        if weighted >= 58:
            size = min(size, 2450)
        elif weighted >= 46:
            size = min(size, 2650)
        elif weighted >= 34:
            size = min(size, 2850)
    elif role == "subtitle":
        if weighted >= 72:
            size = min(size, 1350)
        elif weighted >= 52:
            size = min(size, 1500)
    elif weighted >= 110 or (cx <= 2600000 and weighted >= 72):
        size = min(size, 1180)
    elif weighted >= 86 or cy <= 420000:
        size = min(size, 1320)
    return max(1050, size)


def _ceil_div(value: int, divisor: int) -> int:
    return max(1, (max(0, value) + max(1, divisor) - 1) // max(1, divisor))


def _text_insets_for_role(role: str, cx: int, cy: int) -> tuple[int, int]:
    if role == "title":
        return (120000 if cx <= 5200000 else 160000, 70000)
    if role == "card":
        return (190000 if cx <= 2400000 else 240000, 105000 if cy <= 900000 else 125000)
    if role == "subtitle":
        return (115000, 65000)
    return (100000, 60000)


def _weighted_capacity_per_line(cx: int, font_size: int, inset_x: int) -> int:
    usable_cx = max(300000, cx - inset_x * 2)
    point_size = max(8.0, font_size / 100.0)
    avg_weight_emu = point_size * EMU_PER_POINT * 0.56
    return max(10, int((usable_cx * 2) / max(avg_weight_emu, 1.0)))


def _estimated_text_lines(text: str, cx: int, font_size: int, role: str, inset_x: int) -> int:
    paragraphs = [part.strip() for part in re.split(r"[\r\n]+", text) if part.strip()] or [text]
    capacity = _weighted_capacity_per_line(cx, font_size, inset_x)
    return sum(_ceil_div(_display_weight(paragraph), capacity) for paragraph in paragraphs)


def _required_text_cy(text: str, cx: int, font_size: int, role: str, inset_x: int, inset_y: int) -> int:
    lines = _estimated_text_lines(text, cx, font_size, role, inset_x)
    line_height = int((font_size / 100.0) * EMU_PER_POINT * (1.16 if role == "title" else 1.28))
    return lines * line_height + inset_y * 2


def _minimum_font_size(role: str) -> int:
    if role == "title":
        return 1850
    if role == "subtitle":
        return 1080
    if role == "card":
        return PPT_CARD_MIN
    return 1000


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
    if required > cy:
        cy = min(max(cy, int(required / 0.88)), max_available_cy)
    x, y, cx, cy = _fit_foreground_box(x, y, cx, cy)
    fitted_text, fitted_size = _fit_visible_text_to_frame(text, cx, cy, font_size, role)
    anchor = "ctr" if role == "title" and _estimated_text_lines(fitted_text, cx, fitted_size, role, inset_x) <= 2 else "t"
    return fitted_text, x, y, cx, cy, fitted_size, anchor


def _write_hyperframes_html(deck: SlideDeck, path: Path, visual_assets: dict[int, VisualAsset]) -> None:
    slides = []
    for slide in deck.slides:
        asset = visual_assets.get(slide.slide_index)
        asset_html = _asset_figure_html(asset) if asset else ""
        block_items = []
        for block in _content_blocks(slide, deck_title=deck.title):
            block_items.append(
                '<div class="block block-card">'
                f'<p>{html.escape(_clean_visible_text(block.content, role="card"))}</p>'
                "</div>"
            )
        blocks = "\n".join(block_items[:4])
        plan = slide.design_plan
        explainer_html = _explainer_html(slide)
        title = _clean_visible_text(slide.title, role="title")
        subtitle = _clean_visible_text(slide.subtitle, role="subtitle")
        slides.append(
            f"""
            <section class="frame frame-{html.escape(slide.layout)} composition-{html.escape(plan.composition_archetype)} treatment-{html.escape(plan.image_treatment)} motion-{html.escape(plan.motion_preset)}" data-slide="{slide.slide_index}" data-active="{"true" if slide.slide_index == 1 else "false"}" data-motion-engine="HyperFrames" data-reference-style="cinematic-full-bleed" data-composition-archetype="{html.escape(plan.composition_archetype)}" data-composition-variant="{html.escape(plan.composition_variant)}" data-image-treatment="{html.escape(plan.image_treatment)}" data-motion-preset="{html.escape(plan.motion_preset)}" data-content-density="{html.escape(plan.content_density)}" data-asset-role="{html.escape(plan.asset_role)}">
              <div class="frame-inner" data-reference-style="cinematic-full-bleed">
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
      animation: rise .34s ease both;
    }}
    .frame[data-active="true"] {{
      display: grid;
    }}
    .frame-inner {{
      position: relative;
      --content-w: min(560px, 47%);
      --image-left: 56%;
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
        linear-gradient(90deg, color-mix(in srgb, var(--bg) 88%, transparent) 0%, color-mix(in srgb, var(--bg) 66%, transparent) 34%, color-mix(in srgb, var(--bg) 12%, transparent) 64%, color-mix(in srgb, var(--bg) 38%, transparent) 100%),
        radial-gradient(circle at 18% 78%, color-mix(in srgb, var(--accent) 26%, transparent), transparent 32%),
        radial-gradient(circle at 82% 28%, color-mix(in srgb, var(--soft) 24%, transparent), transparent 34%);
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
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
      font-family: "Times New Roman", SimSun, "宋体", serif;
      font-size: var(--type-title);
      line-height: 1.08;
      margin: 18px 0 20px;
      letter-spacing: -.012em;
      text-wrap: balance;
      text-shadow: 0 12px 34px rgba(0,0,0,.48);
    }}
    h2 {{
      max-width: var(--content-w);
      width: var(--content-w);
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
      font-size: var(--type-subtitle);
      line-height: 1.18;
      opacity: .82;
      font-weight: 560;
      text-shadow: 0 10px 24px rgba(0,0,0,.42);
    }}
    .blocks {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-top: 28px; max-width: var(--content-w); width: var(--content-w); align-items: stretch; }}
    .frame-asset {{
      position: absolute;
      inset: 0;
      z-index: 0;
      margin: 0;
      border: 0;
      border-radius: inherit;
      overflow: hidden;
      min-height: 100%;
      background: var(--bg);
      box-shadow: none;
      transform-origin: 70% 45%;
    }}
    .frame-asset::after {{
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(180deg, color-mix(in srgb, var(--bg) 10%, transparent), color-mix(in srgb, var(--bg) 46%, transparent)),
        radial-gradient(circle at 65% 42%, transparent 0 28%, color-mix(in srgb, var(--bg) 28%, transparent) 65%, color-mix(in srgb, var(--bg) 78%, transparent) 100%);
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
    .treatment-split_crop .frame-asset {{ inset: 10% 5% 10% var(--image-left); border-radius: 28px; }}
    .treatment-split_crop .frame-asset::after {{ background: linear-gradient(90deg, rgba(8,10,15,.88), rgba(8,10,15,.06) 34%, rgba(8,10,15,.18)); }}
    .treatment-masked_window .frame-asset {{ inset: 10% 5% 10% var(--image-left); min-height: auto; border: 1px solid rgba(242,191,74,.36); border-radius: 28px; box-shadow: 0 28px 80px rgba(0,0,0,.42); }}
    .treatment-layered_cutout .frame-asset {{ inset: 11% 5% 10% var(--image-left); min-height: auto; border: 1px solid rgba(255,255,255,.24); border-radius: 36px; transform: none; box-shadow: -14px 18px 0 rgba(242,191,74,.10), 0 36px 90px rgba(0,0,0,.48); }}
    .treatment-evidence_strip .frame-asset {{ inset: 18% 5% 14% var(--image-left); height: auto; min-height: auto; border: 1px solid rgba(242,191,74,.30); border-radius: 24px; }}
    .treatment-atmospheric_backdrop .frame-asset img {{ filter: saturate(.74) contrast(1.08) brightness(.66) blur(1px); transform: scale(1.035); }}
    .block {{ position: relative; overflow: hidden; min-width: 0; min-height: 104px; max-height: 176px; display: grid; align-content: center; padding: 18px; border-radius: 16px; background: color-mix(in srgb, var(--bg) 84%, transparent); border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent); box-shadow: 0 14px 34px rgba(0,0,0,.32); }}
    .block::after {{ content: ""; position: absolute; inset: auto -30px -45px auto; width: 110px; height: 110px; border-radius: 999px; background: var(--accent); opacity: .10; }}
    .block p {{ display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; font-size: var(--type-card); line-height: 1.34; margin: 0; }}
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
      background: color-mix(in srgb, var(--bg) 72%, transparent);
      box-shadow: 0 24px 70px rgba(0,0,0,.38);
      backdrop-filter: blur(20px);
      pointer-events: none;
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
      background: color-mix(in srgb, var(--bg) 72%, transparent);
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
    .frame-asset {{
      inset: 10% 5% 10% var(--image-left) !important;
      z-index: 0 !important;
      min-height: auto !important;
      border-radius: 28px !important;
      border: 1px solid color-mix(in srgb, var(--accent) 34%, transparent) !important;
      box-shadow: 0 28px 80px rgba(0,0,0,.38) !important;
      transform: none !important;
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
<body data-notes="false" data-hyperframes-renderer="local" data-motion-engine="HyperFrames" data-deck-contract="SlideDeck JSON" data-reference-style="cinematic-full-bleed" data-design-system="{html.escape(deck.theme.design_system_id)}">
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
    query = _clean_visible_text(asset.query, role="body", clip=False)
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
    plan = slide.design_plan
    visual_brief = _clean_visible_text(plan.visual_brief, role="body", clip=False) or "outline-grounded explainer"
    nodes = "".join(
        f'<div class="explainer-node">{html.escape(clean_label)}</div>'
        for label in plan.diagram_labels[:3]
        if (clean_label := _clean_visible_text(label, role="card"))
    )
    return (
        '<div class="explainer-layer" '
        f'data-explanation-mode="{html.escape(plan.explanation_mode)}" '
        f'data-visual-brief="{html.escape(visual_brief)}" '
        f'aria-label="{html.escape(visual_brief)}">'
        '<div class="explainer-connector" aria-hidden="true"></div>'
        f"{nodes}</div>"
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
    _theme_bg, _theme_fg, _theme_accent, _theme_soft, _theme_red, _theme_blue = _reference_palette(palette)
    bg, fg, accent, soft, red, blue = "F7FAF6", "10251F", "12A06A", "FFFFFF", "DDEFE7", "DCEBFF"
    slide_for_ppt = RenderSlideProxy(
        slide,
        subtitle=_ppt_subtitle_text(getattr(slide, "subtitle", ""), deck_title),
    )
    content_blocks = _content_blocks(slide_for_ppt, deck_title=deck_title)
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
    {_text_shape(900, f"{slide_for_ppt.slide_index}/{total_slides}", 10700000, 6100000, 760000, 260000, 1150, accent, align="r")}
  </p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>'''


def _explainer_shapes(slide, fg: str, accent: str, soft: str) -> str:
    plan = slide.design_plan
    mode = plan.explanation_mode
    labels: list[str] = []
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
    if mode == "data_evidence" and plan.composition_archetype == "data_landscape":
        geometry = [
            _shape(704 + index, "roundRect", 8750000 + index * 620000, 4300000 - index * 420000, 360000, 850000 + index * 420000, accent, alpha=26000)
            for index in range(4)
        ]
    elif mode == "data_evidence":
        geometry = [
            _shape(704, "roundRect", 7900000, 1900000, 1450000, 1100000, soft, alpha=18000, line=accent),
            _shape(705, "roundRect", 9550000, 2650000, 1450000, 1100000, soft, alpha=18000, line=accent),
            _shape(706, "roundRect", 7900000, 4100000, 1450000, 1100000, soft, alpha=18000, line=accent),
        ]
    elif mode == "comparison_visual":
        geometry = [
            _shape(704, "roundRect", 6820000, 1740000, 2050000, 3300000, soft, alpha=18000, line=accent),
            _shape(705, "roundRect", 9150000, 1740000, 2050000, 3300000, soft, alpha=18000, line=accent),
            _alpha_rect_shape(706, 9020000, 2020000, 26000, 2700000, accent, 52000, name="Explainer Comparison Axis"),
        ]
    elif mode in {"process_diagram", "summary_map"}:
        geometry = [
            _alpha_rect_shape(704, 6900000, 5100000, 4100000, 28000, accent, 52000, name=f"Explainer Connector {mode}"),
            *[
                _shape(705 + index, "ellipse", 7000000 + index * 1900000, 4950000, 330000, 330000, accent, alpha=62000)
                for index in range(3)
            ],
        ]
    elif mode == "concept_diagram":
        geometry = [
            _shape(704, "ellipse", 8500000, 2300000, 1700000, 1700000, soft, alpha=18000, line=accent),
            _shape(705, "ellipse", 7600000, 1600000, 520000, 520000, accent, alpha=52000),
            _shape(706, "ellipse", 10400000, 1900000, 420000, 420000, accent, alpha=42000),
            _shape(707, "ellipse", 10100000, 4300000, 620000, 620000, accent, alpha=36000),
        ]
    else:
        geometry = [
            _shape(704, "ellipse", 9200000, 1250000, 1450000, 1450000, accent, alpha=18000),
            _shape(705, "ellipse", 10100000, 3650000, 520000, 520000, soft, alpha=42000, line=accent),
        ]
    return "\n".join([marker, *geometry, *_explainer_label_shapes(plan.explanation_mode, plan.composition_archetype, labels, fg, accent)])


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
    visual = (
        _image_pic_shape(
            201,
            "rId3",
            0,
            0,
            SLIDE_CX,
            SLIDE_CY,
            visual_asset.alt,
            rounded=False,
            name="Reference Full-Bleed Visual",
        )
        if visual_asset is not None
        else ""
    )
    treatment_visual = _treatment_pic_shape(plan.image_treatment, visual_asset)
    return "\n".join(
        [
            visual,
            _alpha_rect_shape(
                202,
                0,
                0,
                SLIDE_CX,
                SLIDE_CY,
                bg,
                88000,
                name="Reference Cinematic Overlay",
            ),
            _alpha_rect_shape(
                203,
                0,
                0,
                6840000,
                SLIDE_CY,
                bg,
                97000,
                name="Reference Reading Vignette",
            ),
            _alpha_rect_shape(204, 0, 0, 76000, SLIDE_CY, accent, 90000, name="Reference Accent Spine"),
            _alpha_rect_shape(205, 610000, 5960000, 6100000, 42000, accent, 48000, name="Reference Baseline"),
            _shape(206, "ellipse", 8780000, 690000, 1700000, 1700000, blue, alpha=15000),
            _shape(207, "ellipse", -520000, 4620000, 1850000, 1850000, red, alpha=17000),
            _shape(208, "roundRect", 6720000, 540000, 5050000, 5150000, "FFFFFF", alpha=90000, line=accent),
            _shape(209, "roundRect", 7050000, 880000, 4240000, 4300000, soft, alpha=26000, line=accent),
            treatment_visual,
            _alpha_rect_shape(
                219,
                0,
                0,
                1000,
                1000,
                accent,
                0,
                name=f"Page Plan {plan.composition_archetype} {plan.composition_variant} {plan.image_treatment}",
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


def _treatment_pic_shape(image_treatment: str, visual_asset: VisualAsset | None) -> str:
    if visual_asset is None:
        return ""
    geometry = {
        "full_bleed": (6780000, 660000, 4960000, 5000000, True),
        "atmospheric_backdrop": (6860000, 760000, 4820000, 4860000, True),
        "split_crop": (6500000, 720000, 5280000, 5000000, True),
        "masked_window": (7040000, 660000, 4560000, 4820000, True),
        "layered_cutout": (6900000, 920000, 4700000, 4300000, True),
        "evidence_strip": (6740000, 1220000, 4980000, 3640000, True),
    }.get(image_treatment, (6860000, 760000, 4820000, 4860000, True))
    x, y, cx, cy, rounded = geometry
    return _image_pic_shape(
        218,
        "rId3",
        x,
        y,
        cx,
        cy,
        visual_asset.alt,
        rounded=rounded,
        name=f"Page Visual {image_treatment}",
    )


def _content_blocks(slide, *, deck_title: str = "") -> list:
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
        if len(visible_blocks) >= 4:
            break
    return visible_blocks


def _ppt_subtitle_text(value: str, deck_title: str) -> str:
    text = _clean_visible_text(value, role="subtitle", clip=False)
    if not text or _is_offtopic_source_fragment(text, deck_title):
        return ""
    limit = 34 if _contains_cjk(text) else 76
    return _smart_clip_visible_text(text, limit).strip(" \t\r\n，。；：、,:;-—–")


def _ppt_title_text(value: str) -> str:
    text = _clean_visible_text(value, role="title", clip=False)
    if not text:
        return ""
    if _display_weight(text) <= 42:
        return text
    for separator in ("：", ":", "—", "｜", "|"):
        if separator not in text:
            continue
        head = text.split(separator, 1)[0].strip(" \t\r\n，。；：、,:;-—–")
        if 2 <= len(head) <= 18 and _display_weight(head) <= 36:
            return head
    candidate = _presentation_clause(text)
    if "…" in candidate:
        return candidate.split("…", 1)[0].strip(" \t\r\n，。；：、,:;-—–")
    return candidate


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
    return _presentation_clause(text).strip(" \t\r\n，。；：、,:;-—–")


def _presentation_clause(text: str) -> str:
    limit = 44 if _contains_cjk(text) else 96
    candidates = _presentation_clause_candidates(text)
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


def _layout_shapes(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    return _customer_delivery_layout(slide, blocks, fg, accent, soft)
    archetype = slide.design_plan.composition_archetype
    if archetype == "cinematic_hero":
        return _hero_layout(slide, blocks, fg, accent, soft)
    if archetype == "editorial_cover":
        return _editorial_cover_layout(slide, blocks, fg, accent, soft)
    if archetype == "architectural_cover":
        return _architectural_cover_layout(slide, blocks, fg, accent, soft)
    if archetype == "chapter_index":
        return _chapter_index_layout(slide, blocks, fg, accent, soft)
    if archetype == "editorial_split":
        return _two_column_layout(slide, blocks, fg, accent, soft)
    if archetype == "diagonal_story":
        return _diagonal_story_layout(slide, blocks, fg, accent, soft)
    if archetype == "statement_focus":
        return _statement_focus_layout(slide, blocks, fg, accent, soft)
    if archetype == "proof_mosaic":
        return _proof_mosaic_layout(slide, blocks, fg, accent, soft)
    if archetype == "data_landscape":
        return _chart_focus_layout(slide, blocks, fg, accent, soft)
    if archetype == "process_ribbon":
        return _timeline_layout(slide, blocks, fg, accent, soft)
    if archetype == "system_map":
        return _system_map_layout(slide, blocks, fg, accent, soft)
    if archetype == "split_comparison":
        return _split_comparison_layout(slide, blocks, fg, accent, soft)
    if archetype == "priority_stack":
        return _priority_stack_layout(slide, blocks, fg, accent, soft)
    if archetype == "manifesto_close":
        return _manifesto_close_layout(slide, blocks, fg, accent, soft)
    if archetype == "future_horizon":
        return _future_horizon_layout(slide, blocks, fg, accent, soft)
    if archetype == "closing_echo":
        return _closing_layout(slide, blocks, fg, accent, soft)
    return _two_column_layout(slide, blocks, fg, accent, soft)


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
    if purpose in {"agenda", "framework"} or archetype in {"chapter_index", "system_map"}:
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
    if purpose in {"evidence", "insight"} or archetype in {"proof_mosaic", "data_landscape", "statement_focus"}:
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
    if purpose in {"conclusion", "recommendation"} or archetype in {
        "manifesto_close",
        "future_horizon",
        "closing_echo",
        "priority_stack",
    }:
        lead_box = _shape(50, "roundRect", 680000, 1640000, 5740000, 1340000, "FFFFFF", alpha=96000, line=accent)
        lead_text = _text_shape(51, lead, 1020000, 1980000, 5060000, 520000, _ppt_statement_font_size(lead), fg, bold=True)
        support_shapes = []
        for index, block in enumerate(support[:3]):
            y = 3380000 + index * 650000
            width = 5020000 - index * 360000
            support_shapes.append(
                _premium_card_shape(52 + index, block.content, 920000 + index * 280000, y, width, 500000, soft, fg, accent)
            )
        horizon = _alpha_rect_shape(58, 900000, 5450000, 5120000, 36000, accent, 52000, name="Closing Horizon")
        return "\n".join([title, subtitle, lead_box, lead_text, *support_shapes, horizon])
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
            return 2800
        return PPT_COVER_TITLE_MIN
    if weight <= 22:
        return PPT_PAGE_TITLE_MAX
    if weight <= 34:
        return PPT_PAGE_TITLE_MID
    if weight <= 48:
        return 2500
    return PPT_PAGE_TITLE_MIN


def _ppt_statement_font_size(text: str, *, compact: bool = False) -> int:
    weight = _display_weight(text)
    if compact:
        if weight <= 32:
            return PPT_STATEMENT_MID
        if weight <= 48:
            return 1520
        return PPT_STATEMENT_MIN
    if weight <= 36:
        return PPT_STATEMENT_MAX
    if weight <= 56:
        return PPT_STATEMENT_MID
    return PPT_STATEMENT_MIN


def _premium_statement_copy(value: str) -> str:
    text = _clean_visible_text(value, role="body", clip=False)
    limit = 34 if _contains_cjk(text) else 82
    return _strip_terminal_ellipsis(
        _smart_clip_visible_text(text, limit).strip(" \t\r\n锛屻€傦紱锛氥€?:;-鈥斺€?")
    )


def _premium_card_copy(value: str) -> str:
    text = _clean_visible_text(value, role="card", clip=False)
    text = _presentation_clause(text)
    if _contains_cjk(text):
        for marker in ("，", "；", "。", "、"):
            head = text.split(marker, 1)[0].strip()
            if 4 <= len(head) <= 18:
                text = head
                break
    limit = 20 if _contains_cjk(text) else 54
    cleaned = _strip_terminal_ellipsis(
        _smart_clip_visible_text(text, limit).strip(" \t\r\n锛屻€傦紱锛氥€?:;-鈥斺€?")
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
    return str(value).rstrip(" .…鈥?").strip(" \t\r\n锛屻€傦紱锛氥€?:;-鈥斺€?")


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
    subtitle = (
        _text_shape(7, slide.subtitle, 720000, title_y + 860000, 9600000, 360000, 1600, fg)
        if slide.subtitle
        else ""
    )
    return (
        _text_shape(5, slide.title, 700000, title_y, 10200000, 820000, title_size, fg, bold=True)
        + subtitle
    )


def _hero_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    lead = blocks[0].content if blocks else slide.title
    support = blocks[1].content if len(blocks) > 1 else slide.speaker_notes
    subtitle = (
        _text_shape(13, slide.subtitle, 740000, 2550000, 5300000, 360000, 1500, accent, bold=True)
        if slide.subtitle
        else ""
    )
    return "\n".join(
        [
            _shape(10, "roundRect", 7800000, 720000, 3300000, 4800000, soft, alpha=22000, line=accent),
            _shape(11, "ellipse", 8400000, 900000, 2200000, 2200000, accent, alpha=52000),
            _text_shape(12, slide.title, 720000, 900000, 6500000, 1300000, 3900, fg, bold=True),
            subtitle,
            _card_shape(14, lead, 740000, 3300000, 6200000, 880000, soft, fg, accent),
            _card_shape(15, support, 740000, 4400000, 6200000, 880000, soft, fg, accent),
        ]
    )


def _editorial_cover_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    lead = blocks[0].content if blocks else slide.visual_intent
    support = blocks[1].content if len(blocks) > 1 else slide.speaker_notes
    return "\n".join(
        [
            _rect_shape(120, 720000, 760000, 900000, 48000, accent),
            _text_shape(121, slide.title, 720000, 1040000, 5600000, 1800000, 4100, fg, bold=True),
            _text_shape(122, slide.subtitle or lead, 760000, 3060000, 4700000, 620000, 1750, accent, bold=True),
            _card_shape(123, lead, 760000, 3940000, 4700000, 820000, soft, fg, accent),
            _text_shape(124, support, 7900000, 5150000, 3300000, 520000, 1350, fg, align="r"),
        ]
    )


def _architectural_cover_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    lead = blocks[0].content if blocks else slide.visual_intent
    return "\n".join(
        [
            _shape(125, "rect", 620000, 620000, 11000000, 5000000, soft, alpha=9000, line=accent),
            _rect_shape(126, 1160000, 1120000, 64000, 4050000, accent),
            _text_shape(127, slide.title, 1550000, 3400000, 7200000, 1250000, 3900, fg, bold=True),
            _text_shape(128, slide.subtitle or lead, 1580000, 4900000, 6700000, 460000, 1500, accent, bold=True),
            _shape(129, "ellipse", 9100000, 1050000, 1700000, 1700000, accent, alpha=36000),
        ]
    )


def _chapter_index_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    items = blocks[:4] or blocks[:1]
    rows = []
    for index, block in enumerate(items):
        y = 1880000 + index * 900000
        rows.extend(
            [
                _text_shape(132 + index * 3, f"{index + 1:02d}", 760000, y, 620000, 420000, 1750, accent, bold=True),
                _rect_shape(133 + index * 3, 1450000, y + 220000, 900000, 22000, accent),
                _text_shape(134 + index * 3, block.content, 2520000, y - 20000, 7600000, 560000, 1700, fg),
            ]
        )
    return "\n".join([_title_and_subtitle(slide, fg, title_y=420000, title_size=3000), *rows])


def _diagonal_story_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    lead = blocks[0].content if blocks else slide.title
    cards = blocks[1:4] or blocks[:1]
    return "\n".join(
        [
            _shape(145, "parallelogram", 0, 0, 6400000, SLIDE_CY, soft, alpha=33000),
            _text_shape(146, slide.title, 700000, 520000, 6000000, 1040000, 3100, fg, bold=True),
            _text_shape(147, lead, 920000, 2150000, 4650000, 1350000, 2250, fg, bold=True),
            *[
                _card_shape(148 + index, block.content, 7100000, 1350000 + index * 1120000, 4050000, 820000, soft, fg, accent)
                for index, block in enumerate(cards)
            ],
        ]
    )


def _statement_focus_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    statement = blocks[0].content if blocks else slide.title
    support = blocks[1:4]
    support_shapes = "\n".join(
        _card_shape(155 + index, block.content, 740000 + index * 3600000, 4700000, 3200000, 900000, soft, fg, accent)
        for index, block in enumerate(support)
    )
    return "\n".join(
        [
            _text_shape(153, slide.title, 720000, 540000, 10200000, 600000, 1800, accent, bold=True),
            _text_shape(154, statement, 720000, 1450000, 9800000, 2350000, 3600, fg, bold=True),
            support_shapes,
        ]
    )


def _proof_mosaic_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    cards = blocks[:4] or blocks[:1]
    positions = [(720000, 1900000, 3250000, 1250000), (4200000, 1900000, 2200000, 1250000), (720000, 3440000, 2200000, 1250000), (3140000, 3440000, 3250000, 1250000)]
    shapes = [
        _card_shape(160 + index, block.content, *positions[index], soft, fg, accent)
        for index, block in enumerate(cards[:4])
    ]
    return "\n".join([_title_and_subtitle(slide, fg, title_y=420000, title_size=2900), *shapes])


def _system_map_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    nodes = blocks[:5] or blocks[:1]
    positions = [(700000, 2050000), (8300000, 1900000), (780000, 4200000), (8300000, 4180000)]
    shapes = [
        _card_shape(166 + index, block.content, x, y, 3000000, 920000, soft, fg, accent)
        for index, (block, (x, y)) in enumerate(zip(nodes[1:5] or nodes[:1], positions))
    ]
    center = nodes[0].content if nodes else slide.title
    return "\n".join(
        [
            _title_and_subtitle(slide, fg, title_y=360000, title_size=2800),
            _shape(164, "ellipse", 4400000, 2050000, 3300000, 3300000, soft, alpha=44000, line=accent),
            _text_shape(165, center, 4900000, 3100000, 2300000, 1050000, 1850, fg, bold=True, align="ctr"),
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
            _shape(175, "roundRect", 720000, 1900000, 5100000, 3500000, "153B73", alpha=52000, line=accent),
            _shape(176, "roundRect", 6470000, 1900000, 5000000, 3500000, "6E2020", alpha=52000, line=accent),
            _text_shape(177, left_text, 1150000, 2600000, 4200000, 1950000, 1900, fg, bold=True),
            _text_shape(178, right_text, 6900000, 2600000, 4100000, 1950000, 1900, fg, bold=True),
            _shape(179, "ellipse", 5920000, 3170000, 360000, 360000, accent),
        ]
    )


def _priority_stack_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    items = blocks[:4] or blocks[:1]
    cards = []
    for index, block in enumerate(items):
        cards.append(
            _card_shape(
                180 + index,
                block.content,
                780000 + index * 620000,
                1900000 + index * 850000,
                8500000 - index * 620000,
                680000,
                soft,
                fg,
                accent,
            )
        )
    return "\n".join([_title_and_subtitle(slide, fg, title_y=390000, title_size=2900), *cards])


def _manifesto_close_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    takeaway = blocks[0].content if blocks else slide.speaker_notes
    return "\n".join(
        [
            _rect_shape(188, 780000, 820000, 72000, 5000000, accent),
            _text_shape(189, slide.title, 1280000, 1200000, 8800000, 1900000, 4300, fg, bold=True),
            _text_shape(190, takeaway, 1300000, 3620000, 7200000, 950000, 2000, fg),
            _shape(191, "ellipse", 9300000, 4050000, 1500000, 1500000, accent, alpha=39000),
        ]
    )


def _future_horizon_layout(slide, blocks: list, fg: str, accent: str, soft: str) -> str:
    takeaway = blocks[0].content if blocks else slide.speaker_notes
    supporting = blocks[1:4]
    cards = "\n".join(
        _card_shape(194 + index, block.content, 780000 + index * 3600000, 4550000, 3200000, 820000, soft, fg, accent)
        for index, block in enumerate(supporting)
    )
    return "\n".join(
        [
            _text_shape(192, slide.title, 920000, 1150000, 10100000, 1200000, 3900, fg, bold=True, align="ctr"),
            _text_shape(193, takeaway, 1950000, 2850000, 8300000, 720000, 1900, fg, align="ctr"),
            _rect_shape(198, 720000, 4120000, 10750000, 36000, accent),
            cards,
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
    line = _rect_shape(70, 1080000, 3350000, 9800000, 35000, accent)
    nodes = []
    for index, block in enumerate(events):
        x = 1080000 + index * 3100000
        nodes.extend(
            [
                _shape(71 + index * 3, "ellipse", x - 90000, 3260000, 220000, 220000, accent),
                _text_shape(72 + index * 3, f"{index + 1}", x - 62000, 3295000, 160000, 100000, 900, "111111", bold=True, align="ctr"),
                _card_shape(73 + index * 3, block.content, x - 360000, 3780000, 2200000, 1050000, soft, fg, accent),
            ]
        )
    return "\n".join([_title_and_subtitle(slide, fg, title_y=430000, title_size=3000), line, *nodes])


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
            _title_and_subtitle(slide, fg, title_y=430000, title_size=2900),
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
            _text_shape(111, slide.title, 1650000, 1600000, 8900000, 1100000, 3800, fg, bold=True, align="ctr"),
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
        "title" if bold and size >= 2400 else "subtitle" if bold or size >= 1700 else "body"
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
    font_scale = 65000 if inferred_role == "title" else 72000 if inferred_role == "subtitle" else 78000
    safe = html.escape(cleaned_text)
    bold_attr = ' b="1"' if bold else ""
    return f'''<p:sp>
  <p:nvSpPr><p:cNvPr id="{shape_id}" name="Text {shape_id}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>
  <p:txBody><a:bodyPr wrap="square" anchor="{anchor}" horzOverflow="clip" vertOverflow="clip" lIns="{inset_x}" tIns="{inset_y}" rIns="{inset_x}" bIns="{inset_y}"><a:normAutofit fontScale="{font_scale}" lnSpcReduction="18000"/></a:bodyPr><a:lstStyle/><a:p><a:pPr algn="{align}"/><a:r><a:rPr lang="zh-CN" sz="{font_size}"{bold_attr}><a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:latin typeface="Times New Roman"/><a:ea typeface="SimSun"/><a:cs typeface="Times New Roman"/></a:rPr><a:t>{safe}</a:t></a:r></a:p></p:txBody>
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
        '<a:srgbClr val="000000"><a:alpha val="18000"/></a:srgbClr>'
        "</a:outerShdw></a:effectLst>"
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
) -> str:
    safe_description = html.escape(_clean_visible_text(description, role="body"))
    safe_name = html.escape(_clean_visible_text(name, role="body") or "Visual Asset")
    preset = "roundRect" if rounded else "rect"
    chrome_xml = (
        '<a:ln w="9000"><a:solidFill><a:srgbClr val="FFFFFF"><a:alpha val="36000"/></a:srgbClr></a:solidFill></a:ln><a:effectLst><a:outerShdw blurRad="76200" dist="25400" dir="5400000" rotWithShape="0"><a:srgbClr val="000000"><a:alpha val="26000"/></a:srgbClr></a:outerShdw></a:effectLst>'
        if rounded
        else "<a:ln><a:noFill/></a:ln>"
    )
    return f'''<p:pic>
  <p:nvPicPr><p:cNvPr id="{shape_id}" name="{safe_name} {shape_id}" descr="{safe_description}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>
  <p:blipFill><a:blip r:embed="{rel_id}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>
  <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="{preset}"><a:avLst/></a:prstGeom>{chrome_xml}</p:spPr>
</p:pic>'''


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
    font_scale = 70000 if font_size <= 1180 else 78000 if font_size <= 1280 else 84000
    inset_x = 190000 if cx <= 2400000 else 240000
    inset_y = 105000 if cy <= 900000 or font_size <= 1180 else 125000
    effect_xml = (
        '<a:effectLst><a:outerShdw blurRad="76200" dist="38100" dir="5400000" rotWithShape="0">'
        '<a:srgbClr val="000000"><a:alpha val="22000"/></a:srgbClr>'
        "</a:outerShdw></a:effectLst>"
    )
    return f'''<p:sp>
  <p:nvSpPr><p:cNvPr id="{shape_id}" name="Card {shape_id}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="roundRect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="{fill}"><a:alpha val="94000"/></a:srgbClr></a:solidFill><a:ln w="12000"><a:solidFill><a:srgbClr val="{accent}"><a:alpha val="42000"/></a:srgbClr></a:solidFill></a:ln>{effect_xml}</p:spPr>
  <p:txBody><a:bodyPr wrap="square" anchor="{anchor}" horzOverflow="clip" vertOverflow="clip" lIns="{inset_x}" tIns="{inset_y}" rIns="{inset_x}" bIns="{inset_y}"><a:normAutofit fontScale="{font_scale}" lnSpcReduction="18000"/></a:bodyPr><a:lstStyle/>
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
        size = min(size, 1220)
    if compact:
        size = min(size, 1240)
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
