from __future__ import annotations

import struct


def read_raster_dimensions(data: bytes) -> tuple[int, int] | None:
    """Return trusted PNG/JPEG pixel dimensions without decoding the image."""

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(data) < 24 or data[12:16] != b"IHDR":
            return None
        width, height = struct.unpack(">II", data[16:24])
        return (width, height) if width > 0 and height > 0 else None
    if data.startswith(b"\xff\xd8"):
        return _read_jpeg_dimensions(data)
    return None


def _read_jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    position = 2
    size = len(data)
    start_of_frame_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    while position + 1 < size:
        if data[position] != 0xFF:
            position += 1
            continue
        while position < size and data[position] == 0xFF:
            position += 1
        if position >= size:
            return None
        marker = data[position]
        position += 1
        if marker in {0x01, 0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if position + 2 > size:
            return None
        segment_length = int.from_bytes(data[position : position + 2], "big")
        if segment_length < 2 or position + segment_length > size:
            return None
        if marker in start_of_frame_markers:
            if segment_length < 7:
                return None
            height = int.from_bytes(data[position + 3 : position + 5], "big")
            width = int.from_bytes(data[position + 5 : position + 7], "big")
            return (width, height) if width > 0 and height > 0 else None
        position += segment_length
    return None
