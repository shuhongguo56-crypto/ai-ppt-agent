from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from ai_ppt_contracts import SourcePack


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_USER_AGENT = "AI-PPT-Topic-Research/0.1 (public-source synthesis)"


@dataclass(frozen=True, slots=True)
class TopicResearchResult:
    source_pack: SourcePack | None
    mode: str
    providers: list[str]
    query: str
    warnings: list[str]


def research_topic_sources(
    *,
    project_id: str,
    topic: str,
    audience: str,
    language: str,
    enabled: bool = True,
    timeout_seconds: float = 6.0,
    max_sources: int = 5,
    user_agent: str = DEFAULT_USER_AGENT,
) -> TopicResearchResult:
    raw_topic = " ".join(topic.split())
    query = _research_query(raw_topic, audience, language)
    subject = _research_subject(raw_topic, language)
    if not enabled:
        return TopicResearchResult(
            source_pack=None,
            mode="disabled",
            providers=[],
            query=query,
            warnings=[],
        )

    sources: list[dict[str, Any]] = []
    providers: list[str] = []
    warnings: list[str] = []
    wiki_language = "zh" if language == "zh" else "en"
    wiki_query = _wikipedia_query(query, language)
    scholarly_query = _scholarly_query(query, language)

    try:
        wikipedia_sources = _wikipedia_sources(
            topic=wiki_query,
            language=wiki_language,
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
        )
        if wikipedia_sources:
            providers.append("wikipedia")
            sources.extend(wikipedia_sources)
    except (httpx.HTTPError, OSError, ValueError, TypeError, KeyError):
        warnings.append("Wikipedia retrieval was unavailable.")

    scholarly_sources: list[dict[str, Any]] = []
    try:
        scholarly_sources = _openalex_sources(
            topic=scholarly_query,
            language=language,
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
        )
        if scholarly_sources:
            providers.append("openalex")
            sources.extend(scholarly_sources)
    except (httpx.HTTPError, OSError, ValueError, TypeError, KeyError):
        warnings.append("OpenAlex retrieval was unavailable.")

    if not scholarly_sources:
        try:
            crossref_sources = _crossref_sources(
                topic=scholarly_query,
                language=language,
                timeout_seconds=timeout_seconds,
                user_agent=user_agent,
            )
            if crossref_sources:
                providers.append("crossref")
                sources.extend(crossref_sources)
        except (httpx.HTTPError, OSError, ValueError, TypeError, KeyError):
            warnings.append("Crossref retrieval was unavailable.")

    if _is_enterprise_ai_adoption_topic(query):
        authoritative_sources = _enterprise_ai_authoritative_sources(language)
        if authoritative_sources:
            providers.insert(0, "authoritative-research-library")
            sources = [*authoritative_sources, *sources]

    normalized = _deduplicate_sources(sources)[: max(1, min(max_sources, 8))]
    if normalized:
        minimum_for_strict_logic = min(max_sources, 4)
        if len(normalized) < minimum_for_strict_logic:
            warnings.append(
                f"Thin web research: only {len(normalized)} usable live source(s) were retrieved; a research-gap logic brief was added."
            )
            normalized.append(
                _research_gap_source(
                    topic=subject,
                    audience=audience,
                    language=language,
                    retrieved_count=len(normalized),
                    target_count=minimum_for_strict_logic,
                )
            )
        synthesis = _topic_synthesis_source(
            topic=subject,
            audience=audience,
            language=language,
            sources=normalized,
        )
        return TopicResearchResult(
            source_pack=SourcePack(
                schemaVersion="1.0.0",
                projectId=project_id,
                sources=[synthesis, *normalized],
            ),
            mode="web",
            providers=providers,
            query=query,
            warnings=warnings,
        )

    warnings.append("Live public-source retrieval returned no usable results; a local research brief was used.")
    return TopicResearchResult(
        source_pack=SourcePack(
            schemaVersion="1.0.0",
            projectId=project_id,
            sources=[_local_fallback_source(subject, audience, language)],
        ),
        mode="local_fallback",
        providers=[],
        query=query,
        warnings=warnings,
    )


def _enterprise_ai_authoritative_sources(language: str) -> list[dict[str, Any]]:
    """Curated, dated primary/authoritative evidence for enterprise AI adoption.

    Live discovery still runs first.  This library supplies a stable evidence floor
    when broad scholarly search ranks an adjacent industry paper above the actual
    decision topic.  Every claim is dated and linked so it can be audited or
    replaced without changing the outline contract.
    """

    records = [
        {
            "key": "oecd-firm-adoption-2026",
            "title": "OECD: AI use by firms continued to expand in 2025",
            "url": "https://www.oecd.org/en/about/news/announcements/2026/01/ai-use-by-individuals-surges-across-the-oecd-as-adoption-by-firms-continues-to-expand.html",
            "thesis_en": "Firm-level AI adoption expanded across OECD countries in 2025, but adoption remained uneven by company size and industry.",
            "points_en": [
                "AI use is spreading, so the management question is shifting from access to repeatable operating value.",
                "Large and small firms remain at very different adoption stages, which limits one-size-fits-all scale assumptions.",
            ],
            "evidence_en": [
                "In 2025, 20.2% of firms reported using AI, up from 14.2% in 2024 and 8.7% in 2023.",
                "AI use reached 52.0% among large firms and 17.4% among small firms in 2025.",
            ],
            "thesis_zh": "2025 年 OECD 国家企业采用 AI 的比例继续上升，但企业规模与行业之间仍存在明显差异。",
            "points_zh": [
                "AI 正从工具可用性问题转向能否形成可重复经营价值的问题。",
                "大型企业与小型企业处于不同采用阶段，不能套用同一套规模化假设。",
            ],
            "evidence_zh": [
                "2025 年，20.2% 的企业报告使用 AI，高于 2024 年的 14.2% 和 2023 年的 8.7%。",
                "2025 年大型企业 AI 使用率为 52.0%，小型企业为 17.4%。",
            ],
        },
        {
            "key": "stanford-ai-index-economy-2025",
            "title": "Stanford AI Index 2025: Economy",
            "url": "https://hai.stanford.edu/ai-index/2025-ai-index-report/economy",
            "thesis_en": "Organizational AI use rose sharply in 2024, while most reported financial gains inside business functions remained modest.",
            "points_en": [
                "High adoption does not by itself establish material enterprise value.",
                "Financial impact must be measured at the workflow and business-function level.",
            ],
            "evidence_en": [
                "In 2024, 78% of survey respondents reported organizational AI use, up from 55% in 2023.",
                "Most respondents reporting cost savings placed them below 10%, and the most common reported revenue increase was below 5%.",
            ],
            "thesis_zh": "2024 年组织采用 AI 的比例大幅上升，但多数业务职能报告的财务收益仍处于较低水平。",
            "points_zh": [
                "高采用率本身不能证明企业级价值。",
                "财务影响必须落到具体工作流和业务职能中测量。",
            ],
            "evidence_zh": [
                "2024 年，78% 的受访者报告所在组织使用 AI，高于 2023 年的 55%。",
                "多数报告成本节省的受访者将节省幅度归于 10% 以下；最常见的收入增幅低于 5%。",
            ],
        },
        {
            "key": "mckinsey-state-of-ai-2025",
            "title": "McKinsey Global Survey 2025: Agents, innovation, and transformation",
            "url": "https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-state-of-ai",
            "thesis_en": "Most organizations were still early in enterprise AI scaling in 2025, even as experimentation with agents became common.",
            "points_en": [
                "Workflow redesign, not isolated tool deployment, separates higher-value programs from experiments.",
                "Agent scale remains concentrated in a small number of functions for most organizations.",
            ],
            "evidence_en": [
                "Nearly two-thirds of respondents said their organizations had not begun scaling AI across the enterprise.",
                "Sixty-two percent reported at least experimenting with AI agents; in any one function, no more than 10% reported scaling them.",
            ],
            "thesis_zh": "2025 年多数组织仍处于企业 AI 规模化早期，即使智能体试验已较常见。",
            "points_zh": [
                "真正拉开价值差距的是工作流重构，而不是孤立部署工具。",
                "多数组织的智能体规模化仍集中在少数职能。",
            ],
            "evidence_zh": [
                "近三分之二受访者表示，其组织尚未开始在企业范围内规模化 AI。",
                "62% 的受访者表示至少在试验 AI 智能体；在任一单一职能中，报告规模化智能体的比例均不超过 10%。",
            ],
        },
        {
            "key": "nist-genai-profile-2024",
            "title": "NIST AI 600-1: Generative Artificial Intelligence Profile",
            "url": "https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence",
            "thesis_en": "NIST frames trustworthy generative AI as a lifecycle management responsibility spanning design, development, use, and evaluation.",
            "points_en": [
                "Risk controls must align with organizational goals and priorities rather than sit outside the operating workflow.",
                "Evaluation and documented human oversight are part of deployment readiness, not post-launch decoration.",
            ],
            "evidence_en": [
                "NIST AI 600-1 is a cross-sectoral companion profile to AI RMF 1.0 for generative AI.",
                "The profile proposes actions organizations can use to identify and manage generative-AI risks.",
            ],
            "thesis_zh": "NIST 将可信生成式 AI 定义为贯穿设计、开发、使用与评价全生命周期的管理责任。",
            "points_zh": [
                "风险控制必须与组织目标和工作流结合，而不是游离在业务运行之外。",
                "评价机制与有记录的人工监督属于上线准备的一部分。",
            ],
            "evidence_zh": [
                "NIST AI 600-1 是面向生成式 AI 的跨行业 AI RMF 1.0 配套指南。",
                "该指南提出了组织识别和管理生成式 AI 风险时可采用的行动。",
            ],
        },
    ]
    use_zh = language == "zh"
    results: list[dict[str, Any]] = []
    for record in records:
        thesis = str(record["thesis_zh" if use_zh else "thesis_en"])
        key_points = list(record["points_zh" if use_zh else "points_en"])
        evidence = list(record["evidence_zh" if use_zh else "evidence_en"])
        title = str(record["title"])
        url = str(record["url"])
        results.append(
            {
                "schemaVersion": "1.0.0",
                "sourceId": _source_id("authoritative", str(record["key"])),
                "sourceType": "url",
                "title": title,
                "url": url,
                "summary": _structured_summary(
                    topic=title,
                    thesis=thesis,
                    key_points=key_points,
                    evidence=evidence,
                    ppt_flow=_research_ppt_flow(language, "scholarly", title),
                    excerpts=[thesis],
                    source_label="权威研究资料库" if use_zh else "authoritative research library",
                ),
            }
        )
    return results


