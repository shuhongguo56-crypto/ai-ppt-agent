import re
import zipfile
from pathlib import Path
from types import SimpleNamespace

from app.ai.models import GeneratedImage
from app.services import render as render_service
from app.services.render import SLIDE_CX, SLIDE_CY, _clean_visible_text, _compact_render_block_text


PROJECT = {
    "schemaVersion": "1.0.0",
    "projectId": "project-render",
    "inputLanguage": "zh",
    "outputLanguage": "en",
    "deckType": "course_presentation",
    "topic": "CRISPR",
    "audience": "Undergraduates",
    "mode": "professional",
}


FOREGROUND_SAFE_X = 460000
FOREGROUND_SAFE_TOP = 340000
FOREGROUND_SAFE_BOTTOM = 430000


def test_text_shape_fits_long_copy_inside_tighter_safe_area() -> None:
    text = (
        "This is an intentionally long strategic sentence that used to be placed into "
        "a tiny PowerPoint text box, causing clipped slideshow text and ugly overflow."
    )

    xml = render_service._text_shape(
        901,
        text,
        SLIDE_CX - 900000,
        SLIDE_CY - 380000,
        760000,
        120000,
        2200,
        role="body",
    )

    geometry = re.search(
        r'<a:off x="(-?\d+)" y="(-?\d+)"/><a:ext cx="(-?\d+)" cy="(-?\d+)"/>',
        xml,
    )
    assert geometry is not None
    x, y, cx, cy = [int(value) for value in geometry.groups()]
    assert x >= FOREGROUND_SAFE_X
    assert y >= FOREGROUND_SAFE_TOP
    assert x + cx <= SLIDE_CX - FOREGROUND_SAFE_X
    assert y + cy <= SLIDE_CY - FOREGROUND_SAFE_BOTTOM
    assert cy > 120000
    assert 'anchor="t"' in xml
    assert "<a:normAutofit" in xml


def test_text_shape_does_not_clip_before_layout_fit_when_space_allows() -> None:
    text = "瑞幸复兴的本质是信任修复、产品爆点、数字化复购与供应链复制形成增长飞轮"

    xml = render_service._text_shape(
        902,
        text,
        760000,
        740000,
        10100000,
        820000,
        2100,
        role="subtitle",
    )

    assert text in xml
    assert "…" not in xml
    assert "<a:normAutofit" in xml


def test_card_shape_preserves_meaningful_copy_when_frame_can_grow() -> None:
    text = "不是只靠一次营销，而是把产品创新、数字化运营、用户复购和供应链效率连成闭环。"

    xml = render_service._card_shape(
        903,
        text,
        900000,
        1200000,
        4300000,
        360000,
        "FFFFFF",
        "123B2B",
        "1FAE77",
    )

    assert "产品创新" in xml
    assert "供应链效率" in xml
    assert "…" not in xml
    geometry = re.search(
        r'<a:off x="(-?\d+)" y="(-?\d+)"/><a:ext cx="(-?\d+)" cy="(-?\d+)"/>',
        xml,
    )
    assert geometry is not None
    assert int(geometry.group(4)) > 360000


def test_premium_card_copy_keeps_complete_chinese_clause_before_comma() -> None:
    text = "门店扩张说明触达能力，但需要结合履约效率判断"

    compacted = render_service._premium_card_copy(text)

    assert compacted == "门店扩张说明触达能力"
    assert "但需要" not in compacted
    assert "…" not in compacted


def test_compact_render_block_prefers_complete_chinese_clause_over_half_sentence() -> None:
    slide = SimpleNamespace(title="作用机制", subtitle="")
    text = (
        "第二，它用小程序、App、门店数据和会员机制持续降低复购成本；"
        "第三，它通过联名、爆品和高频新品把咖啡从功能消费推向社交话题。"
    )

    compacted = _compact_render_block_text(text, slide, deck_title="瑞幸咖啡品牌复兴")

    assert compacted == "小程序、App、门店数据和会员机制持续降低复购成本"
    assert "…" not in compacted
    assert not compacted.startswith("第二")


def test_ppt_title_text_uses_section_label_for_long_colon_titles() -> None:
    title = "作用机制：它真正需要解决的不是“多做一次营销”，而是如何把产品创新、数字化运营连成系统"

    compact = render_service._ppt_title_text(title)
    assert compact.startswith("作用机制：")
    assert "多做一次营销" in compact
    assert len(compact) < len(title)


