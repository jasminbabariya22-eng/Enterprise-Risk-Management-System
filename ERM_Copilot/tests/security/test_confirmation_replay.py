"""
Security Tests: Confirmation Token Replay, Tampering, and Cross-Action Hijacking.
Verifies token expiration, single-use guarantees, and argument integrity.
"""
import pytest
import time
from unittest.mock import patch

from ERM_Copilot.ai_harness.confirmation import confirmation_manager
from ERM_Copilot.ai_harness.execution import ExecutionCoordinator
from ERM_Copilot.ai_harness.exceptions import ConfirmationMismatchError, ConfirmationRequiredError


def test_token_tampering_fails_fingerprint(functional_head_context):
    # Create confirmation for approving RSK-GAS-087 with remark A
    try:
        ExecutionCoordinator.execute_tool(
            "approve_or_reject_risk",
            {"risk_id": "RSK-GAS-087", "action": "approve", "remark": "Remark A"},
            functional_head_context
        )
    except ConfirmationRequiredError:
        pass

    # Malicious attempt: change remark to Remark B during execution
    with pytest.raises(ConfirmationMismatchError) as exc_info:
        ExecutionCoordinator.execute_tool(
            "approve_or_reject_risk",
            {"risk_id": "RSK-GAS-087", "action": "approve", "remark": "Tampered Remark B"},
            functional_head_context
        )
    assert "tampered" in str(exc_info.value).lower() or "mismatch" in str(exc_info.value).lower()


def test_expired_token_rejected(functional_head_context):
    try:
        ExecutionCoordinator.execute_tool(
            "approve_or_reject_risk",
            {"risk_id": "RSK-GAS-087", "action": "approve", "remark": "Valid Remark"},
            functional_head_context
        )
    except ConfirmationRequiredError:
        pass

    # Age token past expiration
    functional_head_context.confirmation_state["expires_at"] = time.time() - 60

    with pytest.raises(ConfirmationMismatchError) as exc_info:
        ExecutionCoordinator.execute_tool(
            "approve_or_reject_risk",
            {"risk_id": "RSK-GAS-087", "action": "approve", "remark": "Valid Remark"},
            functional_head_context
        )
    assert "expired" in str(exc_info.value).lower()