def _research_query(topic: str, audience: str, language: str) -> str:
    cleaned_topic = _clean_text(topic)
    cleaned_audience = _clean_text(audience)
    if not cleaned_topic:
        return cleaned_audience or "presentation topic"

    ai_pattern = re.compile(r"(?i)(?<![A-Za-z])A\.?\s*I\.?(?![A-Za-z])")
    ai_only = bool(re.fullmatch(r"(?i)\s*A\.?\s*I\.?\s*", cleaned_topic))
    education_context = _contains_education_context(f"{cleaned_topic} {cleaned_audience}")

    if language == "zh":
        query = ai_pattern.sub("人工智能", cleaned_topic)
        if ai_only:
            query = "人工智能"
        if ai_only and education_context:
            query = "人工智能 高等教育 教学 学习 形成性评价"
        return query

    query = ai_pattern.sub("artificial intelligence", cleaned_topic)
    if ai_only:
        query = "artificial intelligence"
    if ai_only and education_context:
        query = "artificial intelligence higher education teaching learning formative assessment"
    return query


def _research_subject(topic: str, language: str) -> str:
    cleaned = _clean_text(topic)
    if re.fullmatch(r"(?i)\s*A\.?\s*I\.?\s*", cleaned or ""):
        return "人工智能（AI）" if language == "zh" else "Artificial Intelligence (AI)"
    if language == "zh":
        return re.sub(
            r"(?i)(?<![A-Za-z])A\.?\s*I\.?(?![A-Za-z])",
            "人工智能（AI）",
            cleaned,
        )
    return re.sub(
        r"(?i)(?<![A-Za-z])A\.?\s*I\.?(?![A-Za-z])",
        "Artificial Intelligence (AI)",
        cleaned,
    )


def _wikipedia_query(query: str, language: str) -> str:
    normalized = query.lower()
    # Keep specific business, scientific, and policy qualifiers in the query.  The
    # previous implementation collapsed every AI topic to the generic
    # "artificial intelligence" page, which made a deck about enterprise agent
    # adoption inherit definitions and consumer applications instead of evidence
    # about adoption, operating models, and ROI.
    if language == "zh" and normalized.strip() in {
        "人工智能",
        "生成式人工智能",
        "人工智能（ai）",
    }:
        return "生成式人工智能" if "生成式" in query else "人工智能"
    if language != "zh" and normalized.strip() in {
        "artificial intelligence",
        "generative artificial intelligence",
        "artificial intelligence (ai)",
    }:
        return (
            "generative artificial intelligence"
            if "generative" in normalized
            else "artificial intelligence"
        )
    return query


def _scholarly_query(query: str, language: str) -> str:
    normalized = query.lower()
    if "人工智能" in query and _contains_education_context(query):
        return "artificial intelligence higher education teaching learning formative assessment"
    if _is_enterprise_ai_adoption_topic(query):
        return "enterprise AI agents adoption pilot scale ROI operating model governance"
    if normalized.strip() in {"人工智能", "人工智能（ai）"}:
        return "artificial intelligence"
    if "artificial intelligence" in normalized and _contains_education_context(query):
        return "artificial intelligence higher education teaching learning formative assessment"
    return query


def _wikipedia_sources(
    *, topic: str, language: str, timeout_seconds: float, user_agent: str
) -> list[dict[str, Any]]:
    payload = _get_json(
        url=f"https://{language}.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "generator": "search",
            "gsrsearch": topic,
            "gsrlimit": 2,
            "prop": "extracts|info",
            "inprop": "url",
            "exintro": 1,
            "explaintext": 1,
            "exsentences": 7,
            "format": "json",
            "formatversion": 2,
        },
        timeout_seconds=timeout_seconds,
        user_agent=user_agent,
    )
    pages = payload.get("query", {}).get("pages", {})
    if isinstance(pages, dict):
        page_items = list(pages.values())
    elif isinstance(pages, list):
        page_items = pages
    else:
        page_items = []
    results: list[dict[str, Any]] = []
    for page in page_items:
        title = _clean_text(str(page.get("title") or ""))
        extract = _clean_text(str(page.get("extract") or ""))
        url = _https_url(page.get("fullurl"))
        if not title or not extract or url is None:
            continue
        if _is_disambiguation_result(title, extract):
            continue
        if not _is_relevant_result(topic, title, extract):
            continue
        sentences = _sentences(extract)
        thesis = sentences[0] if sentences else extract
        key_points = sentences[1:5] or [thesis]
        results.append(
            {
                "schemaVersion": "1.0.0",
                "sourceId": _source_id("wikipedia", str(page.get("pageid") or url)),
                "sourceType": "url",
                "title": title,
                "url": url,
                "summary": _structured_summary(
                    topic=title,
                    thesis=thesis,
                    key_points=key_points,
                    evidence=sentences[1:4] or [thesis],
                    ppt_flow=_research_ppt_flow(language, "overview", title),
                    excerpts=sentences[:2],
                    source_label="Wikipedia",
                ),
            }
        )
    return results


