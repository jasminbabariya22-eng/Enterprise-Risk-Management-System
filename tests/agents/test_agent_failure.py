"""
Agent Tests: Failure Handling, Transient Retries, and Recovery.
"""
import pytest
from ERM_Copilot.ai_harness.retry import RetryPolicy
from ERM_Copilot.ai_harness.exceptions import BoundedExecutionError


@pytest.mark.agent
def test_transient_failure_recovery_in_agent():
    attempts = 0
    def transient_call():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ConnectionError("502 Bad Gateway")
        return "Success"

    result, retries = RetryPolicy.execute_with_retry(
        func=transient_call,
        tool_name="search_risks",
        is_idempotent=True,
        is_state_changing=False,
        max_retries=2
    )
    assert result == "Success"
    assert retries == 1


@pytest.mark.agent
def test_non_idempotent_tool_failure_no_retry():
    attempts = 0
    def failing_save():
        nonlocal attempts
        attempts += 1
        raise TimeoutError("504 Gateway Timeout")

    with pytest.raises(TimeoutError):
        RetryPolicy.execute_with_retry(
            func=failing_save,
            tool_name="save_risk",
            is_idempotent=False,
            is_state_changing=True,
            max_retries=3
        )
    assert attempts == 1
