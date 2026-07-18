from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_PPT_", extra="ignore")

    app_name: str = "ai-ppt-api"
    app_version: str = "0.1.0"
    database_path: Path = Path(".local/ai-ppt.db")
    asset_path: Path = Path(".local/assets")
    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
            "https://shuhongguo56-crypto.github.io",
            "https://humanizeppt-studio.almond-gleam-4876.chatgpt.site",
        ]
    )
    model_backend: Literal["fake", "ollama", "openai", "cascade"] = "fake"
    default_agent_mode: Literal["fast", "research", "enterprise"] = "research"
    default_cost_architecture: Literal["byok", "hybrid_router", "manual_prompt_workspace"] = "hybrid_router"
    model_retry_count: int = Field(default=1, ge=1, le=3)
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    compatible_base_url: str = "http://127.0.0.1:1234/v1"
    compatible_api_key: str | None = None
    compatible_text_model: str = "local-model"
    compatible_enabled: bool = True
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_text_model: str = "gemini-3.5-flash"
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_text_model: str = "meta-llama/llama-3.1-8b-instruct:free"
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_text_model: str = "llama-3.1-8b-instant"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_text_model: str = "qwen2.5:7b"
    cascade_include_ollama: bool = True
    cascade_include_fake_fallback: bool = True
    text_model: str = "gpt-5.4-mini"
    quality_model: str = "gpt-5.4-nano"
    image_model: str = "gpt-image-2"
    image_search_enabled: bool = True
    image_search_timeout_seconds: float = Field(default=3.5, ge=0.2, le=10.0)
    bing_image_search_key: str | None = None
    bing_image_search_endpoint: str = "https://api.bing.microsoft.com/v7.0/images/search"
    stable_diffusion_api_url: str | None = None
    stable_diffusion_api_key: str | None = None
    stable_diffusion_model: str = "stable-diffusion"
    custom_image2_api_url: str | None = None
    custom_image2_api_key: str | None = None
    custom_image2_model: str = "custom-image2"
    midjourney_api_url: str | None = None
    midjourney_api_key: str | None = None
    midjourney_model: str = "midjourney"
    pollinations_image_enabled: bool = True
    pollinations_image_base_url: str = "https://image.pollinations.ai/prompt"
    pollinations_image_model: str = "flux"
    pollinations_image_referrer: str = "ai-ppt-agent"
    pollinations_image_enhance: bool = True
    expert_image_min_long_edge: int = Field(default=1920, ge=1024, le=4096)
    expert_image_min_short_edge: int = Field(default=1080, ge=576, le=4096)
    expert_key_image_min_long_edge: int = Field(default=3840, ge=1024, le=8192)
    expert_key_image_min_short_edge: int = Field(default=2160, ge=576, le=8192)
    realesrgan_enabled: bool = True
    realesrgan_executable: Path | None = None
    realesrgan_model: str = "realesrgan-x4plus"
    realesrgan_timeout_seconds: float = Field(default=180, ge=30, le=300)
    shared_asset_library_path: Path = Path(".local/asset-library")
    topic_research_enabled: bool = True
    topic_research_timeout_seconds: float = Field(default=6.0, ge=1.0, le=20.0)
    topic_research_max_sources: int = Field(default=5, ge=1, le=8)
    topic_research_user_agent: str = "AI-PPT-Topic-Research/0.1 (public-source synthesis)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
