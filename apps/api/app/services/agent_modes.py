from __future__ import annotations

from typing import Any, Literal, cast


AgentMode = Literal["fast", "research", "enterprise"]
CostArchitecture = Literal["byok", "hybrid_router", "manual_prompt_workspace"]
ImageResolutionMode = Literal["auto", "web_first", "generate"]

_VALID_AGENT_MODES: set[str] = {"fast", "research", "enterprise"}


LEGAL_COST_ARCHITECTURES: list[dict[str, object]] = [
    {
        "id": "byok",
        "name": "User-owned API keys",
        "chineseName": "用户自带 API Key",
        "positioning": "The product sells workflow software, prompt assets, generation contracts, QA, and export tools; model bills are paid by the user through their own provider account.",
        "allowed": [
            "Let users configure OpenAI, Claude, Gemini, DeepSeek, Qwen, Kimi, local OpenAI-compatible servers, or Ollama-style local models.",
            "Store only encrypted provider configuration in production; never expose keys in ordinary logs or runtime status payloads.",
            "Charge software subscription or seat fees separately from model usage.",
        ],
        "notAllowed": [
            "Do not share one consumer web subscription across users.",
            "Do not ask users for ChatGPT/Claude/Gemini website cookies or passwords.",
        ],
    },
    {
        "id": "hybrid_router",
        "name": "Hybrid model router",
        "chineseName": "混合模型路由",
        "positioning": "Route cheap/local models to mechanical steps and reserve strong models for taste, consistency, final polish, and high-risk reasoning.",
        "allowed": [
            "Use local/free/low-cost models for cleanup, extraction, tabular normalization, and first drafts.",
            "Use mid-tier models for story logic, visual direction, world/character consistency, and outline revision.",
            "Use strong models only for final director-level polish, critical QA, or enterprise-grade reviews.",
        ],
        "notAllowed": [
            "Do not spend premium-model tokens on every small formatting or parsing step.",
            "Do not present low-confidence local fallback as verified research.",
        ],
    },
    {
        "id": "manual_prompt_workspace",
        "name": "Human-in-the-loop prompt workspace",
        "chineseName": "前端会员人机协作工作台",
        "positioning": "The app generates structured prompt packs; users copy them into their own ChatGPT/Claude/Gemini web membership and paste results back for the next workflow step.",
        "allowed": [
            "Generate copyable prompt packs, checklists, continuity sheets, storyboard tables, and QA forms.",
            "Let users manually paste external model output back into the workflow.",
            "Treat this as human collaboration, not backend model automation.",
        ],
        "notAllowed": [
            "Do not automate login to consumer web products.",
            "Do not scrape or drive a user’s consumer web session as an API replacement.",
            "Do not share cookies, session tokens, or browser profiles.",
        ],
    },
]


_DRAMA_STAGE_ROUTING: list[dict[str, object]] = [
    {
        "stage": "资料清洗",
        "cheapModel": True,
        "strongModel": False,
        "routing": "local/free/cheap model",
        "reason": "This is mostly extraction, cleanup, and structure normalization.",
    },
    {
        "stage": "分集拆解",
        "cheapModel": True,
        "strongModel": "qa_only",
        "routing": "cheap model first; strong model only for spot QA",
        "reason": "Episode splitting benefits from speed, then selective high-quality review.",
    },
    {
        "stage": "分镜表格化",
        "cheapModel": True,
        "strongModel": False,
        "routing": "cheap/local model",
        "reason": "This is a deterministic formatting step once the story decision exists.",
    },
    {
        "stage": "爽点优化",
        "cheapModel": "mid_tier",
        "strongModel": "key_nodes",
        "routing": "mid-tier model; strong model for hooks, reversals, and climax nodes",
        "reason": "Taste and rhythm matter, but not every row needs premium reasoning.",
    },
    {
        "stage": "世界观/人物一致性",
        "cheapModel": "mid_tier",
        "strongModel": True,
        "routing": "mid/high model with consistency memory",
        "reason": "Continuity errors destroy perceived quality and need stronger reasoning.",
    },
    {
        "stage": "最终导演级润色",
        "cheapModel": False,
        "strongModel": True,
        "routing": "strong model",
        "reason": "This is the paid taste layer: pacing, subtext, emotion, and production-ready voice.",
    },
    {
        "stage": "图片提示词生成",
        "cheapModel": "mid_tier",
        "strongModel": "special_characters",
        "routing": "mid-tier model; strong model for important characters and style bibles",
        "reason": "Most prompts are structured; flagship characters need stronger visual specificity.",
    },
]


