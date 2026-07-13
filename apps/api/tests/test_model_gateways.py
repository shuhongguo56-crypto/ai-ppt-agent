import json
import struct
import zlib

import pytest
import httpx
from jsonschema import Draft202012Validator

from app.ai.cascade import CascadeTextGateway, TextProviderCandidate
from app.ai.fakes import FakeImageGateway, FakeTextGateway
from app.ai.errors import ModelGatewayError
from app.ai.image_http import PollinationsImageGateway
from app.ai.models import ImageRequest, TextRequest
from app.ai.ollama import OllamaTextGateway
from app.ai.openai import OpenAITextGateway
from app.ai.protocols import ImageGateway, TextGateway
from app.config import Settings
from app.main import _image_candidates


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
    assert first.data["title"] == ""
    assert first.data["schemaVersion"] == "1.0.0"
    assert first.model == "gpt-5.4-mini"
    assert first.usage == {"inputTokens": 0, "outputTokens": 0}
    assert json.loads(json.dumps(first.data)) == first.data


@pytest.mark.parametrize(
    "changed",
    [
        TextRequest("gpt-5.4", "private prompt", {"type": "object"}),
        TextRequest("gpt-5.4-mini", "different prompt", {"type": "object"}),
        TextRequest(
            "gpt-5.4-mini",
            "private prompt",
            {"type": "object", "properties": {"title": {"type": "string"}}},
        ),
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


def test_fake_image_gateway_draws_prompt_aware_non_solid_visuals() -> None:
    image = FakeImageGateway().generate(
        ImageRequest(
            "gpt-image-2",
            "Image type: course_review_atmosphere. university classroom learning review atmosphere",
            64,
            36,
        )
    )

    idat_length = struct.unpack(">I", image.bytes[33:37])[0]
    raw = zlib.decompress(image.bytes[41 : 41 + idat_length])
    pixels = set()
    stride = 1 + image.width * 3
    for row in range(image.height):
        start = row * stride + 1
        for column in range(image.width):
            offset = start + column * 3
            pixels.add(bytes(raw[offset : offset + 3]))

    assert len(pixels) > 12


def test_image_pixels_change_when_prompt_changes() -> None:
    gateway = FakeImageGateway()
    first = gateway.generate(ImageRequest("gpt-image-2", "first", 2, 2))
    second = gateway.generate(ImageRequest("gpt-image-2", "second", 2, 2))

    assert first.bytes != second.bytes


def test_pollinations_image_gateway_downloads_free_flux_image(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def generated_image(*args: object, **kwargs: object) -> httpx.Response:
        captured["url"] = args[0]
        captured["params"] = kwargs["params"]
        return httpx.Response(
            200,
            headers={"content-type": "image/jpeg"},
            content=b"\xff\xd8\xff\xe0free-image",
        )

    monkeypatch.setattr("app.ai.image_http.httpx.get", generated_image)

    image = PollinationsImageGateway(model="flux").generate(
        ImageRequest("flux", "premium presentation visual", 1024, 576)
    )

    assert image.mime_type == "image/jpeg"
    assert image.bytes.startswith(b"\xff\xd8\xff")
    assert image.model == "pollinations:flux"
    assert "image.pollinations.ai/prompt/" in str(captured["url"])
    assert captured["params"] == {
        "width": 1024,
        "height": 576,
        "model": "flux",
        "enhance": "true",
        "private": "true",
        "nologo": "true",
        "referrer": "ai-ppt-agent",
    }


def test_pollinations_image_gateway_keeps_url_prompt_short_for_batch_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def generated_image(*args: object, **kwargs: object) -> httpx.Response:
        captured["url"] = args[0]
        return httpx.Response(
            200,
            headers={"content-type": "image/jpeg"},
            content=b"\xff\xd8\xff\xe0free-image",
        )

    monkeypatch.setattr("app.ai.image_http.httpx.get", generated_image)
    long_prompt = "premium keynote slide visual " + ("layered cinematic depth " * 80)

    PollinationsImageGateway(model="flux").generate(
        ImageRequest("flux", long_prompt, 1024, 576)
    )

    encoded_prompt = str(captured["url"]).rsplit("/prompt/", 1)[1]

    assert len(encoded_prompt) <= 700
    assert encoded_prompt.startswith("premium%20keynote%20slide%20visual")


def test_pollinations_image_gateway_retries_temporary_provider_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def generated_image(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, content=b"busy")
        return httpx.Response(
            200,
            headers={"content-type": "image/jpeg"},
            content=b"\xff\xd8\xff\xe0free-image",
        )

    monkeypatch.setattr("app.ai.image_http.httpx.get", generated_image)

    image = PollinationsImageGateway(model="flux").generate(
        ImageRequest("flux", "premium presentation visual", 1024, 576, max_attempts=2)
    )

    assert attempts == 2
    assert image.mime_type == "image/jpeg"


def test_pollinations_candidate_keeps_free_image_retry_budget() -> None:
    candidates = _image_candidates(
        Settings(
            model_backend="cascade",
            model_retry_count=1,
            pollinations_image_enabled=True,
        )
    )
    pollinations = next(candidate for candidate in candidates if candidate.name == "pollinations-free")

    assert pollinations.gateway._max_attempts == 2


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


def test_fake_text_output_independently_validates_against_schema() -> None:
    schema = {
        "type": "object",
        "required": ["title", "slides", "published", "score", "nothing"],
        "properties": {
            "title": {"type": "string", "minLength": 2},
            "slides": {
                "type": "array",
                "minItems": 2,
                "items": {"type": "integer", "minimum": 3},
            },
            "published": {"type": "boolean"},
            "score": {"type": "number", "minimum": 1.5},
            "nothing": {"type": "null"},
        },
        "additionalProperties": False,
    }

    result = FakeTextGateway().generate(TextRequest("gpt-5.4-mini", "prompt", schema))

    Draft202012Validator(schema).validate(result.data)


def test_ollama_text_gateway_returns_validated_structured_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(url: str, json: dict, timeout: float) -> httpx.Response:
        assert url == "http://127.0.0.1:11434/api/generate"
        assert json["model"] == "qwen2.5:7b"
        assert json["stream"] is False
        assert json["format"]["required"] == ["title"]
        assert "private prompt" in json["prompt"]
        assert timeout == 12
        return httpx.Response(
            200,
            json={
                "response": '{"title":"Deck"}',
                "prompt_eval_count": 11,
                "eval_count": 3,
            },
        )

    monkeypatch.setattr("app.ai.ollama.httpx.post", fake_post)
    gateway = OllamaTextGateway(model="qwen2.5:7b")
    result = gateway.generate(
        TextRequest(
            "ignored-provider-model",
            "private prompt",
            {
                "type": "object",
                "required": ["title"],
                "properties": {"title": {"const": "Deck"}},
                "additionalProperties": False,
            },
            timeout_seconds=12,
        )
    )

    assert result.data == {"title": "Deck"}
    assert result.model == "qwen2.5:7b"
    assert result.usage == {"inputTokens": 11, "outputTokens": 3}


def test_openai_compatible_gateway_supports_json_object_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(url: str, headers: dict, json: dict, timeout: float) -> httpx.Response:
        assert url == "http://127.0.0.1:1234/v1/chat/completions"
        assert "Authorization" not in headers
        assert json["response_format"] == {"type": "json_object"}
        assert "JSON Schema" in json["messages"][0]["content"]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"title":"Deck"}'}}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 2},
            },
        )

    monkeypatch.setattr("app.ai.openai.httpx.post", fake_post)
    gateway = OpenAITextGateway(
        api_key=None,
        base_url="http://127.0.0.1:1234/v1",
        response_format_mode="json_object",
    )

    result = gateway.generate(
        TextRequest(
            "local-model",
            "private prompt",
            {
                "type": "object",
                "required": ["title"],
                "properties": {"title": {"const": "Deck"}},
                "additionalProperties": False,
            },
        )
    )

    assert result.data == {"title": "Deck"}
    assert result.model == "local-model"
    assert result.usage == {"inputTokens": 9, "outputTokens": 2}


