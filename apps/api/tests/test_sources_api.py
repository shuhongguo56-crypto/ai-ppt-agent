import base64
import io
import zipfile
import zlib


PROJECT = {
    "schemaVersion": "1.0.0",
    "projectId": "project-source",
    "inputLanguage": "zh",
    "outputLanguage": "zh",
    "deckType": "course_presentation",
    "topic": "AI in classroom presentations",
    "audience": "Undergraduates",
    "mode": "professional",
}


def encoded(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def create_project(client) -> None:
    assert client.post("/api/projects", json=PROJECT).status_code == 201


def extract(client, file_name: str, data: bytes, content_type: str | None = None):
    return client.post(
        "/api/projects/project-source/sources/extract",
        json={
            "fileName": file_name,
            "contentType": content_type,
            "dataBase64": encoded(data),
        },
    )


def warning_codes(payload: dict) -> set[str]:
    return {warning["code"] for warning in payload.get("warnings", [])}


def make_docx(parts: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, xml in parts.items():
            archive.writestr(name, xml)
    return output.getvalue()


def make_pptx(slides: dict[int, str | bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for slide_number, xml in slides.items():
            archive.writestr(f"ppt/slides/slide{slide_number}.xml", xml)
    return output.getvalue()


def text_docx_xml(text: str) -> str:
    return (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )


def text_pptx_xml(text: str) -> str:
    return (
        '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        f"<a:t>{text}</a:t></p:sld>"
    )


def simple_pdf_with_text(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = zlib.compress(f"BT ({escaped}) Tj ET".encode("utf-8"))
    return (
        b"%PDF-1.4\n1 0 obj<</Filter/FlateDecode/Length "
        + str(len(stream)).encode("ascii")
        + b">>stream\n"
        + stream
        + b"\nendstream\nendobj\n%%EOF"
    )


def test_extract_text_source_pack(client) -> None:
    create_project(client)

    response = extract(client, "notes.md", "人工智能会改变课程汇报结构。".encode("utf-8"))

    assert response.status_code == 200
    payload = response.json()
    source = payload["sourcePack"]["sources"][0]
    assert payload["sourcePack"]["projectId"] == "project-source"
    assert payload["extractedChars"] >= 10
    assert source["sourceType"] == "text"
    assert source["title"] == "notes.md"
    assert "课程汇报" in source["summary"]


def test_extract_source_builds_structured_reading_report(client) -> None:
    create_project(client)
    article = """
# Sleep and Learning in First-Year Students

The article argues that stable sleep is not a wellness bonus but a learning infrastructure.
In a 2025 campus survey of 1,200 first-year students, learners sleeping less than six hours
reported 31% lower recall in morning seminars and missed more collaborative checkpoints.
The central problem is that students treat slide preparation as a late-night task, so the
presentation quality collapses exactly when synthesis and rehearsal are needed.
The article recommends a three-part intervention: earlier outline locking, shorter rehearsal
loops, and instructor feedback before the final deck export.
"""

    response = extract(client, "sleep-learning.md", article.encode("utf-8"), "text/markdown")

    assert response.status_code == 200
    summary = response.json()["sourcePack"]["sources"][0]["summary"]
    assert "文章主旨：" in summary
    assert "关键论点：" in summary
    assert "重要事实/数据/证据：" in summary
    assert "可做成PPT的大纲建议：" in summary
    assert "stable sleep is not a wellness bonus" in summary
    assert "1,200 first-year students" in summary
    assert "31% lower recall" in summary


def test_extract_preserves_user_structured_chinese_brief(client) -> None:
    create_project(client)
    article = """
核心主题：瑞幸咖啡品牌复兴与新消费增长策略
文章主旨：瑞幸咖啡的复兴应被拆解为信任修复、数字化履约、产品矩阵、门店密度、会员复购与资本市场预期共同作用的增长飞轮。
关键论点：
- 信任修复是叙事起点：治理、透明度、稳定履约和持续产品体验共同重建用户心智。
- 产品矩阵决定复购深度：爆品、季节限定、联名和价格带共同承担拉新与复购。
- 门店密度与数字化履约是增长底盘：App 下单、即时取货和供应链效率让购买路径更短。
重要事实/数据/证据：
- 可验证证据线索：财报中的门店扩张、收入结构、利润率和经营现金流。
- 可验证证据线索：App/会员体系、上新节奏、联名传播、门店密度和供应链履约表现。
可做成PPT的大纲建议：
- 第一部分：从“为什么瑞幸值得重新讨论”切入，区分声量复苏和经营复苏。
- 第二部分：拆解增长飞轮：信任修复、产品矩阵、门店密度、数字化履约、会员复购。
原文摘录：
- 瑞幸真正改变的不是“咖啡是否便宜”，而是把咖啡购买变成一种低摩擦、高频、可被数字化运营的日常消费。
""".strip()

    response = extract(client, "luckin-brief.txt", article.encode("utf-8"), "text/plain")

    assert response.status_code == 200
    summary = response.json()["sourcePack"]["sources"][0]["summary"]
    assert "核心主题：瑞幸咖啡品牌复兴与新消费增长策略" in summary
    assert "信任修复是叙事起点" in summary
    assert "产品矩阵决定复购深度" in summary
    assert "门店密度与数字化履约是增长底盘" in summary
    assert "拆解增长飞轮" in summary
    assert "原文没有明显数字型证据" not in summary


def test_extract_docx_and_pptx_sources(client) -> None:
    create_project(client)

    docx = io.BytesIO()
    with zipfile.ZipFile(docx, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>DOCX 资料重点</w:t></w:r></w:p></w:body></w:document>",
        )
    pptx = io.BytesIO()
    with zipfile.ZipFile(pptx, "w") as archive:
        archive.writestr(
            "ppt/slides/slide1.xml",
            '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            "<a:t>PPTX 页面重点</a:t></p:sld>",
        )

    docx_response = extract(client, "source.docx", docx.getvalue())
    pptx_response = extract(client, "slides.pptx", pptx.getvalue())

    assert docx_response.status_code == 200
    assert "DOCX 资料重点" in docx_response.json()["sourcePack"]["sources"][0]["summary"]
    assert pptx_response.status_code == 200
    pptx_summary = pptx_response.json()["sourcePack"]["sources"][0]["summary"]
    assert "PPT视觉参考指纹" in pptx_summary
    assert "页数" in pptx_summary
    assert "PPTX 页面重点" in pptx_response.json()["sourcePack"]["sources"][0]["summary"]


def test_extract_large_docx_reports_partial_truncation(client) -> None:
    create_project(client)
    early = "EARLY_DOCX_ARGUMENT stable sleep supports classroom synthesis. "
    late = " LATE_DOCX_SENTINEL should not be analyzed."
    body = early + ("DOCX repeated evidence about learning outcomes. " * 1300) + late
    docx = make_docx({"word/document.xml": text_docx_xml(body)})

    response = extract(client, "large-source.docx", docx)

    assert response.status_code == 200
    payload = response.json()
    summary = payload["sourcePack"]["sources"][0]["summary"]
    assert payload["truncated"] is True
    assert payload["understandingStatus"] == "partial"
    assert payload["coverage"]["unit"] == "parts"
    assert payload["coverage"]["analyzedChars"] <= 30_000
    assert "analysis_char_limit" in warning_codes(payload)
    assert "EARLY_DOCX_ARGUMENT" in summary
    assert "LATE_DOCX_SENTINEL" not in summary


def test_extract_docx_reports_malformed_part_without_losing_valid_text(client) -> None:
    create_project(client)
    docx = make_docx(
        {
            "word/document.xml": text_docx_xml("VALID_DOCX_TEXT argues the source can still be used."),
            "word/footnotes.xml": (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>Broken footnote"
            ),
        }
    )

    response = extract(client, "malformed-footnote.docx", docx)

    assert response.status_code == 200
    payload = response.json()
    assert payload["understandingStatus"] == "partial"
    assert payload["coverage"]["failed"] == 1
    assert "malformed_xml_part" in warning_codes(payload)
    assert "VALID_DOCX_TEXT" in payload["sourcePack"]["sources"][0]["summary"]


def test_extract_large_pptx_reports_partial_truncation(client) -> None:
    create_project(client)
    slides = {
        index: text_pptx_xml(
            f"Slide {index} repeated PPTX evidence argues for a careful outline. "
            + ("supporting detail " * 180)
        )
        for index in range(1, 25)
    }

    response = extract(client, "large-deck.pptx", make_pptx(slides))

    assert response.status_code == 200
    payload = response.json()
    assert payload["truncated"] is True
    assert payload["understandingStatus"] == "partial"
    assert payload["coverage"]["unit"] == "slides"
    assert payload["coverage"]["processed"] < payload["coverage"]["discovered"]
    assert "analysis_char_limit" in warning_codes(payload)


def test_extract_pptx_reports_malformed_slide_without_losing_valid_slides(client) -> None:
    create_project(client)
    pptx = make_pptx(
        {
            1: text_pptx_xml("VALID_PPTX_SLIDE argues the deck has enough readable material."),
            2: (
                '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:t>Broken slide'
            ),
        }
    )

    response = extract(client, "malformed-slide.pptx", pptx)

    assert response.status_code == 200
    payload = response.json()
    assert payload["understandingStatus"] == "partial"
    assert payload["coverage"]["failed"] == 1
    assert "malformed_xml_part" in warning_codes(payload)
    assert "VALID_PPTX_SLIDE" in payload["sourcePack"]["sources"][0]["summary"]


def test_extract_pptx_uses_natural_slide_order(client) -> None:
    create_project(client)
    pptx = make_pptx(
        {
            10: text_pptx_xml("Slide 10 late appendix explains procurement evidence."),
            2: text_pptx_xml("Slide 2 natural order opening argues the main thesis."),
        }
    )

    response = extract(client, "natural-order.pptx", pptx)

    assert response.status_code == 200
    summary = response.json()["sourcePack"]["sources"][0]["summary"]
    assert summary.index("Slide 2 natural order opening") < summary.index("Slide 10 late appendix")


def test_extract_large_pdf_reports_partial_truncation(client) -> None:
    create_project(client)
    early = "EARLY_PDF_ARGUMENT stable sleep supports classroom synthesis. "
    late = " LATE_PDF_SENTINEL should not be analyzed."
    body = early + ("PDF repeated evidence about learning outcomes. " * 1300) + late

    response = extract(client, "large-paper.pdf", simple_pdf_with_text(body), "application/pdf")

    assert response.status_code == 200
    payload = response.json()
    summary = payload["sourcePack"]["sources"][0]["summary"]
    assert payload["truncated"] is True
    assert payload["understandingStatus"] == "partial"
    assert payload["coverage"]["analyzedChars"] <= 30_000
    assert "analysis_char_limit" in warning_codes(payload)
    assert "EARLY_PDF_ARGUMENT" in summary
    assert "LATE_PDF_SENTINEL" not in summary


def test_extract_malformed_pdf_returns_structured_error(client) -> None:
    create_project(client)

    response = extract(client, "broken.pdf", b"%PDF-1.4\nnot actually a readable pdf", "application/pdf")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "source_file_invalid"


def test_extract_simple_pdf_source(client) -> None:
    create_project(client)
    stream = zlib.compress(b"BT (PDF source text for AI PPT) Tj ET")
    pdf = (
        b"%PDF-1.4\n1 0 obj<</Filter/FlateDecode/Length "
        + str(len(stream)).encode("ascii")
        + b">>stream\n"
        + stream
        + b"\nendstream\nendobj\n%%EOF"
    )

    response = extract(client, "paper.pdf", pdf, "application/pdf")

    assert response.status_code == 200
    assert "PDF source text" in response.json()["sourcePack"]["sources"][0]["summary"]


def test_extract_rejects_missing_project_and_unsupported_type(client) -> None:
    missing = client.post(
        "/api/projects/missing/sources/extract",
        json={
            "fileName": "notes.txt",
            "dataBase64": encoded(b"hello"),
        },
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "project_not_found"

    create_project(client)
    unsupported = extract(client, "archive.zip", b"PK")
    assert unsupported.status_code == 415
    assert unsupported.json()["error"]["code"] == "source_type_unsupported"
