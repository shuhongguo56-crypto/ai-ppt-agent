from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    settings = Settings(
        database_path=tmp_path / "test.db",
        asset_path=tmp_path / "assets",
        image_search_enabled=False,
        topic_research_enabled=False,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client
