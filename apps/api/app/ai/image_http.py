from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote

import httpx

from .errors import ModelGatewayError, run_provider_operation
from .models import GeneratedImage, ImageRequest
from .png_validator import DEFAULT_MAX_FILE_BYTES, PNGValidationError, validate_png_bytes


SUPPORTED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg"}


@dataclass(frozen=True, slots=True)
class ImageProviderCandidate:
    name: str
    gateway: object
    model: str
    free_or_local: bool = False


class CascadeImageGateway:
    """Try configured image providers in order without leaking provider details."""

    def __init__(self, candidates: list[ImageProviderCandidate]) -> None:
        if not candidates:
            raise ValueError("at least one image provider candidate is required")
        self.candidates = candidates

    def generate(self, request: ImageRequest) -> GeneratedImage:
        last_error: ModelGatewayError | None = None
        for candidate in self.candidates:
            try:
                generated = candidate.gateway.generate(
                    ImageRequest(
                        model=candidate.model,
                        prompt=request.prompt,
                        width=request.width,
                        height=request.height,
                        timeout_seconds=request.timeout_seconds,
                        max_attempts=request.max_attempts,
                    )
                )
                return GeneratedImage(
                    bytes=generated.bytes,
                    mime_type=generated.mime_type,
                    width=generated.width,
                    height=generated.height,
                    model=f"{candidate.name}:{generated.model}",
                )
            except (ModelGatewayError, ValueError, OSError) as error:
                last_error = (
                    error
                    if isinstance(error, ModelGatewayError)
                    else ModelGatewayError(
                        code="image_request_failed",
                        message="The image request could not be completed.",
                        retryable=True,
                    )
                )
                continue
        raise last_error or ModelGatewayError(
            code="model_provider_not_configured",
            message="Real image mode is enabled, but no image provider is configured.",
            retryable=False,
        )


class PollinationsImageGateway:
    """Free no-key image-generation adapter for Pollinations FLUX-style images."""

    def __init__(
        self,
        *,
        base_url: str = "https://image.pollinations.ai/prompt",
        model: str = "flux",
        referrer: str = "ai-ppt-agent",
        enhance: bool = True,
        private: bool = True,
        nologo: bool = True,
        max_attempts: int = 2,
    ) -> None:
        self._base_url = _nonblank(base_url, "base_url").rstrip("/")
        self._model = _nonblank(model, "model")
        self._referrer = _nonblank(referrer, "referrer")
        self._enhance = enhance
        self._private = private
        self._nologo = nologo
        self._max_attempts = max_attempts

    def generate(self, request: ImageRequest) -> GeneratedImage:
        attempts = min(request.max_attempts, self._max_attempts)
        last_error: ModelGatewayError | None = None
        for _attempt in range(attempts):
            try:
                return self._generate_once(request)
            except ModelGatewayError as error:
                last_error = error
                if not error.retryable:
                    raise
        raise last_error or ModelGatewayError(
            code="image_request_failed",
            message="The image request could not be completed.",
            retryable=True,
        )

    def _generate_once(self, request: ImageRequest) -> GeneratedImage:
        prompt = _clip_prompt(request.prompt)
        url = f"{self._base_url}/{quote(prompt, safe='')}"
        params = {
            "width": request.width,
            "height": request.height,
            "model": self._model,
            "enhance": str(self._enhance).lower(),
            "private": str(self._private).lower(),
            "nologo": str(self._nologo).lower(),
            "referrer": self._referrer,
            "negative_prompt": (
                "text, letters, words, numbers, typography, logo, watermark, signature, caption, "
                "label, signage, document, poster, presentation slide, dashboard, user interface, screen"
            ),
        }

        def operation() -> httpx.Response:
            response = httpx.get(
                url,
                params=params,
                headers={
                    "Accept": "image/png,image/jpeg;q=0.95,*/*;q=0.2",
                    "User-Agent": "AI-PPT-Agent/0.1 pollinations-image",
                },
                timeout=request.timeout_seconds,
                follow_redirects=True,
            )
            if response.status_code in {408, 409, 425, 429} or response.status_code >= 500:
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
            return response

        response = run_provider_operation(
            operation,
            code="image_request_failed",
            message="The image request could not be completed.",
            retryable=True,
        )
        mime_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
            mime_type = _mime_from_bytes(response.content) or mime_type
        if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
            raise _validation_error()
        return _safe_generated_image(
            response.content,
            request=request,
            mime_type=mime_type,
            model=f"pollinations:{self._model}",
        )


