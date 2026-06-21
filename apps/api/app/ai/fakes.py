import binascii
import hashlib
import json
import struct
import zlib
from typing import Any

from .models import (
    GeneratedImage,
    ImageRequest,
    TextRequest,
    TextResult,
    validate_image_dimensions,
)


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


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


class FakeTextGateway:
    def generate(self, request: TextRequest) -> TextResult:
        digest = _canonical_hash(
            {
                "model": request.model,
                "prompt": request.prompt,
                "responseSchema": request.response_schema,
            }
        ).hex()
        return TextResult(
            data={"schemaVersion": "1.0.0", "fakeId": digest},
            model=request.model,
            usage={"inputTokens": 0, "outputTokens": 0},
        )


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
            }
        )
        return GeneratedImage(
            bytes=_png(request.width, request.height, seed),
            mime_type="image/png",
            width=request.width,
            height=request.height,
            model=request.model,
        )
