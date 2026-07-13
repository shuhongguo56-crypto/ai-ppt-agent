from __future__ import annotations

import base64
import hashlib
import html
import io
import re
import zipfile
import zlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Callable, Literal
from xml.etree import ElementTree

from ai_ppt_contracts import SourcePack
from app.errors import PublicError

try:  # pypdf is declared as a project dependency, but keep a recovery path for local stale venvs.
    from pypdf import PdfReader
except Exception:  # pragma: no cover - exercised in environments without the optional import.
    PdfReader = None  # type: ignore[assignment]


MAX_UPLOAD_BYTES = 60 * 1024 * 1024
MAX_EXTRACTED_CHARS = 30_000
SUMMARY_CHARS = 12_000
MAX_ZIP_XML_PART_BYTES = 8 * 1024 * 1024
MAX_ZIP_XML_TOTAL_BYTES = 24 * 1024 * 1024
MAX_ZIP_COMPRESSION_RATIO = 250
MAX_FINGERPRINT_XML_BYTES = 2 * 1024 * 1024
MAX_WARNING_UNITS = 12
PPTX_SLIDE_CX = 12192000
PPTX_SLIDE_CY = 6858000


@dataclass
class ExtractionWarning:
    code: str
    message: str
    affected_units: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "affectedUnits": self.affected_units,
        }


@dataclass
class ExtractionCoverage:
    unit: str
    discovered: int | None = None
    processed: int = 0
    failed: int = 0
    skipped: int = 0
    analyzed_chars: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "unit": self.unit,
            "discovered": self.discovered,
            "processed": self.processed,
            "failed": self.failed,
            "skipped": self.skipped,
            "analyzedChars": self.analyzed_chars,
        }


@dataclass
class ExtractionOutcome:
    text: str
    coverage: ExtractionCoverage
    warnings: list[ExtractionWarning] = field(default_factory=list)
    truncated: bool = False


@dataclass
class SourceExtractionResult:
    source_pack: SourcePack
    extracted_chars: int
    truncated: bool
    understanding_status: Literal["complete", "partial"]
    coverage: dict[str, object]
    warnings: list[dict[str, object]]


@dataclass
class TextCollector:
    limit: int
    parts: list[str] = field(default_factory=list)
    chars: int = 0
    truncated: bool = False

    def append(self, text: str) -> None:
        if self.truncated or not text:
            return
        remaining = self.limit - self.chars
        if remaining <= 0:
            self.truncated = True
            return
        if len(text) > remaining:
            self.parts.append(text[:remaining])
            self.chars += remaining
            self.truncated = True
            return
        self.parts.append(text)
        self.chars += len(text)

    def text(self) -> str:
        return "\n".join(self.parts)

_STOPWORDS = {
    "about",
    "after",
    "also",
    "because",
    "between",
    "could",
    "from",
    "have",
    "into",
    "more",
    "that",
    "their",
    "there",
    "this",
    "through",
    "with",
    "would",
    "一个",
    "一种",
    "以及",
    "但是",
    "因此",
    "因为",
    "如果",
    "我们",
    "可以",
    "对于",
    "这个",
    "这些",
    "通过",
}

_CLAIM_MARKERS = (
    "主张",
    "认为",
    "指出",
    "表明",
    "说明",
    "显示",
    "强调",
    "关键",
    "核心",
    "问题",
    "挑战",
    "机会",
    "风险",
    "建议",
    "结论",
    "影响",
    "原因",
    "结果",
    "therefore",
    "however",
    "shows",
    "suggests",
    "argues",
    "indicates",
    "because",
    "challenge",
    "risk",
    "opportunity",
    "recommend",
    "conclusion",
)

_EVIDENCE_MARKERS = (
    "研究",
    "数据",
    "调查",
    "样本",
    "实验",
    "比例",
    "增长",
    "下降",
    "超过",
    "少于",
    "案例",
    "年份",
    "study",
    "data",
    "survey",
    "sample",
    "experiment",
    "percent",
    "increase",
    "decrease",
    "case",
)


