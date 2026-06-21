import binascii
import hashlib
import json
import math
import re
import struct
import zlib
from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from .errors import ModelGatewayError
from .models import (
    GeneratedImage,
    ImageRequest,
    TextRequest,
    TextResult,
    validate_image_dimensions,
)


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_SCHEMA_DEPTH = 8
MAX_SCHEMA_PROPERTIES = 64
MAX_FAKE_ARRAY_ITEMS = 16


def _canonical_hash(payload: dict[str, Any]) -> bytes:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).digest()


def _chunk(kind: bytes, payload: bytes) -> bytes:
    crc = binascii.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def _png(width: int, height: int, seed: bytes) -> bytes:
    pixel = seed[:3]
    row = b"\x00" + pixel * width
    compressor = zlib.compressobj()
    compressed = bytearray()
    for _ in range(height):
        compressed.extend(compressor.compress(row))
    compressed.extend(compressor.flush())
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", bytes(compressed))
        + _chunk(b"IEND", b"")
    )


def _schema_error() -> ModelGatewayError:
    return ModelGatewayError(
        code="invalid_response_schema",
        message="The requested response format is unavailable.",
        retryable=False,
    )


def _candidate_string(schema: Mapping[str, Any], preferred: str = "") -> str:
    minimum = schema.get("minLength", 0)
    maximum = schema.get("maxLength")
    if not isinstance(minimum, int) or isinstance(minimum, bool):
        raise ValueError
    if maximum is not None and (
        not isinstance(maximum, int) or isinstance(maximum, bool) or minimum > maximum
    ):
        raise ValueError
    candidates = [preferred, "", "x", "a", "0"]
    pattern = schema.get("pattern")
    if pattern is not None:
        if not isinstance(pattern, str):
            raise ValueError
        compiled = re.compile(pattern)
        if pattern.isalnum():
            candidates.insert(0, pattern)
    else:
        compiled = None
    for seed in candidates:
        value = seed
        if len(value) < minimum:
            value += "x" * (minimum - len(value))
        if maximum is not None and len(value) > maximum:
            value = value[:maximum]
        if len(value) >= minimum and (compiled is None or compiled.search(value)):
            return value
    raise ValueError


def _candidate_number(schema: Mapping[str, Any], *, integer: bool) -> int | float:
    lower = schema.get("minimum", 0)
    if "exclusiveMinimum" in schema:
        lower = max(lower, schema["exclusiveMinimum"] + (1 if integer else 0.5))
    if not isinstance(lower, (int, float)) or isinstance(lower, bool) or not math.isfinite(lower):
        raise ValueError
    value: int | float = math.ceil(lower) if integer else float(lower)
    multiple = schema.get("multipleOf")
    if multiple is not None:
        if (
            not isinstance(multiple, (int, float))
            or isinstance(multiple, bool)
            or not math.isfinite(multiple)
            or multiple <= 0
        ):
            raise ValueError
        value = math.ceil(value / multiple) * multiple
        if integer:
            if not float(value).is_integer():
                raise ValueError
            value = int(value)
    maximum = schema.get("maximum")
    exclusive_maximum = schema.get("exclusiveMaximum")
    if maximum is not None and value > maximum:
        raise ValueError
    if exclusive_maximum is not None and value >= exclusive_maximum:
        raise ValueError
    return value


def _synthesize(
    schema: Any,
    *,
    digest: str,
    depth: int = 0,
    preferred: str = "",
) -> Any:
    if depth > MAX_SCHEMA_DEPTH or schema is False:
        raise ValueError
    if schema is True:
        return preferred
    if not isinstance(schema, Mapping):
        raise ValueError
    if "const" in schema:
        return schema["const"]
    if "default" in schema:
        return schema["default"]
    enum = schema.get("enum")
    if enum is not None:
        if not isinstance(enum, (list, tuple)) or not enum:
            raise ValueError
        return enum[0]

    kind = schema.get("type")
    if isinstance(kind, (list, tuple)):
        last_error: ValueError | None = None
        for option in kind:
            try:
                return _synthesize(
                    {**schema, "type": option},
                    digest=digest,
                    depth=depth,
                    preferred=preferred,
                )
            except ValueError as error:
                last_error = error
        raise last_error or ValueError()
    if kind is None:
        kind = "object" if "properties" in schema or "required" in schema else "string"

    if kind == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, Mapping) or len(properties) > MAX_SCHEMA_PROPERTIES:
            raise ValueError
        if not isinstance(required, (list, tuple)) or len(required) > MAX_SCHEMA_PROPERTIES:
            raise ValueError
        additional = schema.get("additionalProperties", True)
        result: dict[str, Any] = {}
        names = list(dict.fromkeys([*required, *[n for n in ("schemaVersion", "fakeId") if n in properties]]))
        if any(not isinstance(name, str) for name in names):
            raise ValueError
        for name in names:
            child_schema = properties.get(name, additional)
            child_preferred = (
                "1.0.0" if name == "schemaVersion" else digest if name == "fakeId" else ""
            )
            result[name] = _synthesize(
                child_schema,
                digest=digest,
                depth=depth + 1,
                preferred=child_preferred,
            )
        if additional is not False:
            if "schemaVersion" not in result and "schemaVersion" not in properties:
                result["schemaVersion"] = "1.0.0"
            if "fakeId" not in result and "fakeId" not in properties:
                result["fakeId"] = digest
        return result
    if kind == "array":
        count = schema.get("minItems", 0)
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
            or count > MAX_FAKE_ARRAY_ITEMS
        ):
            raise ValueError
        item_schema = schema.get("items", True)
        return [
            _synthesize(item_schema, digest=digest, depth=depth + 1) for _ in range(count)
        ]
    if kind == "string":
        return _candidate_string(schema, preferred)
    if kind == "integer":
        return _candidate_number(schema, integer=True)
    if kind == "number":
        return _candidate_number(schema, integer=False)
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    raise ValueError


class FakeTextGateway:
    def generate(self, request: TextRequest) -> TextResult:
        digest = _canonical_hash(
            {
                "model": request.model,
                "prompt": request.prompt,
                "responseSchema": request.response_schema,
                "timeoutSeconds": request.timeout_seconds,
                "maxAttempts": request.max_attempts,
            }
        ).hex()
        try:
            schema = dict(request.response_schema)
            Draft202012Validator.check_schema(schema)
            data = _synthesize(schema, digest=digest)
            Draft202012Validator(schema).validate(data)
            return TextResult(
                data=data,
                model=request.model,
                usage={"inputTokens": 0, "outputTokens": 0},
            )
        except (SchemaError, ValidationError, TypeError, ValueError, re.error):
            raise _schema_error() from None


class FakeImageGateway:
    def generate(self, request: ImageRequest) -> GeneratedImage:
        if request.model != "gpt-image-2":
            raise ValueError(
                "image model must be gpt-image-2; fallback requires explicit consent"
            )
        validate_image_dimensions(request.width, request.height)
        seed = _canonical_hash(
            {
                "model": request.model,
                "prompt": request.prompt,
                "width": request.width,
                "height": request.height,
                "timeoutSeconds": request.timeout_seconds,
                "maxAttempts": request.max_attempts,
            }
        )
        return GeneratedImage(
            bytes=_png(request.width, request.height, seed),
            mime_type="image/png",
            width=request.width,
            height=request.height,
            model=request.model,
        )
