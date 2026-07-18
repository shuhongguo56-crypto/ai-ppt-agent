import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.errors import PublicError
from app.main import create_app
from app.ai.fakes import FakeImageGateway, FakeTextGateway
from app.ai.image_http import PollinationsImageGateway
from app.ai.cascade import CascadeTextGateway
from app.ai.ollama import OllamaTextGateway
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


def test_settings_accept_agent_cost_modes() -> None:
    settings = Settings(
        default_agent_mode="research",
        default_cost_architecture="manual_prompt_workspace",
    )

    assert settings.default_agent_mode == "research"
    assert settings.default_cost_architecture == "manual_prompt_workspace"


def test_settings_reject_invalid_agent_mode() -> None:
    with pytest.raises(ValidationError):
        Settings(default_agent_mode="consumer_web_subscription")


def test_settings_parse_prefixed_environment_without_leaking_between_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_PPT_MODEL_BACKEND", "openai")
    monkeypatch.setenv("AI_PPT_MODEL_RETRY_COUNT", "3")
    monkeypatch.setenv("AI_PPT_OPENAI_API_KEY", "test-key")

    from_environment = Settings()
    explicit = Settings(model_backend="fake", model_retry_count=1)

    assert from_environment.model_backend == "openai"
    assert from_environment.model_retry_count == 3
    assert from_environment.openai_api_key == "test-key"
    assert explicit.model_backend == "fake"
    assert explicit.model_retry_count == 1

    monkeypatch.delenv("AI_PPT_MODEL_BACKEND")
    monkeypatch.delenv("AI_PPT_MODEL_RETRY_COUNT")
    monkeypatch.delenv("AI_PPT_OPENAI_API_KEY")

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


def test_create_app_injects_free_ollama_text_gateway_with_free_image_fallback(tmp_path) -> None:
    app = create_app(
        Settings(
            database_path=tmp_path / "ollama.db",
            asset_path=tmp_path / "assets",
            model_backend="ollama",
            ollama_text_model="qwen2.5:7b",
        )
    )

    assert isinstance(app.state.text_gateway, OllamaTextGateway)
    assert isinstance(app.state.image_gateway, PollinationsImageGateway)
    assert isinstance(app.state.image_gateway, ImageGateway)


def test_create_app_injects_cascade_text_gateway(tmp_path) -> None:
    app = create_app(
        Settings(
            database_path=tmp_path / "cascade.db",
            asset_path=tmp_path / "assets",
            model_backend="cascade",
            compatible_enabled=False,
            cascade_include_ollama=False,
        )
    )

    assert isinstance(app.state.text_gateway, CascadeTextGateway)
    assert [candidate.name for candidate in app.state.text_gateway.candidates] == [
        "enhanced-local-fallback"
    ]


def test_runtime_status_reports_model_backend_without_secrets(tmp_path) -> None:
    app = create_app(
        Settings(
            database_path=tmp_path / "runtime.db",
            asset_path=tmp_path / "assets",
            model_backend="openai",
            openai_api_key="secret-key",
        )
    )
    with TestClient(app) as test_client:
        response = test_client.get("/api/runtime/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["modelBackend"] == "openai"
    assert payload["realModelEnabled"] is True
    assert payload["realModelReady"] is True
    assert payload["textModel"] == "gpt-5.4-mini"
    assert payload["defaultAgentMode"] == "research"
    assert payload["defaultCostArchitecture"] == "hybrid_router"
    assert payload["agentModePolicy"]["defaultMode"] == "research"
    assert [mode["id"] for mode in payload["agentModePolicy"]["modes"]] == [
        "fast",
        "research",
        "enterprise",
    ]
    assert [item["id"] for item in payload["agentModePolicy"]["legalCostArchitectures"]] == [
        "byok",
        "hybrid_router",
        "manual_prompt_workspace",
    ]
    assert "cookies" in payload["agentModePolicy"]["frontendMembershipRule"]
    assert "secret-key" not in response.text


def test_runtime_status_reports_free_ollama_backend(tmp_path) -> None:
    app = create_app(
        Settings(
            database_path=tmp_path / "runtime-ollama.db",
            asset_path=tmp_path / "assets",
            model_backend="ollama",
            ollama_text_model="qwen2.5:7b",
        )
    )
    with TestClient(app) as test_client:
        response = test_client.get("/api/runtime/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["modelBackend"] == "ollama"
    assert payload["realModelEnabled"] is False
    assert payload["realModelReady"] is False
    assert payload["freeModelEnabled"] is True
    assert payload["freeModelReady"] is False
    assert payload["textModel"] == "qwen2.5:7b"
    assert "Ollama" in payload["modelReadinessMessage"]


def test_runtime_status_reports_cascade_backend_without_secrets(tmp_path) -> None:
    app = create_app(
        Settings(
            database_path=tmp_path / "runtime-cascade.db",
            asset_path=tmp_path / "assets",
            model_backend="cascade",
            openrouter_api_key="openrouter-secret",
            compatible_enabled=False,
            cascade_include_ollama=False,
        )
    )
    with TestClient(app) as test_client:
        response = test_client.get("/api/runtime/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["modelBackend"] == "cascade"
    assert payload["realModelReady"] is True
    assert payload["freeModelEnabled"] is True
    assert payload["providerChain"][0]["name"] == "openrouter"
    assert payload["providerChain"][-1]["name"] == "enhanced-local-fallback"
    assert payload["imageGenerationReady"] is True
    assert payload["imageUpscalerReady"] is False
    assert payload["imageUpscalerModel"] == "realesrgan-x4plus"
    assert payload["expertImageResolution"] == {
        "ordinary": [1920, 1080],
        "keyPage": [3840, 2160],
    }
    assert any(
        item["name"] == "pollinations-free" and item["configured"] and item["freeOrLocal"]
        for item in payload["imageProviderChain"]
    )
    assert "openrouter-secret" not in response.text


def test_runtime_status_reports_ready_free_ollama_backend(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def ready_model(*_args: object, **_kwargs: object):
        import httpx

        return httpx.Response(200, json={"models": [{"name": "qwen2.5:7b"}]})

    monkeypatch.setattr("app.ai.ollama.httpx.get", ready_model)
    app = create_app(
        Settings(
            database_path=tmp_path / "runtime-ollama-ready.db",
            asset_path=tmp_path / "assets",
            model_backend="ollama",
            ollama_text_model="qwen2.5:7b",
        )
    )
    with TestClient(app) as test_client:
        response = test_client.get("/api/runtime/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["modelBackend"] == "ollama"
    assert payload["freeModelEnabled"] is True
    assert payload["freeModelReady"] is True
    assert payload["modelReadinessMessage"] == "Ollama is ready with model qwen2.5:7b."
    assert payload["imageGenerationReady"] is True


def test_openai_backend_without_key_returns_safe_model_error(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = create_app(
        Settings(
            database_path=tmp_path / "missing-key.db",
            asset_path=tmp_path / "assets",
            model_backend="openai",
        )
    )
    with TestClient(app) as test_client:
        created = test_client.post(
            "/api/projects",
            json={
                "schemaVersion": "1.0.0",
                "projectId": "missing-key",
                "inputLanguage": "zh",
                "outputLanguage": "en",
                "deckType": "course_presentation",
                "topic": "CRISPR",
                "audience": "Undergraduates",
                "mode": "professional",
            },
        )
        response = test_client.post("/api/projects/missing-key/outline/generate", json={})

    assert created.status_code == 201
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "model_provider_not_configured"


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