def test_cascade_text_gateway_falls_back_to_next_provider() -> None:
    class BrokenGateway:
        def generate(self, _request: TextRequest):
            raise ModelGatewayError("model_request_failed", "provider failed", True)

    cascade = CascadeTextGateway(
        [
            TextProviderCandidate("broken", BrokenGateway(), model="bad-model"),
            TextProviderCandidate("fallback", FakeTextGateway(), model="gpt-5.4-mini"),
        ]
    )

    result = cascade.generate(
        TextRequest(
            "ignored",
            "private prompt",
            {"type": "object", "required": ["fakeId"], "properties": {"fakeId": {"type": "string"}}},
        )
    )

    assert result.model.startswith("fallback:")
    assert result.data["fakeId"]


def test_ollama_text_gateway_rejects_invalid_structured_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(*_args: object, **_kwargs: object) -> httpx.Response:
        return httpx.Response(200, json={"response": '{"title":"Wrong"}'})

    monkeypatch.setattr("app.ai.ollama.httpx.post", fake_post)

    with pytest.raises(ModelGatewayError) as captured:
        OllamaTextGateway().generate(
            TextRequest(
                "model",
                "secret prompt",
                {
                    "type": "object",
                    "required": ["title"],
                    "properties": {"title": {"const": "Deck"}},
                    "additionalProperties": False,
                },
            )
        )

    assert captured.value.code == "model_output_invalid"
    assert "secret" not in str(captured.value)


