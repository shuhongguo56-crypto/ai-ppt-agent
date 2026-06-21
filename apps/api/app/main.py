from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Settings, get_settings
from .ai.fakes import FakeImageGateway, FakeTextGateway
from .errors import PublicError
from .persistence.sqlite import SQLiteProjectRepository
from .routes.outline import router as outline_router
from .routes.projects import router as projects_router
from .routes.slide_deck import router as slide_deck_router
from .routes.skills import router as skills_router
from .routes.visual import router as visual_router


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
    app.state.text_gateway = FakeTextGateway()
    app.state.image_gateway = FakeImageGateway()
    app.include_router(projects_router, prefix="/api")
    app.include_router(outline_router, prefix="/api")
    app.include_router(visual_router, prefix="/api")
    app.include_router(slide_deck_router, prefix="/api")
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

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": resolved.app_name,
            "version": resolved.app_version,
        }

    return app


app = create_app()
