from __future__ import annotations

import html
import zipfile
from pathlib import Path

from ai_ppt_contracts import RenderResult, SlideDeck


def render_slide_deck(
    *,
    deck: SlideDeck,
    slide_deck_version: int,
    output_root: Path,
) -> RenderResult:
    render_dir = output_root / "renders" / deck.project_id / f"slide-deck-v{slide_deck_version}"
    render_dir.mkdir(parents=True, exist_ok=True)
    pptx_path = render_dir / "deck.pptx"
    html_path = render_dir / "hyperframes.html"
    _write_pptx(deck, pptx_path)
    _write_hyperframes_html(deck, html_path)
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


def _write_hyperframes_html(deck: SlideDeck, path: Path) -> None:
    slides = []
    for slide in deck.slides:
        blocks = "\n".join(
            f'<div class="block block-{html.escape(block.block_type)}">'
            f'<span class="role">{html.escape(block.role)}</span>'
            f'<p>{html.escape(block.content)}</p>'
            "</div>"
            for block in slide.blocks
        )
        slides.append(
            f"""
            <section class="frame" data-slide="{slide.slide_index}">
              <div class="frame-inner">
                <p class="eyebrow">{html.escape(slide.purpose)} · {html.escape(slide.layout)}</p>
                <h1>{html.escape(slide.title)}</h1>
                {f'<h2>{html.escape(slide.subtitle)}</h2>' if slide.subtitle else ''}
                <div class="blocks">{blocks}</div>
                <aside>{html.escape(slide.speaker_notes)}</aside>
              </div>
            </section>
            """
        )
    palette = deck.theme.palette
    content = f"""<!doctype html>
<html lang="{html.escape(deck.language)}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(deck.title)}</title>
  <style>
    :root {{
      --bg: {html.escape(palette[0])};
      --fg: {html.escape(palette[1])};
      --accent: {html.escape(palette[2])};
      --soft: {html.escape(palette[-1])};
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--fg);
      background: radial-gradient(circle at 20% 10%, var(--soft), transparent 28%), var(--bg);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      scroll-snap-type: y mandatory;
    }}
    .frame {{
      min-height: 100vh;
      padding: 6vh 7vw;
      display: grid;
      place-items: center;
      scroll-snap-align: start;
    }}
    .frame-inner {{
      width: min(1180px, 100%);
      min-height: 72vh;
      padding: 56px;
      border: 1px solid color-mix(in srgb, var(--fg), transparent 78%);
      border-radius: 36px;
      background: color-mix(in srgb, var(--bg), transparent 18%);
      box-shadow: 0 32px 100px rgba(0,0,0,.28);
      backdrop-filter: blur(18px);
    }}
    .eyebrow, .role {{ color: var(--accent); text-transform: uppercase; letter-spacing: .14em; font-size: 12px; }}
    h1 {{ font-size: clamp(46px, 7vw, 92px); line-height: .95; margin: 16px 0 20px; }}
    h2 {{ font-size: clamp(22px, 3vw, 36px); opacity: .78; font-weight: 500; }}
    .blocks {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 18px; margin-top: 42px; }}
    .block {{ padding: 22px; border-radius: 24px; background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.18); }}
    .block p {{ font-size: 20px; line-height: 1.4; margin: 10px 0 0; }}
    aside {{ margin-top: 34px; opacity: .58; font-size: 15px; }}
  </style>
</head>
<body>
  {"".join(slides)}
</body>
</html>
"""
    path.write_text(content, encoding="utf-8")


def _write_pptx(deck: SlideDeck, path: Path) -> None:
    slide_count = len(deck.slides)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types(slide_count))
        archive.writestr("_rels/.rels", _root_rels())
        archive.writestr("ppt/presentation.xml", _presentation(slide_count))
        archive.writestr("ppt/_rels/presentation.xml.rels", _presentation_rels(slide_count))
        archive.writestr("ppt/slideMasters/slideMaster1.xml", _slide_master())
        archive.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", _slide_master_rels())
        archive.writestr("ppt/slideLayouts/slideLayout1.xml", _slide_layout())
        archive.writestr("ppt/theme/theme1.xml", _theme())
        archive.writestr("docProps/core.xml", _core_props(deck))
        archive.writestr("docProps/app.xml", _app_props(slide_count))
        for index, slide in enumerate(deck.slides, start=1):
            archive.writestr(f"ppt/slides/slide{index}.xml", _slide_xml(slide.title, [block.content for block in slide.blocks], slide.speaker_notes))


