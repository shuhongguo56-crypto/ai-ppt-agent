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


def _png(width: int, height: int, seed: bytes, prompt: str = "") -> bytes:
    visual_type = _prompt_visual_type(prompt)
    bg_a = _rgb_from_seed(seed, 0, floor=24, span=70)
    bg_b = _rgb_from_seed(seed, 3, floor=52, span=118)
    accent = _rgb_from_seed(seed, 6, floor=96, span=142)
    support = _rgb_from_seed(seed, 9, floor=64, span=126)
    ink = (246, 248, 252)
    canvas = _background_canvas(width, height, bg_a, bg_b)
    _draw_common_atmosphere(canvas, width, height, accent, support)
    _draw_prompt_visual(canvas, width, height, visual_type, accent, support, ink)
    compressor = zlib.compressobj()
    compressed = compressor.compress(bytes(canvas))
    compressed += compressor.flush()
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", bytes(compressed))
        + _chunk(b"IEND", b"")
    )


def _background_canvas(
    width: int,
    height: int,
    bg_a: tuple[int, int, int],
    bg_b: tuple[int, int, int],
) -> bytearray:
    canvas = bytearray()
    left_width = max(1, int(width * 0.54))
    mid_width = max(0, int(width * 0.18))
    right_width = max(0, width - left_width - mid_width)
    for y in range(height):
        vertical = y / max(height - 1, 1)
        left = _mix(bg_a, bg_b, 0.10 + vertical * 0.14)
        mid = _mix(bg_a, bg_b, 0.22 + vertical * 0.16)
        right = _mix(bg_a, bg_b, 0.40 + vertical * 0.20)
        canvas.extend(bytes([0]) + bytes(left) * left_width + bytes(mid) * mid_width + bytes(right) * right_width)
    return canvas


def _draw_common_atmosphere(
    canvas: bytearray,
    width: int,
    height: int,
    accent: tuple[int, int, int],
    support: tuple[int, int, int],
) -> None:
    _draw_circle(canvas, width, height, 0.10 * width, 0.78 * height, 0.24 * min(width, height), support, 0.28)
    _draw_circle(canvas, width, height, 0.86 * width, 0.22 * height, 0.22 * min(width, height), accent, 0.22)
    _draw_round_rect(canvas, width, height, 0.58 * width, 0.10 * height, 0.91 * width, 0.82 * height, 0.050 * width, (248, 250, 246), 0.08)
    _draw_round_rect(canvas, width, height, 0.60 * width, 0.13 * height, 0.89 * width, 0.79 * height, 0.044 * width, (10, 18, 24), 0.10)
    _draw_line(canvas, width, height, -0.05 * width, 0.30 * height, 1.08 * width, 0.06 * height, 0.018 * min(width, height), (248, 250, 246), 0.11)
    _draw_line(canvas, width, height, 0.08 * width, 0.86 * height, 0.92 * width, 0.74 * height, 0.006 * min(width, height), accent, 0.24)


def _draw_prompt_visual(
    canvas: bytearray,
    width: int,
    height: int,
    visual_type: str,
    accent: tuple[int, int, int],
    support: tuple[int, int, int],
    ink: tuple[int, int, int],
) -> None:
    if visual_type == "course_review_atmosphere":
        _draw_course_visual(canvas, width, height, accent, support, ink)
    elif visual_type == "business_scene":
        _draw_business_visual(canvas, width, height, accent, support, ink)
    elif visual_type == "classical_element":
        _draw_classical_visual(canvas, width, height, accent, support, ink)
    elif visual_type == "product_showcase":
        _draw_product_visual(canvas, width, height, accent, support, ink)
    elif visual_type == "icon_illustration":
        _draw_icon_visual(canvas, width, height, accent, support, ink)
    elif visual_type == "data_visual":
        _draw_data_visual(canvas, width, height, accent, support, ink)
    elif visual_type == "thesis_concept":
        _draw_thesis_visual(canvas, width, height, accent, support, ink)
    else:
        _draw_background_visual(canvas, width, height, accent, support, ink)


