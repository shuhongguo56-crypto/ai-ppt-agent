from collections.abc import Callable
from typing import TypeVar


T = TypeVar("T")


class ModelGatewayError(Exception):
    """A stable public model error that never retains provider details."""

    __slots__ = ("_code", "_message", "_retryable")

    def __init__(self, code: str, message: str, retryable: bool) -> None:
        if not isinstance(code, str) or not code.strip():
            raise ValueError("code must not be blank")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message must not be blank")
        if not isinstance(retryable, bool):
            raise TypeError("retryable must be a boolean")
        self._code = code
        self._message = message
        self._retryable = retryable
        super().__init__(code, message, retryable)

    @property
    def code(self) -> str:
        return self._code

    @property
    def message(self) -> str:
        return self._message

    @property
    def retryable(self) -> bool:
        return self._retryable

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def __repr__(self) -> str:
        return (
            f"ModelGatewayError(code={self.code!r}, message={self.message!r}, "
            f"retryable={self.retryable!r})"
        )


def run_provider_operation(
    operation: Callable[[], T],
    *,
    code: str,
    message: str,
    retryable: bool,
) -> T:
    """Run one provider call without retaining ordinary provider failures."""

    safe_error: ModelGatewayError | None = None
    try:
        return operation()
    except ModelGatewayError as error:
        safe_error = error
    except Exception:
        safe_error = ModelGatewayError(
            code=code,
            message=message,
            retryable=retryable,
        )

    if safe_error is None:
        raise AssertionError("provider boundary exited without a result or error")
    raise safe_error