def test_high_risk_ai_image_prompt_avoids_interface_words() -> None:
    prompt = render_service._ai_image_generation_prompt(
        slide_index=3,
        query="growth dashboard chart diagram",
        image_type="data_visual",
        purpose="解释增长机制",
        image_prompt="data dashboard chart",
        slide_title="作用机制：增长飞轮",
        slide_intent="framework diagram for app user data",
        asset_role="diagram",
        image_treatment="masked_window",
        composition_archetype="system_map",
        direction_name="Product Showcase",
        palette=["#0F5132", "#F6F2E8"],
    )
    lowered = prompt.casefold()

    assert "abstract still life" in lowered
    for forbidden in ("dashboard", "diagram", "chart", "interface", "screen", "app", "website", "panel"):
        assert re.search(rf"\b{forbidden}s?\b", lowered) is None


def test_ai_image_prompt_treats_app_content_as_text_risk_even_for_product_images() -> None:
    prompt = render_service._ai_image_generation_prompt(
        slide_index=4,
        query="Luckin APP 小程序 member dashboard product showcase",
        image_type="product_showcase",
        purpose="解释 APP/小程序复购路径",
        image_prompt="premium product showcase with mobile app",
        slide_title="落地路径：APP/小程序复购",
        slide_intent="show app interface and member dashboard",
        asset_role="context",
        image_treatment="masked_window",
        composition_archetype="priority_stack",
        direction_name="Product Showcase",
        palette=["#0F5132", "#F6F2E8"],
    )
    lowered = prompt.casefold()

    assert "abstract still life" in lowered
    for forbidden in ("dashboard", "interface", "screen", "app", "website", "panel"):
        assert re.search(rf"\b{forbidden}s?\b", lowered) is None
    for forbidden in ("小程序", "界面", "屏幕", "网页", "面板", "图表", "仪表盘"):
        assert forbidden not in prompt


def test_ai_image_prompt_varies_safe_abstract_scene_by_slide() -> None:
    first_prompt = render_service._ai_image_generation_prompt(
        slide_index=2,
        query="growth dashboard chart diagram",
        image_type="data_visual",
        purpose="explain evidence",
        image_prompt="data dashboard chart",
        slide_title="Evidence logic",
        slide_intent="framework diagram for app user data",
        asset_role="diagram",
        image_treatment="masked_window",
        composition_archetype="system_map",
        direction_name="Product Showcase",
        palette=["#0F5132", "#F6F2E8"],
    )
    second_prompt = render_service._ai_image_generation_prompt(
        slide_index=3,
        query="growth dashboard chart diagram",
        image_type="data_visual",
        purpose="explain evidence",
        image_prompt="data dashboard chart",
        slide_title="Evidence logic",
        slide_intent="framework diagram for app user data",
        asset_role="diagram",
        image_treatment="masked_window",
        composition_archetype="system_map",
        direction_name="Product Showcase",
        palette=["#0F5132", "#F6F2E8"],
    )

    assert first_prompt != second_prompt
    assert "Variant " in first_prompt
    assert "Variant " in second_prompt


def create_renderable_deck(client) -> dict:
    assert client.post("/api/projects", json=PROJECT).status_code == 201
    outline = client.post("/api/projects/project-render/outline/generate", json={})
    assert outline.status_code == 200
    outline_confirmed = client.post(
        "/api/projects/project-render/outline/confirm",
        json={"outlineDecisionVersion": outline.json()["version"]},
    )
    assert outline_confirmed.status_code == 200
    visual = client.post(
        "/api/projects/project-render/visual-directions/generate",
        json={"outlineDecisionVersion": outline_confirmed.json()["version"]},
    )
    assert visual.status_code == 200
    direction_id = visual.json()["visualDirection"]["directions"][0]["directionId"]
    selected = client.post(
        "/api/projects/project-render/visual-directions/select",
        json={"visualDirectionVersion": visual.json()["version"], "directionId": direction_id},
    )
    assert selected.status_code == 200
    deck = client.post(
        "/api/projects/project-render/slide-deck/assemble",
        json={"visualDirectionVersion": selected.json()["version"]},
    )
    assert deck.status_code == 200
    return deck.json()