def _draw_course_visual(canvas, w, h, accent, support, ink) -> None:
    _draw_round_rect(canvas, w, h, 0.46 * w, 0.16 * h, 0.88 * w, 0.58 * h, 0.035 * w, (22, 42, 56), 0.72)
    _draw_rect(canvas, w, h, 0.49 * w, 0.21 * h, 0.85 * w, 0.26 * h, accent, 0.62)
    for index in range(3):
        yy = (0.68 + index * 0.08) * h
        _draw_round_rect(canvas, w, h, 0.18 * w, yy, 0.78 * w, yy + 0.035 * h, 0.018 * w, support, 0.48)
        for seat in range(4):
            _draw_circle(canvas, w, h, (0.25 + seat * 0.15) * w, yy - 0.025 * h, 0.025 * min(w, h), ink, 0.55)
    _draw_round_rect(canvas, w, h, 0.10 * w, 0.18 * h, 0.28 * w, 0.42 * h, 0.02 * w, ink, 0.38)


def _draw_business_visual(canvas, w, h, accent, support, ink) -> None:
    _draw_round_rect(canvas, w, h, 0.16 * w, 0.60 * h, 0.84 * w, 0.75 * h, 0.04 * w, (0, 0, 0), 0.24)
    _draw_round_rect(canvas, w, h, 0.18 * w, 0.56 * h, 0.82 * w, 0.70 * h, 0.04 * w, support, 0.58)
    _draw_round_rect(canvas, w, h, 0.22 * w, 0.58 * h, 0.78 * w, 0.62 * h, 0.018 * w, ink, 0.16)
    for cx in (0.28, 0.44, 0.60, 0.74):
        _draw_circle(canvas, w, h, cx * w, 0.40 * h, 0.055 * min(w, h), ink, 0.64)
        _draw_circle(canvas, w, h, (cx - 0.012) * w, 0.385 * h, 0.018 * min(w, h), (255, 255, 255), 0.24)
        _draw_round_rect(canvas, w, h, (cx - 0.065) * w, 0.48 * h, (cx + 0.065) * w, 0.60 * h, 0.020 * w, accent if cx in (0.44, 0.74) else support, 0.52)
    _draw_round_rect(canvas, w, h, 0.61 * w, 0.14 * h, 0.89 * w, 0.42 * h, 0.026 * w, (14, 26, 34), 0.68)
    _draw_round_rect(canvas, w, h, 0.63 * w, 0.17 * h, 0.87 * w, 0.39 * h, 0.018 * w, ink, 0.08)
    for index, bar in enumerate((0.13, 0.20, 0.29, 0.18)):
        _draw_rect(canvas, w, h, (0.67 + index * 0.045) * w, (0.35 - bar) * h, (0.695 + index * 0.045) * w, 0.35 * h, accent, 0.72)
    _draw_line(canvas, w, h, 0.16 * w, 0.78 * h, 0.84 * w, 0.72 * h, 0.010 * min(w, h), support, 0.25)


def _draw_classical_visual(canvas, w, h, accent, support, ink) -> None:
    _draw_circle(canvas, w, h, 0.78 * w, 0.24 * h, 0.10 * min(w, h), accent, 0.55)
    _draw_triangle(canvas, w, h, 0.03 * w, 0.82 * h, 0.34 * w, 0.35 * h, 0.64 * w, 0.82 * h, support, 0.58)
    _draw_triangle(canvas, w, h, 0.32 * w, 0.84 * h, 0.66 * w, 0.30 * h, 0.98 * w, 0.84 * h, (24, 49, 56), 0.52)
    for cx, cy in ((0.22, 0.26), (0.38, 0.22), (0.55, 0.30)):
        _draw_circle(canvas, w, h, cx * w, cy * h, 0.055 * min(w, h), ink, 0.28)
    _draw_rect(canvas, w, h, 0.12 * w, 0.66 * h, 0.34 * w, 0.69 * h, accent, 0.42)


def _draw_product_visual(canvas, w, h, accent, support, ink) -> None:
    _draw_round_rect(canvas, w, h, 0.31 * w, 0.70 * h, 0.75 * w, 0.78 * h, 0.04 * w, (0, 0, 0), 0.28)
    _draw_round_rect(canvas, w, h, 0.33 * w, 0.67 * h, 0.73 * w, 0.73 * h, 0.035 * w, support, 0.48)
    _draw_round_rect(canvas, w, h, 0.38 * w, 0.18 * h, 0.64 * w, 0.68 * h, 0.05 * w, (18, 24, 36), 0.74)
    _draw_round_rect(canvas, w, h, 0.415 * w, 0.24 * h, 0.605 * w, 0.57 * h, 0.030 * w, ink, 0.44)
    _draw_round_rect(canvas, w, h, 0.445 * w, 0.31 * h, 0.575 * w, 0.40 * h, 0.020 * w, accent, 0.68)
    _draw_round_rect(canvas, w, h, 0.455 * w, 0.43 * h, 0.565 * w, 0.49 * h, 0.015 * w, support, 0.30)
    _draw_circle(canvas, w, h, 0.51 * w, 0.62 * h, 0.018 * min(w, h), support, 0.78)
    _draw_line(canvas, w, h, 0.39 * w, 0.20 * h, 0.48 * w, 0.66 * h, 0.010 * min(w, h), (255, 255, 255), 0.12)


