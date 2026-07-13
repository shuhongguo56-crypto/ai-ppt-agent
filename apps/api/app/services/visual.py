from __future__ import annotations

import json
import hashlib
import re
from typing import Any

from ai_ppt_contracts import OutlineDecision, VisualDirectionDecision
from ai_ppt_contracts.visual import visual_generated_at_now
from ai_ppt_skills import builtin_registry
from app.ai.errors import ModelGatewayError
from app.ai.models import TextRequest
from app.ai.protocols import TextGateway


_GENERATION_ID_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["fakeId"],
    "properties": {"fakeId": {"type": "string", "minLength": 64, "maxLength": 64}},
    "additionalProperties": False,
}

_VISUAL_DIRECTION_IDS = [
    "apple",
    "mckinsey",
    "airbnb",
    "academic_clean",
    "thesis_blue",
    "research_journal",
    "startup_pitch",
    "investor_dark",
    "classroom_friendly",
    "data_story",
    "editorial_magazine",
    "glassmorphism",
    "medical_science",
    "cinematic_research",
    "policy_brief",
    "ink_classical",
    "product_showcase",
    "architectural_premium",
    "finance_terminal",
    "workshop_playbook",
]

_VISUAL_CONTENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["directions"],
    "additionalProperties": False,
    "properties": {
        "directions": {
            "type": "array",
            "minItems": 2,
            "maxItems": 8,
            "items": {
                "type": "object",
                "required": [
                    "directionId",
                    "name",
                    "mood",
                    "palette",
                    "typography",
                    "layoutPrinciples",
                    "textureLayer",
                    "sampleSlideIntents",
                    "motionPlan",
                    "layeringPlan",
                    "imageStrategy",
                    "hyperframesPlan",
                    "riskNotes",
                ],
                "additionalProperties": False,
                "properties": {
                    "directionId": {"type": "string", "enum": _VISUAL_DIRECTION_IDS},
                    "name": {"type": "string", "minLength": 2, "maxLength": 80},
                    "mood": {"type": "string", "minLength": 8, "maxLength": 180},
                    "palette": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 8,
                        "items": {"type": "string", "minLength": 4, "maxLength": 24},
                    },
                    "typography": {"type": "string", "minLength": 8, "maxLength": 180},
                    "layoutPrinciples": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 8,
                        "items": {"type": "string", "minLength": 4, "maxLength": 160},
                    },
                    "textureLayer": {"type": "string", "minLength": 8, "maxLength": 220},
                    "sampleSlideIntents": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 8,
                        "items": {"type": "string", "minLength": 8, "maxLength": 220},
                    },
                    "motionPlan": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 8,
                        "items": {"type": "string", "minLength": 8, "maxLength": 220},
                    },
                    "layeringPlan": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 8,
                        "items": {"type": "string", "minLength": 8, "maxLength": 220},
                    },
                    "imageStrategy": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 8,
                        "items": {"type": "string", "minLength": 8, "maxLength": 260},
                    },
                    "hyperframesPlan": {
                        "type": "array",
                        "minItems": 3,
                        "maxItems": 8,
                        "items": {"type": "string", "minLength": 8, "maxLength": 240},
                    },
                    "riskNotes": {
                        "type": "array",
                        "maxItems": 6,
                        "items": {"type": "string", "maxLength": 180},
                    },
                },
            },
        }
    },
}


_LOCAL_VISUAL_CONTENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["recommendedDirectionIds", "rationale"],
    "additionalProperties": False,
    "properties": {
        "recommendedDirectionIds": {
            "type": "array",
            "minItems": 2,
            "maxItems": 8,
            "items": {"type": "string", "enum": list(_VISUAL_DIRECTION_IDS)},
        },
        "rationale": {"type": "string", "minLength": 8, "maxLength": 500},
    },
}


