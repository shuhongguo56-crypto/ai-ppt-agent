from collections.abc import Callable
from typing import TypeVar

from .errors import ModelGatewayError


T = TypeVar("T")


def run_with_retry(operation: Callable[[], T], attempts: int) -> T:
    if not isinstance(attempts, int) or isinstance(attempts, bool):
        raise TypeError("attempts must be an integer")
    if attempts < 1 or attempts > 3:
        raise ValueError("attempts must be between 1 and 3")
    for index in range(attempts):
        try:
            return operation()
        except ModelGatewayError as error:
            if not error.retryable or index + 1 == attempts:
                raise
    raise AssertionError("retry loop exhausted without a result")
