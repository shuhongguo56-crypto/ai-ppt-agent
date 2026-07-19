from copy import deepcopy
from types import SimpleNamespace

from fastapi.testclient import TestClient

from ai_ppt_contracts import SourcePack
from app.config import Settings
from app.main import create_app
from app.services.research import TopicResearchResult


PROJECT = {
    "schemaVersion": "1.0.0",
    "projectId": "project-outline",
    "inputLanguage": "zh",
    "outputLanguage": "en",
    "deckType": "course_presentation",
    "topic": "CRISPR",
    "audience": "Undergraduates",
    "mode": "professional",
}


def create_project(client, project: dict = PROJECT):
    return client.post("/api/projects", json=project)


def generate_outline(client, project_id: str = "project-outline", body: dict | None = None):
    return client.post(
        f"/api/projects/{project_id}/outline/generate",
        json={} if body is None else body,
    )


def test_research_mode_supplements_supplied_sources_without_replacing_them(
    client, monkeypatch
) -> None:
    project = {
        **PROJECT,
        "projectId": "project-supplied-plus-research",
        "outputLanguage": "zh",
        "deckType": "business_pitch",
        "topic": "新能源汽车品牌下一阶段增长",
        "audience": "企业管理层",
        "agentMode": "research",
    }
    client.app.state.settings.topic_research_enabled = True
    assert create_project(client, project).status_code == 201
    supplied = {
        "schemaVersion": "1.0.0",
        "projectId": project["projectId"],
        "sources": [
            {
                "schemaVersion": "1.0.0",
                "sourceId": "supplied-notes",
                "sourceType": "text",
                "title": "用户资料",
                "summary": "\n".join(
                    [
                        "核心主题：新能源汽车增长",
                        "文章主旨：企业需要从规模扩张转向利润、品牌心智与组织效率并重。",
                        "关键论点：",
                        "- 行业竞争已转向产品、成本、渠道与全球化能力。",
                        "- 用户更关注补能体验、可信度与全生命周期成本。",
                    ]
                ),
            }
        ],
    }
    supplement = SourcePack(
        schemaVersion="1.0.0",
        projectId=project["projectId"],
        sources=[
            {
                "schemaVersion": "1.0.0",
                "sourceId": "public-source",
                "sourceType": "url",
                "title": "行业公开资料",
                "url": "https://example.com/industry",
                "summary": "核心主题：新能源汽车行业\n文章主旨：公开资料用于交叉验证行业变化。",
            }
        ],
    )
    monkeypatch.setattr(
        "app.routes.outline.research_topic_sources",
        lambda **_: TopicResearchResult(
            source_pack=supplement,
            mode="web",
            providers=["test-provider"],
            query=project["topic"],
            warnings=[],
        ),
    )

    response = generate_outline(
        client,
        project["projectId"],
        body={"sourcePack": supplied, "supplementResearch": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["research"]["mode"] == "supplied_plus_web"
    assert [source["sourceId"] for source in payload["sourcePack"]["sources"]] == [
        "supplied-notes",
        "public-source",
    ]
    visible = " ".join(
        slide["title"] for slide in payload["outlineDecision"]["slides"]
    )
    assert "补贴" not in visible
    assert "咖啡" not in visible


def test_generate_outline_creates_draft_checkpoint(client) -> None:
    assert create_project(client).status_code == 201

    response = generate_outline(client)

    assert response.status_code == 200
    payload = response.json()
    assert payload["stage"] == "outline"
    assert payload["status"] == "draft"
    assert payload["version"] == 1
    assert payload["nextStep"] == "outline_review"
    outline = payload["outlineDecision"]
    assert outline["schemaVersion"] == "1.0.0"
    assert outline["projectId"] == "project-outline"
    assert outline["language"] == "en"
    assert outline["targetSlideCount"] == len(outline["slides"])
    assert outline["slides"][0]["purpose"] == "cover"
    assert outline["slides"][-1]["purpose"] == "conclusion"
    assert outline["generatedBy"]["skillName"] == "HumanizePPT"


def test_topic_only_outline_researches_public_sources_before_generation(
    client, monkeypatch
) -> None:
    assert create_project(client).status_code == 201
    calls: list[dict] = []

    def fake_research(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            source_pack=SourcePack(
                schemaVersion="1.0.0",
                projectId="project-outline",
                sources=[
                    {
                        "schemaVersion": "1.0.0",
                        "sourceId": "web-wikipedia-crispr",
                        "sourceType": "url",
                        "title": "CRISPR",
                        "url": "https://en.wikipedia.org/wiki/CRISPR",
                        "summary": "\n".join(
                            [
                                "核心主题：CRISPR genome editing",
                                "文章主旨：CRISPR uses guide RNA and Cas proteins to target DNA sequences.",
                                "关键论点：",
                                "- guide RNA provides sequence specificity",
                                "- Cas enzymes cut or modify targeted DNA",
                                "重要事实/数据/证据：",
                                "- the system was adapted from bacterial adaptive immunity",
                                "可做成PPT的大纲建议：",
                                "- explain the mechanism before applications and risks",
                                "原文摘录：",
                                "- clustered regularly interspaced short palindromic repeats",
                            ]
                        ),
                    }
                ],
            ),
            mode="web",
            providers=["wikipedia"],
            query="CRISPR",
            warnings=[],
        )

    monkeypatch.setattr("app.routes.outline.research_topic_sources", fake_research)

    response = generate_outline(client)

    assert response.status_code == 200
    payload = response.json()
    assert calls and calls[0]["topic"] == "CRISPR"
    assert calls[0]["max_sources"] >= 7
    assert calls[0]["timeout_seconds"] >= 10.0
    assert payload["agentMode"] == "research"
    assert payload["executionPolicy"]["qualityProfile"] == "enterprise_ppt"
    assert payload["research"]["mode"] == "web"
    assert payload["research"]["providers"] == ["wikipedia"]
    assert payload["sourcePack"]["sources"][0]["sourceType"] == "url"
    assert payload["sourcePack"]["sources"][0]["url"].startswith("https://")
    assert "web-wikipedia-crispr" in payload["outlineDecision"]["citationNeeds"]
    assert any(
        "web-wikipedia-crispr" in slide["citationIds"]
        for slide in payload["outlineDecision"]["slides"]
    )


def test_enterprise_ai_outline_replaces_generic_ai_with_roi_decision_story(
    client, monkeypatch
) -> None:
    project = {
        **PROJECT,
        "projectId": "enterprise-ai-outline",
        "outputLanguage": "en",
        "deckType": "business_pitch",
        "topic": "Enterprise AI Agent Adoption 2026: From Pilot to Measurable ROI",
        "audience": "Executive leadership and business owners",
        "agentMode": "research",
    }
    client.app.state.settings.topic_research_enabled = True
    assert create_project(client, project).status_code == 201
    source_pack = SourcePack(
        schemaVersion="1.0.0",
        projectId=project["projectId"],
        sources=[
            {
                "schemaVersion": "1.0.0",
                "sourceId": "web-research-synthesis-enterprise-ai",
                "sourceType": "text",
                "title": "Enterprise AI Agent Adoption: public-source synthesis",
                "summary": "\n".join(
                    [
                        "核心主题：Enterprise AI Agent Adoption 2026: From Pilot to Measurable ROI",
                        "文章主旨：Artificial intelligence is the capability of computational systems to perform tasks.",
                        "关键论点：",
                        "- High-profile applications of AI include web search engines and chatbots.",
                        "重要事实/数据/证据：",
                        "- Publication year: 2026",
                    ]
                ),
            }
        ],
    )
    monkeypatch.setattr(
        "app.routes.outline.research_topic_sources",
        lambda **_: TopicResearchResult(
            source_pack=source_pack,
            mode="web",
            providers=["test-provider"],
            query=project["topic"],
            warnings=[],
        ),
    )

    response = generate_outline(client, project["projectId"])

    assert response.status_code == 200
    outline = response.json()["outlineDecision"]
    titles = [slide["title"] for slide in outline["slides"]]
    visible = " ".join(
        [
            *titles,
            *[slide["keyPoint"] for slide in outline["slides"]],
            *[
                point
                for slide in outline["slides"]
                for point in slide["talkingPoints"]
            ],
        ]
    )
    for expected in [
        "Four gates from pilot to scale",
        "ROI chain: use → process → outcome → value",
        "Evidence matrix: baseline, attribution, risk",
        "A 90-day proof path",
        "Run AI agents as an operating system",
    ]:
        assert expected in titles
    for expected in [
        "human takeover",
        "fully loaded cost",
        "continue, redesign, or stop",
        "repeatable business value",
    ]:
        assert expected in visible
    assert "High-profile applications of AI" not in visible
    assert "translate the conclusion into steps" not in visible
    assert len({slide["keyPoint"] for slide in outline["slides"]}) == len(
        outline["slides"]
    )


def test_supplied_source_pack_skips_automatic_topic_research(client, monkeypatch) -> None:
    assert create_project(client).status_code == 201

    def fail_if_called(**_kwargs):
        raise AssertionError("topic research must not replace supplied source material")

    monkeypatch.setattr("app.routes.outline.research_topic_sources", fail_if_called)
    supplied = {
        "schemaVersion": "1.0.0",
        "projectId": "project-outline",
        "sources": [
            {
                "schemaVersion": "1.0.0",
                "sourceId": "user-source",
                "sourceType": "text",
                "summary": "用户提供的材料摘要",
            }
        ],
    }

    response = generate_outline(client, body={"sourcePack": supplied})

    assert response.status_code == 200
    returned_source = response.json()["sourcePack"]["sources"][0]
    assert returned_source["sourceId"] == "user-source"
    assert returned_source["summary"] == "用户提供的材料摘要"
    assert response.json()["research"]["mode"] == "supplied"


def test_one_click_generation_still_requires_outline_review(client) -> None:
    project = PROJECT | {"projectId": "one-click", "mode": "one_click"}
    assert create_project(client, project).status_code == 201

    response = generate_outline(client, "one-click")

    assert response.status_code == 200
    assert response.json()["status"] == "draft"
    assert response.json()["nextStep"] == "outline_review"


def test_generate_outline_accepts_source_pack_and_rejects_mismatch(client) -> None:
    assert create_project(client).status_code == 201
    source_pack = {
        "schemaVersion": "1.0.0",
        "projectId": "project-outline",
        "sources": [
            {
                "schemaVersion": "1.0.0",
                "sourceId": "source-1",
                "sourceType": "text",
                "summary": "A source summary",
            }
        ],
    }

    response = generate_outline(client, body={"sourcePack": source_pack})

    assert response.status_code == 200
    outline = response.json()["outlineDecision"]
    assert outline["citationNeeds"] == ["source-1"]
    assert any(
        "A source summary" in slide["keyPoint"]
        or any("A source summary" in point for point in slide["talkingPoints"])
        for slide in outline["slides"]
    )

    mismatch = deepcopy(source_pack)
    mismatch["projectId"] = "other"
    rejected = generate_outline(client, body={"sourcePack": mismatch})
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "source_pack_project_mismatch"


def test_outline_uses_structured_source_analysis_instead_of_generic_filler(client) -> None:
    assert create_project(client).status_code == 201
    source_pack = {
        "schemaVersion": "1.0.0",
        "projectId": "project-outline",
        "sources": [
            {
                "schemaVersion": "1.0.0",
                "sourceId": "sleep-source",
                "sourceType": "text",
                "title": "sleep-learning.md",
                "summary": "\n".join(
                    [
                        "文件名：sleep-learning.md",
                        "核心主题：Sleep and Learning in First-Year Students",
                        "文章主旨：stable sleep is not a wellness bonus but a learning infrastructure",
                        "关键论点：",
                        "- students treat slide preparation as a late-night task",
                        "- presentation quality collapses when synthesis and rehearsal are needed",
                        "重要事实/数据/证据：",
                        "- a 2025 campus survey of 1,200 first-year students reported 31% lower recall",
                        "可做成PPT的大纲建议：",
                        "- explain why sleep is learning infrastructure",
                        "- visualize the 31% lower recall evidence",
                        "原文摘录：",
                        "- earlier outline locking, shorter rehearsal loops, and instructor feedback",
                        "PPT logic chain:",
                        "Central question: What does sleep timing change in first-year presentation learning?",
                        "Why now: students increasingly compress preparation into late-night tool use.",
                        "Mechanism: connect sleep timing, synthesis quality, rehearsal loops, and feedback.",
                        "Evidence map:",
                        "- 31% lower recall among late-night preparation groups",
                        "Risk boundary: correlation evidence needs careful wording before policy claims.",
                        "Action for audience: help students lock outlines earlier and protect rehearsal time.",
                    ]
                ),
            }
        ],
    }

    response = generate_outline(client, body={"sourcePack": source_pack})

    assert response.status_code == 200
    outline = response.json()["outlineDecision"]
    combined = " ".join(
        [
            outline["objective"],
            *outline["narrative"],
            *[
                " ".join(
                    [
                        slide["title"],
                        slide["keyPoint"],
                        " ".join(slide["talkingPoints"]),
                        slide["speakerNotesDraft"],
                    ]
                )
                for slide in outline["slides"]
            ],
        ]
    )
    assert "sleep is not a wellness bonus" in combined
    assert "late-night task" in combined
    assert "31% lower recall" in combined
    assert "What does sleep timing change" in combined
    assert "correlation evidence needs careful wording" in combined
    assert "sleep-source" in outline["citationNeeds"]
    assert any("sleep-source" in slide["citationIds"] for slide in outline["slides"])


def test_case_competition_outline_parses_chinese_case_sections_into_strategy_story(
    client,
) -> None:
    project = PROJECT | {
        "projectId": "luckin-section-case",
        "outputLanguage": "zh",
        "deckType": "case_competition",
        "topic": "瑞幸咖啡品牌复兴与新消费增长策略",
        "audience": "商业案例竞赛评委、品牌咨询客户与投资人",
    }
    assert create_project(client, project).status_code == 201
    source_pack = {
        "schemaVersion": "1.0.0",
        "projectId": "luckin-section-case",
        "sources": [
            {
                "schemaVersion": "1.0.0",
                "sourceId": "luckin-section-source",
                "sourceType": "text",
                "title": "瑞幸咖啡品牌复兴案例资料",
                "summary": "\n".join(
                    [
                        "瑞幸咖啡案例材料：",
                        "一、背景：瑞幸在财务风波后重建组织信任，通过门店模型、供应链和数字化运营回到增长轨道。",
                        "二、核心问题：品牌如何把低价促销从短期拉新工具，升级为可持续的新消费增长系统。",
                        "三、关键证据：产品端以爆品拉动讨论，渠道端以小店密度和外卖覆盖提升触达，用户端以会员、私域和小程序完成复购。",
                        "四、洞察：真正的复兴不是单点营销胜利，而是把产品创新、价格心智、门店效率和数据闭环组成飞轮。",
                        "五、建议：未来应从低价券补贴转向分层会员权益，从爆品流量转向品类矩阵，并用区域化供应链降低履约成本。",
                        "六、结论：瑞幸的讨论价值在于它把危机后的信任修复、新消费价格心智和数字化效率放在一个系统中评估。",
                    ]
                ),
            }
        ],
    }

    response = generate_outline(
        client,
        "luckin-section-case",
        body={"sourcePack": source_pack},
    )

    assert response.status_code == 200
    outline = response.json()["outlineDecision"]
    titles = [slide["title"] for slide in outline["slides"]]
    visible = " ".join(
        text
        for slide in outline["slides"]
        for text in [slide["title"], slide["keyPoint"], *slide["talkingPoints"]]
    )
    assert "危机后信任修复" in titles
    assert "作用机制：增长飞轮" in titles
    assert "关键证据：产品 × 渠道 × 用户" in titles
    assert "落地路径：会员、品类、供应链" in titles
    assert "结论：信任修复与数字效率" in titles
    assert "一、背景" not in " ".join(titles)
    assert "作用机制：一、背景" not in visible
    for expected in ["财务风波", "低价促销", "产品端", "会员", "供应链", "信任修复"]:
        assert expected in visible
    assert all(len(slide["title"]) <= 36 for slide in outline["slides"])
    assert all(len(slide["keyPoint"]) <= 110 for slide in outline["slides"])


def test_source_grounded_outline_hides_internal_planning_labels_from_visible_copy(client) -> None:
    project = PROJECT | {
        "projectId": "source-copy-zh",
        "outputLanguage": "zh",
        "topic": "生成式人工智能在高校教学中的应用",
        "audience": "高校教师与本科生",
    }
    assert create_project(client, project).status_code == 201
    source_pack = {
        "schemaVersion": "1.0.0",
        "projectId": "source-copy-zh",
        "sources": [
            {
                "schemaVersion": "1.0.0",
                "sourceId": "research-source",
                "sourceType": "url",
                "title": "生成式人工智能与高校教学",
                "url": "https://example.org/research",
                "summary": "\n".join(
                    [
                        "核心主题：生成式人工智能与高校教学",
                        "文章主旨：生成式人工智能正在把高等教育从工具使用推向教学设计、学习支持、评价方式与治理机制的协同重构，它的价值取决于教师能否同时提升学习质量并守住事实核验、学术诚信与自主判断的边界。",
                        "关键论点：",
                        "- 教师需要先定义学习目标，再决定使用何种人工智能能力",
                        "- 学生应说明人工智能参与范围并核验关键事实",
                        "重要事实/数据/证据：",
                        "- 课堂实践需要同时观察学习质量、效率与学术诚信",
                        "可做成PPT的大纲建议：",
                        "- 先解释教学目标，再展示应用流程和风险控制",
                        "原文摘录：",
                        "- 技术采用必须服务于清晰的教学判断",
                    ]
                ),
            }
        ],
    }

    response = generate_outline(
        client,
        "source-copy-zh",
        body={"sourcePack": source_pack},
    )

    assert response.status_code == 200
    outline = response.json()["outlineDecision"]
    visible = " ".join(
        text
        for slide in outline["slides"]
        for text in [slide["title"], slide["keyPoint"], *slide["talkingPoints"]]
    )
    assert "教师需要先定义学习目标" in visible
    assert all(len(slide["title"]) <= 36 for slide in outline["slides"])
    assert all(len(slide["keyPoint"]) <= 110 for slide in outline["slides"])
    assert all(
        len(point) <= 72
        for slide in outline["slides"]
        for point in slide["talkingPoints"]
    )
    for forbidden in (
        "第 1 页",
        "第 2 页",
        "第 3 页",
        "原文线索：",
        "页面作用：",
        "可引用证据：",
        "Source claim:",
        "Slide role:",
        "Traceable evidence:",
        "Useful excerpt:",
    ):
        assert forbidden not in visible


def test_source_grounded_outline_aggregates_multiple_sources_and_prioritizes_scholarly_evidence(
    client,
) -> None:
    project = PROJECT | {
        "projectId": "multi-source-evidence",
        "outputLanguage": "zh",
        "topic": "生成式人工智能与高等教育",
        "audience": "高校教师",
    }
    assert create_project(client, project).status_code == 201
    source_pack = {
        "schemaVersion": "1.0.0",
        "projectId": "multi-source-evidence",
        "sources": [
            {
                "schemaVersion": "1.0.0",
                "sourceId": "web-wikipedia-topic",
                "sourceType": "url",
                "title": "生成式人工智能",
                "url": "https://zh.wikipedia.org/wiki/example",
                "summary": "\n".join(
                    [
                        "核心主题：生成式人工智能",
                        "文章主旨：生成式人工智能可以生成多种内容。",
                        "关键论点：",
                        "- 教师需要明确使用边界",
                        "重要事实/数据/证据：",
                        "- 百科资料说明其核心能力是生成内容",
                        "可做成PPT的大纲建议：",
                        "- 先解释概念",
                        "原文摘录：",
                        "- 生成模型根据训练数据产生内容",
                    ]
                ),
            },
            {
                "schemaVersion": "1.0.0",
                "sourceId": "web-crossref-study",
                "sourceType": "url",
                "title": "高校生成式人工智能教学研究",
                "url": "https://doi.org/10.1000/example",
                "summary": "\n".join(
                    [
                        "核心主题：高校生成式人工智能教学研究",
                        "文章主旨：课程设计与评价机制共同决定技术效果。",
                        "关键论点：",
                        "- 评价方式必须覆盖事实准确性和学生自主判断",
                        "重要事实/数据/证据：",
                        "- 2025 年同行评审研究强调课程目标与评价机制需要同步设计",
                        "可做成PPT的大纲建议：",
                        "- 用证据页说明评价机制",
                        "原文摘录：",
                        "- 技术效果依赖教学设计",
                    ]
                ),
            },
        ],
    }

    response = generate_outline(
        client,
        "multi-source-evidence",
        body={"sourcePack": source_pack},
    )

    assert response.status_code == 200
    outline = response.json()["outlineDecision"]
    evidence_slide = next(slide for slide in outline["slides"] if slide["purpose"] == "evidence")
    visible = " ".join([evidence_slide["title"], evidence_slide["keyPoint"], *evidence_slide["talkingPoints"]])
    assert "2025 年同行评审研究" in visible
    assert "百科资料说明其核心能力" in " ".join(
        point for slide in outline["slides"] for point in slide["talkingPoints"]
    )
    assert set(evidence_slide["citationIds"]) == {
        "web-wikipedia-topic",
        "web-crossref-study",
    }
    assert outline["slides"][0]["title"] == "生成式人工智能与高等教育"
    assert all(len(slide["title"]) <= 36 for slide in outline["slides"])
    assert all(len(slide["keyPoint"]) <= 110 for slide in outline["slides"])
    assert all(
        len(point) <= 72
        for slide in outline["slides"]
        for point in slide["talkingPoints"]
    )


def test_generate_outline_creates_chinese_content_for_chinese_output(client) -> None:
    project = PROJECT | {
        "projectId": "project-outline-zh",
        "outputLanguage": "zh",
        "topic": "人工智能如何帮助大学生提升课堂展示质量",
        "audience": "课堂老师和本科生",
    }
    assert create_project(client, project).status_code == 201

    response = generate_outline(client, "project-outline-zh")

    assert response.status_code == 200
    outline = response.json()["outlineDecision"]
    assert outline["language"] == "zh"
    assert outline["slides"][0]["title"] == "人工智能如何帮助大学生提升课堂展示质量"
    visible = " ".join(
        text
        for slide in outline["slides"]
        for text in [slide["title"], slide["keyPoint"], *slide["talkingPoints"]]
    )
    assert "第1页" not in visible
    assert "用一句清晰主张" not in visible
    assert "这份 PPT 要解决" not in visible
    assert "效率、质量、责任" in visible or "目标、反馈、评价" in visible
    assert outline["slides"][1]["title"] == "汇报路径"


def test_chinese_auto_research_keeps_slide_titles_chinese(tmp_path, monkeypatch) -> None:
    app = create_app(
        Settings(
            database_path=tmp_path / "zh-auto-research.db",
            asset_path=tmp_path / "assets",
            topic_research_enabled=True,
        )
    )

    def fake_research(**_kwargs):
        return SimpleNamespace(
            source_pack=SourcePack(
                schemaVersion="1.0.0",
                projectId="zh-auto-research",
                sources=[
                    {
                        "schemaVersion": "1.0.0",
                        "sourceId": "web-local-research-fallback-crispr",
                        "sourceType": "text",
                        "title": "CRISPR：公开资料综合",
                        "summary": "\n".join(
                            [
                                "核心主题：CRISPR 基因编辑在医学中的应用与风险",
                                "文章主旨：CRISPR 的医学价值需要同时解释作用机制、应用场景与风险边界。",
                                "关键论点：",
                                "- 区分工作机制、现实应用与关键限制",
                                "重要事实/数据/证据：",
                                "- Live public-source evidence should stay out of Chinese slide titles",
                                "可做成PPT的大纲建议：",
                                "- 先解释机制，再讨论医学应用与风险",
                            ]
                        ),
                    }
                ],
            ),
            mode="web",
            providers=["wikipedia"],
            query="CRISPR medicine",
            warnings=[],
        )

    monkeypatch.setattr("app.routes.outline.research_topic_sources", fake_research)
    project = PROJECT | {
        "projectId": "zh-auto-research",
        "outputLanguage": "zh",
        "topic": "CRISPR 基因编辑在医学中的应用与风险",
        "audience": "准备课程汇报的本科生",
    }
    with TestClient(app) as local_client:
        assert create_project(local_client, project).status_code == 201
        response = generate_outline(local_client, "zh-auto-research")

    assert response.status_code == 200
    titles = [slide["title"] for slide in response.json()["outlineDecision"]["slides"]]
    assert "公开资料与研究证据" in titles
    assert all("Live public-source" not in title for title in titles)


def test_topic_only_outline_compacts_disambiguation_topic_for_ppt_titles(client) -> None:
    project = PROJECT | {
        "projectId": "project-outline-long-topic",
        "outputLanguage": "zh",
        "topic": "AI可以指：人工智能 (Artificial Intelligence) 在高等教育课程复习、形成性评价、学习支持与治理机制中的系统性重构路径",
        "audience": "准备课程汇报的本科生和研究生",
    }
    assert create_project(client, project).status_code == 201

    response = generate_outline(client, "project-outline-long-topic")

    assert response.status_code == 200
    outline = response.json()["outlineDecision"]
    visible = " ".join(
        text
        for slide in outline["slides"]
        for text in [slide["title"], slide["keyPoint"], *slide["talkingPoints"]]
    )
    assert outline["slides"][0]["title"] == "人工智能重构高等教育学习、评价与治理"
    assert "…" not in outline["slides"][0]["title"]
    assert "AI可以指" not in visible
    assert "Artificial Intelligence" not in visible
    assert "效率、质量、责任" in visible


def test_luckin_topic_only_outline_uses_business_logic_not_generic_fallback(
    tmp_path, monkeypatch
) -> None:
    app = create_app(
        Settings(
            database_path=tmp_path / "luckin-business-outline.db",
            asset_path=tmp_path / "assets",
            topic_research_enabled=True,
        )
    )

    def fail_get_json(**_kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr("app.services.research._get_json", fail_get_json)
    project = PROJECT | {
        "projectId": "luckin-business-outline",
        "outputLanguage": "zh",
        "deckType": "business_pitch",
        "topic": "瑞幸咖啡品牌复兴与新消费增长策略",
        "audience": "品牌咨询客户和投资人",
    }
    with TestClient(app) as local_client:
        assert create_project(local_client, project).status_code == 201
        response = generate_outline(local_client, "luckin-business-outline")

    assert response.status_code == 200
    payload = response.json()
    assert payload["research"]["mode"] == "local_fallback"
    outline = payload["outlineDecision"]
    visible = " ".join(
        text
        for slide in outline["slides"]
        for text in [slide["title"], slide["keyPoint"], *slide["talkingPoints"]]
    )
    assert "Live public-source retrieval" not in visible
    assert "定义、机制、证据、应用、限制" not in visible
    assert "工作机制、现实应用与关键限制" not in visible
    for expected in ["信任修复", "产品矩阵", "门店密度", "复购"]:
        assert expected in visible
    assert outline["slides"][0]["title"] == "瑞幸咖啡品牌复兴与新消费增长策略"


def test_outline_strips_encoding_damage_from_visible_copy(client) -> None:
    project = PROJECT | {
        "projectId": "project-outline-damaged-topic",
        "outputLanguage": "zh",
        "topic": "CRISPR ??????????????",
        "audience": "准备课程汇报的本科生",
    }
    assert create_project(client, project).status_code == 201

    response = generate_outline(client, "project-outline-damaged-topic")

    assert response.status_code == 200
    outline = response.json()["outlineDecision"]
    visible = " ".join(
        text
        for slide in outline["slides"]
        for text in [slide["title"], slide["keyPoint"], *slide["talkingPoints"]]
    )
    assert outline["slides"][0]["title"] == "CRISPR"
    assert "???" not in visible
    assert "\ufffd" not in visible


def test_cascade_without_real_provider_uses_enhanced_local_planner(tmp_path) -> None:
    app = create_app(
        Settings(
            database_path=tmp_path / "cascade-workflow.db",
            asset_path=tmp_path / "assets",
            model_backend="cascade",
            compatible_enabled=False,
            cascade_include_ollama=False,
            cascade_include_fake_fallback=True,
            topic_research_enabled=False,
        )
    )
    project = PROJECT | {
        "projectId": "cascade-local",
        "outputLanguage": "zh",
        "topic": "人工智能如何帮助大学生提升课堂展示质量",
        "audience": "课堂老师和本科生",
    }
    with TestClient(app) as client:
        assert client.post("/api/projects", json=project).status_code == 201
        outline_response = client.post("/api/projects/cascade-local/outline/generate", json={})
        assert outline_response.status_code == 200
        outline = outline_response.json()["outlineDecision"]
        assert outline["slides"][0]["title"] == "人工智能如何帮助大学生提升课堂展示质量"
        assert "xxxxxxxx" not in outline["slides"][0]["title"]
        confirmed = client.post(
            "/api/projects/cascade-local/outline/confirm",
            json={"outlineDecisionVersion": outline_response.json()["version"]},
        )
        visual = client.post(
            "/api/projects/cascade-local/visual-directions/generate",
            json={"outlineDecisionVersion": confirmed.json()["version"]},
        )

    assert visual.status_code == 200
    direction_ids = [
        direction["directionId"]
        for direction in visual.json()["visualDirection"]["directions"]
    ]
    assert 4 <= len(direction_ids) <= 6
    assert len(set(direction_ids)) == len(direction_ids)
    assert direction_ids[:3] == ["workshop_playbook", "classroom_friendly", "data_story"]


def test_patch_and_confirm_outline_flow(client) -> None:
    assert create_project(client).status_code == 201
    generated = generate_outline(client).json()
    outline = generated["outlineDecision"]
    outline["slides"][1]["title"] = "Edited evidence slide"

    patched = client.patch(
        "/api/projects/project-outline/outline",
        json={"expectedVersion": 1, "outlineDecision": outline},
    )

    assert patched.status_code == 200
    assert patched.json()["version"] == 2
    assert patched.json()["status"] == "draft"
    assert patched.json()["outlineDecision"]["slides"][1]["title"] == "Edited evidence slide"

    stale = client.post(
        "/api/projects/project-outline/outline/confirm",
        json={"outlineDecisionVersion": 1},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "checkpoint_version_conflict"

    confirmed = client.post(
        "/api/projects/project-outline/outline/confirm",
        json={"outlineDecisionVersion": 2},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["version"] == 3
    assert confirmed.json()["status"] == "confirmed"
    assert confirmed.json()["nextStep"] == "visual_direction"


def test_outline_routes_return_safe_missing_and_validation_errors(client) -> None:
    missing = generate_outline(client, "missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "project_not_found"

    assert create_project(client).status_code == 201
    missing_outline = client.post(
        "/api/projects/project-outline/outline/confirm",
        json={"outlineDecisionVersion": 1},
    )
    assert missing_outline.status_code == 404
    assert missing_outline.json()["error"]["code"] == "outline_not_found"

    generated = generate_outline(client).json()
    outline = generated["outlineDecision"]
    outline["projectId"] = "other"
    mismatch = client.patch(
        "/api/projects/project-outline/outline",
        json={"expectedVersion": 1, "outlineDecision": outline},
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "outline_project_mismatch"


def test_brand_growth_source_pack_compacts_short_material_into_enterprise_story(client) -> None:
    project = PROJECT | {
        "projectId": "luckin-short-source",
        "outputLanguage": "zh",
        "deckType": "business_pitch",
        "topic": "瑞幸咖啡品牌复兴与新消费增长策略",
        "audience": "品牌咨询客户与投资分析听众",
    }
    assert create_project(client, project).status_code == 201
    source_pack = {
        "schemaVersion": "1.0.0",
        "projectId": "luckin-short-source",
        "sources": [
            {
                "schemaVersion": "1.0.0",
                "sourceId": "luckin-short-material",
                "sourceType": "text",
                "title": "瑞幸咖啡品牌复兴与新消费增长策略.txt",
                "summary": "\n".join(
                    [
                        "核心主题：瑞幸咖啡品牌复兴与新消费增长策略",
                        "文章主旨：核心判断：瑞幸真正改变的不是单次营销，而是把产品创新、低摩擦购买路径、私域复购、门店密度和供应链周转连成一套可复制增长系统。",
                        "关键论点：",
                        "- 瑞幸咖啡品牌复兴与新消费增长策略：本报告聚焦瑞幸在危机后的信任修复、数字化门店网络、联名产品爆发、供应链效率与会员复购飞轮。",
                        "- 最终建议要形成从问题、机制、证据到行动的严密逻辑。",
                        "- 需要向品牌咨询客户说明：什么可以迁移，什么不可复制，如何建立验证指标。",
                        "- 关键证据方向包括：门店扩张、APP/小程序下单、爆品联名、价格带、年轻消费场景、财务表现、品牌信任修复。",
                    ]
                ),
            }
        ],
    }

    response = generate_outline(
        client,
        "luckin-short-source",
        body={"sourcePack": source_pack},
    )

    assert response.status_code == 200
    outline = response.json()["outlineDecision"]
    titles = [slide["title"] for slide in outline["slides"]]
    visible = " ".join(
        text
        for slide in outline["slides"]
        for text in [slide["title"], slide["keyPoint"], *slide["talkingPoints"]]
    )
    assert "证据地图：门店、APP 与复购" in titles
    assert "核心洞察：从营销热度到增长飞轮" in titles
    assert "落地路径：指标化验收" in titles
    assert all(len(title) <= 36 for title in titles)
    assert all("本报告聚焦" not in title for title in titles)
    assert all("…" not in title for title in titles)
    assert "增长飞轮" in visible
    for expected in ["信任修复", "产品创新", "门店密度", "会员复购", "供应链效率"]:
        assert expected in visible
