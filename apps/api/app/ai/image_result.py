from __future__ import annotations

import base64

from .errors import ModelGatewayError
from .models import GeneratedImage, ImageRequest
from .png_validator import DEFAULT_MAX_FILE_BYTES, PNGValidationError, validate_png_bytes


def decode_image_result(
    encoded: str,
    request: ImageRequest,
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> GeneratedImage:
    """Decode untrusted provider output and expose only a safe boundary error."""

    result: GeneratedImage | None = None
    failed = False
    try:
        if not isinstance(encoded, str):
            raise TypeError("encoded image must be a string")
        if not isinstance(request, ImageRequest):
            raise TypeError("request must be an ImageRequest")
        if (
            not isinstance(max_file_bytes, int)
            or isinstance(max_file_bytes, bool)
            or max_file_bytes < 1
        ):
            raise ValueError("max_file_bytes must be a positive integer")

        max_encoded_bytes = 4 * ((max_file_bytes + 2) // 3)
        if len(encoded) > max_encoded_bytes:
            raise ValueError("encoded image exceeds byte budget")
        decoded = base64.b64decode(encoded, validate=True)
        if len(decoded) > max_file_bytes:
            raise ValueError("decoded image exceeds byte budget")
        validate_png_bytes(
            decoded,
            expected_width=request.width,
            expected_height=request.height,
            max_file_bytes=max_file_bytes,
        )
        result = GeneratedImage(
            bytes=decoded,
            mime_type="image/png",
            width=request.width,
            height=request.height,
            model=request.model,
        )
    except (TypeError, ValueError, PNGValidationError):
        failed = True

    if failed:
        raise ModelGatewayError(
            code="image_validation_failed",
            message="Generated image failed validation.",
            retryable=False,
        )
    if result is None:
        raise AssertionError("image boundary exited without a result or error")
    return result
