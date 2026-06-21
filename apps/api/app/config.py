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
    model_backend: Literal["fake"] = "fake"
    model_retry_count: int = Field(default=1, ge=1, le=3)


@lru_cache
def get_settings() -> Settings:
    return Settings()
