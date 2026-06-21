import struct
import zlib

import pytest

from app.ai.fakes import FakeImageGateway
from app.ai.models import ImageRequest
from app.ai.png_validator import PNGValidationError, validate_png_bytes
from png_factory import PNG_SIGNATURE, assemble, chunk, ihdr, png


def test_exposes_validate_png_bytes_as_the_public_validator() -> None:
    validate_png_bytes(png(2, 1), expected_width=2, expected_height=1)


@pytest.mark.parametrize("color_type", [2, 6])
@pytest.mark.parametrize("idat_parts", [1, 3])
def test_accepts_supported_pngs(color_type: int, idat_parts: int) -> None:
    validate_png_bytes(png(3, 2, color_type=color_type, idat_parts=idat_parts), expected_width=3, expected_height=2)


@pytest.mark.parametrize("color_type", [2, 6])
@pytest.mark.parametrize("entry_count", [1, 256])
def test_accepts_valid_optional_plte_for_truecolor_pngs(color_type: int, entry_count: int) -> None:
    valid = png(2, 1, color_type=color_type)
    with_palette = valid[:33] + chunk(b"PLTE", b"\x00\x00\x00" * entry_count) + valid[33:]

    validate_png_bytes(with_palette, expected_width=2, expected_height=1)


@pytest.mark.parametrize("payload", [b"", b"\x00", b"\x00\x00", b"\x00" * 4, b"\x00" * 771])
def test_rejects_plte_with_invalid_entry_count_or_length(payload: bytes) -> None:
    valid = png(2, 1)
    malformed = valid[:33] + chunk(b"PLTE", payload) + valid[33:]

    with pytest.raises(PNGValidationError):
        validate_png_bytes(malformed, expected_width=2, expected_height=1)


def test_requires_plte_after_ihdr_before_idat_at_most_once() -> None:
    compressed = chunk(b"IDAT", zlib.compress(b"\x00" + b"\x00" * 6))
    palette = chunk(b"PLTE", b"\x00\x00\x00")
    cases = [
        assemble(palette, ihdr(2, 1), compressed, chunk(b"IEND")),
        assemble(ihdr(2, 1), palette, palette, compressed, chunk(b"IEND")),
        assemble(ihdr(2, 1), compressed, palette, chunk(b"IEND")),
    ]

    for bad in cases:
        with pytest.raises(PNGValidationError):
            validate_png_bytes(bad, expected_width=2, expected_height=1)


def test_accepts_fake_image_gateway_output() -> None:
    request = ImageRequest("gpt-image-2", "private", 3, 2)
    image = FakeImageGateway().generate(request)
    validate_png_bytes(image.bytes, expected_width=3, expected_height=2)


@pytest.mark.parametrize("filter_byte", range(5))
def test_accepts_every_png_filter_type(filter_byte: int) -> None:
    validate_png_bytes(png(2, 1, filters=(filter_byte,)), expected_width=2, expected_height=1)


def test_rejects_unknown_filter_type() -> None:
    with pytest.raises(PNGValidationError):
        validate_png_bytes(png(2, 1, filters=(5,)), expected_width=2, expected_height=1)


@pytest.mark.parametrize(
    "bad",
    [b"", b"not png", PNG_SIGNATURE[:-1] + b"x" + png()[8:]],
)
def test_requires_exact_signature(bad: bytes) -> None:
    with pytest.raises(PNGValidationError):
        validate_png_bytes(bad, expected_width=2, expected_height=2)


def test_requires_ihdr_first_once_and_exact_length() -> None:
    valid_idat = chunk(b"IDAT", zlib.compress(b"\x00" + b"\x00" * 6))
    cases = [
        assemble(valid_idat, ihdr(2, 1), chunk(b"IEND")),
        assemble(ihdr(2, 1), ihdr(2, 1), valid_idat, chunk(b"IEND")),
        assemble(chunk(b"IHDR", b"x" * 12), valid_idat, chunk(b"IEND")),
        assemble(valid_idat, chunk(b"IEND")),
    ]
    for bad in cases:
        with pytest.raises(PNGValidationError):
            validate_png_bytes(bad, expected_width=2, expected_height=1)


def test_requires_idat_after_ihdr_before_iend_and_consecutive() -> None:
    compressed = zlib.compress(b"\x00" + b"\x00" * 6)
    cases = [
        assemble(ihdr(2, 1), chunk(b"IEND")),
        assemble(ihdr(2, 1), chunk(b"IEND"), chunk(b"IDAT", compressed)),
        assemble(ihdr(2, 1), chunk(b"IDAT", compressed[:2]), chunk(b"tEXt", b"ok"), chunk(b"IDAT", compressed[2:]), chunk(b"IEND")),
    ]
    for bad in cases:
        with pytest.raises(PNGValidationError):
            validate_png_bytes(bad, expected_width=2, expected_height=1)


