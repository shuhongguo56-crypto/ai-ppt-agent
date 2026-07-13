from __future__ import annotations

import re
from typing import Any

from ai_ppt_contracts import OutlineDecision


PROVIDER_CHAIN = [
    "open_web_search",
    "OpenAI Image API",
    "Pollinations FLUX API",
    "Midjourney API",
    "Stable Diffusion API",
    "custom image2 API",
    "local_png_fallback",
]

IMAGE_TYPE_HINTS = {
    "background": "premium presentation atmosphere, cinematic depth, clean texture, no text",
    "course_review_atmosphere": "university classroom learning review atmosphere, students, lecture hall, no text",
    "business_scene": "professional business meeting scene, strategy workshop, modern office, no text",
    "classical_element": "traditional Chinese classical visual element, ink landscape, heritage texture, no text",
    "thesis_concept": "research paper university concept illustration, knowledge graph, lab/library, no text",
    "product_showcase": "premium product showcase, elegant studio lighting, no text",
    "icon_illustration": "abstract symbolic objects, geometric metaphor, no text, no UI, no screens",
    "data_visual": "abstract evidence metaphor with physical tokens, light beams and layered shapes, no text, no UI, no dashboards",
}


def build_image_plan(
    *,
    outline: OutlineDecision,
    deck_slides: list[dict[str, Any]],
    direction_name: str,
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for outline_slide, deck_slide in zip(outline.slides, deck_slides, strict=True):
        design_plan = deck_slide["designPlan"]
        slide_title = str(deck_slide.get("title") or outline_slide.title)
        image_type = _image_type(
            deck_type=outline.deck_type,
            purpose=str(outline_slide.purpose),
            title=slide_title,
            key_point=outline_slide.key_point,
            asset_role=str(design_plan["assetRole"]),
            archetype=str(design_plan["compositionArchetype"]),
        )
        search_query = _search_query(
            topic=outline.slides[0].title,
            title=slide_title,
            key_point=outline_slide.key_point,
            purpose=str(outline_slide.purpose),
            visual_brief=str(design_plan["visualBrief"]),
            image_type=image_type,
        )
        prompt = _prompt(
            image_type=image_type,
            direction_name=direction_name,
            title=slide_title,
            key_point=outline_slide.key_point,
            visual_intent=outline_slide.visual_intent,
            asset_role=str(design_plan["assetRole"]),
            image_treatment=str(design_plan["imageTreatment"]),
            composition=str(design_plan["compositionArchetype"]),
        )
        plan.append(
            {
                "schemaVersion": "1.0.0",
                "slide": outline_slide.slide_index,
                "needsImage": True,
                "imageType": image_type,
                "prompt": prompt,
                "purpose": _purpose(
                    language=outline.language,
                    asset_role=str(design_plan["assetRole"]),
                    title=slide_title,
                    key_point=outline_slide.key_point,
                ),
                "searchQuery": search_query,
                "providerChain": PROVIDER_CHAIN,
            }
        )
    return plan


def _image_type(
    *,
    deck_type: str,
    purpose: str,
    title: str,
    key_point: str,
    asset_role: str,
    archetype: str,
) -> str:
    content = f"{title} {key_point}".casefold()
    if any(marker in content for marker in ("古风", "诗词", "国风", "传统文化", "history", "heritage", "classical")):
        return "classical_element"
    if any(
        marker in content
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
            "门店",
            "连锁",
            "零售",
            "消费",
            "商业模式",
        )
    ):
        if purpose in {"agenda", "framework"} or archetype in {"chapter_index", "system_map"}:
            return "icon_illustration"
        if purpose in {"evidence", "insight"} or archetype in {"data_landscape", "proof_mosaic"}:
            return "data_visual"
        return "product_showcase" if purpose in {"cover", "recommendation", "conclusion"} else "business_scene"
    if deck_type == "business_pitch":
        if purpose in {"agenda", "framework"} or archetype in {"chapter_index", "system_map"}:
            return "icon_illustration"
        if purpose in {"evidence", "insight"} or archetype in {"data_landscape", "proof_mosaic"}:
            return "data_visual"
        return "product_showcase" if purpose in {"cover", "recommendation"} else "business_scene"
    if purpose == "cover":
        return "background"
    if deck_type == "course_presentation" and purpose in {"agenda", "conclusion"}:
        return "course_review_atmosphere"
    if purpose == "evidence" and archetype == "data_landscape":
        return "data_visual"
    if deck_type in {"thesis_defense", "research_report"} or purpose in {"evidence", "framework"}:
        return "thesis_concept"
    if asset_role in {"diagram", "metaphor"}:
        return "icon_illustration"
    return "background"


def _prompt(
    *,
    image_type: str,
    direction_name: str,
    title: str,
    key_point: str,
    visual_intent: str,
    asset_role: str,
    image_treatment: str,
    composition: str,
) -> str:
    prompt_parts = [
        "premium 16:9 presentation visual for PPT and HyperFrames",
        f"image type: {image_type}",
        f"slide title: {_clean_title_intent(title)}",
        f"core message: {_clean(key_point)}",
        f"visual intent: {_clean(visual_intent)}",
        f"asset role: {asset_role}",
        f"composition: {composition}",
        f"image treatment: {image_treatment}",
        f"art direction: {_clean(direction_name)}",
        IMAGE_TYPE_HINTS[image_type],
        "content-serving visual, explain the slide idea rather than decorating it",
        "award-winning corporate presentation standard, brand-uniform, balanced, judge-ready",
        "premium keynote quality, layered foreground/midground/background, cinematic depth",
        "strong contrast hierarchy with deliberate negative space and a single focal subject",
        "no visible text, no labels, no logos, no watermark",
        "leave clean negative space for editable PowerPoint text and cards",
    ]
    return _clip_prompt_text(" | ".join(part for part in prompt_parts if part), 1000)


