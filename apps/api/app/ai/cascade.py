from __future__ import annotations

from dataclasses import dataclass, replace

from .errors import ModelGatewayError
from .models import TextRequest, TextResult
from .protocols import TextGateway


@dataclass(frozen=True, slots=True)
class TextProviderCandidate:
    name: str
    gateway: TextGateway
    model: str | None = None
    free_or_local: bool = False


class CascadeTextGateway:
    """Try multiple safe text gateways before falling back.

    This is intentionally provider-agnostic: hosted "free tier" APIs, local
    OpenAI-compatible servers, Ollama, and deterministic fallback can all be
    composed without leaking prompts or raw provider failures.
    """

    def __init__(self, candidates: list[TextProviderCandidate]) -> None:
        if not candidates:
            raise ValueError("candidates must not be empty")
        self._candidates = tuple(candidates)

    @property
    def candidates(self) -> tuple[TextProviderCandidate, ...]:
        return self._candidates

    def generate(self, request: TextRequest) -> TextResult:
        last_error: ModelGatewayError | None = None
        for candidate in self._candidates:
            candidate_request = (
                replace(request, model=candidate.model)
                if candidate.model is not None
                else request
            )
            try:
                result = candidate.gateway.generate(candidate_request)
                return TextResult(
                    data=result.data,
                    model=f"{candidate.name}:{result.model}",
                    usage=result.usage,
                )
            except ModelGatewayError as error:
                last_error = error
                if error.code in {"invalid_response_schema"}:
                    break
        if last_error is not None:
            raise ModelGatewayError(
                code="cascade_model_unavailable",
                message="All configured text model providers failed or returned invalid structured output.",
                retryable=last_error.retryable,
            ) from None
        raise ModelGatewayError(
            code="cascade_model_unavailable",
            message="No text model provider is available.",
            retryable=False,
        )