def _draw_icon_visual(canvas, w, h, accent, support, ink) -> None:
    for row in range(2):
        for col in range(3):
            x1 = (0.18 + col * 0.22) * w
            y1 = (0.24 + row * 0.26) * h
            x2 = x1 + 0.14 * w
            y2 = y1 + 0.16 * h
            _draw_round_rect(canvas, w, h, x1, y1, x2, y2, 0.024 * w, ink if (row + col) % 2 else support, 0.34)
            _draw_circle(canvas, w, h, (x1 + x2) / 2, (y1 + y2) / 2, 0.032 * min(w, h), accent, 0.62)


def _draw_data_visual(canvas, w, h, accent, support, ink) -> None:
    _draw_round_rect(canvas, w, h, 0.14 * w, 0.18 * h, 0.86 * w, 0.78 * h, 0.035 * w, (18, 30, 42), 0.56)
    for index, bar in enumerate((0.18, 0.32, 0.25, 0.42, 0.34)):
        _draw_round_rect(canvas, w, h, (0.24 + index * 0.10) * w, (0.70 - bar) * h, (0.29 + index * 0.10) * w, 0.70 * h, 0.01 * w, accent if index % 2 else support, 0.72)
    points = [(0.20, 0.58), (0.34, 0.48), (0.48, 0.52), (0.62, 0.36), (0.78, 0.30)]
    for left, right in zip(points, points[1:]):
        _draw_line(canvas, w, h, left[0] * w, left[1] * h, right[0] * w, right[1] * h, 0.012 * min(w, h), ink, 0.62)


def _draw_thesis_visual(canvas, w, h, accent, support, ink) -> None:
    _draw_round_rect(canvas, w, h, 0.18 * w, 0.20 * h, 0.44 * w, 0.72 * h, 0.018 * w, ink, 0.36)
    for index in range(5):
        _draw_rect(canvas, w, h, 0.22 * w, (0.28 + index * 0.07) * h, 0.40 * w, (0.30 + index * 0.07) * h, accent if index == 1 else support, 0.52)
    nodes = [(0.64, 0.28), (0.76, 0.44), (0.60, 0.58), (0.82, 0.64)]
    center = (0.68, 0.46)
    for node in nodes:
        _draw_line(canvas, w, h, center[0] * w, center[1] * h, node[0] * w, node[1] * h, 0.008 * min(w, h), ink, 0.36)
        _draw_circle(canvas, w, h, node[0] * w, node[1] * h, 0.045 * min(w, h), support, 0.66)
    _draw_circle(canvas, w, h, center[0] * w, center[1] * h, 0.060 * min(w, h), accent, 0.72)


def _draw_background_visual(canvas, w, h, accent, support, ink) -> None:
    _draw_round_rect(canvas, w, h, 0.58 * w, 0.16 * h, 0.90 * w, 0.74 * h, 0.06 * w, support, 0.32)
    _draw_circle(canvas, w, h, 0.70 * w, 0.36 * h, 0.15 * min(w, h), ink, 0.24)
    _draw_rect(canvas, w, h, 0.62 * w, 0.22 * h, 0.84 * w, 0.26 * h, accent, 0.36)


def _pixel_offset(width: int, x: int, y: int) -> int:
    return y * (1 + width * 3) + 1 + x * 3


def _paint_pixel(
    canvas: bytearray,
    width: int,
    x: int,
    y: int,
    color: tuple[int, int, int],
    alpha: float,
) -> None:
    offset = _pixel_offset(width, x, y)
    current = (canvas[offset], canvas[offset + 1], canvas[offset + 2])
    blended = _blend(current, color, alpha)
    canvas[offset : offset + 3] = bytes(blended)


def _draw_rect(canvas, width, height, x1, y1, x2, y2, color, alpha) -> None:
    for y in range(max(0, int(y1)), min(height, int(y2) + 1)):
        for x in range(max(0, int(x1)), min(width, int(x2) + 1)):
            _paint_pixel(canvas, width, x, y, color, alpha)