def _openalex_sources(
    *, topic: str, language: str, timeout_seconds: float, user_agent: str
) -> list[dict[str, Any]]:
    payload = _get_json(
        url="https://api.openalex.org/works",
        params={
            "search": topic,
            "per-page": 3,
            "select": (
                "id,display_name,publication_year,doi,primary_location,"
                "abstract_inverted_index,cited_by_count"
            ),
        },
        timeout_seconds=timeout_seconds,
        user_agent=user_agent,
    )
    results: list[dict[str, Any]] = []
    for work in payload.get("results", []) if isinstance(payload, dict) else []:
        title = _clean_text(str(work.get("display_name") or ""))
        abstract = _abstract_from_inverted_index(work.get("abstract_inverted_index"))
        location = work.get("primary_location") or {}
        url = _https_url(location.get("landing_page_url")) or _https_url(work.get("doi")) or _https_url(work.get("id"))
        if not title or url is None:
            continue
        cross_language_zh_result = (
            language == "zh"
            and not re.search(r"[\u3400-\u9fff]", topic)
            and bool(re.search(r"[\u3400-\u9fff]", f"{title} {abstract}"))
        )
        if (
            _requires_strict_relevance(topic)
            and not cross_language_zh_result
            and not _is_relevant_result(topic, title, abstract)
        ):
            continue
        year = work.get("publication_year")
        cited_by = work.get("cited_by_count")
        sentences = _sentences(abstract) if abstract else []
        thesis = sentences[0] if sentences else title
        if language == "zh":
            evidence = [
                item
                for item in [
                    f"{year} 年研究《{title}》" if year else f"研究《{title}》",
                    f"OpenAlex 收录引用次数：{cited_by}" if isinstance(cited_by, int) else "",
                ]
                if item
            ]
        else:
            evidence = [item for item in [f"Publication year: {year}" if year else "", f"OpenAlex cited-by count: {cited_by}" if isinstance(cited_by, int) else ""] if item]
        results.append(
            {
                "schemaVersion": "1.0.0",
                "sourceId": _source_id("openalex", str(work.get("id") or url)),
                "sourceType": "url",
                "title": title,
                "url": url,
                "summary": _structured_summary(
                    topic=topic,
                    thesis=thesis,
                    key_points=sentences[1:5] or [title],
                    evidence=evidence or ["Scholarly work indexed by OpenAlex."],
                    ppt_flow=_research_ppt_flow(language, "scholarly", title),
                    excerpts=sentences[:2] or [title],
                    source_label="OpenAlex",
                ),
            }
        )
    return results


def _crossref_sources(
    *, topic: str, language: str, timeout_seconds: float, user_agent: str
) -> list[dict[str, Any]]:
    payload = _get_json(
        url="https://api.crossref.org/works",
        params={
            "query": topic,
            "rows": 3,
            "select": "DOI,title,URL,abstract,published,container-title",
        },
        timeout_seconds=timeout_seconds,
        user_agent=user_agent,
    )
    items = payload.get("message", {}).get("items", []) if isinstance(payload, dict) else []
    results: list[dict[str, Any]] = []
    for work in items:
        raw_title = work.get("title") or []
        title = _clean_text(str(raw_title[0] if isinstance(raw_title, list) and raw_title else raw_title))
        url = _https_url(work.get("URL"))
        if not title or url is None:
            continue
        abstract = _clean_text(re.sub(r"<[^>]+>", " ", html.unescape(str(work.get("abstract") or ""))))
        cross_language_zh_result = (
            language == "zh"
            and not re.search(r"[\u3400-\u9fff]", topic)
            and bool(re.search(r"[\u3400-\u9fff]", f"{title} {abstract}"))
        )
        if (
            _requires_strict_relevance(topic)
            and not cross_language_zh_result
            and not _is_relevant_result(topic, title, abstract)
        ):
            continue
        sentences = _sentences(abstract)
        date_parts = (work.get("published") or {}).get("date-parts") or []
        year = date_parts[0][0] if date_parts and date_parts[0] else None
        container = work.get("container-title") or []
        journal = container[0] if isinstance(container, list) and container else ""
        if language == "zh":
            evidence = [
                item
                for item in [
                    f"{year} 年研究《{title}》" if year else f"研究《{title}》",
                    f"发表于《{journal}》" if journal else "",
                ]
                if item
            ]
        else:
            evidence = [
                item
                for item in [
                    f"Publication year: {year}" if year else "",
                    f"Published in: {journal}" if journal else "",
                ]
                if item
            ]
        results.append(
            {
                "schemaVersion": "1.0.0",
                "sourceId": _source_id("crossref", str(work.get("DOI") or url)),
                "sourceType": "url",
                "title": title,
                "url": url,
                "summary": _structured_summary(
                    topic=topic,
                    thesis=sentences[0] if sentences else title,
                    key_points=sentences[1:5] or [title],
                    evidence=evidence or (["Crossref 收录的论文元数据。"] if language == "zh" else ["Publication metadata indexed by Crossref."]),
                    ppt_flow=_research_ppt_flow(language, "scholarly", title),
                    excerpts=sentences[:2] or [title],
                    source_label="Crossref",
                ),
            }
        )
    return results


def _get_json(*, url: str, params: dict, timeout_seconds: float, user_agent: str) -> dict[str, Any]:
    response = httpx.get(
        url,
        params=params,
        headers={"User-Agent": user_agent, "Accept": "application/json"},
        timeout=httpx.Timeout(timeout_seconds),
        follow_redirects=True,
    )
    response.raise_for_status()
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise ValueError("research provider response exceeds size limit")
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("research provider returned a non-object payload")
    return payload


def _structured_summary(
    *,
    topic: str,
    thesis: str,
    key_points: list[str],
    evidence: list[str],
    ppt_flow: list[str],
    excerpts: list[str],
    source_label: str,
    evidence_matrix: list[str] | None = None,
) -> str:
    lines = [
            f"核心主题：{_clip(topic, 180)}",
            f"文章主旨：{_clip(thesis, 420)}",
            "关键论点：",
            *[f"- {_clip(item, 320)}" for item in key_points[:5] if item],
            "重要事实/数据/证据：",
            *[f"- {_clip(item, 320)}" for item in evidence[:4] if item],
    ]
    if evidence_matrix:
        lines.extend(
            [
                "证据矩阵：",
                *[f"- {_clip(item, 420)}" for item in evidence_matrix[:6] if item],
            ]
        )
    lines.extend(
        [
            "可做成PPT的大纲建议：",
            *[f"- {_clip(item, 260)}" for item in ppt_flow[:4] if item],
            "原文摘录：",
            *[f"- {_clip(item, 360)}" for item in excerpts[:3] if item],
            f"资料来源：{source_label}",
        ]
    )
    return "\n".join(lines)