def _foreground_boxes(xml: str) -> list[tuple[str, int, int, int, int]]:
    boxes: list[tuple[str, int, int, int, int]] = []
    for shape in re.findall(r"<p:sp>.*?</p:sp>", xml, flags=re.DOTALL):
        name_match = re.search(r'<p:cNvPr id="\d+" name="([^"]+)"', shape)
        if not name_match:
            continue
        shape_name = name_match.group(1)
        if not (shape_name.startswith("Text ") or shape_name.startswith("Card ")):
            continue
        box_match = re.search(
            r'<a:off x="(-?\d+)" y="(-?\d+)"/><a:ext cx="(-?\d+)" cy="(-?\d+)"/>',
            shape,
        )
        if not box_match:
            continue
        boxes.append((shape_name, *[int(value) for value in box_match.groups()]))
    return boxes


def _font_size_for_shape(xml: str, shape_name: str) -> int:
    for shape in re.findall(r"<p:sp>.*?</p:sp>", xml, flags=re.DOTALL):
        if f'name="{shape_name}"' not in shape:
            continue
        size = re.search(r'\bsz="(\d+)"', shape)
        assert size is not None
        return int(size.group(1))
    raise AssertionError(f"shape not found: {shape_name}")


def test_render_visible_text_cleanup_compacts_titles_and_removes_encoding_damage() -> None:
    assert (
        _clean_visible_text("瑞幸咖啡品牌复兴与新消费增长策略", role="title")
        == "瑞幸咖啡品牌复兴与新消费增长策略"
    )
    assert (
        _clean_visible_text("AI可以指：人工智能 (Artificial Intelligence)", role="title")
        == "人工智能"
    )
    assert (
        _clean_visible_text("AI可以指：人工智能 (Artificial Intelligence) 在高等教育中的应用", role="title")
        == "人工智能在高等教育中的应用"
    )
    assert "????" not in _clean_visible_text("核心问题????需要确认", role="card")
    assert _clean_visible_text("人工智能在高等教育课程、评价、治理与学习支持中的系统性重构路径", role="title").endswith("…")


def test_render_compaction_keeps_required_quoted_business_concept() -> None:
    slide = SimpleNamespace(title="落地路径", subtitle="")
    text = "对投资人来说，瑞幸案例的价值在于它提供了一个“品牌修复 + 数字化零售 + 高频产品创新”的经营样本。"

    compacted = _compact_render_block_text(text, slide, deck_title="瑞幸咖啡品牌复兴与新消费增长策略")

    assert "一个的经营样本" not in compacted
    assert "品牌修复" in compacted


def test_render_compaction_drops_source_metadata_as_customer_copy() -> None:
    slide = SimpleNamespace(title="Conclusion", subtitle="")
    text = "Luckin Coffee (English: luckin coffee, OTC Pink: LKNCY) is a public encyclopedia source title."

    compacted = _compact_render_block_text(text, slide, deck_title="Luckin Coffee growth strategy")

    assert compacted == ""


def test_render_compaction_strips_outline_scaffold_from_customer_visible_copy() -> None:
    slide = SimpleNamespace(
        title="落地路径",
        subtitle="",
        blocks=[
            SimpleNamespace(
                block_type="body",
                content="第四部分：给品牌咨询客户提出可迁移方法：危机后信任修复、低摩擦购买路径、会员复购。",
            ),
            SimpleNamespace(
                block_type="card",
                content="可验证证据线索：财报中的门店扩张、收入结构、利润率、经营现金流和同店表现。",
            ),
            SimpleNamespace(
                block_type="card",
                content="行动优先级 2：行动：对投资人来说，瑞幸案例的价值在于它提供了一个“品牌修复 + 数字化零售 + 高频产品创新”的经营样本。",
            ),
            SimpleNamespace(
                block_type="card",
                content="Core message: make every slide read like a decision, not a prompt trace.",
            ),
        ],
    )

    visible = [
        block.content
        for block in render_service._content_blocks(
            slide,
            deck_title="瑞幸咖啡品牌复兴与新消费增长策略",
        )
    ]

    joined = "\n".join(visible)
    assert "第四部分" not in joined
    assert "可验证证据线索" not in joined
    assert "行动优先级" not in joined
    assert "行动：" not in joined
    assert "Core message" not in joined
    assert any("可迁移方法" in item for item in visible)
    assert any("财报中的门店扩张" in item for item in visible)
    assert any("品牌修复" in item for item in visible)
    assert any("decision" in item for item in visible)


