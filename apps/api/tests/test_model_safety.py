import logging
import traceback

import pytest

from app.ai import errors as gateway_errors
from app.ai.retry import run_with_retry
from app.ai.safe_logging import log_model_event


ModelGatewayError = gateway_errors.ModelGatewayError


def test_model_gateway_error_exposes_only_stable_public_fields() -> None:
    error = ModelGatewayError("provider_failed", "Model request failed.", False)

    assert error.code == "provider_failed"
    assert error.message == "Model request failed."
    assert error.retryable is False
    assert str(error) == "provider_failed: Model request failed."
    assert repr(error) == (
        "ModelGatewayError(code='provider_failed', "
        "message='Model request failed.', retryable=False)"
    )
    assert error.__cause__ is None


@pytest.mark.parametrize(
    "args",
    [("", "safe", False), ("code", " ", False), ("code", "safe", 1)],
)
def test_model_gateway_error_rejects_unstable_fields(args: tuple[object, ...]) -> None:
    with pytest.raises((TypeError, ValueError)):
        ModelGatewayError(*args)


def test_provider_boundary_does_not_retain_provider_exception() -> None:
    def fail() -> None:
        raise RuntimeError("provider-stack-secret")

    with pytest.raises(ModelGatewayError) as caught:
        gateway_errors.run_provider_operation(
            fail,
            code="provider_failed",
            message="Model request failed.",
            retryable=True,
        )

    converted = caught.value
    rendered = "".join(traceback.format_exception(converted))
    assert converted.__context__ is None
    assert converted.__cause__ is None
    for public_output in (str(converted), repr(converted), rendered):
        assert "provider-stack-secret" not in public_output
        assert "RuntimeError" not in public_output


def test_provider_boundary_returns_successful_operation_result() -> None:
    result = gateway_errors.run_provider_operation(
        lambda: {"status": "ok"},
        code="provider_failed",
        message="Model request failed.",
        retryable=True,
    )

    assert result == {"status": "ok"}


def test_provider_boundary_passes_through_safe_gateway_error_unchanged() -> None:
    safe_error = ModelGatewayError(
        "provider_unavailable", "Provider unavailable.", True
    )

    with pytest.raises(ModelGatewayError) as caught:
        gateway_errors.run_provider_operation(
            lambda: (_ for _ in ()).throw(safe_error),
            code="provider_failed",
            message="Model request failed.",
            retryable=False,
        )

    assert caught.value is safe_error
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None


def test_provider_boundary_does_not_wrap_keyboard_interrupt() -> None:
    def interrupt() -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        gateway_errors.run_provider_operation(
            interrupt,
            code="provider_failed",
            message="Model request failed.",
            retryable=True,
        )


def test_retry_stops_at_configured_limit() -> None:
    calls = 0

    def fail() -> None:
        nonlocal calls
        calls += 1
        raise ModelGatewayError("provider_unavailable", "Provider unavailable.", True)

    with pytest.raises(ModelGatewayError):
        run_with_retry(fail, attempts=3)

    assert calls == 3


def test_retry_returns_success_after_retryable_failures() -> None:
    calls = 0

    def eventually_succeed() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ModelGatewayError("provider_unavailable", "Provider unavailable.", True)
        return "ok"

    assert run_with_retry(eventually_succeed, attempts=3) == "ok"
    assert calls == 3


def test_retry_does_not_repeat_nonretryable_error() -> None:
    calls = 0

    def fail() -> None:
        nonlocal calls
        calls += 1
        raise ModelGatewayError("invalid_output", "Invalid model output.", False)

    with pytest.raises(ModelGatewayError):
        run_with_retry(fail, attempts=3)

    assert calls == 1


def test_retry_does_not_wrap_or_repeat_unexpected_errors() -> None:
    calls = 0

    def fail() -> None:
        nonlocal calls
        calls += 1
        raise LookupError("unexpected")

    with pytest.raises(LookupError, match="unexpected"):
        run_with_retry(fail, attempts=3)

    assert calls == 1


@pytest.mark.parametrize("attempts", [0, 4, True])
def test_retry_rejects_values_outside_one_to_three(attempts: int) -> None:
    with pytest.raises((TypeError, ValueError)):
        run_with_retry(lambda: None, attempts=attempts)


def test_safe_model_log_contains_allowlisted_metadata_only(caplog) -> None:
    prompt = "full-private-prompt"
    upload = "uploaded-text-marker"
    base64_marker = "iVBORw0KGgo-private-base64"
    provider_exception = RuntimeError("provider-stack-secret")

    with caplog.at_level(logging.INFO, logger="ai_ppt.model"):
        log_model_event(
            request_id="request-123",
            model="gpt-5.4-mini",
            latency_ms=12.5,
            error_code="provider_failed",
            usage={"inputTokens": 10, "outputTokens": 4},
        )

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.getMessage() == "model gateway event"
    assert record.request_id == "request-123"
    assert record.model == "gpt-5.4-mini"
    assert record.latency_ms == 12.5
    assert record.error_code == "provider_failed"
    assert record.usage == {"inputTokens": 10, "outputTokens": 4}
    for secret in (prompt, upload, base64_marker, str(provider_exception)):
        assert secret not in caplog.text


def test_safe_model_log_sanitizes_untrusted_identifiers_and_usage(caplog) -> None:
    secret = "provider-secret\nforged-record"

    with caplog.at_level(logging.INFO, logger="ai_ppt.model"):
        log_model_event(
            request_id=secret,
            model=f"bad\rmodel-{secret}",
            latency_ms=1.0,
            error_code=f"bad\terror-{secret}",
            usage={
                "inputTokens": 8,
                "outputTokens": -1,
                secret: 99,
                "unexpected": 10,
            },
        )

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.request_id == "invalid-request-id"
    assert record.model == "invalid-model"
    assert record.error_code == "invalid-error-code"
    assert record.usage == {"inputTokens": 8}
    allowed_extra = {"request_id", "model", "latency_ms", "error_code", "usage"}
    standard_fields = set(logging.makeLogRecord({}).__dict__) | {"message"}
    assert set(record.__dict__) - standard_fields <= allowed_extra
    assert secret not in caplog.text
    assert secret not in repr(record.__dict__)
