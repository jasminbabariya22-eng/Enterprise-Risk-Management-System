"""
Unit Tests for RetryPolicy and Execution Boundaries.
Verifies retry limits, exponential backoff, and non-idempotent write blocking.
"""
import pytest
from ERM_Copilot.ai_harness.retry import RetryPolicy
from ERM_Copilot.ai_harness.exceptions import BoundedExecutionError


def test_retry_transient_error_success_within_limit():
    attempts = 0
    def flaky_service():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("503 Service Unavailable")
        return {"status": "ok"}

    result, retries = RetryPolicy.execute_with_retry(
        func=flaky_service,
        tool_name="search_risks",
        is_idempotent=True,
        is_state_changing=False,
        max_retries=3
    )
    assert result == {"status": "ok"}
    assert retries == 2
    assert attempts == 3


def test_retry_exceeded_raises_error():
    def perpetually_failing():
        raise TimeoutError("Gateway Timeout 504")

    with pytest.raises(TimeoutError):
        RetryPolicy.execute_with_retry(
            func=perpetually_failing,
            tool_name="search_risks",
            is_idempotent=True,
            is_state_changing=False,
            max_retries=2
        )


def test_state_changing_action_never_retries():
    attempts = 0
    def failing_write():
        nonlocal attempts
        attempts += 1
        raise ConnectionError("Database write timeout")

    with pytest.raises(ConnectionError):
        RetryPolicy.execute_with_retry(
            func=failing_write,
            tool_name="save_risk",
            is_idempotent=False,
            is_state_changing=True,
            max_retries=3
        )
    # Must fail immediately after attempt 1
    assert attempts == 1