def _topic_synthesis_source(
    *, topic: str, audience: str, language: str, sources: list[dict[str, Any]]
) -> dict[str, Any]:
    source_theses: list[str] = []
    source_points: list[str] = []
    source_evidence: list[str] = []
    excerpts: list[str] = []
    for source in sources:
        summary = str(source.get("summary") or "")
        thesis = _summary_section_value(summary, "文章主旨")
        if thesis:
            source_theses.append(thesis)
        source_points.extend(_summary_section_items(summary, "关键论点"))
        source_evidence.extend(_summary_section_items(summary, "重要事实/数据/证据"))
        excerpts.extend(_summary_section_items(summary, "原文摘录"))

    topic_context = f"{topic} {audience}"
    ai_education = _is_ai_education_topic(topic_context)
    enterprise_ai_adoption = _is_enterprise_ai_adoption_topic(topic_context)
    if language == "zh" and enterprise_ai_adoption:
        thesis = (
            f"“{topic}”的决策重点不是证明智能体能完成一次演示，而是证明它能在受控风险下被持续采用，"
            "稳定改变业务流程，并把过程改善归因到可衡量的经营结果；从试点走向规模化必须同时通过价值、采用、治理与运行四道门。"
        )
        key_points = [
            "价值链：把模型调用连接到任务采用率、流程周期、质量/错误率、收入或成本结果，避免用调用量替代 ROI。",
            "证据设计：试点前先冻结基线与对照口径，再记录时间节省、返工、人工复核和业务结果，才能区分相关性与可归因收益。",
            "运行模型：明确业务负责人、产品/工程、数据、安全与一线使用者的责任，并为人工接管、异常处理和版本变更建立机制。",
            "规模化门槛：只有当价值可重复、使用可持续、风险可接受、单位经济性成立时，试点才应进入下一轮扩展。",
        ]
        ppt_flow = [
            "先回答为什么大量试点仍难形成可复述的经营价值。",
            "再用‘使用—流程—业务—财务’四层 ROI 链解释价值如何产生与归因。",
            "用证据矩阵区分已检索事实、来源元数据、合理推断和仍待补强的内部经营数据。",
            f"最后为{audience}给出 90 天验证路径与规模化决策门槛。",
        ]
    elif language != "zh" and enterprise_ai_adoption:
        thesis = (
            f"The decision in {topic} is not whether an agent can complete a demo. It is whether the agent can earn sustained adoption, "
            "change a business workflow under controlled risk, and produce attributable operating value. Moving from pilot to scale requires "
            "four gates: value, adoption, governance, and reliable operations."
        )
        key_points = [
            "Value chain: connect model use to task adoption, cycle time, quality or error rates, and then revenue or cost outcomes; invocation volume is not ROI.",
            "Evidence design: freeze a baseline and comparison method before the pilot, then capture time saved, rework, human review, and business outcomes so attribution can be tested.",
            "Operating model: assign ownership across business, product, engineering, data, security, and frontline users, with explicit human takeover and exception handling.",
            "Scale gate: expand only when value repeats, usage persists, risk remains acceptable, and unit economics support the next deployment wave.",
        ]
        ppt_flow = [
            "Start with why many pilots demonstrate feasibility without proving repeatable enterprise value.",
            "Explain the ROI chain from use to process change, business outcome, and financial value.",
            "Use an evidence matrix to separate retrieved facts, source metadata, inference, and internal data still required.",
            f"Close with a 90-day proof path and scale gates for {audience}.",
        ]
    elif language == "zh" and ai_education:
        thesis = (
            "生成式人工智能正在把高等教育从“工具使用”推向教学设计、学习支持、评价方式与治理机制的协同重构；"
            "它的价值取决于能否提升学习质量，同时守住事实核验、学术诚信与自主判断的边界。"
        )
        key_points = [
            "教学端：把生成式人工智能用于备课、案例生成、反馈与个性化支持，同时由教师定义任务和验收标准。",
            "学习端：把人工智能作为启发、练习与反馈伙伴，而不是替代阅读、推理和原创表达。",
            "评价端：从只看最终答案转向审查过程、证据、反思与口头答辩，降低代写和幻觉风险。",
            "治理端：明确可用场景、披露要求、隐私边界与事实核验责任，让创新和问责同步。",
        ]
        ppt_flow = [
            "从教学痛点与机会切入，建立为什么现在必须讨论生成式人工智能。",
            "按教学、学习、评价和治理四个层次解释作用机制。",
            "用公开研究与高校案例区分已知证据、现实应用和仍需验证的问题。",
            f"最后为{audience}给出可执行的课程设计、评价与治理动作。",
        ]
    elif language != "zh" and ai_education:
        thesis = (
            "Generative AI is moving higher education from tool adoption toward coordinated redesign of teaching, "
            "learning support, assessment, and governance; its value depends on improving learning while protecting "
            "verification, academic integrity, and independent judgment."
        )
        key_points = [
            "Teaching: use generative AI for preparation, examples, feedback, and tailored support while educators define the task and acceptance criteria.",
            "Learning: use AI as a partner for inquiry, practice, and feedback rather than a substitute for reading, reasoning, and original expression.",
            "Assessment: evaluate process, evidence, reflection, and oral defense—not only the final answer—to reduce ghostwriting and hallucination risk.",
            "Governance: define allowed uses, disclosure, privacy boundaries, and verification responsibility so innovation remains accountable.",
        ]
        ppt_flow = [
            "Open with the teaching problem and opportunity.",
            "Explain the mechanism across teaching, learning, assessment, and governance.",
            "Use public research and institutional cases to separate evidence from open questions.",
            f"Close with actions for {audience}.",
        ]
    elif language == "zh":
        thesis = source_theses[0] if source_theses else f"公开资料从概念、机制、证据、应用与限制五个层次解释“{topic}”。"
        key_points = source_points[:4] or source_theses[:4]
        ppt_flow = [
            f"先说明“{topic}”的核心问题与现实意义。",
            "再按机制、证据、案例和限制组织公开资料。",
            f"最后为{audience}提炼可复述的结论与行动建议。",
        ]
    else:
        thesis = source_theses[0] if source_theses else f"Public sources explain {topic} through its mechanism, evidence, applications, and limitations."
        key_points = source_points[:4] or source_theses[:4]
        ppt_flow = [
            f"Frame the central question and relevance of {topic}.",
            "Organize the public evidence around mechanism, cases, and limitations.",
            f"Close with a repeatable conclusion and actions for {audience}.",
        ]

    evidence_seeds: list[str] = []
    if language == "zh" and enterprise_ai_adoption:
        evidence_seeds = [
            "可交付的 ROI 证据必须同时说明试点前基线、测量窗口、业务结果、归因方法、人工复核成本与风险事件，不能只报告模型能力或调用量。",
            "公开来源可以支撑行业背景与方法框架；客户自身的采用率、流程指标、财务口径和风险记录仍需作为内部证据补齐。",
        ]
    elif language != "zh" and enterprise_ai_adoption:
        evidence_seeds = [
            "Delivery-grade ROI evidence must state the pre-pilot baseline, measurement window, business outcome, attribution method, human-review cost, and risk events—not only model capability or usage volume.",
            "Public sources can support the market context and evaluation method; customer adoption, workflow, financial, and risk data remain required as internal evidence.",
        ]
    elif language == "zh" and ai_education:
        evidence_seeds = [
            "公开资料与论文检索共同指向：AI 在高等教育中的价值需要同时评估教学设计、学习支持、评价方式和治理边界。",
            "形成性评价场景尤其需要过程证据、反馈闭环和学术诚信约束，不能只用生成速度衡量效果。",
        ]
    elif language != "zh" and ai_education:
        evidence_seeds = [
            "Public sources and scholarly search both point to teaching design, learning support, assessment, and governance as the core evaluation frame.",
            "Formative assessment requires process evidence, feedback loops, and academic-integrity safeguards rather than speed alone.",
        ]
    combined_points = _unique_text_items([*key_points, *source_points])[:5]
    if evidence_seeds:
        combined_evidence = _unique_text_items(
            [*evidence_seeds[:1], *source_evidence, *evidence_seeds[1:]]
        )[:5]
    else:
        combined_evidence = _unique_text_items(source_evidence)[:4]
    combined_excerpts = _unique_text_items([*excerpts, *source_theses])[:3]
    evidence_matrix = _build_evidence_matrix(
        topic=topic,
        language=language,
        sources=sources,
    )
    summary = _structured_summary(
        topic=topic,
        thesis=thesis,
        key_points=combined_points,
        evidence=combined_evidence or source_theses[:2],
        ppt_flow=ppt_flow,
        excerpts=combined_excerpts or [thesis],
        source_label="公开资料综合" if language == "zh" else "public-source synthesis",
        evidence_matrix=evidence_matrix,
    )
    summary = "\n".join(
        [
            summary,
            _logic_chain_summary(
                topic=topic,
                audience=audience,
                language=language,
                thesis=thesis,
                key_points=combined_points,
                evidence=combined_evidence or source_theses[:2],
            ),
        ]
    )
    return {
        "schemaVersion": "1.0.0",
        "sourceId": _source_id("research-synthesis", topic),
        "sourceType": "text",
        "title": f"{topic}：公开资料综合" if language == "zh" else f"{topic}: public-source synthesis",
        "summary": summary,
    }


