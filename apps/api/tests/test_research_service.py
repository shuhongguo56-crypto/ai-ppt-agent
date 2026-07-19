from app.services import research


def test_research_topic_sources_normalizes_wikipedia_and_openalex(monkeypatch) -> None:
    def fake_get_json(*, url: str, params: dict, timeout_seconds: float, user_agent: str):
        assert timeout_seconds > 0
        assert "AI-PPT" in user_agent
        if "wikipedia.org" in url:
            return {
                "query": {
                    "pages": {
                        "1": {
                            "pageid": 1,
                            "title": "CRISPR",
                            "fullurl": "https://en.wikipedia.org/wiki/CRISPR",
                            "extract": (
                                "CRISPR is a family of DNA sequences found in prokaryotes. "
                                "Cas proteins use guide RNA to recognize and modify matching genetic material."
                            ),
                        }
                    }
                }
            }
        if "openalex.org" in url:
            return {
                "results": [
                    {
                        "id": "https://openalex.org/W123",
                        "display_name": "A programmable dual-RNA-guided DNA endonuclease",
                        "publication_year": 2012,
                        "doi": "https://doi.org/10.1126/science.1225829",
                        "cited_by_count": 22000,
                        "primary_location": {
                            "landing_page_url": "https://doi.org/10.1126/science.1225829"
                        },
                        "abstract_inverted_index": {
                            "A": [0],
                            "programmable": [1],
                            "RNA-guided": [2],
                            "system": [3],
                            "can": [4],
                            "target": [5],
                            "DNA": [6],
                        },
                    }
                ]
            }
        raise AssertionError(f"unexpected provider URL: {url}")

    monkeypatch.setattr(research, "_get_json", fake_get_json)

    result = research.research_topic_sources(
        project_id="project-research",
        topic="CRISPR",
        audience="undergraduates",
        language="en",
        enabled=True,
        timeout_seconds=3,
        max_sources=4,
    )

    assert result.mode == "web"
    assert result.providers == ["wikipedia", "openalex"]
    assert len(result.source_pack.sources) == 4
    assert any("Thin web research" in warning for warning in result.warnings)
    assert result.source_pack.sources[0].source_type == "text"
    assert all(
        item.url and item.url.startswith("https://")
        for item in result.source_pack.sources[1:]
        if item.source_type == "url"
    )
    combined = "\n".join(item.summary for item in result.source_pack.sources)
    assert "CRISPR" in combined
    assert "guide RNA" in combined
    assert "2012" in combined
    assert "22000" in combined
    synthesis = result.source_pack.sources[0].summary
    assert "Central question:" in synthesis
    assert "Why now:" in synthesis
    assert "Mechanism:" in synthesis
    assert "Evidence map:" in synthesis
    assert "Risk boundary:" in synthesis
    assert "Action for audience:" in synthesis
    assert "可做成PPT的大纲建议" in combined


