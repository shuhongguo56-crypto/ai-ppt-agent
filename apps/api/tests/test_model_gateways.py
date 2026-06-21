import json
import struct
import zlib

import pytest

from app.ai.fakes import FakeImageGateway, FakeTextGateway
from app.ai.models import ImageRequest, TextRequest
from app.ai.protocols import ImageGateway, TextGateway


def test_fake_text_gateway_is_deterministic_and_json_serializable() -> None:
    gateway = FakeTextGateway()
    request = TextRequest(
        model="gpt-5.4-mini",
        prompt="private prompt",
        response_schema={"type": "object", "required": ["title"]},
    )

    first = gateway.generate(request)
    second = gateway.generate(request)

    assert first == second
    assert first.data["schemaVersion"] == "1.0.0"
    assert first.model == "gpt-5.4-mini"
    assert first.usage == {"inputTokens": 0, "outputTokens": 0}
    assert json.loads(json.dumps(first.data)) == first.data


@pytest.mark.parametrize(
    "changed",
    [
        TextRequest("gpt-5.4", "private prompt", {"type": "object"}),
        TextRequest("gpt-5.4-mini", "different prompt", {"type": "object"}),
        TextRequest("gpt-5.4-mini", "private prompt", {"type": "array"}),
    ],
)
def test_fake_text_id_changes_when_a_meaningful_request_field_changes(
    changed: TextRequest,
) -> None:
    baseline = TextRequest("gpt-5.4-mini", "private prompt", {"type": "object"})

    assert FakeTextGateway().generate(baseline).data["fakeId"] != (
        FakeTextGateway().generate(changed).data["fakeId"]
    )


def test_request_and_result_nested_maps_are_isolated_and_immutable() -> None:
    schema = {"properties": {"title": {"type": "string"}}}
    request = TextRequest("gpt-5.4-mini", "private prompt", schema)
    schema["properties"]["title"]["type"] = "number"

    assert request.response_schema["properties"]["title"]["type"] == "string"
    with pytest.raises(TypeError):
        request.response_schema["properties"]["title"]["type"] = "boolean"

    result = FakeTextGateway().generate(request)
    with pytest.raises(TypeError):
        result.data["fakeId"] = "changed"
    with pytest.raises(TypeError):
        result.usage["inputTokens"] = 99


@pytest.mark.parametrize(
    "factory",
    [
        lambda: TextRequest("", "prompt", {}),
        lambda: TextRequest("model", "   ", {}),
        lambda: ImageRequest("", "prompt", 2, 2),
        lambda: ImageRequest("gpt-image-2", "\t", 2, 2),
    ],
)
def test_requests_reject_blank_model_or_prompt(factory) -> None:
    with pytest.raises(ValueError):
        factory()


@pytest.mark.parametrize(
    ("width", "height"),
    [(0, 1), (1, 0), (-1, 1), (1, -1), (20_000, 20_000), (True, 2)],
)
def test_image_request_rejects_unsafe_dimensions(width: int, height: int) -> None:
    with pytest.raises(ValueError, match="dimensions"):
        ImageRequest("gpt-image-2", "visual", width, height)


@pytest.mark.parametrize(
    ("width", "height"),
    [(1, 16_777_216), (16_777_216, 1), (4_097, 1), (1, 4_097)],
)
def test_image_request_rejects_an_oversized_individual_dimension(
    width: int, height: int
) -> None:
    with pytest.raises(ValueError, match="dimensions"):
        ImageRequest("gpt-image-2", "visual", width, height)


@pytest.mark.parametrize(("width", "height"), [(4_096, 1), (1, 4_096), (4_096, 4_096)])
def test_image_request_accepts_dimensions_at_the_safety_boundary(
    width: int, height: int
) -> None:
    request = ImageRequest("gpt-image-2", "visual", width, height)

    assert (request.width, request.height) == (width, height)


def test_fake_image_gateway_revalidates_dimensions_before_png_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid = object.__new__(ImageRequest)
    object.__setattr__(invalid, "model", "gpt-image-2")
    object.__setattr__(invalid, "prompt", "visual")
    object.__setattr__(invalid, "width", 1)
    object.__setattr__(invalid, "height", 16_777_216)
    allocation_started = False

    def allocation_probe(*_args: object) -> bytes:
        nonlocal allocation_started
        allocation_started = True
        return b"not a png"

    monkeypatch.setattr("app.ai.fakes._png", allocation_probe)

    with pytest.raises(ValueError, match="dimensions"):
        FakeImageGateway().generate(invalid)
    assert allocation_started is False


def test_fake_image_gateway_builds_deterministic_rgb_png_at_exact_dimensions() -> None:
    gateway = FakeImageGateway()
    request = ImageRequest("gpt-image-2", "private image prompt", 3, 2)

    first = gateway.generate(request)
    second = gateway.generate(request)

    assert first == second
    assert first.bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert first.mime_type == "image/png"
    assert (first.width, first.height, first.model) == (3, 2, "gpt-image-2")
    width, height, bit_depth, color_type, _, _, interlace = struct.unpack(
        ">IIBBBBB", first.bytes[16:29]
    )
    assert (width, height, bit_depth, color_type, interlace) == (3, 2, 8, 2, 0)
    idat_length = struct.unpack(">I", first.bytes[33:37])[0]
    assert first.bytes[37:41] == b"IDAT"
    raw = zlib.decompress(first.bytes[41 : 41 + idat_length])
    assert len(raw) == height * (1 + width * 3)
    assert raw[0] == raw[1 + width * 3] == 0


def test_image_pixels_change_when_prompt_changes() -> None:
    gateway = FakeImageGateway()
    first = gateway.generate(ImageRequest("gpt-image-2", "first", 2, 2))
    second = gateway.generate(ImageRequest("gpt-image-2", "second", 2, 2))

    assert first.bytes != second.bytes


@pytest.mark.parametrize("model", ["nano-banana", "nano-banana-2", "gpt-image-1"])
def test_image_gateway_rejects_automatic_fallback(model: str) -> None:
    with pytest.raises(ValueError, match="gpt-image-2"):
        FakeImageGateway().generate(ImageRequest(model, "visual", 2, 2))


def test_gateways_structurally_satisfy_protocols() -> None:
    assert isinstance(FakeTextGateway(), TextGateway)
    assert isinstance(FakeImageGateway(), ImageGateway)


def test_fake_text_id_ignores_mapping_insertion_order() -> None:
    first = TextRequest(
        "gpt-5.4-mini",
        "private prompt",
        {"type": "object", "properties": {"title": {"type": "string"}}},
    )
    second = TextRequest(
        "gpt-5.4-mini",
        "private prompt",
        {"properties": {"title": {"type": "string"}}, "type": "object"},
    )

    assert (
        FakeTextGateway().generate(first).data["fakeId"]
        == FakeTextGateway().generate(second).data["fakeId"]
    )