_TEMPLATE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "apple": {
        "name": "Apple 发布会高级留白",
        "mood": "安静、高级、克制、适合课程汇报和产品叙事",
        "palette": ["#0B0F19", "#F8FAFC", "#D7E3FF", "#8AB4F8"],
        "typography": "大标题、细字重正文、接近产品发布会的呼吸感",
        "layoutPrinciples": ["一页一个核心观点", "大面积留白", "电影感封面与透明面板"],
        "textureLayer": "柔和渐变、半透明蒙版、细腻阴影、避免塑料感",
        "riskNotes": ["资料密度很高时需要压缩文字。"],
    },
    "mckinsey": {
        "name": "McKinsey 咨询逻辑",
        "mood": "严谨、结论先行、图表驱动、适合商业与研究汇报",
        "palette": ["#071A2C", "#FFFFFF", "#D6E4F0", "#2F80ED"],
        "typography": "清晰商务无衬线，强调标题结论和图表标签",
        "layoutPrinciples": ["标题直接给结论", "证据和图表支撑论点", "严格网格与分组"],
        "textureLayer": "浅卡片、精确分割线、克制蓝色强调",
        "riskNotes": ["课堂展示可能显得偏商务。"],
    },
    "airbnb": {
        "name": "Airbnb 温暖故事感",
        "mood": "温暖、人本、叙事、适合课程案例和用户故事",
        "palette": ["#2B1B1B", "#FFF7F0", "#FF5A5F", "#FFC7B8"],
        "typography": "亲和圆润标题，正文保持清晰可读",
        "layoutPrinciples": ["故事先于抽象概念", "浮动卡片与快照", "用例子带出结论"],
        "textureLayer": "纸感底色、圆角卡片、柔和景深与透明遮罩",
        "riskNotes": ["正式答辩需要加强证据呈现。"],
    },
    "academic_clean": {
        "name": "学术极简白底",
        "mood": "干净、可信、克制，适合论文阅读与研究报告",
        "palette": ["#F8FAFC", "#111827", "#2563EB", "#CBD5E1"],
        "typography": "标题清晰、正文偏论文摘要风格，引用信息可读",
        "layoutPrinciples": ["摘要式信息层级", "证据卡片", "脚注引用位置固定"],
        "textureLayer": "浅灰底纹、细分割线、轻量信息卡",
        "riskNotes": ["视觉冲击力低于发布会风格。"],
    },
    "thesis_blue": {
        "name": "蓝色论文答辩",
        "mood": "正式、稳定、学术感，适合 thesis defense",
        "palette": ["#082F49", "#F8FAFC", "#38BDF8", "#BAE6FD"],
        "typography": "稳重标题、清晰章节编号、图表标签突出",
        "layoutPrinciples": ["章节推进明确", "方法-结果-贡献结构", "评委快速定位信息"],
        "textureLayer": "深蓝渐变、半透明图表容器、学术页眉",
        "riskNotes": ["需要避免每页文字过密。"],
    },
    "research_journal": {
        "name": "Research Journal 期刊感",
        "mood": "理性、文献感、适合研究综述和数据报告",
        "palette": ["#FAF7F0", "#1F2937", "#7C3AED", "#DDD6FE"],
        "typography": "类期刊标题、编号注释、图注友好",
        "layoutPrinciples": ["图注和来源清晰", "方法框架模块化", "结果页强调证据"],
        "textureLayer": "温和纸张质感、细线网格、引用角标",
        "riskNotes": ["商务路演场景可能显得保守。"],
    },
    "startup_pitch": {
        "name": "Startup Pitch 明亮路演",
        "mood": "有能量、直接、适合创业项目和比赛",
        "palette": ["#06131A", "#F7FFF7", "#00D084", "#FDE68A"],
        "typography": "强标题、大数字、行动导向按钮感",
        "layoutPrinciples": ["问题-解决方案-市场-增长", "大数字强化记忆", "结尾行动明确"],
        "textureLayer": "发光边缘、深色卡片、亮色指标",
        "riskNotes": ["学术汇报需要降低营销语气。"],
    },
    "investor_dark": {
        "name": "Investor Dark 高级深色",
        "mood": "高端、稳重、资本市场感",
        "palette": ["#050816", "#F8FAFC", "#A78BFA", "#22D3EE"],
        "typography": "大号数字、窄体标题、信息密度适中",
        "layoutPrinciples": ["暗色背景突出关键指标", "卡片分层", "每页保留一个强记忆点"],
        "textureLayer": "深色玻璃、霓虹细线、柔光蒙版",
        "riskNotes": ["投影环境太亮时对比度需要检查。"],
    },
    "classroom_friendly": {
        "name": "课堂友好清爽",
        "mood": "亲切、易懂、适合老师授课和学生展示",
        "palette": ["#F0FDF4", "#14532D", "#22C55E", "#BBF7D0"],
        "typography": "可读性优先，标题适中，重点词高亮",
        "layoutPrinciples": ["概念解释分步", "例子卡片", "结尾复习要点"],
        "textureLayer": "浅绿柔和背景、圆角提示框、轻量图标",
        "riskNotes": ["高级商务感较弱。"],
    },
    "data_story": {
        "name": "Data Story 数据叙事",
        "mood": "数据驱动、清晰、适合图表和研究结果",
        "palette": ["#0F172A", "#F8FAFC", "#38BDF8", "#F97316"],
        "typography": "数字优先、图表标题强结论",
        "layoutPrinciples": ["图表即论点", "关键数字放大", "对比关系清晰"],
        "textureLayer": "深色图表面板、坐标网格、透明数据卡",
        "riskNotes": ["素材缺少数据时会显得空。"],
    },
    "editorial_magazine": {
        "name": "Editorial Magazine 杂志叙事",
        "mood": "高级、叙事、适合人文社科和案例分析",
        "palette": ["#1C1917", "#FFF7ED", "#FB923C", "#FED7AA"],
        "typography": "杂志大标题、图文错位、引语突出",
        "layoutPrinciples": ["大图或大标题制造节奏", "引语页增强记忆", "图文错位排版"],
        "textureLayer": "胶片颗粒、暖色纸感、半透明色块",
        "riskNotes": ["严肃技术报告需要控制装饰感。"],
    },
    "glassmorphism": {
        "name": "Glassmorphism 玻璃拟态",
        "mood": "现代、科技、透明层次，适合 AI 和产品汇报",
        "palette": ["#020617", "#F8FAFC", "#60A5FA", "#C084FC"],
        "typography": "现代科技感标题，正文轻量",
        "layoutPrinciples": ["悬浮卡片", "透明遮罩", "多层信息景深"],
        "textureLayer": "毛玻璃、渐变光斑、柔和阴影和边框高光",
        "riskNotes": ["需要控制对比度，避免文字被背景干扰。"],
    },
    "medical_science": {
        "name": "Medical Science 生命科学精密",
        "mood": "冷静、专业、实验室可信感，适合生物医学、药学、健康与科学课程",
        "palette": ["#07111F", "#F7FBFF", "#22C1C3", "#BEEBF0"],
        "typography": "精密无衬线标题，正文像研究摘要一样清楚，图注和证据标签突出",
        "layoutPrinciples": ["显微/实验场景作为中景", "机制解释优先于装饰", "证据和概念图并列呈现"],
        "textureLayer": "冷色微光、细网格、实验室玻璃质感，保持高对比和可读性",
        "riskNotes": ["避免把生命科学内容做成泛科技蓝图。"],
    },
    "cinematic_research": {
        "name": "Cinematic Research 纪录片研究感",
        "mood": "有景深、叙事、沉浸，适合需要把研究问题讲成故事的报告",
        "palette": ["#0A0C10", "#F4EFE7", "#D6A44B", "#59708A"],
        "typography": "电影字幕式章节标题，正文保持克制，重点句具备旁白感",
        "layoutPrinciples": ["封面和转场页使用大画面", "证据页转为克制卡片", "结尾回到一个强 takeaway"],
        "textureLayer": "暗部渐变、柔光边缘、轻微胶片颗粒和清晰前景卡片",
        "riskNotes": ["资料密度高时需要减少氛围层，避免压低证据可读性。"],
    },
    "policy_brief": {
        "name": "Policy Brief 政策简报",
        "mood": "稳健、公共议题、结论清楚，适合政策、治理、社会议题和教育改革",
        "palette": ["#102033", "#F7F3EA", "#9B2C2C", "#D7B98E"],
        "typography": "报告标题式层级，强调问题、证据、选择和建议",
        "layoutPrinciples": ["问题定义先行", "证据—影响—建议三段式", "地图/人群/制度图作为解释层"],
        "textureLayer": "哑光纸面、深色标题条、细线图表和克制红色强调",
        "riskNotes": ["避免像政府模板；需要保留高级留白和现代排版。"],
    },
    "ink_classical": {
        "name": "Ink Classical 新中式国风",
        "mood": "含蓄、东方审美、文化感，适合古风、诗词、历史与传统文化主题",
        "palette": ["#15110D", "#F7F1E7", "#8C5E34", "#C8B28A"],
        "typography": "现代宋黑混合感：标题有书卷气，正文仍然清楚可读",
        "layoutPrinciples": ["留白像画卷", "古风元素服务文本意境", "引用页用题跋式信息层级"],
        "textureLayer": "宣纸纹理、墨色层次、低饱和金棕强调，不做廉价贴图",
        "riskNotes": ["必须避免过度装饰和低清晰度古风素材。"],
    },
    "product_showcase": {
        "name": "Product Showcase 产品展示",
        "mood": "精致、商业、聚焦价值，适合产品介绍、功能发布和方案路演",
        "palette": ["#060B12", "#FFFFFF", "#6EE7F9", "#A7F3D0"],
        "typography": "产品发布式强标题，功能点短句化，视觉重心在产品/场景图",
        "layoutPrinciples": ["价值主张先出现", "产品图/场景图占据中景", "功能卡片围绕图像分层"],
        "textureLayer": "高光边缘、干净深色舞台、柔和投影和可编辑标签层",
        "riskNotes": ["没有产品图时需要用场景图或高质量概念图替代，不可空泛。"],
    },
    "architectural_premium": {
        "name": "Architectural Premium 建筑网格",
        "mood": "秩序、高级、空间感，适合品牌方案、商业分析和高端汇报",
        "palette": ["#111111", "#F5F3EE", "#B89B5E", "#C8D0D8"],
        "typography": "窄体感标题与严谨网格，信息像建筑平面一样有结构",
        "layoutPrinciples": ["强网格和轴线", "图文错位但对齐明确", "大留白承托高密度信息"],
        "textureLayer": "石材/金属般克制质感、细线框和轻阴影",
        "riskNotes": ["不能把所有页面都做成同一网格，需要逐页变化构图。"],
    },
    "finance_terminal": {
        "name": "Finance Terminal 金融终端",
        "mood": "冷静、数据信号、投资判断感，适合金融、市场、趋势与经营分析",
        "palette": ["#05070A", "#E8FFF5", "#00C853", "#FFB020"],
        "typography": "数字和短结论优先，图表标签像专业终端一样清楚",
        "layoutPrinciples": ["指标面板服务结论", "趋势与对比占主视觉", "风险/机会分层呈现"],
        "textureLayer": "深色低噪点背景、细网格、信号绿和警示橙谨慎使用",
        "riskNotes": ["没有数据时不得伪造金融图表，只能做结构化判断。"],
    },
    "workshop_playbook": {
        "name": "Workshop Playbook 教学工作坊",
        "mood": "清楚、可参与、步骤感，适合课程复习、训练营、课堂活动和教学设计",
        "palette": ["#F8FBF7", "#173B2F", "#5DAE7B", "#F4C95D"],
        "typography": "可读性第一，标题像讲义，行动步骤与复习点一眼可扫",
        "layoutPrinciples": ["学习目标—例子—练习递进", "每页有一个可执行动作", "复习图和课堂场景图并用"],
        "textureLayer": "浅色教学纸面、柔和色块、清楚的步骤条和手册式页码",
        "riskNotes": ["高级感来自秩序和留白，不靠儿童化图标。"],
    },
}


