from contextlib import asynccontextmanager
from threading import Lock
import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, get_settings
from .ai.cascade import CascadeTextGateway, TextProviderCandidate
from .ai.errors import ModelGatewayError
from .ai.fakes import FakeImageGateway, FakeTextGateway
from .ai.image_http import CascadeImageGateway, HttpJsonImageGateway, ImageProviderCandidate, PollinationsImageGateway
from .ai.models import GeneratedImage, ImageRequest, TextRequest, TextResult
from .ai.ollama import OllamaTextGateway
from .ai.openai import OpenAIImageGateway, OpenAITextGateway
from .errors import PublicError
from .persistence.sqlite import SQLiteProjectRepository
from .routes.billing import router as billing_router
from .routes.exports import router as exports_router
from .routes.image_agent import router as image_agent_router
from .routes.outline import router as outline_router
from .routes.projects import router as projects_router
from .routes.quality import router as quality_router
from .routes.render import router as render_router
from .routes.slide_deck import router as slide_deck_router
from .routes.sources import router as sources_router
from .routes.skills import router as skills_router
from .routes.visual import router as visual_router
from .services.agent_modes import runtime_agent_modes


class _UnavailableTextGateway:
    def generate(self, _request: TextRequest) -> TextResult:
        raise ModelGatewayError(
            code="model_provider_not_configured",
            message="Real model mode is enabled, but the provider key is not configured.",
            retryable=False,
        )


class _UnavailableImageGateway:
    def generate(self, _request: ImageRequest) -> GeneratedImage:
        raise ModelGatewayError(
            code="model_provider_not_configured",
            message="Real image mode is enabled, but the provider key is not configured.",
            retryable=False,
        )


def _provider_key(settings: Settings) -> str | None:
    return settings.openai_api_key or os.getenv("OPENAI_API_KEY")


def _env_or_value(value: str | None, env_name: str) -> str | None:
    return value or os.getenv(env_name)


def _build_text_gateway(settings: Settings):
    if settings.model_backend == "fake":
        return FakeTextGateway()
    if settings.model_backend == "ollama":
        return OllamaTextGateway(
            base_url=settings.ollama_base_url,
            model=settings.ollama_text_model,
            max_attempts=settings.model_retry_count,
        )
    if settings.model_backend == "cascade":
        return CascadeTextGateway(_cascade_candidates(settings))
    key = _provider_key(settings)
    if key is None:
        return _UnavailableTextGateway()
    return OpenAITextGateway(
        api_key=key,
        base_url=settings.openai_base_url,
        max_attempts=settings.model_retry_count,
    )


def _cascade_candidates(settings: Settings) -> list[TextProviderCandidate]:
    candidates: list[TextProviderCandidate] = []
    openai_key = _provider_key(settings)
    if openai_key:
        candidates.append(
            TextProviderCandidate(
                name="openai",
                gateway=OpenAITextGateway(
                    api_key=openai_key,
                    base_url=settings.openai_base_url,
                    max_attempts=settings.model_retry_count,
                    response_format_mode="json_schema",
                ),
                model=settings.text_model,
            )
        )
    gemini_key = _env_or_value(settings.gemini_api_key, "GEMINI_API_KEY")
    if gemini_key:
        candidates.append(
            TextProviderCandidate(
                name="gemini",
                gateway=OpenAITextGateway(
                    api_key=gemini_key,
                    base_url=settings.gemini_base_url,
                    max_attempts=settings.model_retry_count,
                    response_format_mode="json_object",
                ),
                model=settings.gemini_text_model,
                free_or_local=True,
            )
        )
    openrouter_key = _env_or_value(settings.openrouter_api_key, "OPENROUTER_API_KEY")
    if openrouter_key:
        candidates.append(
            TextProviderCandidate(
                name="openrouter",
                gateway=OpenAITextGateway(
                    api_key=openrouter_key,
                    base_url=settings.openrouter_base_url,
                    max_attempts=settings.model_retry_count,
                    response_format_mode="json_object",
                ),
                model=settings.openrouter_text_model,
                free_or_local=True,
            )
        )
    groq_key = _env_or_value(settings.groq_api_key, "GROQ_API_KEY")
    if groq_key:
        candidates.append(
            TextProviderCandidate(
                name="groq",
                gateway=OpenAITextGateway(
                    api_key=groq_key,
                    base_url=settings.groq_base_url,
                    max_attempts=settings.model_retry_count,
                    response_format_mode="json_object",
                ),
                model=settings.groq_text_model,
                free_or_local=True,
            )
        )
    if settings.compatible_enabled:
        candidates.append(
            TextProviderCandidate(
                name="openai-compatible-local",
                gateway=OpenAITextGateway(
                    api_key=_env_or_value(settings.compatible_api_key, "AI_PPT_COMPATIBLE_API_KEY"),
                    base_url=settings.compatible_base_url,
                    max_attempts=1,
                    response_format_mode="json_object",
                ),
                model=settings.compatible_text_model,
                free_or_local=True,
            )
        )
    if settings.cascade_include_ollama:
        candidates.append(
            TextProviderCandidate(
                name="ollama",
                gateway=OllamaTextGateway(
                    base_url=settings.ollama_base_url,
                    model=settings.ollama_text_model,
                    max_attempts=settings.model_retry_count,
                ),
                model=settings.ollama_text_model,
                free_or_local=True,
            )
        )
    if settings.cascade_include_fake_fallback:
        candidates.append(
            TextProviderCandidate(
                name="enhanced-local-fallback",
                gateway=FakeTextGateway(),
                model=settings.text_model,
                free_or_local=True,
            )
        )
    return candidates