def _content_types(slide_count: int) -> str:
    slides = "\n".join(
        f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        for i in range(1, slide_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  {slides}
</Types>'''


def _root_rels() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''


def _presentation(slide_count: int) -> str:
    slide_ids = "\n".join(
        f'<p:sldId id="{255 + i}" r:id="rId{i}"/>' for i in range(1, slide_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId{slide_count + 1}"/></p:sldMasterIdLst>
  <p:sldIdLst>{slide_ids}</p:sldIdLst>
  <p:sldSz cx="12192000" cy="6858000" type="wide"/>
  <p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>'''


def _presentation_rels(slide_count: int) -> str:
    slides = "\n".join(
        f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>'
        for i in range(1, slide_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  {slides}
  <Relationship Id="rId{slide_count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>
</Relationships>'''


def _slide_xml(title: str, blocks: list[str], notes: str) -> str:
    body = "\n".join(_text_shape(i + 2, text, 700000, 1650000 + i * 560000, 10600000, 420000, 2200) for i, text in enumerate(blocks[:7]))
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree>
    <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>
    {_text_shape(1, title, 700000, 520000, 10600000, 900000, 3600)}
    {body}
    {_text_shape(99, notes, 700000, 6100000, 10600000, 420000, 1200)}
  </p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>'''


def _text_shape(shape_id: int, text: str, x: int, y: int, cx: int, cy: int, size: int) -> str:
    safe = html.escape(text)
    return f'''<p:sp>
  <p:nvSpPr><p:cNvPr id="{shape_id}" name="Text {shape_id}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>
  <p:txBody><a:bodyPr wrap="square"/><a:lstStyle/><a:p><a:r><a:rPr lang="en-US" sz="{size}"/><a:t>{safe}</a:t></a:r></a:p></p:txBody>
</p:sp>'''


def _slide_master() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
  <p:sldLayoutIdLst><p:sldLayoutId id="1" r:id="rId1"/></p:sldLayoutIdLst>
  <p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles>
</p:sldMaster>'''


def _slide_master_rels() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>'''


def _slide_layout() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">
  <p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>
</p:sldLayout>'''


def _theme() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="AI PPT Agent"><a:themeElements><a:clrScheme name="Agent"><a:dk1><a:srgbClr val="111111"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="222222"/></a:dk2><a:lt2><a:srgbClr val="EEEEEE"/></a:lt2><a:accent1><a:srgbClr val="5B8DEF"/></a:accent1><a:accent2><a:srgbClr val="FF5A5F"/></a:accent2><a:accent3><a:srgbClr val="7BD88F"/></a:accent3><a:accent4><a:srgbClr val="FFD166"/></a:accent4><a:accent5><a:srgbClr val="9B5DE5"/></a:accent5><a:accent6><a:srgbClr val="00BBF9"/></a:accent6><a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink></a:clrScheme><a:fontScheme name="Agent"><a:majorFont><a:latin typeface="Aptos Display"/></a:majorFont><a:minorFont><a:latin typeface="Aptos"/></a:minorFont></a:fontScheme><a:fmtScheme name="Agent"><a:fillStyleLst/><a:lnStyleLst/><a:effectStyleLst/><a:bgFillStyleLst/></a:fmtScheme></a:themeElements></a:theme>'''


def _core_props(deck: SlideDeck) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{html.escape(deck.title)}</dc:title><dc:creator>AI PPT Agent</dc:creator></cp:coreProperties>'''


def _app_props(slide_count: int) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>AI PPT Agent</Application><Slides>{slide_count}</Slides></Properties>'''