def _draw_round_rect(canvas, width, height, x1, y1, x2, y2, radius, color, alpha) -> None:
    for y in range(max(0, int(y1)), min(height, int(y2) + 1)):
        for x in range(max(0, int(x1)), min(width, int(x2) + 1)):
            if _rounded_rect(x, y, x1, y1, x2, y2, radius):
                _paint_pixel(canvas, width, x, y, color, alpha)


def _draw_circle(canvas, width, height, cx, cy, radius, color, alpha) -> None:
    for y in range(max(0, int(cy - radius)), min(height, int(cy + radius) + 1)):
        for x in range(max(0, int(cx - radius)), min(width, int(cx + radius) + 1)):
            if _circle(x, y, cx, cy, radius):
                _paint_pixel(canvas, width, x, y, color, alpha)


def _draw_line(canvas, width, height, x1, y1, x2, y2, line_width, color, alpha) -> None:
    pad = max(1, int(line_width) + 2)
    for y in range(max(0, int(min(y1, y2)) - pad), min(height, int(max(y1, y2)) + pad + 1)):
        for x in range(max(0, int(min(x1, x2)) - pad), min(width, int(max(x1, x2)) + pad + 1)):
            if _line(x, y, x1, y1, x2, y2, line_width):
                _paint_pixel(canvas, width, x, y, color, alpha)


def _draw_triangle(canvas, width, height, ax, ay, bx, by, cx, cy, color, alpha) -> None:
    for y in range(max(0, int(min(ay, by, cy))), min(height, int(max(ay, by, cy)) + 1)):
        for x in range(max(0, int(min(ax, bx, cx))), min(width, int(max(ax, bx, cx)) + 1)):
            if _triangle(x, y, ax, ay, bx, by, cx, cy):
                _paint_pixel(canvas, width, x, y, color, alpha)


def _prompt_visual_type(prompt: str) -> str:
    text = prompt.casefold()
    if "course_review_atmosphere" in text or "classroom" in text or "university" in text:
        return "course_review_atmosphere"
    if "business_scene" in text or "business" in text or "meeting" in text:
        return "business_scene"
    if "classical_element" in text or "classical" in text or "heritage" in text:
        return "classical_element"
    if "product_showcase" in text or "product" in text or "device" in text:
        return "product_showcase"
    if "icon_illustration" in text or "icon" in text or "illustration" in text:
        return "icon_illustration"
    if "data_visual" in text or "data landscape" in text or "chart" in text:
        return "data_visual"
    if "thesis_concept" in text or "research" in text or "concept" in text:
        return "thesis_concept"
    return "background"


def _prompt_visual_pixel(
    color: tuple[int, int, int],
    x: int,
    y: int,
    width: int,
    height: int,
    visual_type: str,
    accent: tuple[int, int, int],
    support: tuple[int, int, int],
    ink: tuple[int, int, int],
) -> tuple[int, int, int]:
    if _circle(x, y, 0.10 * width, 0.78 * height, 0.24 * min(width, height)):
        color = _blend(color, support, 0.28)
    if _circle(x, y, 0.86 * width, 0.22 * height, 0.22 * min(width, height)):
        color = _blend(color, accent, 0.22)
    if visual_type == "course_review_atmosphere":
        color = _course_visual(color, x, y, width, height, accent, support, ink)
    elif visual_type == "business_scene":
        color = _business_visual(color, x, y, width, height, accent, support, ink)
    elif visual_type == "classical_element":
        color = _classical_visual(color, x, y, width, height, accent, support, ink)
    elif visual_type == "product_showcase":
        color = _product_visual(color, x, y, width, height, accent, support, ink)
    elif visual_type == "icon_illustration":
        color = _icon_visual(color, x, y, width, height, accent, support, ink)
    elif visual_type == "data_visual":
        color = _data_visual(color, x, y, width, height, accent, support, ink)
    elif visual_type == "thesis_concept":
        color = _thesis_visual(color, x, y, width, height, accent, support, ink)
    else:
        color = _background_visual(color, x, y, width, height, accent, support, ink)
    return color