def test_research_topic_sources_falls_back_safely_when_providers_fail(monkeypatch) -> None:
    def fail_get_json(**_kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr(research, "_get_json", fail_get_json)

    result = research.research_topic_sources(
        project_id="project-fallback",
        topic="量子计算",
        audience="本科生",
        language="zh",
        enabled=True,
        timeout_seconds=1,
        max_sources=4,
    )

    assert result.mode == "local_fallback"
    assert result.providers == []
    assert result.warnings
    assert result.source_pack.sources[0].source_type == "text"
    assert "量子计算" in result.source_pack.sources[0].summary


def test_local_fallback_is_topic_specific_without_engine_filler(monkeypatch) -> None:
    def fail_get_json(**_kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr(research, "_get_json", fail_get_json)

    result = research.research_topic_sources(
        project_id="project-luckin-fallback",
        topic="瑞幸咖啡品牌复兴与新消费增长策略",
        audience="品牌咨询客户和投资人",
        language="zh",
        enabled=True,
        timeout_seconds=1,
        max_sources=4,
    )

    assert result.mode == "local_fallback"
    summary = result.source_pack.sources[0].summary
    assert "Live public-source retrieval" not in summary
    assert "retrieval was unavailable" not in summary
    assert "定义、机制、证据、应用、限制" not in summary
    for expected in ["信任修复", "产品矩阵", "门店密度", "复购", "投资人"]:
        assert expected in summary


def test_research_filters_weakly_related_scholarly_results_for_specific_brand_topic(
    monkeypatch,
) -> None:
    def fake_get_json(*, url: str, params: dict, timeout_seconds: float, user_agent: str):
        if "wikipedia.org" in url:
            return {"query": {"pages": []}}
        if "openalex.org" in url:
            return {
                "results": [
                    {
                        "id": "https://openalex.org/W-offtopic",
                        "display_name": "绿色消费趋势下日用品品牌环保策略与实践",
                        "publication_year": 2024,
                        "doi": "https://doi.org/10.1000/offtopic",
                        "cited_by_count": 3,
                        "primary_location": {
                            "landing_page_url": "https://doi.org/10.1000/offtopic"
                        },
                        "abstract_inverted_index": {},
                    },
                    {
                        "id": "https://openalex.org/W-luckin",
                        "display_name": "瑞幸咖啡体验营销策略研究",
                        "publication_year": 2020,
                        "doi": "https://doi.org/10.1000/luckin",
                        "cited_by_count": 12,
                        "primary_location": {
                            "landing_page_url": "https://doi.org/10.1000/luckin"
                        },
                        "abstract_inverted_index": {},
                    },
                ]
            }
        if "crossref.org" in url:
            return {"message": {"items": []}}
        raise AssertionError(url)

    monkeypatch.setattr(research, "_get_json", fake_get_json)

    result = research.research_topic_sources(
        project_id="project-luckin-relevance",
        topic="瑞幸咖啡品牌复兴与新消费增长策略",
        audience="品牌咨询客户和投资人",
        language="zh",
        enabled=True,
        timeout_seconds=1,
        max_sources=4,
    )

    combined = "\n".join(source.summary for source in result.source_pack.sources)
    assert "瑞幸咖啡体验营销策略研究" in combined
    assert "绿色消费趋势下日用品品牌环保策略与实践" not in combined


def test_disabled_topic_research_does_not_create_synthetic_sources() -> None:
    result = research.research_topic_sources(
        project_id="project-disabled",
        topic="CRISPR",
        audience="undergraduates",
        language="en",
        enabled=False,
    )

    assert result.mode == "disabled"
    assert result.source_pack is None


def test_research_topic_sources_adds_gap_brief_when_web_sources_are_thin(monkeypatch) -> None:
    def fake_get_json(*, url: str, params: dict, timeout_seconds: float, user_agent: str):
        if "wikipedia.org" in url:
            return {
                "query": {
                    "pages": [
                        {
                            "pageid": 42,
                            "title": "Generative artificial intelligence",
                            "fullurl": "https://en.wikipedia.org/wiki/Generative_artificial_intelligence",
                            "extract": "Generative AI can create text, images, and other media. It raises questions about education, work, evidence, and governance.",
                        }
                    ]
                }
            }
        if "openalex.org" in url:
            return {"results": []}
        if "crossref.org" in url:
            return {"message": {"items": []}}
        raise AssertionError(url)

    monkeypatch.setattr(research, "_get_json", fake_get_json)

    result = research.research_topic_sources(
        project_id="project-thin-web",
        topic="generative AI in higher education",
        audience="university teachers",
        language="en",
        enabled=True,
        max_sources=5,
    )

    assert result.mode == "web"
    assert any("Thin web research" in warning for warning in result.warnings)
    assert any(source.source_id.startswith("web-research-gap") for source in result.source_pack.sources)
    combined = "\n".join(source.summary for source in result.source_pack.sources)
    assert "Research gap and logic补强" in combined
    assert "verified evidence" in combined
    assert "PPT logic chain:" in combined


def test_chinese_research_uses_source_facts_instead_of_english_retrieval_filler(
    monkeypatch,
) -> None:
    def fake_get_json(*, url: str, params: dict, timeout_seconds: float, user_agent: str):
        if "wikipedia.org" in url:
            return {
                "query": {
                    "pages": [
                        {
                            "pageid": 9,
                            "title": "生成式人工智能",
                            "fullurl": "https://zh.wikipedia.org/wiki/生成式人工智能",
                            "extract": (
                                "生成式人工智能能够根据训练数据生成文本、图像与其他内容。"
                                "它在教育中的价值取决于任务设计、事实核验和评价方式。"
                                "教师需要明确人工智能参与边界并保留学生的自主判断。"
                            ),
                        }
                    ]
                }
            }
        if "openalex.org" in url:
            return {"results": []}
        if "crossref.org" in url:
            return {
                "message": {
                    "items": [
                        {
                            "DOI": "10.1000/education",
                            "title": ["生成式人工智能在高等教育中的应用与效果"],
                            "URL": "https://doi.org/10.1000/education",
                            "published": {"date-parts": [[2025, 3, 1]]},
                            "container-title": ["高等教育研究"],
                        }
                    ]
                }
            }
        raise AssertionError(url)

    monkeypatch.setattr(research, "_get_json", fake_get_json)

    result = research.research_topic_sources(
        project_id="project-zh-research",
        topic="生成式人工智能在高校教学中的应用",
        audience="高校教师与本科生",
        language="zh",
        enabled=True,
    )

    synthesis = result.source_pack.sources[0]
    assert synthesis.title == "生成式人工智能在高校教学中的应用：公开资料综合"
    assert "教学设计、学习支持、评价方式与治理机制的协同重构" in synthesis.summary
    assert "教学端" in synthesis.summary
    assert "评价端" in synthesis.summary
    assert "学术诚信" in synthesis.summary
    assert "它在教育中的价值取决于任务设计、事实核验和评价方式" in synthesis.summary
    assert "2025 年研究《生成式人工智能在高等教育中的应用与效果》" in synthesis.summary

    wikipedia_summary = result.source_pack.sources[1].summary
    assert "它在教育中的价值取决于任务设计、事实核验和评价方式" in wikipedia_summary
    assert "先解释核心概念与作用机制" in wikipedia_summary
    assert "Wikipedia overview retrieved" not in wikipedia_summary
    assert "Separate established facts" not in wikipedia_summary
    scholarly_summary = result.source_pack.sources[2].summary
    assert "2025 年研究《生成式人工智能在高等教育中的应用与效果》" in scholarly_summary
    assert "发表于《高等教育研究》" in scholarly_summary
    assert "Publication year" not in scholarly_summary


def test_enterprise_ai_research_preserves_qualifiers_and_rejects_generic_ai(
    monkeypatch,
) -> None:
    captured_queries: list[tuple[str, str]] = []

    def fake_get_json(*, url: str, params: dict, timeout_seconds: float, user_agent: str):
        captured_queries.append((url, str(params.get("search") or params.get("gsrsearch") or "")))
        if "wikipedia.org" in url:
            return {
                "query": {
                    "pages": [
                        {
                            "pageid": 1,
                            "title": "Artificial intelligence",
                            "fullurl": "https://en.wikipedia.org/wiki/Artificial_intelligence",
                            "extract": "Artificial intelligence is a field of computer science. High-profile applications include web search and chatbots.",
                        }
                    ]
                }
            }
        if "openalex.org" in url:
            return {
                "results": [
                    {
                        "id": "https://openalex.org/W-generic-ai",
                        "display_name": "Artificial intelligence applications",
                        "publication_year": 2026,
                        "doi": "https://doi.org/10.1000/generic-ai",
                        "cited_by_count": 1,
                        "primary_location": {"landing_page_url": "https://doi.org/10.1000/generic-ai"},
                        "abstract_inverted_index": {},
                    },
                    {
                        "id": "https://openalex.org/W-enterprise-agents",
                        "display_name": "Measuring enterprise AI agent adoption from pilot to ROI",
                        "publication_year": 2026,
                        "doi": "https://doi.org/10.1000/enterprise-agents",
                        "cited_by_count": 4,
                        "primary_location": {"landing_page_url": "https://doi.org/10.1000/enterprise-agents"},
                        "abstract_inverted_index": {
                            "Enterprise": [0],
                            "AI": [1],
                            "agents": [2],
                            "require": [3],
                            "workflow": [4],
                            "baselines": [5],
                            "and": [6],
                            "attribution": [7],
                            "before": [8],
                            "scaling": [9],
                        },
                    },
                    {
                        "id": "https://openalex.org/W-energy-ai",
                        "display_name": "Addressing challenges for effective adoption of artificial intelligence in the energy sector",
                        "publication_year": 2026,
                        "doi": "https://doi.org/10.1000/energy-ai",
                        "cited_by_count": 2,
                        "primary_location": {"landing_page_url": "https://doi.org/10.1000/energy-ai"},
                        "abstract_inverted_index": {
                            "Artificial": [0],
                            "intelligence": [1],
                            "adoption": [2],
                            "can": [3],
                            "transform": [4],
                            "the": [5],
                            "energy": [6],
                            "sector": [7],
                        },
                    },
                ]
            }
        if "crossref.org" in url:
            return {"message": {"items": []}}
        raise AssertionError(url)

    monkeypatch.setattr(research, "_get_json", fake_get_json)
    topic = "Enterprise AI Agent Adoption 2026: From Pilot to Measurable ROI"
    result = research.research_topic_sources(
        project_id="enterprise-ai-research",
        topic=topic,
        audience="Executive leadership and business owners",
        language="en",
        enabled=True,
        max_sources=5,
    )

    assert any(topic.replace("AI", "artificial intelligence") in query for _, query in captured_queries)
    combined = "\n".join(source.summary for source in result.source_pack.sources)
    assert "Measuring enterprise AI agent adoption from pilot to ROI" in combined
    assert "energy sector" not in combined
    assert "High-profile applications include web search" not in combined
    assert "Evidence matrix:" not in combined  # canonical summaries use the bilingual section label
    assert "证据矩阵：" in result.source_pack.sources[0].summary
    assert "value, adoption, governance, and reliable operations" in result.source_pack.sources[0].summary


def test_enterprise_ai_authoritative_floor_is_decision_ready_when_live_apis_fail(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        research,
        "_get_json",
        lambda **_: (_ for _ in ()).throw(OSError("network unavailable")),
    )

    result = research.research_topic_sources(
        project_id="enterprise-ai-fallback",
        topic="Enterprise AI Agent Adoption: From Pilot to ROI",
        audience="Executive leadership",
        language="en",
        enabled=True,
    )

    summary = result.source_pack.sources[0].summary
    combined = "\n".join(source.summary for source in result.source_pack.sources)
    assert result.mode == "web"
    assert "authoritative-research-library" in result.providers
    assert "20.2% of firms" in combined
    assert "78% of survey respondents" in combined
    assert "Nearly two-thirds of respondents" in combined
    assert "NIST AI 600-1" in combined
    assert "…" not in combined
    for expected in [
        "Value chain: connect model use to task adoption",
        "human takeover",
        "fully loaded cost",
        "continue, redesign, or stop",
    ]:
        assert expected in summary
    assert "what does Enterprise AI" not in summary