def test_render_foreground_text_and_cards_stay_inside_slide(client) -> None:
    deck = create_renderable_deck(client)

    response = client.post(
        "/api/projects/project-render/render",
        json={"slideDeckVersion": deck["version"]},
    )

    assert response.status_code == 200
    pptx_path = Path(response.json()["renderResult"]["artifacts"][0]["path"])
    with zipfile.ZipFile(pptx_path) as archive:
        slide_xml = [
            archive.read(f"ppt/slides/slide{index}.xml").decode("utf-8")
            for index in range(1, len(deck["slideDeck"]["slides"]) + 1)
        ]
    for slide_number, xml in enumerate(slide_xml, start=1):
        for shape_name, x, y, cx, cy in _foreground_boxes(xml):
            assert x >= FOREGROUND_SAFE_X, (slide_number, shape_name, x, y, cx, cy)
            assert y >= FOREGROUND_SAFE_TOP, (slide_number, shape_name, x, y, cx, cy)
            assert x + cx <= SLIDE_CX - FOREGROUND_SAFE_X, (
                slide_number,
                shape_name,
                x,
                y,
                cx,
                cy,
            )
            assert y + cy <= SLIDE_CY - FOREGROUND_SAFE_BOTTOM, (
                slide_number,
                shape_name,
                x,
                y,
                cx,
                cy,
            )