def extract_source_pack(
    *,
    project_id: str,
    file_name: str,
    content_type: str | None,
    data_base64: str,
) -> SourceExtractionResult:
    file_bytes = _decode_upload(data_base64)
    safe_name = _safe_file_name(file_name)
    suffix = PurePath(safe_name).suffix.lower()
    outcome = _extract_text(file_bytes, suffix=suffix, content_type=content_type)
    normalized = _normalize_text(outcome.text)
    if not normalized:
        raise PublicError(
            "source_text_empty",
            "No readable text could be extracted from this source.",
            422,
        )
    truncated = outcome.truncated or len(normalized) > MAX_EXTRACTED_CHARS
    analysis_text = normalized[:MAX_EXTRACTED_CHARS]
    warnings = list(outcome.warnings)
    if truncated and not _has_warning(warnings, "analysis_char_limit"):
        warnings.append(
            ExtractionWarning(
                "analysis_char_limit",
                f"Only the first {MAX_EXTRACTED_CHARS} readable characters were analyzed.",
            )
        )
    outcome.coverage.analyzed_chars = len(analysis_text)
    if outcome.coverage.unit == "characters":
        outcome.coverage.processed = len(analysis_text)
        if truncated and outcome.coverage.discovered is not None:
            outcome.coverage.skipped = max(0, outcome.coverage.discovered - len(analysis_text))
    understanding_status: Literal["complete", "partial"] = (
        "partial"
        if truncated or warnings or outcome.coverage.failed > 0 or outcome.coverage.skipped > 0
        else "complete"
    )
    summary = _source_analysis_summary(
        analysis_text,
        safe_name=safe_name,
        truncated=truncated,
    )
    source_id = "file-" + hashlib.sha256(
        safe_name.encode("utf-8") + b"\0" + file_bytes[:4096]
    ).hexdigest()[:16]
    source_type: Literal["text", "document"] = "text" if suffix in {".txt", ".md"} else "document"
    return SourceExtractionResult(
        source_pack=SourcePack(
            schemaVersion="1.0.0",
            projectId=project_id,
            sources=[
                {
                    "schemaVersion": "1.0.0",
                    "sourceId": source_id,
                    "sourceType": source_type,
                    "title": safe_name,
                    "summary": summary,
                }
            ],
        ),
        extracted_chars=len(analysis_text),
        truncated=truncated,
        understanding_status=understanding_status,
        coverage=outcome.coverage.as_dict(),
        warnings=[warning.as_dict() for warning in warnings],
    )


def _decode_upload(data_base64: str) -> bytes:
    if not isinstance(data_base64, str) or not data_base64.strip():
        raise PublicError("source_payload_invalid", "Uploaded source payload is invalid.", 422)
    try:
        decoded = base64.b64decode(data_base64, validate=True)
    except ValueError:
        raise PublicError("source_payload_invalid", "Uploaded source payload is invalid.", 422) from None
    if not decoded:
        raise PublicError("source_file_empty", "Uploaded source file is empty.", 422)
    if len(decoded) > MAX_UPLOAD_BYTES:
        raise PublicError("source_file_too_large", "Uploaded source file is too large.", 413)
    return decoded


def _safe_file_name(file_name: str) -> str:
    name = PurePath(file_name or "uploaded-source").name.strip()
    if not name:
        return "uploaded-source"
    return name[:160]


def _extract_text(file_bytes: bytes, *, suffix: str, content_type: str | None) -> ExtractionOutcome:
    if suffix in {".txt", ".md"} or (content_type or "").startswith("text/"):
        return _extract_plain_text(file_bytes)
    if suffix == ".docx":
        return _extract_docx(file_bytes)
    if suffix == ".pptx":
        return _extract_pptx(file_bytes)
    if suffix == ".pdf" or content_type == "application/pdf":
        return _extract_pdf(file_bytes)
    raise PublicError(
        "source_type_unsupported",
        "Supported source files are .txt, .md, .docx, .pptx, and .pdf.",
        415,
    )


def _has_warning(warnings: list[ExtractionWarning], code: str) -> bool:
    return any(warning.code == code for warning in warnings)


def _extract_plain_text(file_bytes: bytes) -> ExtractionOutcome:
    text = _decode_text(file_bytes)
    collector = TextCollector(MAX_EXTRACTED_CHARS)
    collector.append(text)
    return ExtractionOutcome(
        text=collector.text(),
        coverage=ExtractionCoverage(
            unit="characters",
            discovered=len(text),
            processed=collector.chars,
            skipped=max(0, len(text) - collector.chars),
        ),
        truncated=collector.truncated,
    )


