from __future__ import annotations

import json
from typing import Any, Literal

import httpx
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from .errors import ModelGatewayError, run_provider_operation
from .image_result import decode_image_result
from .models import GeneratedImage, ImageRequest, TextRequest, TextResult
from .retry import run_with_retry


def _normalize_base_url(base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    if not value:
        raise ValueError("base_url must not be blank")
    return value


def _provider_headers(api_key: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key is not None and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    return headers


def _usage(payload: dict[str, Any]) -> dict[str, int]:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return {"inputTokens": 0, "outputTokens": 0}
    return {
        "inputTokens": int(
            usage.get("prompt_tokens")
            or usage.get("input_tokens")
            or 0
        ),
        "outputTokens": int(
            usage.get("completion_tokens")
            or usage.get("output_tokens")
            or 0
        ),
    }


class OpenAITextGateway:
    """Safe OpenAI-compatible JSON text gateway.

    The gateway returns only validated JSON and converts provider failures into
    stable public errors without retaining provider tracebacks, prompts, or raw
    response bodies.
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.openai.com/v1",
        max_attempts: int = 1,
        response_format_mode: Literal["json_schema", "json_object"] = "json_schema",
    ) -> None:
        self._api_key = api_key
        self._base_url = _normalize_base_url(base_url)
        self._max_attempts = max_attempts
        self._response_format_mode = response_format_mode

    def generate(self, request: TextRequest) -> TextResult:
        attempts = min(request.max_attempts, self._max_attempts)
        return run_with_retry(lambda: self._generate_once(request), attempts)

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

        system_content = (
            "You are an AI PPT SaaS engine. Return only valid JSON "
            "that matches the provided schema. Do not include markdown."
        )
        if self._response_format_mode == "json_object":
            system_content = (
                f"{system_content}\nJSON Schema:\n"
                f"{json.dumps(schema, ensure_ascii=False, sort_keys=True)}"
            )
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": request.prompt},
            ],
        }
        if self._response_format_mode == "json_schema":
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "ai_ppt_structured_response",
                    "strict": True,
                    "schema": schema,
                },
            }
        else:
            payload["response_format"] = {"type": "json_object"}
        provider_payload = self._post_json(
            "/chat/completions",
            payload,
            timeout_seconds=request.timeout_seconds,
        )
        try:
            choices = provider_payload["choices"]
            content = choices[0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError
            data = json.loads(content)
            Draft202012Validator(schema).validate(data)
        except (KeyError, IndexError, TypeError, ValueError, ValidationError, json.JSONDecodeError):
            raise ModelGatewayError(
                code="model_output_invalid",
                message="The model returned invalid structured output.",
                retryable=True,
            ) from None
        return TextResult(data=data, model=request.model, usage=_usage(provider_payload))

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
                headers=_provider_headers(self._api_key),
                json=payload,
                timeout=timeout_seconds,
            )
            if response.status_code in {408, 409, 429} or response.status_code >= 500:
                raise ModelGatewayError(
                    code="model_provider_unavailable",
                    message="The model provider is temporarily unavailable.",
                    retryable=True,
                )
            if response.status_code >= 400:
                raise ModelGatewayError(
                    code="model_request_failed",
                    message="The model request could not be completed.",
                    retryable=False,
                )
            data = response.json()
            if not isinstance(data, dict):
                raise TypeError
            return data

        return run_provider_operation(
            operation,
            code="model_request_failed",
            message="The model request could not be completed.",
            retryable=True,
        )


class OpenAIImageGateway:
    """Safe GPT Image 2 gateway with no automatic fallback."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        max_attempts: int = 1,
    ) -> None:
        self._api_key = api_key
        self._base_url = _normalize_base_url(base_url)
        self._max_attempts = max_attempts

    def generate(self, request: ImageRequest) -> GeneratedImage:
        if request.model != "gpt-image-2":
            raise ModelGatewayError(
                code="image_model_fallback_not_allowed",
                message="GPT Image 2 is required unless the user explicitly approves a fallback.",
                retryable=False,
            )
        attempts = min(request.max_attempts, self._max_attempts)
        return run_with_retry(lambda: self._generate_once(request), attempts)

    def _generate_once(self, request: ImageRequest) -> GeneratedImage:
        payload = {
            "model": request.model,
            "prompt": request.prompt,
            "size": f"{request.width}x{request.height}",
            "response_format": "b64_json",
        }

        def operation() -> dict[str, Any]:
            response = httpx.post(
                f"{self._base_url}/images/generations",
                headers=_provider_headers(self._api_key),
                json=payload,
                timeout=request.timeout_seconds,
            )
            if response.status_code in {408, 409, 429} or response.status_code >= 500:
                raise ModelGatewayError(
                    code="model_provider_unavailable",
                    message="The image provider is temporarily unavailable.",
                    retryable=True,
                )
            if response.status_code >= 400:
                raise ModelGatewayError(
                    code="image_request_failed",
                    message="The image request could not be completed.",
                    retryable=False,
                )
            data = response.json()
            if not isinstance(data, dict):
                raise TypeError
            return data

        provider_payload = run_provider_operation(
            operation,
            code="image_request_failed",
            message="The image request could not be completed.",
            retryable=True,
        )
        try:
            encoded = provider_payload["data"][0]["b64_json"]
        except (KeyError, IndexError, TypeError):
            raise ModelGatewayError(
                code="image_validation_failed",
                message="Generated image failed validation.",
                retryable=False,
            ) from None
        return decode_image_result(encoded, request)
