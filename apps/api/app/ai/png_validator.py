from __future__ import annotations

import binascii
import struct
import zlib

from .models import validate_image_dimensions


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DEFAULT_MAX_FILE_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_CHUNK_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_CHUNKS = 4_096


class PNGValidationError(ValueError):
    """Internal PNG rejection reason; callers must map this at trust boundaries."""


def _reject(reason: str) -> None:
    raise PNGValidationError(reason)


def _positive_limit(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def validate_png_bytes(
    data: bytes,
    *,
    expected_width: int,
    expected_height: int,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_chunk_bytes: int = DEFAULT_MAX_CHUNK_BYTES,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
) -> None:
    """Validate the strict PNG subset accepted from image model providers."""

    if not isinstance(data, bytes):
        raise TypeError("PNG data must be bytes")
    _positive_limit(max_file_bytes, "max_file_bytes")
    _positive_limit(max_chunk_bytes, "max_chunk_bytes")
    _positive_limit(max_chunks, "max_chunks")
    validate_image_dimensions(expected_width, expected_height)
    if len(data) > max_file_bytes:
        _reject("file exceeds byte budget")
    if len(data) < len(PNG_SIGNATURE) or data[:8] != PNG_SIGNATURE:
        _reject("invalid PNG signature")

    offset = len(PNG_SIGNATURE)
    chunk_count = 0
    saw_ihdr = False
    saw_idat = False
    idat_ended = False
    saw_iend = False
    saw_plte = False
    color_type: int | None = None
    data_view = memoryview(data)
    compressed_parts: list[memoryview] = []
    compressed_bytes = 0

    while offset < len(data):
        chunk_count += 1
        if chunk_count > max_chunks:
            _reject("chunk count exceeds budget")
        if len(data) - offset < 12:
            _reject("truncated chunk framing")

        length = int.from_bytes(data[offset : offset + 4], "big")
        kind = data[offset + 4 : offset + 8]
        if length > max_chunk_bytes:
            _reject("chunk exceeds byte budget")
        if any(not (65 <= byte <= 90 or 97 <= byte <= 122) for byte in kind):
            _reject("invalid chunk type")
        if not 65 <= kind[2] <= 90:
            _reject("invalid reserved chunk-type bit")

        remaining = len(data) - (offset + 8)
        if remaining < length + 4:
            _reject("truncated chunk payload")
        payload_start = offset + 8
        payload_end = payload_start + length
        payload = data_view[payload_start:payload_end]
        stored_crc = int.from_bytes(data[payload_end : payload_end + 4], "big")
        actual_crc = binascii.crc32(payload, binascii.crc32(kind)) & 0xFFFFFFFF
        if stored_crc != actual_crc:
            _reject("chunk CRC mismatch")
        offset = payload_end + 4

        if not saw_ihdr and kind != b"IHDR":
            _reject("IHDR must be first")
        if saw_iend:
            _reject("data found after IEND")

        if kind == b"IHDR":
            if saw_ihdr:
                _reject("duplicate IHDR")
            if chunk_count != 1 or length != 13:
                _reject("invalid IHDR placement or length")
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if width < 1 or height < 1:
                _reject("zero image dimension")
            if width != expected_width or height != expected_height:
                _reject("image dimensions do not match request")
            if bit_depth != 8 or color_type not in (2, 6):
                _reject("unsupported PNG pixel format")
            if compression != 0 or filtering != 0 or interlace != 0:
                _reject("unsupported PNG encoding method")
            saw_ihdr = True
        elif kind == b"PLTE":
            if saw_plte or saw_idat:
                _reject("invalid PLTE placement")
            if length < 3 or length > 768 or length % 3:
                _reject("invalid PLTE length")
            saw_plte = True
        elif kind == b"IDAT":
            if idat_ended:
                _reject("IDAT chunks must be consecutive")
            saw_idat = True
            compressed_bytes += length
            if compressed_bytes > max_file_bytes:
                _reject("compressed image exceeds budget")
            compressed_parts.append(payload)
        elif kind == b"IEND":
            if length != 0 or not saw_idat:
                _reject("invalid IEND")
            saw_iend = True
            if offset != len(data):
                _reject("IEND must be final")
        else:
            if 65 <= kind[0] <= 90:
                _reject("unknown critical chunk")
            if saw_idat:
                idat_ended = True

    if not saw_ihdr or not saw_idat or not saw_iend or color_type is None:
        _reject("missing required PNG chunk")

    bytes_per_pixel = 3 if color_type == 2 else 4
    row_size = 1 + expected_width * bytes_per_pixel
    expected_size = expected_height * row_size
    inflater = zlib.decompressobj()
    raw_parts: list[bytes] = []
    raw_size = 0
    try:
        for compressed_part in compressed_parts:
            raw_part = inflater.decompress(compressed_part, expected_size - raw_size + 1)
            raw_parts.append(raw_part)
            raw_size += len(raw_part)
            if raw_size > expected_size or inflater.unconsumed_tail:
                _reject("decompressed image exceeds budget")
        final_part = inflater.flush(expected_size - raw_size + 1)
        raw_parts.append(final_part)
        raw_size += len(final_part)
    except zlib.error:
        _reject("invalid zlib stream")
    if raw_size != expected_size:
        _reject("unexpected decompressed image size")
    if not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
        _reject("incomplete or trailing zlib stream")
    raw = b"".join(raw_parts)
    for row in range(expected_height):
        if raw[row * row_size] > 4:
            _reject("invalid scanline filter")
