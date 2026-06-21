import base64
import traceback

import pytest

from app.ai.errors import ModelGatewayError
from app.ai.image_result import decode_image_result
from app.ai.models import ImageRequest
from png_factory import png


def _request(*, prompt: str = "private-prompt", width: int = 2, height: int = 1) -> ImageRequest:
    return ImageRequest("gpt-image-2", prompt, width, height)


def test_decodes_and_validates_a_png_result() -> None:
    request = _request()
    payload = png(2, 1, color_type=6)

    result = decode_image_result(base64.b64encode(payload).decode("ascii"), request)

    assert result.bytes == payload
    assert result.mime_type == "image/png"
    assert (result.width, result.height, result.model) == (2, 1, "gpt-image-2")


@pytest.mark.parametrize(
    "encoded",
    ["not!!base64", "aGVsbG8=\n", "YWJjZA", 123, None],
)
def test_maps_invalid_base64_and_nonstring_values_to_one_safe_error(encoded: object) -> None:
    _assert_safe_failure(encoded, _request(prompt="prompt-secret"))


def test_rejects_encoded_input_before_decoding_when_file_budget_cannot_hold_it() -> None:
    encoded = base64.b64encode(b"x" * 64).decode("ascii")
    _assert_safe_failure(encoded, _request(), max_file_bytes=8)


def test_maps_invalid_png_and_dimension_mismatch_to_one_safe_error() -> None:
    _assert_safe_failure(base64.b64encode(b"internal-png-reason").decode("ascii"), _request())
    wrong_dimensions = base64.b64encode(png(3, 1)).decode("ascii")
    _assert_safe_failure(wrong_dimensions, _request(width=2, height=1))


def _assert_safe_failure(
    encoded: object,
    request: ImageRequest,
    *,
    max_file_bytes: int = 32 * 1024 * 1024,
) -> None:
    with pytest.raises(ModelGatewayError) as caught:
        decode_image_result(encoded, request, max_file_bytes=max_file_bytes)  # type: ignore[arg-type]

    error = caught.value
    assert error.code == "image_validation_failed"
    assert error.message == "Generated image failed validation."
    assert error.retryable is False
    assert error.__context__ is None
    assert error.__cause__ is None
    rendered = "".join(traceback.format_exception(error))
    for secret in (
        request.prompt,
        str(encoded),
        "internal-png-reason",
        "PNGValidationError",
        "binascii",
    ):
        assert secret not in str(error)
        assert secret not in repr(error)
        assert secret not in rendered