def generate_visual_direction_decision(
    *,
    outline: OutlineDecision,
    outline_version: int,
    text_gateway: TextGateway,
    model_backend: str = "fake",
    agent_mode: str = "research",
    prompt_quality_target: str | None = None,
) -> VisualDirectionDecision:
    skill = builtin_registry().get("Frontend-Slides", "1.0.0")
    if skill is None:
        raise RuntimeError("Frontend-Slides skill is not registered")

    target_direction_count = _target_direction_count(outline, agent_mode)
    prompt = json.dumps(
        {
            "task": "Frontend-Slides visual direction planning",
            "agentMode": agent_mode,
            "targetDirectionCount": target_direction_count,
            "modeQualityTarget": prompt_quality_target or "",
            "enterpriseGradeRules": (
                [
                    "Research and enterprise modes must create client-ready visual directions, not renamed templates.",
                    "Every direction must have a different composition system, image grammar, depth strategy, and motion rhythm.",
                    "Each direction must explicitly plan how images support slide meaning and leave text-safe foreground areas.",
                    "HyperFrames motion must serve narrative sequence and include reduced-motion fallback.",
                    "PPTX must remain editable and show-safe; avoid layouts that push text into images or outside the slide.",
                ]
                if agent_mode in {"research", "enterprise"}
                else [
                    "Fast mode may be simpler, but directions must still differ by layout and image strategy.",
                    "Do not output only color palette changes.",
                ]
            ),
            "requirement": (
                f"Generate exactly {target_direction_count} premium visual directions based on the outline. "
                "Do not merely fill text into a template. Think about narrative rhythm, "
                "audience, information density, layout system, and texture. Each direction "
                "must feel like a different art direction, not just a different color palette."
            ),
            "qualityBar": [
                "Match each direction to the deck type, audience expectations, evidence density, and presenting context.",
                "Describe concrete layout behavior: hierarchy, grid, cards, charts, image treatment, and whitespace.",
                "Use premium texture language carefully: glass, paper, editorial masks, soft gradients, or academic restraint only where appropriate.",
                "Include sample slide intents that show how this outline would actually look in that direction.",
                "Co-plan every direction with Frontend-Slides and HyperFrames: Frontend-Slides defines composition and hierarchy; HyperFrames defines motion, transitions, and dynamic HTML behavior.",
                "Every direction must include concrete animation/motion choreography, foreground-midground-background layering, and a per-slide image strategy.",
                "Image strategy must first derive search queries from the user brief and source-grounded outline, search open/licensed web material, keep attribution, and only then use GPT Image 2 as a high-quality fallback.",
                "Call out risks such as low contrast, too much decoration, weak evidence, or excessive business tone.",
            ],
            "outline": outline.model_dump(by_alias=True, mode="json"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    if model_backend in {"openai", "cascade"}:
        try:
            generation = text_gateway.generate(
                TextRequest(
                    model=skill.model,
                    prompt=prompt,
                    response_schema=_VISUAL_CONTENT_SCHEMA,
                    timeout_seconds=90,
                    max_attempts=2,
                )
            )
        except ModelGatewayError as error:
            if model_backend == "cascade" and error.code == "cascade_model_unavailable":
                return _visual_from_local_model_payload(
                    outline=outline,
                    outline_version=outline_version,
                    payload={
                        "recommendedDirectionIds": _recommended_direction_ids(outline),
                        "rationale": "Enhanced local fallback selected directions from deck type, audience, and outline structure.",
                    },
                    skill=skill,
                    model_name="enhanced-local-fallback",
                    generation_id=_stable_generation_id({"cascadeFallback": prompt}),
                    target_direction_count=target_direction_count,
                )
            raise
        if generation.model.startswith("enhanced-local-fallback:"):
            return _visual_from_local_model_payload(
                outline=outline,
                outline_version=outline_version,
                payload={
                    "recommendedDirectionIds": _recommended_direction_ids(outline),
                    "rationale": "Enhanced local fallback selected directions from deck type, audience, and outline structure.",
                },
                skill=skill,
                model_name=generation.model,
                generation_id=_stable_generation_id(generation.data),
                target_direction_count=target_direction_count,
            )
        return _visual_from_model_payload(
            outline=outline,
            outline_version=outline_version,
            payload=dict(generation.data),
            skill=skill,
            generation_id=_stable_generation_id(generation.data),
            target_direction_count=target_direction_count,
        )

    if model_backend == "ollama":
        generation = text_gateway.generate(
            TextRequest(
                model=skill.model,
                prompt=prompt,
                response_schema=_LOCAL_VISUAL_CONTENT_SCHEMA,
                timeout_seconds=90,
                max_attempts=2,
            )
        )
        return _visual_from_local_model_payload(
            outline=outline,
            outline_version=outline_version,
            payload=dict(generation.data),
            skill=skill,
            model_name=generation.model,
            generation_id=_stable_generation_id(generation.data),
            target_direction_count=target_direction_count,
        )

    generation = text_gateway.generate(
        TextRequest(
            model=skill.model,
            prompt=prompt,
            response_schema=_GENERATION_ID_SCHEMA,
            timeout_seconds=30,
            max_attempts=1,
        )
    )

    payload: dict[str, Any] = {
        "schemaVersion": "1.0.0",
        "projectId": outline.project_id,
        "outlineVersion": outline_version,
        "directions": _template_directions(outline, target_direction_count),
        "selectedDirectionId": None,
        "generatedBy": {
            "schemaVersion": "1.0.0",
            "skillName": skill.name,
            "skillVersion": skill.version,
            "model": skill.model,
            "promptHash": skill.prompt_hash,
            "generationId": str(generation.data["fakeId"]),
            "generatedAt": visual_generated_at_now(),
        },
    }
    return VisualDirectionDecision(**payload)


def _visual_from_model_payload(
    *,
    outline: OutlineDecision,
    outline_version: int,
    payload: dict[str, Any],
    skill,
    generation_id: str,
    target_direction_count: int,
) -> VisualDirectionDecision:
    by_id = {
        str(direction["directionId"]): dict(direction)
        for direction in payload.get("directions", [])
        if isinstance(direction, dict) and direction.get("directionId") in _VISUAL_DIRECTION_IDS
    }
    directions: list[dict[str, Any]] = []
    for direction_id in _direction_ids_from_model_payload(payload, outline, target_direction_count):
        if direction_id in by_id:
            item = by_id[direction_id]
            item["schemaVersion"] = "1.0.0"
            directions.append(_complete_direction_item(outline, item, direction_id))
        else:
            directions.append(_template_direction(outline, direction_id))
    return VisualDirectionDecision(
        schemaVersion="1.0.0",
        projectId=outline.project_id,
        outlineVersion=outline_version,
        directions=directions,
        selectedDirectionId=None,
        generatedBy={
            "schemaVersion": "1.0.0",
            "skillName": skill.name,
            "skillVersion": skill.version,
            "model": skill.model,
            "promptHash": skill.prompt_hash,
            "generationId": generation_id,
            "generatedAt": visual_generated_at_now(),
        },
    )


def _visual_from_local_model_payload(
    *,
    outline: OutlineDecision,
    outline_version: int,
    payload: dict[str, Any],
    skill,
    model_name: str,
    generation_id: str,
    target_direction_count: int,
) -> VisualDirectionDecision:
    recommended = [
        item
        for item in payload.get("recommendedDirectionIds", [])
        if item in _VISUAL_DIRECTION_IDS
    ]
    chosen_ids = (recommended + _expanded_direction_ids(outline))[:target_direction_count]
    directions = [
        _template_direction(outline, direction_id)
        for direction_id in _unique_direction_ids(chosen_ids)[:target_direction_count]
    ]
    fallback_ids = _expanded_direction_ids(outline)
    while len(directions) < target_direction_count:
        directions.append(_template_direction(outline, fallback_ids[len(directions)]))
    if recommended:
        rationale = str(payload.get("rationale", "")).strip()
        for direction in directions:
            if direction["directionId"] in recommended:
                direction["riskNotes"] = [
                    *(direction.get("riskNotes") or []),
                    f"本地免费 AI 推荐理由：{rationale}",
                ][:4]
    return VisualDirectionDecision(
        schemaVersion="1.0.0",
        projectId=outline.project_id,
        outlineVersion=outline_version,
            directions=directions[:target_direction_count],
        selectedDirectionId=None,
        generatedBy={
            "schemaVersion": "1.0.0",
            "skillName": skill.name,
            "skillVersion": skill.version,
            "model": model_name,
            "promptHash": skill.prompt_hash,
            "generationId": generation_id,
            "generatedAt": visual_generated_at_now(),
        },
    )


def select_visual_direction(
    decision: VisualDirectionDecision,
    direction_id: str,
) -> VisualDirectionDecision:
    payload = decision.model_dump(by_alias=True, mode="json")
    payload["selectedDirectionId"] = direction_id
    return VisualDirectionDecision(**payload)


def _sample_intents(outline: OutlineDecision, style: str) -> list[str]:
    intents: list[str] = []
    for slide in outline.slides[:6]:
        layout = str(slide.suggested_layout).replace("_", " ")
        focus = _sample_focus(slide)
        focus_limit = 124 if slide.citation_ids else 78
        if outline.language == "zh":
            intents.append(
                _clip(
                    f"第 {slide.slide_index} 页《{_clip(slide.title, 34)}》：用{style}把“{_clip(focus, focus_limit)}”做成 {layout} 画面，文字只取自 OutlineDecision。",
                    220,
                )
            )
        else:
            intents.append(
                _clip(
                    f"Slide {slide.slide_index} “{_clip(slide.title, 34)}”: use {style} to turn “{_clip(focus, focus_limit)}” into a {layout} frame, using OutlineDecision content only.",
                    220,
                )
            )
    return intents[:6]


def _target_direction_count(outline: OutlineDecision, agent_mode: str) -> int:
    if agent_mode == "fast":
        target = 4
    elif agent_mode == "enterprise":
        target = 6
    else:
        target = 5
    if getattr(outline, "target_slide_count", 0) >= 12 and target < 6:
        target += 1
    if _evidence_heavy(outline) and target < 6:
        target += 1
    return min(6, max(4, target))


def _template_directions(outline: OutlineDecision, target_direction_count: int) -> list[dict[str, Any]]:
    return [
        _template_direction(outline, direction_id)
        for direction_id in _expanded_direction_ids(outline)[:target_direction_count]
    ]


def _direction_ids_from_model_payload(
    payload: dict[str, Any], outline: OutlineDecision, target_direction_count: int
) -> list[str]:
    model_ids = [
        str(direction.get("directionId"))
        for direction in payload.get("directions", [])
        if isinstance(direction, dict) and direction.get("directionId") in _VISUAL_DIRECTION_IDS
    ]
    return _unique_direction_ids(model_ids + _expanded_direction_ids(outline))[:target_direction_count]


def _expanded_direction_ids(outline: OutlineDecision) -> list[str]:
    content = _outline_content_index(outline)
    ids = list(_recommended_direction_ids(outline))
    if outline.deck_type == "business_pitch":
        ids.extend(["startup_pitch", "architectural_premium", "investor_dark", "product_showcase", "data_story"])
    elif outline.deck_type == "case_competition":
        ids.extend(["mckinsey", "data_story", "editorial_magazine", "architectural_premium", "cinematic_research"])
    elif outline.deck_type == "thesis_defense":
        ids.extend(["thesis_blue", "research_journal", "academic_clean", "cinematic_research", "data_story"])
    elif outline.deck_type == "research_report":
        ids.extend(["research_journal", "academic_clean", "data_story", "cinematic_research", "policy_brief"])
    else:
        ids.extend(["workshop_playbook", "classroom_friendly", "academic_clean", "cinematic_research", "data_story"])
    if _evidence_heavy(outline):
        ids.extend(["data_story", "mckinsey", "research_journal", "finance_terminal"])
    if _contains_any(content, ["ai", "人工智能", "machine learning", "llm", "agent"]):
        ids.extend(["glassmorphism", "cinematic_research", "data_story", "architectural_premium"])
    if _contains_any(content, ["brand", "retail", "consumer", "coffee", "品牌", "零售", "消费"]):
        ids.extend(["product_showcase", "editorial_magazine", "architectural_premium", "data_story"])
    return _unique_direction_ids(ids)


def _recommended_direction_ids(outline: OutlineDecision) -> list[str]:
    evidence_heavy = _evidence_heavy(outline)
    content = _outline_content_index(outline)
    academic_audience = any(
        keyword in outline.audience.lower()
        for keyword in ["teacher", "student", "undergraduate", "professor", "committee", "学", "老师", "学生", "答辩", "导师"]
    )
    if _contains_any(content, ["crispr", "gene", "genome", "基因", "生物", "医学", "医疗", "药物", "健康", "细胞", "蛋白"]):
        return ["medical_science", "cinematic_research", "academic_clean"]
    if _contains_any(content, ["古风", "诗词", "国风", "传统文化", "历史", "文物", "heritage", "classical", "poetry"]):
        return ["ink_classical", "editorial_magazine", "academic_clean"]
    if _contains_any(
        content,
        [
            "luckin",
            "coffee",
            "brand",
            "retail",
            "chain",
            "store",
            "consumer",
            "瑞幸",
            "咖啡",
            "品牌",
            "门店",
            "连锁",
            "零售",
            "消费",
            "商业模式",
        ],
    ):
        if evidence_heavy:
            return ["product_showcase", "editorial_magazine", "data_story"]
        return ["product_showcase", "architectural_premium", "editorial_magazine"]
    if outline.language == "zh" and any(keyword in content for keyword in ["课堂", "课程", "教学", "老师", "学生", "复习", "训练营"]):
        return ["workshop_playbook", "classroom_friendly", "data_story"]
    if _contains_any(content, ["政策", "治理", "公共", "教育改革", "社会", "policy", "governance", "public sector"]):
        return ["policy_brief", "data_story", "academic_clean"]
    if _contains_any(
        content,
        [
            "luckin",
            "coffee",
            "brand",
            "retail",
            "chain",
            "store",
            "consumer",
            "瑞幸",
            "咖啡",
            "品牌",
            "门店",
            "连锁",
            "零售",
            "消费",
            "商业模式",
        ],
    ):
        if evidence_heavy:
            return ["product_showcase", "editorial_magazine", "data_story"]
        return ["product_showcase", "architectural_premium", "editorial_magazine"]
    if _contains_any(content, ["金融", "投资", "市场", "估值", "财务", "finance", "investment", "market", "valuation"]):
        return ["finance_terminal", "investor_dark", "data_story"]
    if _contains_any(content, ["产品", "用户", "功能", "app", "saas", "product", "feature", "launch"]):
        if outline.deck_type == "business_pitch":
            return ["product_showcase", "architectural_premium", "startup_pitch"]
        return ["product_showcase", "apple", "architectural_premium"]
    if _contains_any(content, ["ai", "人工智能", "机器学习", "大模型", "llm", "agent"]):
        return ["glassmorphism", "cinematic_research", "data_story"]
    if evidence_heavy and outline.deck_type in {"course_presentation", "research_report", "case_competition"}:
        base = ["data_story", "academic_clean", "apple"]
        if outline.language == "zh" and academic_audience:
            base = ["workshop_playbook", "classroom_friendly", "data_story"]
        if outline.deck_type == "case_competition":
            base = ["data_story", "mckinsey", "airbnb"]
        return _unique_direction_ids(base)[:3]
    if outline.deck_type == "thesis_defense":
        return ["thesis_blue", "research_journal", "academic_clean"]
    if outline.deck_type == "research_report":
        return ["research_journal", "cinematic_research", "data_story"]
    if outline.deck_type == "business_pitch":
        return ["startup_pitch", "architectural_premium", "investor_dark"]
    if outline.deck_type == "case_competition":
        return ["mckinsey", "data_story", "architectural_premium"]
    if outline.language == "zh" and "课堂" in outline.audience:
        return ["workshop_playbook", "classroom_friendly", "apple"]
    return ["apple", "mckinsey", "airbnb"]


def _outline_content_index(outline: OutlineDecision) -> str:
    parts = [
        outline.deck_type,
        outline.audience,
        outline.objective,
        *outline.narrative,
        *(slide.title for slide in outline.slides),
        *(slide.subtitle or "" for slide in outline.slides),
        *(slide.key_point for slide in outline.slides),
        *(slide.visual_intent for slide in outline.slides),
        *(asset for slide in outline.slides for asset in slide.required_assets),
        *(point for slide in outline.slides for point in slide.talking_points),
    ]
    return " ".join(part for part in parts if part).casefold()


def _contains_any(content: str, keywords: list[str]) -> bool:
    return any(keyword.casefold() in content for keyword in keywords)


def _unique_direction_ids(ids: list[str]) -> list[str]:
    result: list[str] = []
    for direction_id in ids:
        if direction_id in _VISUAL_DIRECTION_IDS and direction_id not in result:
            result.append(direction_id)
    for fallback in _VISUAL_DIRECTION_IDS:
        if fallback not in result:
            result.append(fallback)
    return result


def _template_direction(outline: OutlineDecision, direction_id: str) -> dict[str, Any]:
    definition = _TEMPLATE_DEFINITIONS[direction_id]
    layout_principles = [
        *definition["layoutPrinciples"],
        *_outline_layout_principles(outline),
    ][:8]
    risk_notes = [
        *definition["riskNotes"],
        *_outline_risk_notes(outline),
    ][:6]
    return {
        "schemaVersion": "1.0.0",
        "directionId": direction_id,
        "name": definition["name"],
        "mood": definition["mood"],
        "palette": definition["palette"],
        "typography": definition["typography"],
        "layoutPrinciples": layout_principles,
        "textureLayer": _outline_texture_layer(outline, definition["textureLayer"]),
        "sampleSlideIntents": _sample_intents(outline, definition["name"]),
        "motionPlan": _motion_plan(outline, definition["name"]),
        "layeringPlan": _layering_plan(outline, definition["name"]),
        "imageStrategy": _image_strategy(outline, definition["name"]),
        "hyperframesPlan": _hyperframes_plan(outline, definition["name"]),
        "riskNotes": risk_notes,
    }


def _complete_direction_item(
    outline: OutlineDecision,
    item: dict[str, Any],
    direction_id: str,
) -> dict[str, Any]:
    definition = _TEMPLATE_DEFINITIONS[direction_id]
    item.setdefault("motionPlan", _motion_plan(outline, str(item.get("name") or definition["name"])))
    item.setdefault("layeringPlan", _layering_plan(outline, str(item.get("name") or definition["name"])))
    item.setdefault("imageStrategy", _image_strategy(outline, str(item.get("name") or definition["name"])))
    item.setdefault("hyperframesPlan", _hyperframes_plan(outline, str(item.get("name") or definition["name"])))
    return item


def _motion_plan(outline: OutlineDecision, style: str) -> list[str]:
    first = outline.slides[0] if outline.slides else None
    focus = _clip(first.key_point if first else outline.project_id, 86)
    if outline.language == "zh":
        return [
            f"Frontend-Slides 先确定 {style} 的信息节奏：封面只 reveal “{_clip(first.title if first else outline.project_id, 30)}”，再浮现核心判断。",
            "HyperFrames 为 HTML 版加入逐层入场动画：背景光斑 240ms、主标题 320ms、证据卡片 420ms stagger；PPTX 保持可编辑静态层。",
            f"动画必须服务本页 keyPoint：围绕“{focus}”做强调，不做无意义漂浮或装饰性转场。",
            "所有动效提供 prefers-reduced-motion 降级，演示时仍保持层级和阅读顺序。",
        ]
    return [
        f"Frontend-Slides defines the {style} narrative rhythm: reveal the hero title first, then surface the core judgment.",
        "HyperFrames adds staged HTML motion: background wash at 240ms, headline at 320ms, evidence cards at 420ms stagger; PPTX stays editable and stable.",
        f"Motion emphasizes the slide keyPoint around “{focus}” instead of adding decorative movement.",
        "Every animation has a prefers-reduced-motion fallback while preserving reading order and hierarchy.",
    ]


def _layering_plan(outline: OutlineDecision, style: str) -> list[str]:
    evidence_titles = [slide.title for slide in outline.slides if slide.citation_ids][:2]
    if outline.language == "zh":
        items = [
            f"Frontend-Slides 用 {style} 建立三层画面：背景氛围层、正文证据层、前景记忆点层。",
            "每页至少保留一个可视焦点：图片/图表在中景，标题与 keyPoint 在前景，辅助卡片降低透明度。",
            "图片不做纯装饰：必须和本页 visualIntent 或 requiredAssets 对应，并给正文留出安全留白。",
        ]
        if evidence_titles:
            items.append(f"证据页为“{_clip(' / '.join(evidence_titles), 48)}”预留图表/引用层，避免把证据压成脚注。")
        else:
            items.append("没有明确数据页时，用概念配图和结构卡片形成层次，不额外编造数字。")
        return items
    items = [
        f"Frontend-Slides builds a three-layer {style} composition: atmospheric background, evidence/content middle layer, foreground memory point.",
        "Each slide keeps one visual focus: image/chart in the midground, title and keyPoint in the foreground, supporting cards softened.",
        "Images are not decorative: they must map to visualIntent or requiredAssets and leave safe reading space.",
    ]
    if evidence_titles:
        items.append(f"Reserve a citation/chart layer for “{_clip(' / '.join(evidence_titles), 52)}” so evidence is readable.")
    else:
        items.append("When no explicit data exists, use conceptual imagery and structure cards without inventing numbers.")
    return items


def _image_strategy(outline: OutlineDecision, style: str) -> list[str]:
    search_seed = _image_search_seed(outline)
    if outline.language == "zh":
        return [
            f"配图生成前先读取用户需求与 SourcePack 生成的大纲；检索词从“{search_seed}”和每页 visualIntent/requiredAssets 派生。",
            "先检索公开/可授权网页资料与图片库，优先使用真实照片、研究图、场景图或概念图，并保留来源/授权元数据。",
            "找不到高匹配、可用、清晰的资料图时，才调用 GPT Image 2 生成高质量 16:9 配图；不自动切换到未经确认的图片模型。",
            f"Frontend-Slides 决定图片裁切、遮罩和留白；HyperFrames 决定图片在 HTML 中的景深动效与轻微视差。",
        ]
    return [
        f"Before image generation, read the user brief and source-grounded outline; derive queries from “{search_seed}” plus each slide visualIntent/requiredAssets.",
        "Search open/licensed web material first, prioritizing authentic photos, research visuals, scene images, or concept imagery with attribution metadata.",
        "Only if no suitable clear asset is found, call GPT Image 2 for a high-quality 16:9 fallback image; do not switch to an unapproved image model.",
        "Frontend-Slides owns crop, mask, and whitespace; HyperFrames owns depth motion and subtle parallax in HTML.",
    ]


def _hyperframes_plan(outline: OutlineDecision, style: str) -> list[str]:
    if outline.language == "zh":
        return [
            "HyperFrames HTML 必须与 PPTX 共用同一份 SlideDeck JSON，不单独重写内容。",
            f"HyperFrames 为 {style} 方向生成动态层级：图片层轻微浮入、卡片层错峰进入、进度条与键盘翻页保持清晰。",
            "动画节奏匹配大纲：封面更慢、证据页更克制、结尾页聚焦一个 takeaway。",
            "HyperFrames 输出必须带 reduced-motion 降级和可访问的 alt/source 标记。",
        ]
    return [
        "HyperFrames HTML must render from the same SlideDeck JSON as PPTX; it must not rewrite deck content separately.",
        f"HyperFrames creates dynamic depth for {style}: image layer floats in, cards enter staggered, progress and keyboard navigation stay clear.",
        "Motion follows outline rhythm: slower cover, restrained evidence slides, focused conclusion takeaway.",
        "HyperFrames output must include reduced-motion fallback plus accessible alt/source markers.",
    ]


def _image_search_seed(outline: OutlineDecision) -> str:
    parts = [
        outline.slides[0].title if outline.slides else outline.project_id,
        outline.audience,
        outline.deck_type,
    ]
    for slide in outline.slides[:3]:
        parts.append(slide.visual_intent)
        parts.extend(slide.required_assets[:2])
    return _clip(" ".join(part for part in parts if part), 96)


def _evidence_heavy(outline: OutlineDecision) -> bool:
    citation_count = sum(len(slide.citation_ids) for slide in outline.slides)
    numeric_count = sum(
        1
        for slide in outline.slides
        if _has_evidence_number(
            f"{slide.title} {slide.key_point} {' '.join(slide.talking_points)}"
        )
    )
    return citation_count >= 2 or numeric_count >= 2


def _sample_focus(slide) -> str:
    key_point = str(slide.key_point)
    if not slide.citation_ids:
        return key_point
    percent_match = re.search(
        r"[^。.!?;；]{0,72}\d+(?:\.\d+)?[%％][^。.!?;；]{0,72}",
        key_point,
    )
    if percent_match:
        return percent_match.group(0).strip(" ,，;；")
    number_match = re.search(
        r"[^。.!?;；]{0,72}\b(?:19|20)\d{2}\b[^。.!?;；]{0,72}",
        key_point,
    )
    if number_match:
        return number_match.group(0).strip(" ,，;；")
    return key_point


def _has_evidence_number(value: str) -> bool:
    lowered = value.lower()
    if any(marker in lowered for marker in ["%", "％", "survey", "sample", "study", "data", "研究", "调查", "样本", "数据"]):
        return bool(re.search(r"\d", lowered)) or any(marker in lowered for marker in ["研究", "调查", "样本", "数据"])
    return bool(re.search(r"\b(19|20)\d{2}\b|\b\d{2,}(,\d{3})*\b", lowered))


def _outline_layout_principles(outline: OutlineDecision) -> list[str]:
    first = outline.slides[0] if outline.slides else None
    evidence_titles = [slide.title for slide in outline.slides if slide.citation_ids][:2]
    if outline.language == "zh":
        principles = [
            "Frontend-Slides 从已确认大纲生成视觉方向，不直接改写正文",
            f"封面记忆点围绕“{_clip(first.title if first else outline.project_id, 28)}”建立",
            "每个版式先服务该页 keyPoint，再考虑装饰和质感",
        ]
        if evidence_titles:
            principles.append(f"证据页需要给“{_clip(' / '.join(evidence_titles), 42)}”留出引用/图表区域")
        return principles
    principles = [
        "Frontend-Slides derives art direction from the confirmed outline, not from fixed template text",
        f"Build the hero memory point around “{_clip(first.title if first else outline.project_id, 30)}”",
        "Choose composition from each slide keyPoint before adding texture",
    ]
    if evidence_titles:
        principles.append(f"Reserve citation/chart space for “{_clip(' / '.join(evidence_titles), 44)}”")
    return principles


def _outline_risk_notes(outline: OutlineDecision) -> list[str]:
    evidence_slides = [slide for slide in outline.slides if slide.citation_ids]
    dense_slides = [slide for slide in outline.slides if len(slide.key_point) > 130 or len(slide.talking_points) >= 5]
    if outline.language == "zh":
        notes = ["本地 Frontend-Slides 已调用：方向基于 OutlineDecision 的页标题、keyPoint、证据和版式生成。"]
        if evidence_slides:
            notes.append(f"共有 {len(evidence_slides)} 页带引用，需要避免把证据做成装饰性小字。")
        if dense_slides:
            notes.append(f"{len(dense_slides)} 页信息较密，应优先压缩成卡片/图表。")
        return notes
    notes = ["Local Frontend-Slides planner was invoked: directions are based on outline titles, keyPoints, citations, and layouts."]
    if evidence_slides:
        notes.append(f"{len(evidence_slides)} citation-backed slides need readable evidence treatment.")
    if dense_slides:
        notes.append(f"{len(dense_slides)} dense slides should be compressed into cards or charts.")
    return notes


def _outline_texture_layer(outline: OutlineDecision, base_texture: str) -> str:
    topic = _clip(outline.slides[0].title if outline.slides else outline.project_id, 36)
    if outline.language == "zh":
        return f"{base_texture}；围绕“{topic}”控制质感强度，不能盖过大纲内容。"
    return f"{base_texture}; tune texture around “{topic}” without overpowering outline content."


def _clip(value: str, limit: int) -> str:
    value = " ".join(str(value).split()).strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def _stable_generation_id(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