def _logic_chain_summary(
    *,
    topic: str,
    audience: str,
    language: str,
    thesis: str,
    key_points: list[str],
    evidence: list[str],
) -> str:
    if _is_enterprise_ai_adoption_topic(f"{topic} {audience}"):
        if language == "zh":
            return "\n".join(
                [
                    "PPT 逻辑链：",
                    "核心问题：哪个工作流值得规模化、服务谁、处于什么风险边界？",
                    "为什么是现在：企业采用率持续上升，但规模化程度和财务影响仍不均衡。",
                    "作用机制：持续任务采用必须先带来流程变化，才能把经营结果归因到智能体。",
                    "证据地图：",
                    "- 外部证据：采用趋势、规模化成熟度与治理要求。",
                    "- 内部证据：基线、对照、流程结果、完整成本与风险事件。",
                    "风险边界：公开资料不能替代客户 ROI；内部数据必须闭合归因链。",
                    "面向受众的行动：选择一个高频、可测、可回退的流程，用 90 天完成继续、调整或停止决策。",
                ]
            )
        return "\n".join(
            [
                "PPT logic chain:",
                "Central question: which workflow merits scaling, for whom, and within what risk boundary?",
                "Why now: enterprise adoption is rising, while scaling maturity and financial impact remain uneven.",
                "Mechanism: sustained task use must change a workflow before business value can be attributed to an agent.",
                "Evidence map:",
                "- External evidence: adoption trends, scaling maturity, and governance requirements.",
                "- Internal evidence: baseline, comparison, process outcome, fully loaded cost, and risk events.",
                "Risk boundary: public evidence cannot prove a client's ROI; internal data must close the attribution chain.",
                "Action for audience: select one frequent, measurable, reversible workflow and use 90 days to continue, redesign, or stop.",
            ]
        )
    first_point = key_points[0] if key_points else thesis
    second_point = key_points[1] if len(key_points) > 1 else first_point
    evidence_line = evidence[0] if evidence else "public sources provide context but still require verification"
    if language == "zh":
        return "\n".join(
            [
                "PPT逻辑链：",
                f"中心问题：{topic}真正改变了什么，为什么值得现在讨论？",
                f"为什么现在：公开资料显示，{_clip(first_point, 220)}",
                f"作用机制：围绕“{_clip(second_point, 180)}”建立从背景、机制、证据到行动的因果链。",
                "证据地图：",
                f"- {_clip(evidence_line, 240)}",
                f"- {_clip(thesis, 240)}",
                "风险边界：区分已经有资料支撑的判断、仍需验证的推断，以及正式交付前需要补强的引用。",
                f"面向受众的行动：把结论转译成{audience}可以复述、讨论和执行的建议。",
            ]
        )
    return "\n".join(
        [
            "PPT logic chain:",
            f"Central question: What does {topic} actually change, and why does it matter now?",
            f"Why now: public sources indicate that {_clip(first_point, 220)}",
            f"Mechanism: use {_clip(second_point, 180)} to connect context, mechanism, evidence, and action.",
            "Evidence map:",
            f"- {_clip(evidence_line, 240)}",
            f"- {_clip(thesis, 240)}",
            "Risk boundary: distinguish source-backed claims, weaker inferences, and citations that need strengthening before final delivery.",
            f"Action for audience: translate the conclusion into steps {audience} can repeat, discuss, and execute.",
        ]
    )


def _is_ai_education_topic(topic: str) -> bool:
    normalized = topic.lower()
    ai_terms = ("生成式", "人工智能", "ai", "aigc", "generative ai", "artificial intelligence")
    return any(term in normalized for term in ai_terms) and _contains_education_context(
        normalized
    )


def _contains_education_context(value: str) -> bool:
    normalized = value.lower()
    education_terms = (
        "教育",
        "高等教育",
        "高校",
        "大学",
        "教学",
        "课堂",
        "课程",
        "学习",
        "复习",
        "评价",
        "形成性评价",
        "education",
        "higher education",
        "university",
        "college",
        "teaching",
        "learning",
        "assessment",
        "formative assessment",
    )
    return any(term in normalized for term in education_terms)


def _is_disambiguation_result(title: str, extract: str) -> bool:
    normalized_title = title.lower()
    normalized_extract = re.sub(r"\s+", "", extract.lower())
    if "消歧义" in title or "disambiguation" in normalized_title:
        return True
    disambiguation_markers = (
        "可以指：",
        "可以指:",
        "可以指",
        "可能指",
        "可指",
        "mayreferto",
        "canreferto",
        "referstoanyof",
    )
    return any(marker in normalized_extract[:220] for marker in disambiguation_markers)


def _is_relevant_result(query: str, title: str, extract: str) -> bool:
    terms = _query_relevance_terms(query)
    if not terms:
        return True
    haystack = f"{title} {extract}".lower()
    matches = {term for term in terms if term.lower() in haystack}
    if not matches:
        return False
    if not _requires_strict_relevance(query):
        return True
    # A specific query needs more than one generic overlap.  This prevents a
    # result about "AI applications" from entering a research pack about agent
    # adoption and measurable ROI merely because both contain the token "AI".
    required_matches = 2 if len(terms) >= 3 else 1
    if len(matches) < required_matches:
        return False
    if _is_enterprise_ai_adoption_topic(query):
        adoption_terms = {
            "agent",
            "agents",
            "agentic",
            "adoption",
            "pilot",
            "scale",
            "scaling",
            "roi",
            "enterprise",
            "智能体",
            "采用",
            "试点",
            "规模化",
            "投资回报",
        }
        normalized_haystack = haystack.casefold()
        has_agent = any(
            term in normalized_haystack
            for term in ("agent", "agents", "agentic", "intelligent agent", "智能体")
        )
        has_enterprise_context = any(
            term in normalized_haystack
            for term in (
                "enterprise",
                "business",
                "organization",
                "workflow",
                "operating model",
                "企业",
                "业务",
                "组织",
                "流程",
                "运行模型",
            )
        )
        has_adoption_or_value = any(
            term in normalized_haystack
            for term in (
                "adoption",
                "pilot",
                "scale",
                "scaling",
                "deployment",
                "roi",
                "return on investment",
                "采用",
                "试点",
                "规模化",
                "投资回报",
            )
        )
        query_requires_agent = any(
            term in query.casefold()
            for term in ("agent", "agentic", "智能体")
        )
        if query_requires_agent and not has_agent:
            return False
        return (
            has_adoption_or_value
            and (has_agent or has_enterprise_context)
            and any(term in matches for term in adoption_terms)
        )
    return True


def _requires_strict_relevance(query: str) -> bool:
    normalized = query.lower()
    if any(term in query for term in ("瑞幸", "瑞幸咖啡")) or "luckin" in normalized:
        return True
    if len(_query_relevance_terms(query)) >= 3:
        return True
    cjk = re.sub(r"[^㐀-鿿]", "", query)
    return len(cjk) >= 6


def _query_relevance_terms(query: str) -> list[str]:
    normalized = query.lower()
    if any(term in query for term in ("瑞幸", "瑞幸咖啡")) or "luckin" in normalized:
        return ["瑞幸", "瑞幸咖啡", "luckin", "luckin coffee"]
    phrase_terms: list[str] = []
    if "人工智能" in query:
        phrase_terms.extend(["人工智能", "artificial intelligence"])
    if "生成式人工智能" in query or "generative artificial intelligence" in normalized:
        phrase_terms.extend(["生成式人工智能", "generative artificial intelligence"])
    if "artificial intelligence" in normalized:
        phrase_terms.extend(["artificial intelligence", "ai"])
    compact_source = re.sub(
        r"(?i)artificial intelligence|generative artificial intelligence",
        " ",
        query,
    )
    compact = re.sub(r"[^0-9a-zA-Z\u3400-\u9fff]+", " ", compact_source).strip()
    raw_terms = [
        term
        for term in compact.split()
        if len(term) >= 3 or re.search(r"[\u3400-\u9fff]", term)
    ]
    generic = {
        "研究",
        "分析",
        "策略",
        "品牌",
        "消费",
        "增长",
        "问题",
        "背景",
        "机制",
        "证据",
        "行动",
        "复兴",
        "报告",
        "课程",
        "客户",
        "投资人",
        "the",
        "and",
        "for",
        "from",
        "into",
        "with",
        "about",
        "research",
        "analysis",
        "strategy",
        "report",
        "presentation",
        "measurable",
        "year",
    }
    terms: list[str] = list(phrase_terms)
    for term in raw_terms:
        if re.search(r"[\u3400-\u9fff]", term):
            parts = [part for part in re.split(r"[、，,；;：:\s和与的]+", term) if part]
            for part in parts:
                if part not in generic and 2 <= len(part) <= 12:
                    terms.append(part)
            for size in (6, 5, 4, 3):
                for index in range(0, max(0, len(term) - size + 1)):
                    candidate = term[index : index + size]
                    if candidate not in generic and not any(word in candidate for word in generic):
                        terms.append(candidate)
        elif term.lower() not in generic:
            terms.append(term)
    unique: list[str] = []
    for term in terms:
        lowered = term.lower()
        if lowered and lowered not in unique:
            unique.append(lowered)
    return unique[:10]