def _build_image_gateway(settings: Settings):
    if settings.model_backend == "fake":
        return FakeImageGateway()
    candidates = _image_candidates(settings)
    if candidates:
        return CascadeImageGateway(candidates) if len(candidates) > 1 else candidates[0].gateway
    if settings.model_backend == "ollama":
        return _UnavailableImageGateway()
    return _UnavailableImageGateway()


def _image_candidates(settings: Settings) -> list[ImageProviderCandidate]:
    candidates: list[ImageProviderCandidate] = []
    openai_key = _provider_key(settings)
    if openai_key:
        candidates.append(
            ImageProviderCandidate(
                name="openai-image",
                gateway=OpenAIImageGateway(
                    api_key=openai_key,
                    base_url=settings.openai_base_url,
                    max_attempts=settings.model_retry_count,
                ),
                model=settings.image_model,
            )
        )
    if settings.pollinations_image_enabled:
        candidates.append(
            ImageProviderCandidate(
                name="pollinations-free",
                gateway=PollinationsImageGateway(
                    base_url=settings.pollinations_image_base_url,
                    model=settings.pollinations_image_model,
                    referrer=settings.pollinations_image_referrer,
                    enhance=settings.pollinations_image_enhance,
                    max_attempts=max(settings.model_retry_count, 2),
                ),
                model=settings.pollinations_image_model,
                free_or_local=True,
            )
        )
    midjourney_url = _env_or_value(settings.midjourney_api_url, "AI_PPT_MIDJOURNEY_API_URL")
    if midjourney_url:
        candidates.append(
            ImageProviderCandidate(
                name="midjourney-compatible",
                gateway=HttpJsonImageGateway(
                    provider_name="midjourney-compatible",
                    api_url=midjourney_url,
                    api_key=_env_or_value(settings.midjourney_api_key, "AI_PPT_MIDJOURNEY_API_KEY"),
                    model=settings.midjourney_model,
                    max_attempts=settings.model_retry_count,
                ),
                model=settings.midjourney_model,
                free_or_local=False,
            )
        )
    stable_url = _env_or_value(settings.stable_diffusion_api_url, "AI_PPT_STABLE_DIFFUSION_API_URL")
    if stable_url:
        candidates.append(
            ImageProviderCandidate(
                name="stable-diffusion",
                gateway=HttpJsonImageGateway(
                    provider_name="stable-diffusion",
                    api_url=stable_url,
                    api_key=_env_or_value(settings.stable_diffusion_api_key, "AI_PPT_STABLE_DIFFUSION_API_KEY"),
                    model=settings.stable_diffusion_model,
                    max_attempts=settings.model_retry_count,
                ),
                model=settings.stable_diffusion_model,
                free_or_local=True,
            )
        )
    custom_url = _env_or_value(settings.custom_image2_api_url, "AI_PPT_CUSTOM_IMAGE2_API_URL")
    if custom_url:
        candidates.append(
            ImageProviderCandidate(
                name="custom-image2",
                gateway=HttpJsonImageGateway(
                    provider_name="custom-image2",
                    api_url=custom_url,
                    api_key=_env_or_value(settings.custom_image2_api_key, "AI_PPT_CUSTOM_IMAGE2_API_KEY"),
                    model=settings.custom_image2_model,
                    max_attempts=settings.model_retry_count,
                ),
                model=settings.custom_image2_model,
                free_or_local=True,
            )
        )
    return candidates


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    repository = SQLiteProjectRepository(resolved.database_path)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        repository.initialize()
        try:
            yield
        finally:
            repository.close()

    app = FastAPI(
        title=resolved.app_name,
        version=resolved.app_version,
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.repository = repository
    app.state.text_gateway = _build_text_gateway(resolved)
    app.state.image_gateway = _build_image_gateway(resolved)
    app.state.image_jobs = {}
    app.state.image_jobs_lock = Lock()
    if resolved.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=resolved.allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "PUT", "OPTIONS"],
            allow_headers=["*"],
        )
    app.include_router(billing_router, prefix="/api")
    app.include_router(projects_router, prefix="/api")
    app.include_router(outline_router, prefix="/api")
    app.include_router(visual_router, prefix="/api")
    app.include_router(slide_deck_router, prefix="/api")
    app.include_router(render_router, prefix="/api")
    app.include_router(quality_router, prefix="/api")
    app.include_router(exports_router, prefix="/api")
    app.include_router(sources_router, prefix="/api")
    app.include_router(image_agent_router, prefix="/api")
    app.include_router(skills_router, prefix="/api")

    @app.exception_handler(PublicError)
    async def public_error_handler(
        _request: Request,
        exc: PublicError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(ModelGatewayError)
    async def model_gateway_error_handler(
        _request: Request,
        exc: ModelGatewayError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503 if exc.retryable else 502,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": resolved.app_name,
            "version": resolved.app_version,
        }

    @app.get("/api/runtime/status")
    def runtime_status() -> dict[str, Any]:
        provider_key_present = _provider_key(resolved) is not None
        text_model = (
            resolved.ollama_text_model
            if resolved.model_backend == "ollama"
            else " / ".join(candidate.model or "" for candidate in app.state.text_gateway.candidates)
            if isinstance(app.state.text_gateway, CascadeTextGateway)
            else resolved.text_model
        )
        free_model_ready = False
        model_readiness_message: str | None = None
        provider_chain = _runtime_provider_chain(resolved, app.state.text_gateway)
        image_provider_chain = _runtime_image_provider_chain(resolved)
        if resolved.model_backend == "ollama":
            health = app.state.text_gateway.health()
            free_model_ready = health.service_ready and health.model_ready
            model_readiness_message = health.message
        elif resolved.model_backend == "cascade":
            free_model_ready = any(item["configured"] for item in provider_chain if item["freeOrLocal"])
            configured = [item["name"] for item in provider_chain if item["configured"]]
            model_readiness_message = (
                f"Cascade mode is ready. Provider order: {', '.join(configured)}."
                if configured
                else "Cascade mode has no configured provider."
            )
        elif resolved.model_backend == "openai":
            model_readiness_message = (
                "OpenAI API key is configured."
                if provider_key_present
                else "OpenAI mode is selected but no API key is configured."
            )
        else:
            model_readiness_message = "Fake mode is ready for deterministic local testing."
        return {
            "status": "ok",
            "modelBackend": resolved.model_backend,
            "realModelEnabled": resolved.model_backend in {"openai", "cascade"},
            "realModelReady": (
                (resolved.model_backend == "openai" and provider_key_present)
                or (resolved.model_backend == "cascade" and any(item["configured"] for item in provider_chain))
            ),
            "freeModelEnabled": resolved.model_backend in {"ollama", "cascade"},
            "freeModelReady": free_model_ready,
            "modelReadinessMessage": model_readiness_message,
            "textModel": text_model,
            "qualityModel": text_model if resolved.model_backend in {"ollama", "cascade"} else resolved.quality_model,
            "imageModel": resolved.image_model,
            "providerChain": provider_chain,
            "imageSearchReady": resolved.image_search_enabled,
            "imageGenerationReady": any(
                item["configured"] and item["name"] not in {"open-web-search", "local-png-fallback"}
                for item in image_provider_chain
            ),
            "imageProviderChain": image_provider_chain,
            "imageUpscalerReady": bool(
                resolved.realesrgan_enabled
                and resolved.realesrgan_executable is not None
                and resolved.realesrgan_executable.is_file()
            ),
            "imageUpscalerModel": resolved.realesrgan_model,
            "expertImageResolution": {
                "ordinary": [
                    resolved.expert_image_min_long_edge,
                    resolved.expert_image_min_short_edge,
                ],
                "keyPage": [
                    resolved.expert_key_image_min_long_edge,
                    resolved.expert_key_image_min_short_edge,
                ],
            },
            "defaultAgentMode": resolved.default_agent_mode,
            "defaultCostArchitecture": resolved.default_cost_architecture,
            "agentModePolicy": runtime_agent_modes(resolved.default_agent_mode),
        }

    return app


app = create_app()


def _runtime_provider_chain(settings: Settings, gateway) -> list[dict[str, str | bool]]:
    if isinstance(gateway, CascadeTextGateway):
        return [
            {
                "name": candidate.name,
                "model": candidate.model or "",
                "configured": True,
                "freeOrLocal": candidate.free_or_local,
            }
            for candidate in gateway.candidates
        ]
    if settings.model_backend == "openai":
        return [
            {
                "name": "openai",
                "model": settings.text_model,
                "configured": _provider_key(settings) is not None,
                "freeOrLocal": False,
            }
        ]
    if settings.model_backend == "ollama":
        return [
            {
                "name": "ollama",
                "model": settings.ollama_text_model,
                "configured": True,
                "freeOrLocal": True,
            }
        ]
    return [
        {
            "name": "enhanced-local-fallback",
            "model": settings.text_model,
            "configured": True,
            "freeOrLocal": True,
        }
    ]


def _runtime_image_provider_chain(settings: Settings) -> list[dict[str, str | bool]]:
    openai_key_present = _provider_key(settings) is not None
    bing_key_present = _env_or_value(settings.bing_image_search_key, "AI_PPT_BING_IMAGE_SEARCH_KEY") is not None
    midjourney_ready = _env_or_value(settings.midjourney_api_url, "AI_PPT_MIDJOURNEY_API_URL") is not None
    stable_ready = _env_or_value(settings.stable_diffusion_api_url, "AI_PPT_STABLE_DIFFUSION_API_URL") is not None
    custom_ready = _env_or_value(settings.custom_image2_api_url, "AI_PPT_CUSTOM_IMAGE2_API_URL") is not None
    return [
        {
            "name": "open-web-search",
            "model": "Wikimedia Commons" + (" + Bing Images" if bing_key_present else ""),
            "configured": settings.image_search_enabled,
            "freeOrLocal": True,
        },
        {
            "name": "openai-image",
            "model": settings.image_model,
            "configured": openai_key_present,
            "freeOrLocal": False,
        },
        {
            "name": "pollinations-free",
            "model": settings.pollinations_image_model,
            "configured": settings.pollinations_image_enabled,
            "freeOrLocal": True,
        },
        {
            "name": "midjourney-compatible",
            "model": settings.midjourney_model,
            "configured": midjourney_ready,
            "freeOrLocal": False,
        },
        {
            "name": "stable-diffusion",
            "model": settings.stable_diffusion_model,
            "configured": stable_ready,
            "freeOrLocal": True,
        },
        {
            "name": "custom-image2",
            "model": settings.custom_image2_model,
            "configured": custom_ready,
            "freeOrLocal": True,
        },
        {
            "name": "local-png-fallback",
            "model": "deterministic-local-png",
            "configured": True,
            "freeOrLocal": True,
        },
    ]