def _purpose(*, language: str, asset_role: str, title: str, key_point: str) -> str:
    if language == "zh":
        return _clip(
            f"服务 {asset_role} 内容：用配图解释《{_clean(title)}》这一页的核心判断——{_clean(key_point)}",
            260,
        )
    return _clip(
        f"Serves {asset_role} content by visualizing the slide claim: {_clean(title)} — {_clean(key_point)}",
        260,
    )


def _search_query(
    *,
    topic: str,
    title: str,
    key_point: str,
    purpose: str,
    visual_brief: str,
    image_type: str,
) -> str:
    raw = _clean(f"{topic} {title} {key_point}")
    subject = _primary_subject(raw)
    slide_focus = _clean(
        " ".join(
            part
            for part in [
                _compact_query(title, 48),
                _compact_query(key_point, 72),
                _compact_query(visual_brief, 48),
            ]
            if part
        )
    )
    compact = _clean(f"{subject} {purpose} {slide_focus}") if subject else _compact_query(raw, 140)
    intent = IMAGE_TYPE_HINTS[image_type]
    if image_type in {"business_scene", "product_showcase"}:
        intent = "store product business scene photo, real-world brand context, no text"
    return _clip(_clean(f"{compact} {intent}"), 220)


def _primary_subject(value: str) -> str:
    aliases = [
        alias.strip(" ,，;；")
        for alias in re.findall(
            r"(?:英语|英文|English)\s*[:：]\s*([A-Za-z][A-Za-z0-9 .&'’\-]{2,80})",
            value,
            flags=re.IGNORECASE,
        )
    ]
    without_parentheses = re.sub(r"[（(][^）)]{0,120}[）)]", " ", value)
    first_clause = re.split(r"[。；;？！!?，,：:|/\\]", without_parentheses, maxsplit=1)[0]
    first_clause = _strip_outline_scaffold(first_clause)
    first_clause = _clip(first_clause, 36)
    if aliases:
        alias = _clip(aliases[0], 36)
        if first_clause and alias.casefold() not in first_clause.casefold():
            return _clip(f"{first_clause} {alias}", 78)
        return alias or first_clause
    return first_clause


def _compact_query(value: str, limit: int) -> str:
    value = re.sub(r"\s*[（(][A-Za-z][A-Za-z0-9 ,./&:;+\-]{2,120}[）)]", "", value).strip()
    value = re.sub(r"\s*（\s*(?:英语|英文|English)\s*[:：][^）]{2,120}）", "", value, flags=re.IGNORECASE)
    value = re.sub(r"AI\s*可以指\s*[：:]\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\?{3,}", " ", value)
    value = value.replace("\ufffd", " ")
    value = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", value)
    return _clip(value, limit)


def _clean(value: str) -> str:
    value = str(value).replace("\ufffd", " ")
    value = re.sub(r"\?{3,}", " ", value)
    return _strip_outline_scaffold(re.sub(r"\s+", " ", value).strip())


def _clean_title_intent(value: str) -> str:
    cleaned = str(value).replace("\ufffd", " ")
    cleaned = re.sub(r"\?{3,}", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) <= 80:
        return cleaned
    return cleaned[:79].rstrip() + "…"


def _clip_prompt_text(value: str, limit: int) -> str:
    cleaned = str(value).replace("\ufffd", " ")
    cleaned = re.sub(r"\?{3,}", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


_CJK_NUMERAL_RE = r"[零〇一二三四五六七八九十百千万两\d]+"


def _strip_outline_scaffold(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    for _ in range(4):
        before = cleaned
        cleaned = re.sub(
            rf"^第\s*{_CJK_NUMERAL_RE}\s*(?:部分|章节|章|节|页|张|步|阶段|幕|层|点)\s*[：:\-—–]\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            rf"^行动优先级\s*{_CJK_NUMERAL_RE}\s*[：:\-—–]\s*(?:行动\s*[：:\-—–]\s*)?",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"^(?:"
            r"文章先回答的问题|原文线索|页面作用|可引用证据|可验证证据线索|证据线索|"
            r"讲解时可参考摘录|叙事路径|核心判断|核心问题|背景|洞察|行动|证据|结论|建议|主题|"
            r"Source claim|Slide role|Traceable evidence|Useful excerpt|Core message|Main takeaway"
            r")\s*[：:\-—–]\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            rf"(^|[\s，,。；;：:、（(《“\"'—–-])第\s*{_CJK_NUMERAL_RE}\s*(?:部分|章节|章|节|页|张|步|阶段|幕|层|点)\s*[：:]\s*",
            r"\1",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            rf"(^|[\s，,。；;：:、（(《“\"'—–-])行动优先级\s*{_CJK_NUMERAL_RE}\s*[：:\-—–]\s*(?:行动\s*[：:\-—–]\s*)?",
            r"\1",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"(^|[\s，,。；;：:、（(《“\"'—–-])(?:"
            r"文章先回答的问题|原文线索|页面作用|可引用证据|可验证证据线索|证据线索|"
            r"讲解时可参考摘录|叙事路径|核心判断|核心问题|背景|洞察|行动|证据|结论|建议|主题|"
            r"Source claim|Slide role|Traceable evidence|Useful excerpt|Core message|Main takeaway"
            r")\s*[：:]\s*",
            r"\1",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = cleaned.strip(" \t\r\n，。；：、,:;-—–")
        if cleaned == before:
            break
    return cleaned


def _clip(value: str, limit: int) -> str:
    value = _clean(value)
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"
