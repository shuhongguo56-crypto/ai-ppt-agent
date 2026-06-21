import logging
import math
import re
from collections.abc import Mapping


LOGGER = logging.getLogger("ai_ppt.model")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")


def _safe_identifier(value: object, fallback: str) -> str:
    if isinstance(value, str) and _IDENTIFIER.fullmatch(value):
        return value
    return fallback


def _safe_latency(value: object) -> float:
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    ):
        return float(value)
    return 0.0


def log_model_event(
    *,
    request_id: str,
    model: str,
    latency_ms: float,
    error_code: str | None = None,
    usage: Mapping[str, int] | None = None,
) -> None:
    """Log only explicitly allowlisted operational metadata."""

    usage_summary = {
        key: value
        for key, value in (usage or {}).items()
        if key in {"inputTokens", "outputTokens"}
        and isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    }
    LOGGER.info(
        "model gateway event",
        extra={
            "request_id": _safe_identifier(request_id, "invalid-request-id"),
            "model": _safe_identifier(model, "invalid-model"),
            "latency_ms": _safe_latency(latency_ms),
            "error_code": (
                None
                if error_code is None
                else _safe_identifier(error_code, "invalid-error-code")
            ),
            "usage": usage_summary,
        },
    )