def _is_enterprise_ai_adoption_topic(value: str) -> bool:
    normalized = value.casefold()
    ai_terms = (
        "人工智能",
        "生成式人工智能",
        "智能体",
        "artificial intelligence",
        "agent",
        "agentic",
    )
    enterprise_terms = (
        "企业",
        "组织",
        "业务",
        "enterprise",
        "business",
        "organization",
    )
    adoption_terms = (
        "采用",
        "落地",
        "试点",
        "规模化",
        "投资回报",
        "roi",
        "adoption",
        "pilot",
        "scale",
        "scaling",
        "deployment",
        "value",
    )
    return (
        (
            any(term in normalized for term in ai_terms)
            or bool(re.search(r"(?:^|\W)ai(?:$|\W)", normalized, re.IGNORECASE))
        )
        and any(term in normalized for term in enterprise_terms)
        and any(term in normalized for term in adoption_terms)
    )


def _build_evidence_matrix(
    *, topic: str, language: str, sources: list[dict[str, Any]]
) -> list[str]:
    """Create traceable claim-to-decision rows without inventing source facts."""

    rows: list[str] = []
    for source in sources:
        summary = str(source.get("summary") or "")
        source_id = str(source.get("sourceId") or "unknown-source")
        title = str(source.get("title") or source_id)
        thesis = _summary_section_value(summary, "文章主旨")
        evidence = _summary_section_items(summary, "重要事实/数据/证据")
        candidate = next(
            (
                item
                for item in [*evidence, thesis]
                if item and not _is_provenance_only_evidence(item)
            ),
            thesis or (evidence[0] if evidence else ""),
        )
        if not candidate:
            continue
        source_text = f"{title} {candidate} {source_id}".casefold()
        if "research-gap" in source_id or any(
            marker in source_text
            for marker in ("待补", "尚缺", "需补", "to verify", "citation needed")
        ):
            evidence_type = "缺口" if language == "zh" else "gap"
            decision_role = "交付前补证" if language == "zh" else "evidence required before delivery"
        elif any(
            marker in source_text
            for marker in ("roi", "return on investment", "投资回报", "profit", "revenue", "cost", "利润", "收入", "成本")
        ):
            evidence_type = "事实" if language == "zh" else "fact"
            decision_role = "价值与归因" if language == "zh" else "value and attribution"
        elif any(
            marker in source_text
            for marker in ("risk", "governance", "security", "privacy", "风险", "治理", "安全", "隐私")
        ):
            evidence_type = "边界" if language == "zh" else "boundary"
            decision_role = "风险与治理" if language == "zh" else "risk and governance"
        elif any(
            marker in source_text
            for marker in ("adoption", "pilot", "deployment", "agent", "采用", "试点", "落地", "智能体")
        ) or (
            re.search(r"\d+(?:\.\d+)?%", source_text) is not None
            and any(marker in source_text for marker in ("ai use", "using ai", "使用 ai"))
        ):
            evidence_type = "事实" if language == "zh" else "fact"
            decision_role = "采用与规模化" if language == "zh" else "adoption and scale"
        else:
            evidence_type = "背景" if language == "zh" else "context"
            decision_role = "决策背景" if language == "zh" else "decision context"
        complete_title = _complete_matrix_fragment(title, limit=82)
        complete_candidate = _complete_matrix_fragment(
            candidate,
            limit=240,
            fallback_title=title,
            language=language,
        )
        if language == "zh":
            row = f"[{evidence_type}] {decision_role}｜{complete_title}｜{complete_candidate}｜来源 {source_id}"
        else:
            row = f"[{evidence_type}] {decision_role} | {complete_title} | {complete_candidate} | source {source_id}"
        if row not in rows:
            rows.append(row)
    return rows[:6]


def _complete_matrix_fragment(
    value: str,
    *,
    limit: int,
    fallback_title: str = "",
    language: str = "en",
) -> str:
    """Keep evidence rows readable without presenting clipped prose as a fact."""

    cleaned = _clean_text(value).strip(" |｜")
    incomplete = "…" in cleaned or bool(re.search(r"\.{3,}", cleaned))
    if incomplete and fallback_title:
        title = _clean_text(fallback_title).strip(" |｜")
        cleaned = (
            f"资料范围：{title}。"
            if language == "zh"
            else f"Source scope: {title}."
        )
    if len(cleaned) <= limit:
        return cleaned
    candidate = cleaned[:limit]
    sentence_ends = [match.end() for match in re.finditer(r"[。！？.!?](?=\s|$)", candidate)]
    if sentence_ends and sentence_ends[-1] >= max(28, limit // 2):
        return candidate[: sentence_ends[-1]].strip()
    if language == "zh":
        return candidate.rstrip(" ，,、;；:：") + "。"
    boundary = candidate.rfind(" ")
    if boundary >= max(24, limit // 2):
        candidate = candidate[:boundary]
    return candidate.rstrip(" ,;:") + "."


def _is_provenance_only_evidence(value: str) -> bool:
    normalized = " ".join(value.casefold().split())
    return bool(
        re.fullmatch(
            r"(?:publication year|openalex cited-by count|published in)\s*[:：].+",
            normalized,
        )
        or re.fullmatch(r"(?:\d{4}\s*年研究|发表于).+", normalized)
    )


def _summary_section_value(summary: str, heading: str) -> str:
    for line in summary.splitlines():
        stripped = line.strip()
        for separator in ("：", ":"):
            prefix = f"{heading}{separator}"
            if stripped.startswith(prefix):
                return stripped[len(prefix) :].strip()
    return ""


def _summary_section_items(summary: str, heading: str) -> list[str]:
    lines = summary.splitlines()
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip() in {f"{heading}：", f"{heading}:"}
        ),
        -1,
    )
    if start < 0:
        return []
    items: list[str] = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith(("-", "•", "*", "·")):
            break
        items.append(stripped[1:].strip())
    return [item for item in items if item]