class HttpJsonImageGateway:
    """Generic HTTP image-generation adapter for SD/custom image2 style APIs.

    The adapter is intentionally conservative: it never exposes prompts or raw
    provider bodies in public errors, accepts only PNG/JPEG bytes, and supports
    the common JSON response shapes used by Stable Diffusion WebUI, OpenAI-like
    image APIs, and lightweight custom image2 gateways.
    """

    def __init__(
        self,
        *,
        provider_name: str,
        api_url: str,
        api_key: str | None = None,
        model: str = "image-provider",
        max_attempts: int = 1,
    ) -> None:
        _nonblank(api_url, "api_url")
        self._provider_name = _nonblank(provider_name, "provider_name")
        self._api_url = api_url.strip()
        self._api_key = api_key.strip() if api_key and api_key.strip() else None
        self._model = _nonblank(model, "model")
        self._max_attempts = max_attempts

    def generate(self, request: ImageRequest) -> GeneratedImage:
        attempts = min(request.max_attempts, self._max_attempts)
        last_error: ModelGatewayError | None = None
        for _attempt in range(attempts):
            try:
                return self._generate_once(request)
            except ModelGatewayError as error:
                last_error = error
                if not error.retryable:
                    raise
        raise last_error or ModelGatewayError(
            code="image_request_failed",
            message="The image request could not be completed.",
            retryable=True,
        )

    def _generate_once(self, request: ImageRequest) -> GeneratedImage:
        payload = self._payload(request)
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        def operation() -> httpx.Response:
            response = httpx.post(
                self._api_url,
                headers=headers,
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
            return response

        response = run_provider_operation(
            operation,
            code="image_request_failed",
            message="The image request could not be completed.",
            retryable=True,
        )
        mime_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        if mime_type in SUPPORTED_IMAGE_MIME_TYPES:
            return _safe_generated_image(
                response.content,
                request=request,
                mime_type=mime_type,
                model=f"{self._provider_name}:{self._model}",
            )
        try:
            data = response.json()
        except ValueError:
            raise _validation_error() from None
        if not isinstance(data, Mapping):
            raise _validation_error()
        encoded = _first_b64_image(data)
        if not encoded:
            raise _validation_error()
        try:
            raw = base64.b64decode(_strip_data_url(encoded), validate=True)
        except ValueError:
            raise _validation_error() from None
        return _safe_generated_image(
            raw,
            request=request,
            mime_type=_mime_from_bytes(raw) or "image/png",
            model=f"{self._provider_name}:{self._model}",
        )

    def _payload(self, request: ImageRequest) -> dict[str, Any]:
        if "sdapi" in self._api_url or "stable" in self._provider_name.casefold():
            return {
                "prompt": request.prompt,
                "negative_prompt": "text, watermark, logo, blurry, low quality, malformed",
                "width": request.width,
                "height": request.height,
                "steps": 28,
                "cfg_scale": 7,
                "sampler_name": "DPM++ 2M Karras",
            }
        return {
            "model": self._model,
            "prompt": request.prompt,
            "width": request.width,
            "height": request.height,
            "size": f"{request.width}x{request.height}",
            "response_format": "b64_json",
        }


def _nonblank(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must not be blank")
    return value.strip()


def _first_b64_image(data: Mapping[str, Any]) -> str | None:
    candidates: list[Any] = [
        data.get("b64_json"),
        data.get("imageBase64"),
        data.get("image_base64"),
        data.get("image"),
    ]
    images = data.get("images")
    if isinstance(images, list) and images:
        candidates.append(images[0])
    records = data.get("data")
    if isinstance(records, list) and records:
        first = records[0]
        if isinstance(first, Mapping):
            candidates.extend([first.get("b64_json"), first.get("image"), first.get("imageBase64")])
        else:
            candidates.append(first)
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _strip_data_url(value: str) -> str:
    if value.startswith("data:") and "," in value:
        return value.split(",", 1)[1]
    return value


def _clip_prompt(value: str, encoded_limit: int = 700) -> str:
    value = " ".join(str(value or "").split())
    if len(quote(value, safe="")) <= encoded_limit:
        return value
    low = 0
    high = len(value)
    while low < high:
        midpoint = (low + high + 1) // 2
        candidate = value[:midpoint].rstrip()
        if len(quote(candidate, safe="")) <= encoded_limit:
            low = midpoint
        else:
            high = midpoint - 1
    return value[:low].rstrip()


def _mime_from_bytes(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def _safe_generated_image(
    data: bytes,
    *,
    request: ImageRequest,
    mime_type: str,
    model: str,
) -> GeneratedImage:
    if len(data) > DEFAULT_MAX_FILE_BYTES:
        raise _validation_error()
    detected = _mime_from_bytes(data)
    if detected not in SUPPORTED_IMAGE_MIME_TYPES:
        raise _validation_error()
    if detected == "image/png":
        try:
            validate_png_bytes(
                data,
                expected_width=request.width,
                expected_height=request.height,
                max_file_bytes=DEFAULT_MAX_FILE_BYTES,
            )
        except PNGValidationError:
            raise _validation_error() from None
    return GeneratedImage(
        bytes=data,
        mime_type=detected or mime_type,
        width=request.width,
        height=request.height,
        model=model,
    )


def _validation_error() -> ModelGatewayError:
    return ModelGatewayError(
        code="image_validation_failed",
        message="Generated image failed validation.",
        retryable=False,
    )
