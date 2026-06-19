from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Settings, get_settings
from .errors import PublicError


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    app = FastAPI(title=resolved.app_name, version=resolved.app_version)
    app.state.settings = resolved

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