def _course_visual(color, x, y, w, h, accent, support, ink):
    if _rounded_rect(x, y, 0.46 * w, 0.16 * h, 0.88 * w, 0.58 * h, 0.035 * w):
        color = _blend(color, (22, 42, 56), 0.72)
    if _rect(x, y, 0.49 * w, 0.21 * h, 0.85 * w, 0.26 * h):
        color = _blend(color, accent, 0.62)
    for index in range(3):
        yy = (0.68 + index * 0.08) * h
        if _rounded_rect(x, y, 0.18 * w, yy, 0.78 * w, yy + 0.035 * h, 0.018 * w):
            color = _blend(color, support, 0.48)
        for seat in range(4):
            cx = (0.25 + seat * 0.15) * w
            if _circle(x, y, cx, yy - 0.025 * h, 0.025 * min(w, h)):
                color = _blend(color, ink, 0.55)
    if _rounded_rect(x, y, 0.10 * w, 0.18 * h, 0.28 * w, 0.42 * h, 0.02 * w):
        color = _blend(color, ink, 0.38)
    return color


def _business_visual(color, x, y, w, h, accent, support, ink):
    if _rounded_rect(x, y, 0.18 * w, 0.58 * h, 0.82 * w, 0.72 * h, 0.04 * w):
        color = _blend(color, support, 0.48)
    for cx in (0.28, 0.44, 0.60, 0.74):
        if _circle(x, y, cx * w, 0.43 * h, 0.055 * min(w, h)):
            color = _blend(color, ink, 0.58)
        if _rounded_rect(x, y, (cx - 0.055) * w, 0.50 * h, (cx + 0.055) * w, 0.60 * h, 0.018 * w):
            color = _blend(color, accent, 0.46)
    if _rounded_rect(x, y, 0.63 * w, 0.16 * h, 0.88 * w, 0.40 * h, 0.024 * w):
        color = _blend(color, (20, 36, 48), 0.62)
    for index, bar in enumerate((0.13, 0.20, 0.29, 0.18)):
        if _rect(x, y, (0.67 + index * 0.045) * w, (0.35 - bar) * h, (0.695 + index * 0.045) * w, 0.35 * h):
            color = _blend(color, accent, 0.72)
    return color


def _classical_visual(color, x, y, w, h, accent, support, ink):
    if _circle(x, y, 0.78 * w, 0.24 * h, 0.10 * min(w, h)):
        color = _blend(color, accent, 0.55)
    if _triangle(x, y, 0.03 * w, 0.82 * h, 0.34 * w, 0.35 * h, 0.64 * w, 0.82 * h):
        color = _blend(color, support, 0.58)
    if _triangle(x, y, 0.32 * w, 0.84 * h, 0.66 * w, 0.30 * h, 0.98 * w, 0.84 * h):
        color = _blend(color, (24, 49, 56), 0.52)
    for cx, cy in ((0.22, 0.26), (0.38, 0.22), (0.55, 0.30)):
        if _circle(x, y, cx * w, cy * h, 0.055 * min(w, h)):
            color = _blend(color, ink, 0.28)
    if _rect(x, y, 0.12 * w, 0.66 * h, 0.34 * w, 0.69 * h):
        color = _blend(color, accent, 0.42)
    return color


def _product_visual(color, x, y, w, h, accent, support, ink):
    if _rounded_rect(x, y, 0.28 * w, 0.16 * h, 0.72 * w, 0.76 * h, 0.05 * w):
        color = _blend(color, (18, 24, 36), 0.66)
    if _rounded_rect(x, y, 0.33 * w, 0.23 * h, 0.67 * w, 0.66 * h, 0.028 * w):
        color = _blend(color, ink, 0.46)
    if _rounded_rect(x, y, 0.38 * w, 0.31 * h, 0.62 * w, 0.42 * h, 0.02 * w):
        color = _blend(color, accent, 0.64)
    if _circle(x, y, 0.50 * w, 0.70 * h, 0.018 * min(w, h)):
        color = _blend(color, support, 0.72)
    return color


def _icon_visual(color, x, y, w, h, accent, support, ink):
    for row in range(2):
        for col in range(3):
            x1 = (0.18 + col * 0.22) * w
            y1 = (0.24 + row * 0.26) * h
            x2 = x1 + 0.14 * w
            y2 = y1 + 0.16 * h
            if _rounded_rect(x, y, x1, y1, x2, y2, 0.024 * w):
                color = _blend(color, ink if (row + col) % 2 else support, 0.34)
            if _circle(x, y, (x1 + x2) / 2, (y1 + y2) / 2, 0.032 * min(w, h)):
                color = _blend(color, accent, 0.62)
    return color