_MODE_POLICIES: dict[AgentMode, dict[str, object]] = {
    "fast": {
        "id": "fast",
        "name": "Fast mode",
        "chineseName": "快速模式",
        "costLevel": "low",
        "latencyTarget": "short interactive loop",
        "defaultArchitecture": "hybrid_router",
        "modelRouting": {
            "cleanup": "cheap_or_local",
            "outline": "cheap_or_mid",
            "visualDirection": "mid_if_available_else_local",
            "finalPolish": "skip_or_mid",
            "quality": "cheap_automated_checks",
            "image": "open_web_search_then_local_or_free_fallback",
        },
        "researchDepth": "bounded_or_disabled",
        "bestFor": [
            "drafts",
            "student preview",
            "low-cost ideation",
            "workflow demonstrations",
        ],
        "guardrails": [
            "Must label local fallback as fallback.",
            "Must not spend strong-model calls unless the user explicitly upgrades mode.",
        ],
    },
    "research": {
        "id": "research",
        "name": "Research mode",
        "chineseName": "研究模式",
        "costLevel": "medium_controlled",
        "latencyTarget": "enterprise-grade interactive generation",
        "defaultArchitecture": "hybrid_router",
        "modelRouting": {
            "cleanup": "cheap_or_local",
            "outline": "mid_model_with_web_sources",
            "visualDirection": "mid_or_strong_for_art_direction",
            "finalPolish": "mid_model",
            "quality": "cheap_checks_plus_selective_strong_review",
            "image": "licensed_open_web_search_first_then_configured_image_provider",
        },
        "researchDepth": "public_source_cascade_with_gap_brief",
        "bestFor": [
            "course reports",
            "business analysis",
            "thesis-style structured decks",
            "client-facing drafts",
            "enterprise-grade PPT baseline",
        ],
        "guardrails": [
            "Must separate verified sources from inference.",
            "Must keep citations/source metadata out of customer-visible card copy unless intentionally shown.",
            "Must pass the enterprise PPT baseline quality profile before export.",
        ],
    },
    "enterprise": {
        "id": "enterprise",
        "name": "Enterprise mode",
        "chineseName": "企业级模式",
        "costLevel": "high_controlled",
        "latencyTarget": "slower but audited",
        "defaultArchitecture": "byok",
        "modelRouting": {
            "cleanup": "cheap_or_private_model",
            "outline": "strong_or_enterprise_key",
            "visualDirection": "strong_model_for_direction_and_consistency",
            "finalPolish": "strong_model",
            "quality": "strict_gate_plus_human_review",
            "image": "licensed_asset_search_or_enterprise_image_provider",
        },
        "researchDepth": "deep_source_review_with_audit_trail",
        "bestFor": [
            "paid customer delivery",
            "agency workflows",
            "enterprise presentation systems",
            "high-stakes narrative assets",
        ],
        "guardrails": [
            "Prefer BYOK or customer-owned enterprise provider accounts.",
            "No consumer-web automation, shared cookies, or hidden subscription resale.",
            "Keep audit trail, source traceability, and cost estimates visible.",
        ],
    },
}


def coerce_agent_mode(value: object, default_mode: AgentMode = "research") -> AgentMode:
    raw = str(value or default_mode)
    if raw in _VALID_AGENT_MODES:
        return cast(AgentMode, raw)
    return default_mode


def project_agent_mode(brief: Any, default_mode: AgentMode = "research") -> AgentMode:
    return coerce_agent_mode(getattr(brief, "agent_mode", None), default_mode)


def mode_policy(mode: AgentMode) -> dict[str, object]:
    return dict(_MODE_POLICIES[mode])


def execution_policy(mode: AgentMode) -> dict[str, object]:
    if mode == "fast":
        return {
            "mode": "fast",
            "researchEnabled": True,
            "researchMaxSources": 3,
            "researchTimeoutSeconds": 4.0,
            "imageResolutionMode": "auto",
            "imageSearchTimeoutSeconds": 3.5,
            "qualityProfile": "standard",
            "promptQualityTarget": (
                "Fast draft: source-grounded enough for preview, concise copy, "
                "low-cost routing, no enterprise delivery claim."
            ),
            "enterpriseGrade": False,
            "requiresHumanReview": False,
        }
    if mode == "enterprise":
        return {
            "mode": "enterprise",
            "researchEnabled": True,
            "researchMaxSources": 8,
            "researchTimeoutSeconds": 14.0,
            "imageResolutionMode": "web_first",
            "imageSearchTimeoutSeconds": 9.0,
            "qualityProfile": "enterprise_ppt",
            "promptQualityTarget": (
                "Audited enterprise delivery: strict source grounding, BYOK/customer-owned "
                "provider posture, source traceability, premium art direction, and final human review hooks."
            ),
            "enterpriseGrade": True,
            "requiresHumanReview": True,
        }
    return {
        "mode": "research",
        "researchEnabled": True,
        "researchMaxSources": 7,
        "researchTimeoutSeconds": 10.0,
        "imageResolutionMode": "web_first",
        "imageSearchTimeoutSeconds": 7.0,
        "qualityProfile": "enterprise_ppt",
        "promptQualityTarget": (
            "Research mode must reach the enterprise PPT baseline: source-grounded storyline, "
            "non-generic outline, content-serving images, varied premium slide planning, "
            "and strict PPTX/HyperFrames quality gates before export."
        ),
        "enterpriseGrade": True,
        "requiresHumanReview": False,
    }


def runtime_agent_modes(default_mode: AgentMode) -> dict[str, object]:
    return {
        "defaultMode": default_mode,
        "modes": [mode_policy("fast"), mode_policy("research"), mode_policy("enterprise")],
        "legalCostArchitectures": LEGAL_COST_ARCHITECTURES,
        "dramaAgentStageRouting": _DRAMA_STAGE_ROUTING,
        "frontendMembershipRule": (
            "Consumer web subscriptions may be used only by the user manually through copy/paste prompt workspaces; "
            "the product must not automate logins, reuse cookies, or treat a browser session as a backend API."
        ),
    }