def test_render_creates_pptx_and_hyperframes_from_same_slide_deck(client) -> None:
    deck = create_renderable_deck(client)

    response = client.post(
        "/api/projects/project-render/render",
        json={"slideDeckVersion": deck["version"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["stage"] == "render"
    assert payload["status"] == "complete"
    assert payload["nextStep"] == "quality"
    result = payload["renderResult"]
    artifacts = result["artifacts"]
    assert [artifact["target"] for artifact in artifacts] == ["pptx", "hyperframes_html"]
    assert {artifact["slideCount"] for artifact in artifacts} == {
        len(deck["slideDeck"]["slides"])
    }

    pptx_path = Path(artifacts[0]["path"])
    html_path = Path(artifacts[1]["path"])
    assert pptx_path.is_file()
    assert html_path.is_file()
    html = html_path.read_text(encoding="utf-8")
    assert "project-render" in html or "CRISPR" in html
    assert 'font-family: "Times New Roman", SimSun, "宋体", serif' in html
    assert "--type-title: clamp(30px, 3.55vw, 48px)" in html
    assert "--type-subtitle: clamp(17px, 1.85vw, 25px)" in html
    assert "--type-card: clamp(14px, 1.18vw, 17px)" in html
    assert "--content-w: min(560px, 47%)" in html
    assert "--image-left: 56%" in html
    assert "max-width: var(--content-w) !important" in html
    assert "inset: 10% 5% 10% var(--image-left) !important" in html
    assert "display: none !important" in html
    assert 'data-action="next"' in html
    assert 'data-action="present"' in html
    assert "全屏放映" in html
    assert "requestFullscreen" in html
    assert 'body[data-presenter="true"] .frame-inner' in html
    assert 'data-action="zoom-in"' in html
    assert 'data-action="fit"' in html
    assert 'name="generator" content="HyperFrames local renderer"' in html
    assert 'data-hyperframes-renderer="local"' in html
    assert 'data-motion-engine="HyperFrames"' in html
    assert 'data-deck-contract="SlideDeck JSON"' in html
    assert 'data-reference-style="cinematic-full-bleed"' in html
    assert 'data-design-system="' in html
    assert 'data-composition-archetype="' in html
    assert 'data-image-treatment="' in html
    assert 'data-motion-preset="' in html
    assert html.count('class="explainer-layer"') == len(deck["slideDeck"]["slides"])
    rendered_explanation_modes = re.findall(
        r'<div class="explainer-layer" data-explanation-mode="([^"]+)"', html
    )
    assert len(rendered_explanation_modes) == len(deck["slideDeck"]["slides"])
    assert 'class="explainer-node"' in html
    assert 'class="explainer-connector"' in html
    assert html.count('class="explainer-node"') <= len(deck["slideDeck"]["slides"]) * 3
    assert len(set(rendered_explanation_modes)) >= 3
    assert "presentation visual" not in html
    assert re.search(r'class="frame [^"]*composition-', html)
    assert 'class="frame-asset"' in html
    assert 'data-source-type="' in html
    assert 'data-image-plan-type="' in html
    assert 'data-image-plan-purpose="' in html
    assert 'data-provider-chain="' in html
    assert deck["slideDeck"]["imagePlan"][0]["imageType"] in html
    assert deck["slideDeck"]["imagePlan"][0]["searchQuery"] in html
    assert "@keyframes asset-float" in html
    assert "@keyframes block-rise" in html
    assert "@keyframes reference-light-sweep" in html
    assert "object-fit: cover" in html
    assert "position: absolute" in html
    assert "background: var(--bg);" in html
    assert "color-mix(in srgb, var(--accent)" in html
    assert "@media (prefers-reduced-motion: reduce)" in html
    assert 'class="dots"' in html
    assert 'aria-label="幻灯片导航"' in html
    assert "上一页" in html
    assert "下一页" in html
    assert "讲稿" in html
    assert ".brand span" in html
    assert "padding: 76px 4vw 46px" in html
    assert 'class="frame frame-hero ' in html
    assert ".frame-three_cards .blocks" in html
    assert "window.addEventListener('keydown'" in html
    assert "visual asset for" not in html
    assert len(set(re.findall(r'data-composition-archetype="([^"]+)"', html))) >= 3
    assert len(set(re.findall(r'data-image-treatment="([^"]+)"', html))) >= 2
    with zipfile.ZipFile(pptx_path) as archive:
        names = set(archive.namelist())
        content_types = archive.read("[Content_Types].xml").decode("utf-8")
        presentation_rels = archive.read("ppt/_rels/presentation.xml.rels").decode("utf-8")
        master = archive.read("ppt/slideMasters/slideMaster1.xml").decode("utf-8")
        slide1 = archive.read("ppt/slides/slide1.xml").decode("utf-8")
        slide1_rels = archive.read("ppt/slides/_rels/slide1.xml.rels").decode("utf-8")
        notes1 = archive.read("ppt/notesSlides/notesSlide1.xml").decode("utf-8")
        notes1_rels = archive.read("ppt/notesSlides/_rels/notesSlide1.xml.rels").decode("utf-8")
        slide2 = archive.read("ppt/slides/slide2.xml").decode("utf-8")
        slide5 = archive.read("ppt/slides/slide5.xml").decode("utf-8")
        slide_xml = [
            archive.read(f"ppt/slides/slide{index}.xml").decode("utf-8")
            for index in range(1, len(deck["slideDeck"]["slides"]) + 1)
        ]
        media_names = [name for name in names if name.startswith("ppt/media/")]
    assert "ppt/presentation.xml" in names
    assert {
        "ppt/presProps.xml",
        "ppt/viewProps.xml",
        "ppt/tableStyles.xml",
        "ppt/notesMasters/notesMaster1.xml",
        "ppt/notesMasters/_rels/notesMaster1.xml.rels",
        "ppt/theme/theme2.xml",
    } <= names
    assert "notesMaster+xml" in content_types
    assert "relationships/notesMaster" in presentation_rels
    assert "relationships/presProps" in presentation_rels
    assert "relationships/viewProps" in presentation_rels
    assert "relationships/tableStyles" in presentation_rels
    assert "relationships/notesMaster" in notes1_rels
    assert "Times New Roman" in master
    assert "SimSun" in master
    assert "Times New Roman" in slide1
    assert "SimSun" in slide1
    assert "Aptos" not in master + slide1
    assert "Microsoft YaHei" not in master + slide1
    cover_title_size = _font_size_for_shape(slide1, "Text 5")
    assert 2800 <= cover_title_size <= 3300
    cover_statement_size = _font_size_for_shape(slide1, "Text 25")
    assert 1460 <= cover_statement_size <= 1780
    cover_card_size = _font_size_for_shape(slide1, "Card 26")
    assert 1220 <= cover_card_size <= 1540
    assert int(re.search(r"<p:sldLayoutId id=\"(\d+)\"", master).group(1)) >= 2147483648
    assert "ppt/slides/slide1.xml" in names
    assert "ppt/slides/_rels/slide1.xml.rels" in names
    assert "ppt/notesSlides/notesSlide1.xml" in names
    assert "ppt/notesSlides/_rels/notesSlide1.xml.rels" in names
    assert "ppt/slideLayouts/_rels/slideLayout7.xml.rels" in names
    assert len(media_names) >= len(deck["slideDeck"]["slides"])
    assert "relationships/image" in slide1_rels
    assert "ppt/media/" not in slide1_rels
    assert "../media/" in slide1_rels
    assert "<p:pic>" in slide1
    assert "Reference Full-Bleed Visual" in slide1
    assert all("Page Visual " in xml for xml in slide_xml)
    assert "Image Agent " in slide1
    assert deck["slideDeck"]["imagePlan"][0]["imageType"] in slide1
    assert "F7FAF6" in slide1
    assert "10251F" in slide1
    assert "Page Plan cinematic_hero" in slide1 or "Page Plan editorial_cover" in slide1 or "Page Plan architectural_cover" in slide1
    assert all("Page Explainer " in xml for xml in slide_xml)
    assert all('name="Card 710"' not in xml for xml in slide_xml)
    assert all("<a:normAutofit" in xml for xml in slide_xml)
    assert all('horzOverflow="clip"' in xml for xml in slide_xml)
    assert all('vertOverflow="clip"' in xml for xml in slide_xml)
    assert all('anchor="mid"' not in xml for xml in slide_xml)
    assert all('anchor="ctr"' in xml for xml in slide_xml)
    assert deck["slideDeck"]["slides"][0]["designPlan"]["diagramLabels"][0] in slide1
    assert '<a:off x="0" y="0"/>' in slide1
    assert '<a:ext cx="12192000" cy="6858000"/>' in slide1
    assert "notesSlide1.xml" in slide1_rels
    assert "Explain how this slide advances" in notes1
    assert 'prst="ellipse"' in slide1
    assert "Explain how this slide advances" not in slide1
    assert "SECTION 02" not in slide2
    assert "EVIDENCE VIEW" not in slide5
    assert "Agenda Vertical Rhythm" in slide2
    assert "Framework Connector" in slide_xml[3]
    assert "Evidence Logic Rail" in slide5
    assert "Insight Pause Line" in slide_xml[5]
    assert "Closing Horizon" in slide_xml[-1]
    assert "CORE MESSAGE" not in slide1
    assert "WHAT TO EXPECT" not in slide1
    assert "MAIN TAKEAWAY" not in slide2
    assert "Thank you" not in "\n".join([slide1, slide2, slide5])
    assert "citation-" not in slide5
    assert "citation-" not in html
    assert "CORE MESSAGE" not in html
    assert "WHAT TO EXPECT" not in html
    assert 'class="role"' not in html
    assert 'prst="roundRect"' in slide5
    assert "outerShdw" in slide5


def test_open_visual_search_uses_wikipedia_page_images_without_bing_key(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AI_PPT_BING_IMAGE_SEARCH_KEY", raising=False)
    requested_urls: list[str] = []

    def fake_read_json_url(url: str, *, timeout: float, headers: dict[str, str] | None = None) -> dict:
        requested_urls.append(url)
        if "wikipedia.org" in url:
            return {
                "query": {
                    "pages": {
                        "1": {
                            "title": "Luckin Coffee",
                            "fullurl": "https://en.wikipedia.org/wiki/Luckin_Coffee",
                            "original": {"source": "https://upload.wikimedia.org/luckin.jpg"},
                        }
                    }
                }
            }
        return {}

    def fake_download_binary(url: str, path: Path, *, timeout: float) -> str:
        path.write_bytes(b"\xff\xd8\xff\x00")
        return "image/jpeg"

    monkeypatch.setattr(render_service, "_read_json_url", fake_read_json_url)
    monkeypatch.setattr(render_service, "_download_binary", fake_download_binary)

    asset = render_service._search_open_visual_asset(
        1,
        "结论：瑞幸咖啡（英语：luckin coffee）是真实商业案例",
        tmp_path,
        image_type="business_scene",
        purpose="用配图解释瑞幸咖啡的商业场景",
        prompt="瑞幸咖啡商业场景",
        provider_chain=["open_web_search"],
        timeout_seconds=0.2,
    )

    assert asset is not None
    assert asset.source_type == "wikipedia_page_image"
    assert asset.file_name.endswith(".jpg")
    assert asset.mime_type == "image/jpeg"
    assert "Luckin Coffee" in (asset.attribution or "")
    assert any("wikipedia.org" in url for url in requested_urls)


def test_ppt_render_compacts_and_deduplicates_visible_body_blocks() -> None:
    slide = SimpleNamespace(
        title="汇报路径",
        subtitle="品牌咨询客户和投资人",
        blocks=[
            SimpleNamespace(
                block_type="body",
                content="叙事路径：先说明“瑞幸咖啡品牌复兴与新消费增长策略”的核心问题与现实意义。",
            ),
            SimpleNamespace(
                block_type="card",
                content="叙事路径：先说明“瑞幸咖啡品牌复兴与新消费增长策略”的核心问题与现实意义。",
            ),
            SimpleNamespace(
                block_type="card",
                content="围绕“瑞幸咖啡品牌复兴与新消费增长策略”建立从背景、机制、证据到行动的因果链。",
            ),
            SimpleNamespace(
                block_type="card",
                content="2024 年研究《绿色消费趋势下日用品品牌环保策略与实践》",
            ),
            SimpleNamespace(
                block_type="card",
                content="绿色消费趋势下日用品品牌环保策略与实践",
            ),
            SimpleNamespace(
                block_type="body",
                content="背景：绿色消费趋势下日用品品牌环保策略与实践",
            ),
            SimpleNamespace(block_type="image_placeholder", content="不可见素材说明"),
        ],
    )

    blocks = render_service._content_blocks(slide, deck_title="瑞幸咖啡品牌复兴与新消费增长策略")
    visible = [block.content for block in blocks]

    assert visible == [
        "先说明核心问题与现实意义",
        "建立从背景、机制、证据到行动的因果链",
    ]
    assert all(slide.title not in item for item in visible)
    assert len(visible) == len(set(visible))


def test_ppt_explainer_layer_keeps_diagram_labels_out_of_visible_text() -> None:
    slide = SimpleNamespace(
        slide_index=3,
        design_plan=SimpleNamespace(
            explanation_mode="summary_map",
            composition_archetype="process_ribbon",
            diagram_labels=["汇报路径", "核心洞察", "行动建议"],
        ),
    )

    xml = render_service._explainer_shapes(slide, "F8F3E7", "F2BF4A", "111216")

    assert "汇报路径" not in xml
    assert "核心洞察" not in xml
    assert "行动建议" not in xml


def test_ppt_subtitle_filters_offtopic_research_titles() -> None:
    deck_title = "瑞幸咖啡品牌复兴与新消费增长策略"

    assert render_service._ppt_subtitle_text(
        "绿色消费趋势下日用品品牌环保策略与实践",
        deck_title,
    ) == ""
    assert render_service._ppt_subtitle_text(
        "瑞幸咖啡体验营销策略研究",
        deck_title,
    ) == "瑞幸咖啡体验营销策略研究"


def test_ppt_render_removes_audience_setup_phrases_from_cards() -> None:
    slide = SimpleNamespace(
        title="落地路径",
        subtitle="",
        blocks=[
            SimpleNamespace(
                block_type="body",
                content="面向品牌咨询客户和投资人，把瑞幸咖啡成功因素有很多，其中利用体验营销强调品牌与消费者之间联系。",
            )
        ],
    )

    blocks = render_service._content_blocks(
        slide,
        deck_title="瑞幸咖啡品牌复兴与新消费增长策略",
    )

    assert [block.content for block in blocks] == [
        "瑞幸咖啡成功因素有很多，其中利用体验营销强调品牌与消费者之间联系"
    ]


def test_ai_visual_generation_uses_retry_budget_for_free_image_providers(tmp_path, monkeypatch) -> None:
    captured = {}

    class CapturingImageGateway:
        def generate(self, request):
            captured["request"] = request
            return GeneratedImage(
                bytes=b"\xff\xd8\xff\xe0free-image",
                mime_type="image/jpeg",
                width=request.width,
                height=request.height,
                model="pollinations-free:pollinations:flux",
            )

    asset = render_service._generate_visual_asset_with_ai(
        1,
        "Luckin Coffee premium product scene",
        tmp_path,
        CapturingImageGateway(),
        image_type="product_showcase",
        purpose="解释品牌复兴",
        image_prompt="premium brand presentation visual",
        provider_chain=["Pollinations FLUX API"],
        slide_title="品牌复兴",
        slide_intent="用真实/生成图片解释增长策略",
        asset_role="hero",
        image_treatment="masked_window",
        composition_archetype="editorial_cover",
        direction_name="Product Showcase",
        palette=["#0F5132", "#F6F2E8"],
    )

    assert asset is not None
    assert asset.source_type == "free_ai_fallback"
    assert asset.path.exists()
    assert captured["request"].timeout_seconds >= 90
    assert captured["request"].max_attempts == 2
    assert "ABSOLUTELY NO visible text" in captured["request"].prompt
    assert "digital devices, data graphics, or pseudo-writing" in captured["request"].prompt

    monkeypatch.setenv("AI_PPT_ALLOW_RISKY_FREE_AI_IMAGES", "true")
    asset = render_service._generate_visual_asset_with_ai(
        1,
        "Luckin Coffee premium product scene",
        tmp_path,
        CapturingImageGateway(),
        image_type="product_showcase",
        purpose="解释品牌复兴",
        image_prompt="premium brand presentation visual",
        provider_chain=["Pollinations FLUX API"],
        slide_title="品牌复兴",
        slide_intent="用真实生成图片解释增长策略",
        asset_role="hero",
        image_treatment="masked_window",
        composition_archetype="editorial_cover",
        direction_name="Product Showcase",
        palette=["#0F5132", "#F6F2E8"],
    )

    assert asset is not None
    assert asset.source_type == "free_ai_fallback"


def test_visual_asset_resolution_retries_until_replacement_is_unique(tmp_path) -> None:
    generated_bytes = [
        b"\xff\xd8\xff\xe0shared-image",
        b"\xff\xd8\xff\xe0shared-image",
        b"\xff\xd8\xff\xe0shared-image",
        b"\xff\xd8\xff\xe0page-specific-image",
    ]

    class SequenceImageGateway:
        def __init__(self) -> None:
            self.requests = []

        def generate(self, request):
            self.requests.append(request)
            content = generated_bytes[len(self.requests) - 1]
            return GeneratedImage(
                bytes=content,
                mime_type="image/jpeg",
                width=request.width,
                height=request.height,
                model="gpt-image-2",
            )

    def slide(slide_index: int):
        return SimpleNamespace(
            slide_index=slide_index,
            title=f"Slide {slide_index}",
            visual_intent=f"Explain page-specific idea {slide_index}",
            design_plan=SimpleNamespace(
                asset_role="hero",
                image_treatment="masked_window",
                composition_archetype="editorial_cover",
            ),
        )

    def image_plan(slide_index: int):
        return SimpleNamespace(
            slide=slide_index,
            search_query="shared search result",
            image_type="business_scene",
            purpose=f"Explain slide {slide_index}",
            prompt=f"Page-specific visual {slide_index}",
            provider_chain=["OpenAI Image API"],
        )

    deck = SimpleNamespace(
        slides=[slide(1), slide(2)],
        image_plan=[image_plan(1), image_plan(2)],
        theme=SimpleNamespace(name="Enterprise Editorial", palette=["#111111", "#F2BF4A"]),
    )
    gateway = SequenceImageGateway()

    assets = render_service.resolve_visual_assets(
        deck,
        tmp_path,
        gateway,
        mode="generate",
        image_search_enabled=False,
    )

    assert len(gateway.requests) == 4
    assert assets[1].path.read_bytes() == generated_bytes[0]
    assert assets[2].path.read_bytes() == generated_bytes[3]
    assert render_service._visual_asset_hash(assets[1].path) != render_service._visual_asset_hash(
        assets[2].path
    )
    assert "Unique visual alternative 2 for slide 2" in gateway.requests[-1].prompt


def test_render_requires_confirmed_slide_deck_and_fresh_version(client) -> None:
    missing_project = client.post(
        "/api/projects/missing/render",
        json={"slideDeckVersion": 1},
    )
    assert missing_project.status_code == 404
    assert missing_project.json()["error"]["code"] == "project_not_found"

    assert client.post("/api/projects", json=PROJECT).status_code == 201
    missing_deck = client.post(
        "/api/projects/project-render/render",
        json={"slideDeckVersion": 1},
    )
    assert missing_deck.status_code == 404
    assert missing_deck.json()["error"]["code"] == "slide_deck_not_found"


def test_render_rejects_stale_slide_deck_version(client) -> None:
    deck = create_renderable_deck(client)

    stale = client.post(
        "/api/projects/project-render/render",
        json={"slideDeckVersion": deck["version"] + 1},
    )

    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "checkpoint_version_conflict"