def test_ollama_health_reports_missing_service(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(*_args: object, **_kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("app.ai.ollama.httpx.get", fake_get)

    health = OllamaTextGateway(model="qwen2.5:7b").health()

    assert health.service_ready is False
    assert health.model_ready is False
    assert "Start Ollama" in health.message


def test_ollama_health_reports_missing_and_ready_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_model(*_args: object, **_kwargs: object) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "llama3.2:3b"}]})

    monkeypatch.setattr("app.ai.ollama.httpx.get", missing_model)
    missing = OllamaTextGateway(model="qwen2.5:7b").health()
    assert missing.service_ready is True
    assert missing.model_ready is False
    assert "ollama pull qwen2.5:7b" in missing.message

    def ready_model(*_args: object, **_kwargs: object) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "qwen2.5:7b"}]})

    monkeypatch.setattr("app.ai.ollama.httpx.get", ready_model)
    ready = OllamaTextGateway(model="qwen2.5:7b").health()
    assert ready.service_ready is True
    assert ready.model_ready is True


def test_strict_text_schema_receives_no_fake_metadata() -> None:
    schema = {
        "type": "object",
        "required": ["title"],
        "properties": {"title": {"const": "Deck"}},
        "additionalProperties": False,
    }

    result = FakeTextGateway().generate(TextRequest("gpt-5.4-mini", "prompt", schema))

    assert result.data == {"title": "Deck"}


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "not-a-json-type"},
        {
            "type": "object",
            "required": ["title"],
            "properties": {},
            "additionalProperties": False,
        },
        {"type": "string", "pattern": "(?!)"},
        {"type": "integer", "minimum": 2, "maximum": 1},
    ],
)
def test_invalid_or_unsatisfiable_text_schema_returns_safe_error(schema) -> None:
    with pytest.raises(ModelGatewayError) as captured:
        FakeTextGateway().generate(TextRequest("gpt-5.4-mini", "secret prompt", schema))

    assert captured.value.code == "invalid_response_schema"
    assert captured.value.retryable is False
    assert "secret" not in str(captured.value)
    assert "pattern" not in str(captured.value)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: TextRequest("model", "prompt", {}, timeout_seconds=0),
        lambda: TextRequest("model", "prompt", {}, timeout_seconds=float("inf")),
        lambda: TextRequest("model", "prompt", {}, timeout_seconds=301),
        lambda: TextRequest("model", "prompt", {}, max_attempts=0),
        lambda: TextRequest("model", "prompt", {}, max_attempts=4),
        lambda: ImageRequest("gpt-image-2", "prompt", 1, 1, timeout_seconds=0),
        lambda: ImageRequest("gpt-image-2", "prompt", 1, 1, max_attempts=4),
    ],
)
def test_requests_reject_invalid_execution_controls(factory) -> None:
    with pytest.raises(ValueError):
        factory()


def test_execution_controls_have_defaults_and_affect_fake_outputs() -> None:
    text_default = TextRequest("model", "prompt", {"type": "object"})
    text_changed = TextRequest(
        "model", "prompt", {"type": "object"}, timeout_seconds=31, max_attempts=2
    )
    image_default = ImageRequest("gpt-image-2", "prompt", 1, 1)
    image_changed = ImageRequest(
        "gpt-image-2", "prompt", 1, 1, timeout_seconds=31, max_attempts=2
    )

    assert (text_default.timeout_seconds, text_default.max_attempts) == (30, 1)
    assert (image_default.timeout_seconds, image_default.max_attempts) == (30, 1)
    assert FakeTextGateway().generate(text_default) != FakeTextGateway().generate(
        text_changed
    )
    assert FakeImageGateway().generate(image_default).bytes != FakeImageGateway().generate(
        image_changed
    ).bytes
