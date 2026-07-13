from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from .errors import ModelGatewayError, run_provider_operation
from .models import TextRequest, TextResult
from .retry import run_with_retry


def _normalize_base_url(base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    if not value:
        raise ValueError("base_url must not be blank")
    return value


@dataclass(frozen=True, slots=True)
class OllamaHealth:
    service_ready: bool
    model_ready: bool
    message: str


class OllamaTextGateway:
    """Free local structured text gateway backed by Ollama.

    This gateway intentionally calls only a local Ollama-compatible endpoint. It
    never sends prompts to OpenAI and it returns only JSON validated against the
    caller-provided schema.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:7b",
        max_attempts: int = 1,
    ) -> None:
        self._base_url = _normalize_base_url(base_url)
        self._model = model
        self._max_attempts = max_attempts

    def generate(self, request: TextRequest) -> TextResult:
        attempts = min(request.max_attempts, self._max_attempts)
        return run_with_retry(lambda: self._generate_once(request), attempts)

    def health(self, timeout_seconds: float = 1.5) -> OllamaHealth:
        try:
            response = httpx.get(f"{self._base_url}/api/tags", timeout=timeout_seconds)
        except Exception:
            return OllamaHealth(
                service_ready=False,
                model_ready=False,
                message="Ollama is not reachable. Start Ollama before using free local AI.",
            )
        if response.status_code >= 400:
            return OllamaHealth(
                service_ready=False,
                model_ready=False,
                message="Ollama responded with an error.",
            )
        try:
            payload = response.json()
            models = payload.get("models", [])
            names = {str(model.get("name", "")) for model in models if isinstance(model, dict)}
        except Exception:
            return OllamaHealth(
                service_ready=True,
                model_ready=False,
                message="Ollama is running but returned an unexpected model list.",
            )
        if self._model in names:
            return OllamaHealth(
                service_ready=True,
                model_ready=True,
                message=f"Ollama is ready with model {self._model}.",
            )
        return OllamaHealth(
            service_ready=True,
            model_ready=False,
            message=f"Ollama is running, but model {self._model} is missing. Run: ollama pull {self._model}",
        )

    def _generate_once(self, request: TextRequest) -> TextResult:
        schema = dict(request.response_schema)
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError:
            raise ModelGatewayError(
                code="invalid_response_schema",
                message="The requested response format is unavailable.",
                retryable=False,
            ) from None

        prompt = (
            "You are the local free AI engine for an AI PPT SaaS. "
            "Return only valid JSON matching this JSON Schema. "
            "Do not include markdown, explanations, or extra keys.\n\n"
            f"JSON Schema:\n{json.dumps(schema, ensure_ascii=False, sort_keys=True)}\n\n"
            f"Task payload:\n{request.prompt}"
        )
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "format": schema,
            "options": {
                "temperature": 0.2,
                "num_ctx": 8192,
            },
        }
        provider_payload = self._post_json(
            "/api/generate",
            payload,
            timeout_seconds=request.timeout_seconds,
        )
        try:
            content = provider_payload["response"]
            if not isinstance(content, str):
                raise TypeError
            data = _parse_json_response(content)
            Draft202012Validator(schema).validate(data)
        except (KeyError, TypeError, ValueError, ValidationError, json.JSONDecodeError):
            raise ModelGatewayError(
                code="model_output_invalid",
                message="The local free model returned invalid structured output.",
                retryable=True,
            ) from None
        return TextResult(data=data, model=self._model, usage=_usage(provider_payload))

    def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            response = httpx.post(
                f"{self._base_url}{path}",
                json=payload,
                timeout=timeout_seconds,
            )
            if response.status_code == 404:
                raise ModelGatewayError(
                    code="ollama_model_not_found",
                    message="The configured free local AI model is not available in Ollama.",
                    retryable=False,
                )
            if response.status_code in {408, 409, 429} or response.status_code >= 500:
                raise ModelGatewayError(
                    code="ollama_unavailable",
                    message="The free local AI service is temporarily unavailable.",
                    retryable=True,
                )
            if response.status_code >= 400:
                raise ModelGatewayError(
                    code="ollama_request_failed",
                    message="The free local AI request could not be completed.",
                    retryable=False,
                )
            data = response.json()
            if not isinstance(data, dict):
                raise TypeError
            return data

        return run_provider_operation(
            operation,
            code="ollama_unavailable",
            message="The free local AI service is unavailable. Start Ollama and pull the configured model.",
            retryable=True,
        )


def _parse_json_response(content: str) -> Any:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(stripped[start : end + 1])


def _usage(payload: dict[str, Any]) -> dict[str, int]:
    return {
        "inputTokens": int(payload.get("prompt_eval_count") or 0),
        "outputTokens": int(payload.get("eval_count") or 0),
    }