def test_requires_one_empty_final_iend_with_no_trailing_bytes() -> None:
    compressed = chunk(b"IDAT", zlib.compress(b"\x00" + b"\x00" * 6))
    cases = [
        assemble(ihdr(2, 1), compressed),
        assemble(ihdr(2, 1), compressed, chunk(b"IEND", b"x")),
        assemble(ihdr(2, 1), compressed, chunk(b"IEND"), chunk(b"IEND")),
        assemble(ihdr(2, 1), compressed, chunk(b"IEND"), trailing=b"secret"),
    ]
    for bad in cases:
        with pytest.raises(PNGValidationError):
            validate_png_bytes(bad, expected_width=2, expected_height=1)


def test_rejects_bad_crc_truncated_chunk_and_invalid_chunk_type() -> None:
    cases = [
        assemble(ihdr(2, 1), chunk(b"IDAT", zlib.compress(b"\x00" + b"\x00" * 6), crc=0), chunk(b"IEND")),
        png(2, 1)[:-2],
        assemble(ihdr(2, 1), chunk(b"ID@T", b"data"), chunk(b"IEND")),
    ]
    for bad in cases:
        with pytest.raises(PNGValidationError):
            validate_png_bytes(bad, expected_width=2, expected_height=1)


def test_rejects_unknown_critical_chunk_but_allows_ancillary_chunk() -> None:
    valid = png(2, 1)
    injected = valid[:33] + chunk(b"vpAg", b"metadata") + valid[33:]
    validate_png_bytes(injected, expected_width=2, expected_height=1)
    with pytest.raises(PNGValidationError):
        validate_png_bytes(valid[:33] + chunk(b"VPAG", b"critical") + valid[33:], expected_width=2, expected_height=1)


@pytest.mark.parametrize(
    "header",
    [
        ihdr(2, 1, bit_depth=16),
        ihdr(2, 1, color_type=0),
        ihdr(2, 1, color_type=3),
        ihdr(2, 1, compression=1),
        ihdr(2, 1, filter_method=1),
        ihdr(2, 1, interlace=1),
        ihdr(0, 1),
        ihdr(2, 0),
    ],
)
def test_rejects_unsupported_ihdr_fields(header: bytes) -> None:
    raw = b"\x00" + b"\x00" * 6
    with pytest.raises(PNGValidationError):
        validate_png_bytes(assemble(header, chunk(b"IDAT", zlib.compress(raw)), chunk(b"IEND")), expected_width=2, expected_height=1)


def test_requires_exact_requested_dimensions_before_decompression() -> None:
    with pytest.raises(PNGValidationError):
        validate_png_bytes(png(3, 2), expected_width=2, expected_height=2)


@pytest.mark.parametrize("compressed", [b"corrupt", zlib.compress(b"\x00" + b"\x00" * 6)[:-1]])
def test_rejects_corrupt_or_truncated_zlib_stream(compressed: bytes) -> None:
    bad = assemble(ihdr(2, 1), chunk(b"IDAT", compressed), chunk(b"IEND"))
    with pytest.raises(PNGValidationError):
        validate_png_bytes(bad, expected_width=2, expected_height=1)


def test_rejects_trailing_or_concatenated_zlib_streams() -> None:
    stream = zlib.compress(b"\x00" + b"\x00" * 6)
    for compressed in (stream + b"junk", stream + stream):
        with pytest.raises(PNGValidationError):
            validate_png_bytes(assemble(ihdr(2, 1), chunk(b"IDAT", compressed), chunk(b"IEND")), expected_width=2, expected_height=1)


def test_rejects_wrong_decompressed_length_and_decompression_bomb() -> None:
    for raw in (b"\x00" * 6, b"\x00" * 8, b"\x00" * 1_000_000):
        with pytest.raises(PNGValidationError):
            validate_png_bytes(assemble(ihdr(2, 1), chunk(b"IDAT", zlib.compress(raw)), chunk(b"IEND")), expected_width=2, expected_height=1)


def test_enforces_file_chunk_and_chunk_count_budgets() -> None:
    valid = png(2, 1)
    with pytest.raises(PNGValidationError):
        validate_png_bytes(valid, expected_width=2, expected_height=1, max_file_bytes=len(valid) - 1)
    with pytest.raises(PNGValidationError):
        validate_png_bytes(valid, expected_width=2, expected_height=1, max_chunk_bytes=12)
    many = valid[:33] + b"".join(chunk(b"tEXt", b"") for _ in range(5)) + valid[33:]
    with pytest.raises(PNGValidationError):
        validate_png_bytes(many, expected_width=2, expected_height=1, max_chunks=4)


def test_requires_bytes_and_valid_limits() -> None:
    with pytest.raises(TypeError):
        validate_png_bytes(bytearray(png()), expected_width=2, expected_height=2)
    with pytest.raises(ValueError):
        validate_png_bytes(png(), expected_width=2, expected_height=2, max_chunks=0)


def test_length_prefix_cannot_claim_bytes_past_end() -> None:
    bad = PNG_SIGNATURE + struct.pack(">I", 0xFFFFFFFF) + b"IDAT"
    with pytest.raises(PNGValidationError):
        validate_png_bytes(bad, expected_width=2, expected_height=2)