def _data_visual(color, x, y, w, h, accent, support, ink):
    if _rounded_rect(x, y, 0.14 * w, 0.18 * h, 0.86 * w, 0.78 * h, 0.035 * w):
        color = _blend(color, (18, 30, 42), 0.56)
    for index, bar in enumerate((0.18, 0.32, 0.25, 0.42, 0.34)):
        if _rounded_rect(x, y, (0.24 + index * 0.10) * w, (0.70 - bar) * h, (0.29 + index * 0.10) * w, 0.70 * h, 0.01 * w):
            color = _blend(color, accent if index % 2 else support, 0.72)
    points = [(0.20, 0.58), (0.34, 0.48), (0.48, 0.52), (0.62, 0.36), (0.78, 0.30)]
    for left, right in zip(points, points[1:]):
        if _line(x, y, left[0] * w, left[1] * h, right[0] * w, right[1] * h, 0.012 * min(w, h)):
            color = _blend(color, ink, 0.62)
    return color


def _thesis_visual(color, x, y, w, h, accent, support, ink):
    if _rounded_rect(x, y, 0.18 * w, 0.20 * h, 0.44 * w, 0.72 * h, 0.018 * w):
        color = _blend(color, ink, 0.36)
    for index in range(5):
        if _rect(x, y, 0.22 * w, (0.28 + index * 0.07) * h, 0.40 * w, (0.30 + index * 0.07) * h):
            color = _blend(color, accent if index == 1 else support, 0.52)
    nodes = [(0.64, 0.28), (0.76, 0.44), (0.60, 0.58), (0.82, 0.64)]
    center = (0.68, 0.46)
    for node in nodes:
        if _line(x, y, center[0] * w, center[1] * h, node[0] * w, node[1] * h, 0.008 * min(w, h)):
            color = _blend(color, ink, 0.36)
        if _circle(x, y, node[0] * w, node[1] * h, 0.045 * min(w, h)):
            color = _blend(color, support, 0.66)
    if _circle(x, y, center[0] * w, center[1] * h, 0.060 * min(w, h)):
        color = _blend(color, accent, 0.72)
    return color


def _background_visual(color, x, y, w, h, accent, support, ink):
    if _rounded_rect(x, y, 0.58 * w, 0.16 * h, 0.90 * w, 0.74 * h, 0.06 * w):
        color = _blend(color, support, 0.32)
    if _circle(x, y, 0.70 * w, 0.36 * h, 0.15 * min(w, h)):
        color = _blend(color, ink, 0.24)
    if _rect(x, y, 0.62 * w, 0.22 * h, 0.84 * w, 0.26 * h):
        color = _blend(color, accent, 0.36)
    return color


def _rgb_from_seed(seed: bytes, offset: int, *, floor: int, span: int) -> tuple[int, int, int]:
    return tuple(floor + seed[(offset + index) % len(seed)] % span for index in range(3))


def _gradient(
    a: tuple[int, int, int],
    b: tuple[int, int, int],
    x: int,
    y: int,
    width: int,
    height: int,
) -> tuple[int, int, int]:
    denominator = max(width + height - 2, 1)
    t = (x + y) / denominator
    return _mix(a, b, t)


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(int(round(left * (1 - t) + right * t)) for left, right in zip(a, b))


def _blend(
    base: tuple[int, int, int],
    overlay: tuple[int, int, int],
    alpha: float,
) -> tuple[int, int, int]:
    return _mix(base, overlay, alpha)


def _rect(x: int, y: int, x1: float, y1: float, x2: float, y2: float) -> bool:
    return x1 <= x <= x2 and y1 <= y <= y2


def _rounded_rect(
    x: int,
    y: int,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
) -> bool:
    if not _rect(x, y, x1, y1, x2, y2):
        return False
    radius = max(radius, 1.0)
    cx = min(max(x, x1 + radius), x2 - radius)
    cy = min(max(y, y1 + radius), y2 - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius**2


def _circle(x: int, y: int, cx: float, cy: float, radius: float) -> bool:
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius**2


def _line(
    x: int,
    y: int,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    width: float,
) -> bool:
    dx = x2 - x1
    dy = y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq <= 0:
        return False
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length_sq))
    px = x1 + t * dx
    py = y1 + t * dy
    return (x - px) ** 2 + (y - py) ** 2 <= width**2


def _triangle(
    x: int,
    y: int,
    ax: float,
    ay: float,
    bx: float,
    by: float,
    cx: float,
    cy: float,
) -> bool:
    denominator = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if denominator == 0:
        return False
    first = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / denominator
    second = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / denominator
    third = 1 - first - second
    return first >= 0 and second >= 0 and third >= 0


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
            bytes=_png(request.width, request.height, seed, request.prompt),
            mime_type="image/png",
            width=request.width,
            height=request.height,
            model=request.model,
        )