def _decode_text(file_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("utf-8", errors="ignore")


def _extract_docx(file_bytes: bytes) -> ExtractionOutcome:
    xml_names = [
        "word/document.xml",
        "word/footnotes.xml",
        "word/endnotes.xml",
    ]
    return _extract_zip_xml_text(file_bytes, xml_names, tag_suffixes=("}t",), unit="parts")


def _extract_pptx(file_bytes: bytes) -> ExtractionOutcome:
    with _open_zip(file_bytes) as archive:
        slide_names = sorted(
            (name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
            key=_pptx_slide_number,
        )
        outcome = _extract_zip_xml_text_from_archive(
            archive,
            slide_names,
            tag_suffixes=("}t",),
            unit="slides",
            label_for_name=_pptx_slide_label,
        )
        collector = TextCollector(MAX_EXTRACTED_CHARS)
        collector.append(outcome.text)
        if not collector.truncated:
            visual_fingerprint = _pptx_visual_fingerprint(archive, slide_names, warnings=outcome.warnings)
            if visual_fingerprint:
                collector.append("\n\n" + visual_fingerprint if collector.parts else visual_fingerprint)
        return ExtractionOutcome(
            text=collector.text(),
            coverage=outcome.coverage,
            warnings=outcome.warnings,
            truncated=outcome.truncated or collector.truncated,
        )


def _pptx_slide_number(name: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", name)
    return int(match.group(1)) if match else 0


def _pptx_slide_label(name: str) -> str:
    return f"slide {_pptx_slide_number(name)}"


def _pptx_visual_fingerprint(
    archive: zipfile.ZipFile,
    slide_names: list[str],
    *,
    warnings: list[ExtractionWarning],
) -> str:
    names = archive.namelist()
    media_names = [name for name in names if name.startswith("ppt/media/")]
    media_ext = Counter(PurePath(name).suffix.lower().lstrip(".") or "unknown" for name in media_names)
    color_counts: Counter[str] = Counter()
    font_counts: Counter[str] = Counter()
    slide_summaries: list[str] = []
    full_bleed_slides = 0
    pictured_slides = 0
    transition_count = 0
    timing_count = 0
    for slide_position, slide_name in enumerate(slide_names, start=1):
        xml = _read_bounded_zip_text(archive, slide_name, warnings=warnings, label=_pptx_slide_label(slide_name))
        if xml is None:
            continue
        color_counts.update(f"#{match.upper()}" for match in re.findall(r'<a:srgbClr[^>]*\bval="([0-9A-Fa-f]{6})"', xml))
        font_counts.update(_pptx_fonts_from_xml(xml))
        pic_count = xml.count("<p:pic")
        shape_count = xml.count("<p:sp")
        text_count = xml.count("<a:t>")
        max_coverage = _pptx_max_picture_coverage(xml)
        if pic_count:
            pictured_slides += 1
        if max_coverage >= 0.82:
            full_bleed_slides += 1
        if "<p:transition" in xml:
            transition_count += 1
        if "<p:timing" in xml or "<p:tnLst" in xml:
            timing_count += 1
        if slide_position <= 8:
            slide_summaries.append(
                f"第 {slide_position} 页：文字块 {text_count}，形状 {shape_count}，图片 {pic_count}，最大图片覆盖 {max_coverage:.0%}"
            )
    for name in ["ppt/theme/theme1.xml", *[item for item in names if item.startswith("ppt/slideMasters/") and item.endswith(".xml")]]:
        if name in names:
            xml = _read_bounded_zip_text(archive, name, warnings=warnings, label=name)
            if xml is None:
                continue
            color_counts.update(f"#{match.upper()}" for match in re.findall(r'<a:srgbClr[^>]*\bval="([0-9A-Fa-f]{6})"', xml))
            font_counts.update(_pptx_fonts_from_xml(xml))

    top_colors = [color for color, _ in color_counts.most_common(8)]
    top_fonts = [font for font, _ in font_counts.most_common(6)]
    media_summary = "、".join(f"{ext} {count}" for ext, count in media_ext.most_common()) or "无"
    style_hints = _pptx_style_hints(
        top_colors=top_colors,
        top_fonts=top_fonts,
        full_bleed_slides=full_bleed_slides,
        slide_count=len(slide_names),
    )
    lines = [
        "PPT视觉参考指纹：",
        f"- 页数：{len(slide_names)}",
        f"- 媒体资源：{len(media_names)}（{media_summary}）",
        f"- 主色：{'、'.join(top_colors) if top_colors else '未检测到显式色值'}",
        f"- 字体：{'、'.join(top_fonts) if top_fonts else '未检测到显式字体'}",
        f"- 图片密度：{pictured_slides}/{len(slide_names)} 页含图片，{full_bleed_slides}/{len(slide_names)} 页接近全屏图",
        f"- 动效判断：检测到 {transition_count} 页 transition，{timing_count} 页 timing；若缺少 timing，应在 HyperFrames HTML 中补足光扫、景深、错峰入场和键盘翻页。",
        f"- 视觉建议：{style_hints}",
    ]
    if slide_summaries:
        lines.append("- 页面结构抽样：" + "；".join(slide_summaries))
    return "\n".join(lines)


def _pptx_fonts_from_xml(xml: str) -> list[str]:
    fonts = []
    for font in re.findall(r'\btypeface="([^"]+)"', xml):
        cleaned = html.unescape(font).strip()
        if cleaned:
            fonts.append(cleaned)
    return fonts


def _pptx_max_picture_coverage(xml: str) -> float:
    max_coverage = 0.0
    for pic_xml in re.findall(r"<p:pic\b.*?</p:pic>", xml, flags=re.DOTALL):
        xfrm = re.search(
            r"<a:xfrm>.*?<a:off\b[^>]*\bx=\"(-?\d+)\"[^>]*\by=\"(-?\d+)\"[^>]*/>.*?<a:ext\b[^>]*\bcx=\"(\d+)\"[^>]*\bcy=\"(\d+)\"[^>]*/>",
            pic_xml,
            flags=re.DOTALL,
        )
        if not xfrm:
            continue
        cx = int(xfrm.group(3))
        cy = int(xfrm.group(4))
        coverage = min(1.0, max(0.0, (cx * cy) / (PPTX_SLIDE_CX * PPTX_SLIDE_CY)))
        max_coverage = max(max_coverage, coverage)
    return max_coverage


def _pptx_style_hints(
    *,
    top_colors: list[str],
    top_fonts: list[str],
    full_bleed_slides: int,
    slide_count: int,
) -> str:
    colors = set(top_colors)
    hints: list[str] = []
    if full_bleed_slides >= max(1, slide_count // 3):
        hints.append("保留 full-bleed 主图和深色遮罩")
    if {"#F2BF4A", "#A92323", "#1F67D2"} & colors:
        hints.append("延续金色强调、红蓝对撞光场")
    if {"#000000", "#111216", "#080A0F"} & colors:
        hints.append("使用暗色电影感底色")
    if any("YaHei" in font or "雅黑" in font for font in top_fonts):
        hints.append("中文优先使用 Microsoft YaHei / 系统无衬线")
    if not hints:
        hints.append("从参考 PPT 中提取配色、字体、图片比例和版式密度后再生成视觉方案")
    return "；".join(hints)


def _open_zip(file_bytes: bytes) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile:
        raise PublicError("source_file_invalid", "Uploaded source file is invalid.", 422) from None


def _extract_zip_xml_text(
    file_bytes: bytes,
    xml_names: list[str],
    *,
    tag_suffixes: tuple[str, ...],
    unit: str,
) -> ExtractionOutcome:
    with _open_zip(file_bytes) as archive:
        return _extract_zip_xml_text_from_archive(archive, xml_names, tag_suffixes=tag_suffixes, unit=unit)


def _extract_zip_xml_text_from_archive(
    archive: zipfile.ZipFile,
    xml_names: list[str],
    *,
    tag_suffixes: tuple[str, ...],
    unit: str,
    label_for_name: Callable[[str], str] | None = None,
) -> ExtractionOutcome:
    available = [name for name in xml_names if name in archive.namelist()]
    coverage = ExtractionCoverage(unit=unit, discovered=len(available))
    warnings: list[ExtractionWarning] = []
    collector = TextCollector(MAX_EXTRACTED_CHARS)
    cumulative_xml_bytes = 0
    label_for_name = label_for_name or (lambda name: name)

    for index, name in enumerate(available):
        if collector.truncated:
            coverage.skipped += len(available) - index
            break
        label = label_for_name(name)
        try:
            info = archive.getinfo(name)
        except KeyError:
            coverage.skipped += 1
            warnings.append(ExtractionWarning("zip_part_missing", "A referenced document part was missing.", [label]))
            continue

        skip_warning = _zip_xml_skip_warning(info, label)
        if skip_warning is not None:
            coverage.skipped += 1
            warnings.append(skip_warning)
            continue
        cumulative_xml_bytes += info.file_size
        if cumulative_xml_bytes > MAX_ZIP_XML_TOTAL_BYTES:
            coverage.skipped += len(available) - index
            warnings.append(
                ExtractionWarning(
                    "zip_xml_budget_exceeded",
                    "The document contains more XML than this local parser will scan in one source.",
                    [label],
                )
            )
            break

        try:
            with archive.open(info) as stream:
                _append_xml_text(stream, tag_suffixes=tag_suffixes, collector=collector)
        except ElementTree.ParseError:
            coverage.failed += 1
            warnings.append(ExtractionWarning("malformed_xml_part", "A document XML part was malformed.", [label]))
            continue
        except (RuntimeError, OSError, zipfile.BadZipFile):
            coverage.failed += 1
            warnings.append(ExtractionWarning("zip_part_unreadable", "A document XML part could not be read.", [label]))
            continue
        coverage.processed += 1
        if collector.truncated:
            remaining = len(available) - index - 1
            coverage.skipped += max(0, remaining)
            warnings.append(
                ExtractionWarning(
                    "analysis_char_limit",
                    f"Only the first {MAX_EXTRACTED_CHARS} readable characters were analyzed.",
                    [label],
                )
            )
            break

    return ExtractionOutcome(
        text=collector.text(),
        coverage=coverage,
        warnings=warnings,
        truncated=collector.truncated,
    )


def _zip_xml_skip_warning(info: zipfile.ZipInfo, label: str) -> ExtractionWarning | None:
    if info.file_size > MAX_ZIP_XML_PART_BYTES:
        return ExtractionWarning(
            "zip_part_too_large",
            "A document XML part was too large to scan safely.",
            [label],
        )
    if info.compress_size and info.file_size > 1_000_000:
        ratio = info.file_size / max(info.compress_size, 1)
        if ratio > MAX_ZIP_COMPRESSION_RATIO:
            return ExtractionWarning(
                "zip_part_suspicious_compression",
                "A document XML part had suspicious compression and was skipped.",
                [label],
            )
    return None


def _append_xml_text(stream: object, *, tag_suffixes: tuple[str, ...], collector: TextCollector) -> None:
    for _, element in ElementTree.iterparse(stream, events=("end",)):
        if element.text and any(element.tag.endswith(suffix) for suffix in tag_suffixes):
            collector.append(element.text)
            if collector.truncated:
                element.clear()
                return
        element.clear()


def _read_bounded_zip_text(
    archive: zipfile.ZipFile,
    name: str,
    *,
    warnings: list[ExtractionWarning],
    label: str,
) -> str | None:
    try:
        info = archive.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_FINGERPRINT_XML_BYTES:
        warnings.append(
            ExtractionWarning(
                "zip_part_too_large",
                "A visual-reference XML part was too large to scan safely.",
                [label],
            )
        )
        return None
    try:
        return archive.read(info).decode("utf-8", errors="ignore")
    except (RuntimeError, OSError, zipfile.BadZipFile):
        warnings.append(
            ExtractionWarning(
                "zip_part_unreadable",
                "A visual-reference XML part could not be read.",
                [label],
            )
        )
        return None


def _extract_pdf(file_bytes: bytes) -> ExtractionOutcome:
    if PdfReader is None:
        fallback = _extract_pdf_stream_fallback(file_bytes)
        if fallback.text.strip():
            return fallback
        raise PublicError("source_file_invalid", "Uploaded PDF could not be read.", 422)
    try:
        outcome = _extract_pdf_with_pypdf(file_bytes)
    except PublicError:
        raise
    except Exception:
        fallback = _extract_pdf_stream_fallback(file_bytes)
        if fallback.text.strip():
            return fallback
        raise PublicError("source_file_invalid", "Uploaded PDF could not be read.", 422) from None
    if outcome.text.strip():
        return outcome
    fallback = _extract_pdf_stream_fallback(file_bytes)
    if fallback.text.strip():
        return fallback
    return outcome


def _extract_pdf_with_pypdf(file_bytes: bytes) -> ExtractionOutcome:
    reader = PdfReader(io.BytesIO(file_bytes), strict=False)  # type: ignore[operator]
    if reader.is_encrypted:
        try:
            decrypt_result = reader.decrypt("")
        except Exception:
            decrypt_result = 0
        if not decrypt_result:
            raise PublicError("source_file_encrypted", "Uploaded PDF is encrypted and cannot be read.", 422)

    pages = list(reader.pages)
    coverage = ExtractionCoverage(unit="pages", discovered=len(pages))
    warnings: list[ExtractionWarning] = []
    collector = TextCollector(MAX_EXTRACTED_CHARS)
    empty_pages: list[str] = []
    failed_pages: list[str] = []

    for index, page in enumerate(pages, start=1):
        if collector.truncated:
            coverage.skipped += len(pages) - index + 1
            break
        label = f"page {index}"
        try:
            page_text = page.extract_text() or ""
        except Exception:
            coverage.failed += 1
            failed_pages.append(label)
            continue
        if page_text.strip():
            collector.append(page_text)
            coverage.processed += 1
        else:
            coverage.skipped += 1
            empty_pages.append(label)
        if collector.truncated:
            remaining = len(pages) - index
            coverage.skipped += max(0, remaining)
            warnings.append(
                ExtractionWarning(
                    "analysis_char_limit",
                    f"Only the first {MAX_EXTRACTED_CHARS} readable characters were analyzed.",
                    [label],
                )
            )
            break

    if failed_pages:
        warnings.append(
            ExtractionWarning(
                "pdf_page_extract_failed",
                "Some PDF pages could not be extracted.",
                _limited_units(failed_pages),
            )
        )
    if empty_pages:
        warnings.append(
            ExtractionWarning(
                "pdf_page_text_empty",
                "Some PDF pages had no machine-readable text. OCR is not enabled for this step.",
                _limited_units(empty_pages),
            )
        )
    return ExtractionOutcome(
        text=collector.text(),
        coverage=coverage,
        warnings=warnings,
        truncated=collector.truncated,
    )


def _limited_units(units: list[str]) -> list[str]:
    if len(units) <= MAX_WARNING_UNITS:
        return units
    return [*units[:MAX_WARNING_UNITS], f"+{len(units) - MAX_WARNING_UNITS} more"]


def _extract_pdf_stream_fallback(file_bytes: bytes) -> ExtractionOutcome:
    collector = TextCollector(MAX_EXTRACTED_CHARS)
    direct = _pdf_text_fragments(_decode_text(file_bytes))
    if direct:
        collector.append(direct)
    for stream in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", file_bytes, re.DOTALL):
        if collector.truncated:
            break
        payload = stream.group(1).strip(b"\r\n")
        for candidate in (payload, _maybe_decompress(payload)):
            if not candidate:
                continue
            text = _pdf_text_fragments(_decode_text(candidate))
            if text:
                collector.append(text)
            if collector.truncated:
                break
    return ExtractionOutcome(
        text=html.unescape(collector.text()),
        coverage=ExtractionCoverage(unit="characters", discovered=None, processed=collector.chars),
        truncated=collector.truncated,
    )


def _maybe_decompress(payload: bytes) -> bytes:
    try:
        decompressor = zlib.decompressobj()
        result = decompressor.decompress(payload, MAX_EXTRACTED_CHARS * 20)
        result += decompressor.flush(MAX_EXTRACTED_CHARS * 2)
        return result
    except zlib.error:
        return b""


def _pdf_text_fragments(text: str) -> str:
    fragments: list[str] = []
    for match in re.finditer(r"\((?:\\.|[^\\)])*\)", text):
        fragments.append(_unescape_pdf_string(match.group(0)[1:-1]))
    for match in re.finditer(r"<([0-9A-Fa-f\s]{4,})>", text):
        raw = re.sub(r"\s+", "", match.group(1))
        try:
            fragments.append(bytes.fromhex(raw).decode("utf-16-be", errors="ignore"))
        except ValueError:
            continue
    return "\n".join(fragments)


def _unescape_pdf_string(value: str) -> str:
    replacements = {
        r"\(": "(",
        r"\)": ")",
        r"\\": "\\",
        r"\n": "\n",
        r"\r": "\r",
        r"\t": "\t",
        r"\b": "\b",
        r"\f": "\f",
    }
    for escaped, replacement in replacements.items():
        value = value.replace(escaped, replacement)
    value = re.sub(r"\\([0-7]{1,3})", lambda m: chr(int(m.group(1), 8)), value)
    return value


def _normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _source_analysis_summary(
    text: str,
    *,
    safe_name: str,
    truncated: bool,
) -> str:
    structured = _structured_source_report(text, safe_name=safe_name, truncated=truncated)
    if structured:
        return structured

    paragraphs = _paragraphs(text)
    sentences = _sentences(text)
    title = _candidate_title(safe_name, paragraphs)
    thesis = _candidate_thesis(paragraphs, sentences)
    headings = _section_headings(paragraphs)
    key_points = _important_sentences(sentences, limit=8)
    evidence = _evidence_sentences(sentences, limit=6)
    keywords = _keywords(text, title=title, limit=12)
    ppt_flow = _ppt_flow(title, thesis, key_points, evidence)
    excerpts = _representative_excerpts(paragraphs, limit=4)
    pptx_visual_fingerprint = _embedded_pptx_visual_fingerprint(text)

    lines: list[str] = [
        f"文件名：{safe_name}",
        f"核心主题：{title}",
        f"文章主旨：{thesis}",
    ]
    if keywords:
        lines.append("关键词：" + "、".join(keywords))
    lines.extend(_section("结构判断", headings or _fallback_structure(paragraphs)))
    lines.extend(_section("关键论点", key_points or [thesis]))
    lines.extend(_section("重要事实/数据/证据", evidence or ["原文没有明显数字型证据；生成 PPT 时应把关键判断标注为待核验证据。"]))
    lines.extend(_section("可做成PPT的大纲建议", ppt_flow))
    if pptx_visual_fingerprint:
        lines.extend(_section("PPT视觉参考指纹", pptx_visual_fingerprint))
    lines.extend(_section("原文摘录", excerpts))
    if truncated:
        lines.append(f"截断说明：原文超过 {MAX_EXTRACTED_CHARS} 字符，本报告基于前 {MAX_EXTRACTED_CHARS} 字符做结构化阅读。")
    summary = "\n".join(lines).strip()
    if len(summary) <= SUMMARY_CHARS:
        return summary
    return summary[: SUMMARY_CHARS - 40].rstrip() + "\n……（结构化阅读报告已压缩）"


_USER_STRUCTURED_HEADINGS = (
    "核心主题",
    "文章主旨",
    "关键词",
    "结构判断",
    "关键论点",
    "重要事实/数据/证据",
    "可做成PPT的大纲建议",
    "原文摘录",
    "资料来源",
)


def _structured_source_report(text: str, *, safe_name: str, truncated: bool) -> str:
    title = _structured_value(text, "核心主题")
    thesis = _structured_value(text, "文章主旨")
    key_points = _structured_items(text, "关键论点", limit=8)
    evidence = _structured_items(text, "重要事实/数据/证据", limit=6)
    ppt_flow = _structured_items(text, "可做成PPT的大纲建议", limit=6)
    excerpts = _structured_items(text, "原文摘录", limit=4)
    keywords = _structured_value(text, "关键词")
    if not (title and thesis and (key_points or evidence or ppt_flow)):
        return ""

    lines: list[str] = [
        f"文件名：{safe_name}",
        f"核心主题：{_clip_summary_line(title, 220)}",
        f"文章主旨：{_clip_summary_line(thesis, 520)}",
    ]
    if keywords:
        lines.append(f"关键词：{_clip_summary_line(keywords, 260)}")
    lines.extend(
        _section(
            "结构判断",
            [
                "用户资料已提供结构化主旨、论点、证据线索和 PPT 大纲建议；生成大纲时应优先保留这些内容，而不是重新套用通用摘要模板。"
            ],
        )
    )
    lines.extend(_section("关键论点", key_points))
    if evidence:
        lines.extend(_section("重要事实/数据/证据", evidence))
    lines.extend(_section("可做成PPT的大纲建议", ppt_flow or key_points[:4]))
    lines.extend(_section("原文摘录", excerpts or [thesis]))
    if truncated:
        lines.append(f"截断说明：原文超过 {MAX_EXTRACTED_CHARS} 字符，本报告基于前 {MAX_EXTRACTED_CHARS} 字符做结构化阅读。")
    summary = "\n".join(lines).strip()
    if len(summary) <= SUMMARY_CHARS:
        return summary
    return summary[: SUMMARY_CHARS - 40].rstrip() + "\n……（结构化阅读报告已压缩）"


def _structured_value(text: str, heading: str) -> str:
    for raw_line in text.splitlines():
        stripped = _clean_structured_line(raw_line)
        for prefix in (f"{heading}：", f"{heading}:"):
            if stripped.startswith(prefix):
                return stripped[len(prefix) :].strip()
    return ""


def _structured_items(text: str, heading: str, *, limit: int) -> list[str]:
    lines = text.splitlines()
    start = -1
    inline = ""
    for index, raw_line in enumerate(lines):
        stripped = _clean_structured_line(raw_line)
        for prefix in (f"{heading}：", f"{heading}:"):
            if stripped in {heading, prefix[:-1], prefix}:
                start = index
                break
            if stripped.startswith(prefix):
                start = index
                inline = stripped[len(prefix) :].strip()
                break
        if start >= 0:
            break
    if start < 0:
        return []
    items: list[str] = []
    if inline:
        items.append(inline)
    for raw_line in lines[start + 1 :]:
        stripped = _clean_structured_line(raw_line)
        if not stripped:
            continue
        if _is_user_structured_heading(stripped):
            break
        item = re.sub(r"^[-•*·]\s*", "", stripped)
        item = re.sub(r"^\d+[.)、]\s*", "", item).strip()
        if item and item not in items:
            items.append(item)
        if len(items) >= limit:
            break
    return [_clip_summary_line(item, 360) for item in items[:limit]]


def _is_user_structured_heading(line: str) -> bool:
    for heading in _USER_STRUCTURED_HEADINGS:
        if line in {heading, f"{heading}：", f"{heading}:"}:
            return True
        if line.startswith(f"{heading}：") or line.startswith(f"{heading}:"):
            return True
    return False


def _clean_structured_line(value: str) -> str:
    return _clean_line(value).lstrip("#").strip()


def _clip_summary_line(value: str, limit: int) -> str:
    cleaned = _clean_line(value)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _section(name: str, items: list[str]) -> list[str]:
    cleaned = [_clean_line(item) for item in items if _clean_line(item)]
    if not cleaned:
        return [f"{name}：", "- 暂无可读信息"]
    return [f"{name}：", *[f"- {item}" for item in cleaned]]


def _embedded_pptx_visual_fingerprint(text: str) -> list[str]:
    marker = "PPT视觉参考指纹："
    index = text.find(marker)
    if index < 0:
        return []
    tail = text[index + len(marker) :].strip()
    result: list[str] = []
    for line in tail.splitlines():
        cleaned = _clean_line(line).lstrip("- ").strip()
        if not cleaned:
            continue
        result.append(cleaned)
        if len(result) >= 8:
            break
    return result


def _paragraphs(text: str) -> list[str]:
    raw = re.split(r"\n{2,}|(?<=。)\s*\n|(?<=\.)\s*\n", text)
    paragraphs = [_clean_line(item) for item in raw]
    return [item for item in paragraphs if len(item) >= 2]


def _sentences(text: str) -> list[str]:
    text_without_markdown_headings = re.sub(r"(?m)^\s*#{1,6}\s+.*$", " ", text)
    normalized = re.sub(r"\s+", " ", text_without_markdown_headings)
    parts = re.split(r"(?<=[。！？!?；;])\s*|(?<=[.!?])\s+(?=[A-Z0-9\"“])", normalized)
    sentences = [_clean_line(part) for part in parts]
    return [sentence for sentence in sentences if 8 <= len(sentence) <= 260]


def _candidate_title(safe_name: str, paragraphs: list[str]) -> str:
    for paragraph in paragraphs[:8]:
        candidate = paragraph.lstrip("#").strip()
        if 4 <= len(candidate) <= 80 and not re.search(r"[。！？!?；;]$", candidate):
            return candidate
    stem = PurePath(safe_name).stem.strip()
    return stem or safe_name


def _candidate_thesis(paragraphs: list[str], sentences: list[str]) -> str:
    for sentence in sentences[:20]:
        lowered = sentence.lower()
        if any(marker in lowered for marker in _CLAIM_MARKERS):
            return sentence
    if sentences:
        return max(sentences[:12], key=lambda item: min(len(item), 180))
    if paragraphs:
        return paragraphs[0][:220]
    return "原文内容较短，暂未形成清晰主旨。"


def _section_headings(paragraphs: list[str]) -> list[str]:
    headings: list[str] = []
    for paragraph in paragraphs:
        stripped = paragraph.strip()
        candidate = stripped.lstrip("#").strip()
        is_markdown_heading = stripped.startswith("#")
        is_numbered_heading = bool(re.match(r"^(\d+(\.\d+)*|[一二三四五六七八九十]+)[、.．]\s*\S+", candidate))
        is_short_label = 3 <= len(candidate) <= 42 and not re.search(r"[。！？!?；;]$", candidate)
        if (is_markdown_heading or is_numbered_heading or is_short_label) and candidate not in headings:
            headings.append(candidate[:80])
        if len(headings) >= 8:
            break
    return headings


def _important_sentences(sentences: list[str], *, limit: int) -> list[str]:
    scored = [(_sentence_score(sentence), index, sentence) for index, sentence in enumerate(sentences)]
    scored = [item for item in scored if item[0] > 0]
    scored.sort(key=lambda item: (-item[0], item[1]))
    result: list[str] = []
    seen: set[str] = set()
    for _, _, sentence in scored:
        fingerprint = _fingerprint(sentence)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        result.append(sentence)
        if len(result) >= limit:
            break
    if len(result) < min(limit, 4):
        for sentence in sentences:
            fingerprint = _fingerprint(sentence)
            if fingerprint not in seen:
                result.append(sentence)
                seen.add(fingerprint)
            if len(result) >= limit:
                break
    return result


def _sentence_score(sentence: str) -> int:
    lowered = sentence.lower()
    score = 0
    score += sum(3 for marker in _CLAIM_MARKERS if marker in lowered)
    score += sum(4 for marker in _EVIDENCE_MARKERS if marker in lowered)
    if re.search(r"\d|%|％|[一二三四五六七八九十百千万亿]+(个|项|年|月|日|倍|成|人|次|例)", sentence):
        score += 6
    if "？" in sentence or "?" in sentence:
        score += 1
    if 28 <= len(sentence) <= 180:
        score += 2
    return score


def _evidence_sentences(sentences: list[str], *, limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        lowered = sentence.lower()
        has_number = bool(re.search(r"\d|%|％|[一二三四五六七八九十百千万亿]+(个|项|年|月|日|倍|成|人|次|例)", sentence))
        has_marker = any(marker in lowered for marker in _EVIDENCE_MARKERS)
        if not (has_number or has_marker):
            continue
        fingerprint = _fingerprint(sentence)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        result.append(sentence)
        if len(result) >= limit:
            break
    return result


def _keywords(text: str, *, title: str, limit: int) -> list[str]:
    english_tokens = [
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", text)
        if token.lower() not in _STOPWORDS
    ]
    chinese_candidates = [
        token
        for token in re.findall(r"[\u4e00-\u9fff]{2,12}", text)
        if token not in _STOPWORDS and token not in {"文件名", "核心主题", "文章主旨"}
    ]
    counts = Counter(english_tokens + chinese_candidates)
    seeded = [item for item in re.split(r"[\s、,，:：｜|/]+", title) if 2 <= len(item) <= 18]
    result: list[str] = []
    for token in seeded + [token for token, _ in counts.most_common(limit * 2)]:
        cleaned = token.strip(" .。,:：;；!?！？()（）[]【】")
        if not cleaned or cleaned.lower() in _STOPWORDS or cleaned in result:
            continue
        result.append(cleaned)
        if len(result) >= limit:
            break
    return result


def _ppt_flow(title: str, thesis: str, key_points: list[str], evidence: list[str]) -> list[str]:
    flow = [
        f"封面直接给出主题“{_clip(title, 42)}”，并用一句话压缩文章主旨。",
        f"背景页解释文章为什么提出这个判断：{_clip(thesis, 86)}",
    ]
    for point in key_points[:3]:
        flow.append(f"论点页围绕“{_clip(point, 76)}”展开，不额外发散。")
    if evidence:
        flow.append(f"证据页优先可视化“{_clip(evidence[0], 86)}”。")
    flow.append("结尾页回到原文主旨，只保留一个可复述结论。")
    return flow[:8]


def _fallback_structure(paragraphs: list[str]) -> list[str]:
    if len(paragraphs) <= 1:
        return ["短文本：适合提炼为封面主张、2-3 个论点和一个结论。"]
    if len(paragraphs) <= 4:
        return ["短文章：适合按背景、核心论点、证据、结论拆成 PPT。"]
    return ["长文章：适合先提取主旨，再按章节/论点/证据分层生成 PPT。"]


def _representative_excerpts(paragraphs: list[str], *, limit: int) -> list[str]:
    candidates = sorted(paragraphs, key=lambda item: _sentence_score(item), reverse=True)
    result: list[str] = []
    seen: set[str] = set()
    for paragraph in candidates or paragraphs:
        excerpt = _clip(paragraph, 220)
        fingerprint = _fingerprint(excerpt)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        result.append(excerpt)
        if len(result) >= limit:
            break
    return result


def _clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _fingerprint(value: str) -> str:
    return re.sub(r"\W+", "", value.lower())[:80]


def _clip(value: str, limit: int) -> str:
    value = _clean_line(value)
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"
