import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.errors import PublicError
from app.main import create_app
from app.ai.fakes import FakeImageGateway, FakeTextGateway
from app.ai.protocols import ImageGateway, TextGateway


def test_health_reports_exact_service_version(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "ai-ppt-api",
        "version": "0.1.0",
    }


@pytest.mark.parametrize("retry_count", [1, 3])
def test_retry_count_accepts_boundaries(retry_count: int) -> None:
    assert Settings(model_retry_count=retry_count).model_retry_count == retry_count


@pytest.mark.parametrize("retry_count", [0, 4])
def test_retry_count_rejects_values_outside_boundaries(retry_count: int) -> None:
    with pytest.raises(ValidationError):
        Settings(model_retry_count=retry_count)


def test_settings_parse_prefixed_environment_without_leaking_between_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_PPT_MODEL_BACKEND", "fake")
    monkeypatch.setenv("AI_PPT_MODEL_RETRY_COUNT", "3")

    from_environment = Settings()
    explicit = Settings(model_backend="fake", model_retry_count=1)

    assert from_environment.model_backend == "fake"
    assert from_environment.model_retry_count == 3
    assert explicit.model_backend == "fake"
    assert explicit.model_retry_count == 1

    monkeypatch.delenv("AI_PPT_MODEL_BACKEND")
    monkeypatch.delenv("AI_PPT_MODEL_RETRY_COUNT")

    defaults = Settings()
    assert defaults.model_backend == "fake"
    assert defaults.model_retry_count == 1


def test_settings_reject_unsupported_model_backend() -> None:
    with pytest.raises(ValidationError):
        Settings(model_backend="provider")


def test_create_app_injects_independent_fake_gateways(tmp_path) -> None:
    first = create_app(Settings(database_path=tmp_path / "first.db"))
    second = create_app(Settings(database_path=tmp_path / "second.db"))

    assert isinstance(first.state.text_gateway, FakeTextGateway)
    assert isinstance(first.state.text_gateway, TextGateway)
    assert isinstance(first.state.image_gateway, FakeImageGateway)
    assert isinstance(first.state.image_gateway, ImageGateway)
    assert first.state.text_gateway is not second.state.text_gateway
    assert first.state.image_gateway is not second.state.image_gateway


def test_cors_allows_configured_local_frontend_origin(tmp_path) -> None:
    app = create_app(
        Settings(
            database_path=tmp_path / "cors.db",
            asset_path=tmp_path / "assets",
            allowed_origins=["http://localhost:3000"],
        )
    )
    with TestClient(app) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_public_error_handler_returns_only_stable_public_fields(tmp_path) -> None:
    app: FastAPI = create_app(
        Settings(
            database_path=tmp_path / "test.db",
            asset_path=tmp_path / "assets",
        )
    )

    @app.get("/_test/public-error")
    def raise_public_error() -> None:
        raise PublicError(
            code="invalid_request",
            message="The request is invalid.",
            status_code=422,
        )

    with TestClient(app) as test_client:
        response = test_client.get("/_test/public-error")

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_request",
            "message": "The request is invalid.",
        }
    }


def test_public_error_has_stable_safe_string_format() -> None:
    error = PublicError(code="not_found", message="Project not found.", status_code=404)

    assert isinstance(error, Exception)
    assert str(error) == "not_found: Project not found."
