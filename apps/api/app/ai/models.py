from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping


MAX_IMAGE_PIXELS = 16_777_216
MAX_IMAGE_DIMENSION = 4_096


class FrozenDict(dict[str, Any]):
    """A JSON-compatible dict whose contents cannot be changed after creation."""

    def __init__(self, values: Mapping[str, Any]) -> None:
        dict.__init__(self)
        for key, value in values.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            dict.__setitem__(self, key, _freeze_json(value))

    def _immutable(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("mapping is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable

    def __deepcopy__(self, _memo: dict[int, object]) -> FrozenDict:
        return self


class FrozenList(list[Any]):
    """A JSON array that remains compatible with JSON Schema type checks."""

    def __init__(self, values: list[Any] | tuple[Any, ...]) -> None:
        list.__init__(self, (_freeze_json(value) for value in values))

    def _immutable(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("sequence is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable
    __iadd__ = _immutable
    __imul__ = _immutable

    def __deepcopy__(self, _memo: dict[int, object]) -> FrozenList:
        return self


def _freeze_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return value
    if isinstance(value, Mapping):
        return FrozenDict(value)
    if isinstance(value, (list, tuple)):
        return FrozenList(value)
    raise TypeError("value must contain only JSON-compatible data")


def _nonblank(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")


def validate_image_dimensions(width: int, height: int) -> None:
    if (
        not isinstance(width, int)
        or isinstance(width, bool)
        or not isinstance(height, int)
        or isinstance(height, bool)
        or width < 1
        or height < 1
        or width > MAX_IMAGE_DIMENSION
        or height > MAX_IMAGE_DIMENSION
        or width * height > MAX_IMAGE_PIXELS
    ):
        raise ValueError("image dimensions exceed the safe pixel budget")


@dataclass(frozen=True, slots=True)
class TextRequest:
    model: str
    prompt: str
    response_schema: dict[str, Any]
    timeout_seconds: float = 30
    max_attempts: int = 1

    def __post_init__(self) -> None:
        _nonblank(self.model, "model")
        _nonblank(self.prompt, "prompt")
        if not isinstance(self.response_schema, Mapping):
            raise TypeError("response_schema must be a mapping")
        _validate_execution_controls(self.timeout_seconds, self.max_attempts)
        object.__setattr__(self, "response_schema", FrozenDict(self.response_schema))


@dataclass(frozen=True, slots=True)
class TextResult:
    data: Any
    model: str
    usage: dict[str, int]

    def __post_init__(self) -> None:
        _nonblank(self.model, "model")
        if not isinstance(self.usage, Mapping):
            raise TypeError("usage must be a mapping")
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in self.usage.values()
        ):
            raise ValueError("usage values must be non-negative integers")
        object.__setattr__(self, "data", _freeze_json(self.data))
        object.__setattr__(self, "usage", FrozenDict(self.usage))


@dataclass(frozen=True, slots=True)
class ImageRequest:
    model: str
    prompt: str
    width: int
    height: int
    timeout_seconds: float = 30
    max_attempts: int = 1

    def __post_init__(self) -> None:
        _nonblank(self.model, "model")
        _nonblank(self.prompt, "prompt")
        validate_image_dimensions(self.width, self.height)
        _validate_execution_controls(self.timeout_seconds, self.max_attempts)


def _validate_execution_controls(timeout_seconds: float, max_attempts: int) -> None:
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
        or timeout_seconds > 300
    ):
        raise ValueError("timeout_seconds must be finite and between 0 and 300")
    if (
        not isinstance(max_attempts, int)
        or isinstance(max_attempts, bool)
        or not 1 <= max_attempts <= 3
    ):
        raise ValueError("max_attempts must be between 1 and 3")


@dataclass(frozen=True, slots=True)
class GeneratedImage:
    bytes: bytes
    mime_type: str
    width: int
    height: int
    model: str

    def __post_init__(self) -> None:
        if not isinstance(self.bytes, bytes):
            raise TypeError("bytes must be immutable bytes")
        if not self.bytes:
            raise ValueError("bytes must not be empty")
        _nonblank(self.mime_type, "mime_type")
        _nonblank(self.model, "model")
        validate_image_dimensions(self.width, self.height)