def _unique_text_items(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        cleaned = _clean_text(item)
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def _research_ppt_flow(language: str, source_kind: str, title: str) -> list[str]:
    if language == "zh":
        if source_kind == "scholarly":
            return [
                f"用《{_clip(title, 48)}》支撑一个核心判断",
                "把研究方法、发现或影响转成带标签的证据图",
            ]
        return [
            "先解释核心概念与作用机制",
            "再区分已知事实、应用场景、限制与影响",
        ]
    if source_kind == "scholarly":
        return [
            f"Use {_clip(title, 56)} to substantiate one core claim.",
            "Translate the method, finding, or implication into a labelled evidence visual.",
        ]
    return [
        f"Define {_clip(title, 56)} through a concrete mechanism or context.",
        "Separate established facts, applications, limitations, and implications.",
    ]


def _local_fallback_source(topic: str, audience: str, language: str) -> dict[str, Any]:
    profile = _local_fallback_profile(topic, audience, language)
    source_label = "本地主题研究草案（待联网核验）" if language == "zh" else "local topic research draft pending citation check"
    return {
        "schemaVersion": "1.0.0",
        "sourceId": _source_id("local-research-fallback", topic),
        "sourceType": "text",
        "title": f"{topic}：本地主题研究草案" if language == "zh" else f"{topic}: local topic research draft",
        "summary": _structured_summary(
            topic=topic,
            thesis=profile["thesis"],
            key_points=profile["points"],
            evidence=profile["evidence"],
            ppt_flow=profile["flow"],
            excerpts=[profile["thesis"]],
            source_label=source_label,
        ),
    }


def _local_fallback_profile(topic: str, audience: str, language: str) -> dict[str, list[str] | str]:
    context = f"{topic} {audience}"
    if _is_enterprise_ai_adoption_topic(context):
        if language == "zh":
            return {
                "thesis": (
                    f"“{topic}”必须从一次性能力演示升级为可归因的经营改进：面向{audience}，"
                    "需要同时证明智能体被持续采用、流程指标稳定改善、风险边界可控，并且收益覆盖建设与运行成本。"
                ),
                "points": [
                    "试点目标必须从‘能不能做’改为‘在哪个业务任务上、对谁、在什么风险边界内创造什么结果’。",
                    "ROI 证据链应按使用、流程、业务、财务四层记录：采用率和人工接管率只是起点，周期、质量、收入或成本才是结果。",
                    "测量前先冻结基线、对照口径与观察窗口，并把模型、集成、人工复核、合规和运维成本全部计入单位经济性。",
                    "规模化不是复制提示词，而是复制责任结构、数据权限、异常处理、评估集、版本管理和业务复盘机制。",
                    "管理层需要以价值可重复、采用可持续、风险可接受、运行可恢复四项门槛决定继续、调整或停止。",
                ],
                "evidence": [
                    "内部证据必需项：试点前基线、任务采用率、人工接管率、流程周期、返工/错误率、业务结果与完整成本。",
                    "归因必需项：明确对照组或前后对比方法、测量窗口、样本范围、外部变量和数据责任人。",
                    "交付前待补：与具体行业、企业流程和合规边界对应的公开案例、权威研究与客户内部经营数据。",
                ],
                "flow": [
                    "先解释为什么能力演示不等于规模化价值。",
                    "再建立‘使用—流程—业务—财务’ROI 链和证据矩阵。",
                    "把技术、业务、数据、安全和一线运营组织成同一套运行模型。",
                    f"最后给{audience}一套 90 天验证路径、三类指标和明确的继续/停止门槛。",
                ],
            }
        return {
            "thesis": (
                f"{topic} must move from a one-off capability demo to attributable operating improvement. For {audience}, the proof must show "
                "sustained adoption, repeatable workflow gains, controlled risk, and benefits that exceed build and run cost."
            ),
            "points": [
                "Replace the pilot question ‘can it work?’ with ‘which task, for which user, within which risk boundary, should change which outcome?’",
                "Build the ROI chain across use, process, business, and financial layers: adoption and human takeover are leading indicators; cycle time, quality, revenue, or cost are outcomes.",
                "Freeze the baseline, comparison method, and measurement window before launch, and include model, integration, human review, compliance, and operations in unit economics.",
                "Scale the operating system—not the prompt—by making ownership, data access, exception handling, evaluation sets, version control, and business review repeatable.",
                "Leadership should use four gates to continue, redesign, or stop: repeatable value, sustained adoption, acceptable risk, and recoverable operations.",
            ],
            "evidence": [
                "Required internal evidence: pre-pilot baseline, task adoption, human takeover, cycle time, rework or error rate, business outcome, and fully loaded cost.",
                "Required attribution design: comparison method, measurement window, sample scope, external variables, and a named data owner.",
                "Before delivery, add industry-specific cases, authoritative research, and customer operating data tied to the selected workflow and risk boundary.",
            ],
            "flow": [
                "Explain why capability evidence is not scale evidence.",
                "Build the use-to-process-to-business-to-financial ROI chain and evidence matrix.",
                "Define one operating model across business, technology, data, security, and frontline operations.",
                f"Close with a 90-day proof path, three metric families, and explicit continue-or-stop gates for {audience}.",
            ],
        }
    if _is_brand_retail_topic(context):
        if language == "zh":
            return {
                "thesis": (
                    f"“{topic}”不应只讲成一次品牌翻身故事，而要解释信任修复、产品矩阵、门店密度、数字化履约与复购机制如何共同形成增长飞轮；"
                    f"面向{audience}时，关键是判断增长质量能否从补贴驱动转向品牌资产、经营效率和可持续盈利。"
                ),
                "points": [
                    "信任修复是叙事起点：需要把危机后的治理、透明度和用户心智重建讲清楚，而不是只展示热度回升。",
                    "产品矩阵决定复购深度：爆品、季节限定、价格带和联名内容共同承担拉新、唤醒与客单价管理。",
                    "门店密度和数字化履约是增长底盘：小店模型、即时取货、App 下单与供应链效率共同影响体验稳定性。",
                    "会员私域与高频消费让品牌从一次性补贴转向复购经营，核心不是便宜，而是让购买路径更短、更确定。",
                    f"投资人更关心同店表现、利润率、履约成本、加盟/自营结构和海外扩张风险，{audience}需要看到这些指标如何进入判断框架。",
                ],
                "evidence": [
                    "可验证证据线索：财报披露的门店扩张、收入结构、利润率变化与经营现金流。",
                    "可验证证据线索：App/会员体系、上新节奏、联名传播、门店密度和供应链履约表现。",
                    "需要交付前补强引用：危机后治理信息、行业咖啡消费趋势、竞争品牌价格带与门店网络对比。",
                ],
                "flow": [
                    "先用信任修复解释为什么品牌能重新进入讨论桌。",
                    "再拆解产品矩阵、价格带、门店密度和数字化履约如何组成增长飞轮。",
                    "用投资人视角把增长拆成收入质量、复购效率、利润弹性与扩张风险。",
                    f"最后给{audience}一套可判断、可复述、可落地的品牌增长建议。",
                ],
            }
        return {
            "thesis": (
                f"{topic} should not be framed only as a turnaround story; it should explain how trust repair, product portfolio, store density, "
                f"digital fulfillment, and repeat purchase loops form a growth flywheel. For {audience}, the central question is whether growth quality "
                "is shifting from subsidy-led acquisition toward brand equity, operating efficiency, and durable profitability."
            ),
            "points": [
                "Trust repair is the opening logic: governance, transparency, and rebuilt consumer memory matter more than short-term buzz.",
                "The product portfolio drives repeat depth through hero products, seasonal drops, price bands, and co-branded attention.",
                "Store density plus digital fulfillment forms the operating base: pickup convenience, app ordering, and supply-chain stability shape experience.",
                "Membership and private-domain loops move the brand from discounting toward repeat purchase management.",
                f"{audience} should evaluate same-store momentum, margin quality, fulfillment cost, store mix, and expansion risk.",
            ],
            "evidence": [
                "Evidence to verify: financial filings on store expansion, revenue mix, margin movement, and operating cash flow.",
                "Evidence to verify: app membership, launch cadence, co-brand campaigns, store density, and fulfillment performance.",
                "Citations needed before delivery: governance after crisis, coffee consumption trends, competitor price bands, and store-network comparison.",
            ],
            "flow": [
                "Open with trust repair: why the brand returned to the strategic conversation.",
                "Unpack the growth flywheel across portfolio, price band, store density, and digital fulfillment.",
                "Translate growth into investor-facing indicators: revenue quality, repeat efficiency, margin elasticity, and expansion risk.",
                f"Close with actionable brand-growth recommendations for {audience}.",
            ],
        }

    if _is_ai_education_topic(context):
        if language == "zh":
            return {
                "thesis": (
                    f"“{topic}”的价值不在于更快生成内容，而在于重构教学设计、学习支持、评价证据与治理边界；"
                    f"面向{audience}时，必须同时讲清效率、质量、责任和学术诚信。"
                ),
                "points": [
                    "教学端：把 AI 用于备课、案例生成、个性化反馈和复习支持，但任务目标仍由教师定义。",
                    "学习端：把 AI 作为启发、练习和反馈伙伴，而不是替代阅读、推理和原创表达。",
                    "评价端：从只看最终答案转向过程证据、反思记录、口头解释和事实核验。",
                    "治理端：明确可用场景、披露要求、隐私边界和责任归属。",
                ],
                "evidence": [
                    "可验证证据线索：高校 AI 使用规范、形成性评价研究、教师反馈案例和学生学习过程记录。",
                    "需要交付前补强引用：事实准确性、学术诚信、隐私保护和学习成效评估相关研究。",
                ],
                "flow": [
                    "先从课程复习和评价痛点切入，说明为什么现在必须讨论 AI。",
                    "按教学、学习、评价、治理四层解释作用机制。",
                    "用案例和研究区分已知收益、风险边界和待验证问题。",
                    f"最后给{audience}一套课程落地与风险控制清单。",
                ],
            }
        return {
            "thesis": (
                f"The value of {topic} is not faster content generation; it is the redesign of teaching, learning support, assessment evidence, "
                f"and governance boundaries for {audience}."
            ),
            "points": [
                "Teaching: use AI for preparation, examples, feedback, and review support while educators define learning goals.",
                "Learning: use AI as a partner for inquiry and practice, not a substitute for reading, reasoning, and original expression.",
                "Assessment: evaluate process evidence, reflection, oral explanation, and fact checking.",
                "Governance: define allowed uses, disclosure, privacy boundaries, and responsibility.",
            ],
            "evidence": [
                "Evidence to verify: institutional AI policies, formative-assessment research, teacher feedback cases, and learner-process records.",
                "Citations needed before delivery: factual accuracy, academic integrity, privacy protection, and learning-outcome evaluation.",
            ],
            "flow": [
                "Open with the review and assessment pain point.",
                "Explain the mechanism across teaching, learning, assessment, and governance.",
                "Separate known benefits, risk boundaries, and open questions.",
                f"Close with a classroom implementation checklist for {audience}.",
            ],
        }

    if language == "zh":
        return {
            "thesis": (
                f"围绕“{topic}”先明确中心问题、相关角色、关键驱动因素、可验证证据与风险边界，"
                f"再把结论转化为{audience}能理解和执行的判断框架。"
            ),
            "points": [
                f"中心问题：{topic}真正改变了什么，以及为什么现在值得讨论。",
                "利益相关者：区分谁受影响、谁做决策、谁承担风险。",
                "驱动因素：把背景、行为机制、资源约束和外部环境连成因果链。",
                "行动判断：把结论压缩成可验证、可讨论、可执行的下一步。",
            ],
            "evidence": [
                "可验证证据线索：权威资料、行业报告、论文、政策文件、案例或用户数据。",
                "需要交付前补强引用：核心数字、来源日期、适用范围和反例。",
            ],
            "flow": [
                "先提出中心问题和现实意义。",
                "再拆成驱动因素、证据地图、风险边界和行动建议。",
                f"最后为{audience}提炼一个能复述的结论。",
            ],
        }
    return {
        "thesis": (
            f"For {topic}, first identify the central question, stakeholders, drivers, verifiable evidence, and risk boundary; "
            f"then translate the conclusion into a decision frame {audience} can understand and act on."
        ),
        "points": [
            f"Central question: what does {topic} actually change, and why does it matter now?",
            "Stakeholders: separate who is affected, who decides, and who carries risk.",
            "Drivers: connect context, behavior, constraints, and external environment into a causal chain.",
            "Action judgment: compress the conclusion into a verifiable, discussable, executable next step.",
        ],
        "evidence": [
            "Evidence to verify: authoritative sources, industry reports, papers, policies, cases, or user data.",
            "Citations needed before delivery: core figures, source dates, scope, and counterexamples.",
        ],
        "flow": [
            "Open with the central question and current relevance.",
            "Move through drivers, evidence map, risk boundary, and recommendation.",
            f"Close with a repeatable conclusion for {audience}.",
        ],
    }


def _is_brand_retail_topic(value: str) -> bool:
    normalized = value.lower()
    if "瑞幸" in normalized or "luckin" in normalized:
        return True
    retail_terms = (
        "咖啡",
        "门店",
        "零售",
        "新消费",
        "连锁",
        "复购",
        "coffee",
        "retail",
        "store",
        "chain",
    )
    growth_terms = ("品牌", "增长", "消费", "brand", "growth", "consumer")
    return sum(term in normalized for term in retail_terms) >= 2 and any(
        term in normalized for term in growth_terms
    )


def _research_gap_source(
    *,
    topic: str,
    audience: str,
    language: str,
    retrieved_count: int,
    target_count: int,
) -> dict[str, Any]:
    if language == "zh":
        thesis = (
            f"当前联网检索只得到 {retrieved_count} 条可用资料，少于严密 PPT 大纲建议的 {target_count} 条；"
            "因此大纲必须把已检索事实、合理推断和待补强引用分层处理，避免把资料缺口包装成确定结论。"
        )
        key_points = [
            "先用已检索资料回答中心问题，但不要夸大来源覆盖面。",
            "把机制链条拆成背景、作用机制、证据地图、风险边界和面向受众的行动。",
            "凡是缺少来源支撑的判断，都应在 PPT 中表述为待验证假设或交付前补充引用。",
            f"面向{audience}时，要把结论转成可执行的课程、研究、商业或治理动作。",
        ]
        evidence = [
            f"实时检索返回的可用来源数：{retrieved_count}/{target_count}。",
            "资料不足本身是质量信号：它要求大纲更严格地区分事实、推断和行动建议。",
        ]
        ppt_flow = [
            "第 1 层：中心问题与为什么现在需要讨论。",
            "第 2 层：从来源中抽取机制链条和关键证据。",
            "第 3 层：明确风险边界、资料缺口和下一步补强方向。",
            f"第 4 层：给{audience}一个可落地的行动清单。",
        ]
        title = f"{topic}：资料缺口与逻辑补强"
        source_label = "research-gap logic brief"
        gap_label = "资料缺口与逻辑补强"
    else:
        thesis = (
            f"Live research returned only {retrieved_count} usable source(s), below the {target_count}-source threshold for a rigorous PPT outline; "
            "therefore the outline must separate verified evidence, reasonable inference, and citations that need strengthening."
        )
        key_points = [
            "Use retrieved sources to answer the central question without overstating coverage.",
            "Force the narrative into context, mechanism, evidence map, risk boundary, and audience action.",
            "Treat unsupported claims as hypotheses or citation gaps before final delivery.",
            f"Translate conclusions into actions that {audience} can execute or debate.",
        ]
        evidence = [
            f"Usable live sources retrieved: {retrieved_count}/{target_count}.",
            "Thin source coverage is a quality signal that requires stricter claim boundaries.",
        ]
        ppt_flow = [
            "Layer 1: central question and why-now framing.",
            "Layer 2: mechanism and evidence extracted from available sources.",
            "Layer 3: risks, source gaps, and citation-strengthening plan.",
            f"Layer 4: action checklist for {audience}.",
        ]
        title = f"{topic}: Research gap and logic补强"
        source_label = "research-gap logic brief"
        gap_label = "Research gap and logic补强"
    summary = _structured_summary(
        topic=title,
        thesis=thesis,
        key_points=key_points,
        evidence=evidence,
        ppt_flow=ppt_flow,
        excerpts=[thesis],
        source_label=source_label,
    )
    summary = "\n".join(
        [
            summary,
            _logic_chain_summary(
                topic=topic,
                audience=audience,
                language=language,
                thesis=thesis,
                key_points=key_points,
                evidence=evidence,
            ),
        ]
    )
    return {
        "schemaVersion": "1.0.0",
        "sourceId": _source_id("research-gap", f"{topic}|{retrieved_count}|{target_count}"),
        "sourceType": "text",
        "title": gap_label,
        "summary": summary,
    }


def _abstract_from_inverted_index(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    positions: list[tuple[int, str]] = []
    for word, indexes in value.items():
        if not isinstance(indexes, list):
            continue
        positions.extend((int(index), str(word)) for index in indexes if isinstance(index, int))
    return _clean_text(" ".join(word for _, word in sorted(positions)))


def _sentences(value: str) -> list[str]:
    return [
        _clip(item.strip(), 420)
        for item in re.split(r"(?<=[。！？.!?])\s+|(?<=[。！？])", value)
        if len(item.strip()) >= 20
    ][:8]


def _deduplicate_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for source in sources:
        key = str(source.get("url") or source.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result


def _https_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    return value.strip()


def _source_id(provider: str, identity: str) -> str:
    digest = hashlib.sha256(f"{provider}|{identity}".encode("utf-8")).hexdigest()[:16]
    return f"web-{provider}-{digest}"


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _clip(value: str, limit: int) -> str:
    cleaned = _clean_text(value)
    if len(cleaned) <= limit:
        return cleaned
    candidate = cleaned[:limit].rstrip()
    sentence_ends = [
        match.end()
        for match in re.finditer(r"[。！？.!?](?=\s|$)", candidate)
        if match.end() >= max(20, limit // 2)
    ]
    if sentence_ends:
        return candidate[: sentence_ends[-1]].strip()
    clause_break = max(
        candidate.rfind(separator)
        for separator in ("；", ";", "：", ":", "，", ",")
    )
    if clause_break >= max(20, limit // 2):
        return candidate[:clause_break].strip()
    if not re.search(r"[\u3400-\u9fff]", candidate):
        word_break = candidate.rfind(" ")
        if word_break >= max(20, limit // 2):
            return candidate[:word_break].strip()
    return candidate.strip()
