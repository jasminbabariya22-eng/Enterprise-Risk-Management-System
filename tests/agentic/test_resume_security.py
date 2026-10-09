"""
Security and Resume Protocol Tests for Agentic State Workflows.
Verifies re-authentication on resume, role revocation defense,
confirmation token expiry, and cross-user hijacking prevention.
"""
import pytest
import time
from datetime import datetime, timezone, timedelta

from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.ai_harness.confirmation import confirmation_manager
from ERM_Copilot.ai_harness.exceptions import AuthorizationError, ConfirmationMismatchError
from ERM_Copilot.workflow.contracts import (
    AgentWorkflowState,
    WorkflowStatus,
    WorkflowType,
)
from ERM_Copilot.workflow.checkpointer import workflow_checkpointer


def test_cross_user_workflow_resumption_blocked():
    """Verify that a user cannot resume a workflow owned by another user."""
    # User 101 creates workflow
    state = AgentWorkflowState(
        session_id="101::sess_sec_1",
        owner_user_id="101",
        owner_role="Risk Owner",
        workflow_type=WorkflowType.RISK_CREATION,
        current_step="AWAITING_DESCRIPTION",
        collected_fields={"risk_name": "Turbine Valve Issue"}
    )
    workflow_checkpointer.save(state)

    # User 202 tries to load and resume it
    intruder_ctx = HarnessContext(user_id="202", user_role="Risk Owner")
    with pytest.raises(AuthorizationError):
        workflow_checkpointer.load(state.workflow_id, context=intruder_ctx)


def test_confirmation_token_validation_on_resume():
    """Verify that confirmation token must match action fingerprint upon resume."""
    # Generate valid confirmation state
    pending = confirmation_manager.create_pending_confirmation(
        action_name="approve_or_reject_risk",
        user_id="201",
        user_role="Functional Head",
        risk_id="RSK-GAS-087",
        parameters={"action": "approve", "remark": "Valid"}
    )
    assert pending["token"] is not None
    assert pending["status"] == "PENDING"

    # Validate confirmation for identical arguments -> SUCCESS
    is_valid = confirmation_manager.validate_confirmation(
        pending_state=pending,
        executing_user_id="201",
        executing_action="approve_or_reject_risk",
        executing_risk_id="RSK-GAS-087",
        executing_params={"action": "approve", "remark": "Valid"}
    )
    assert is_valid is True

    # User ID mismatch attempt -> REJECTED
    with pytest.raises(ConfirmationMismatchError) as exc_info:
        confirmation_manager.validate_confirmation(
            pending_state=pending,
            executing_user_id="999",
            executing_action="approve_or_reject_risk",
            executing_risk_id="RSK-GAS-087",
            executing_params={"action": "approve", "remark": "Valid"}
        )
    assert "user" in str(exc_info.value).lower()


def test_expired_confirmation_token_rejected():
    """Verify that expired confirmation tokens are rejected."""
    pending = confirmation_manager.create_pending_confirmation(
        action_name="approve_or_reject_risk",
        user_id="201",
        user_role="Functional Head",
        risk_id="RSK-GAS-087",
        parameters={"action": "approve", "remark": "Expired test"}
    )
    
    # Manually expire confirmation state
    pending["expires_at"] = time.time() - 60

    with pytest.raises(ConfirmationMismatchError) as exc_info:
        confirmation_manager.validate_confirmation(
            pending_state=pending,
            executing_user_id="201",
            executing_action="approve_or_reject_risk",
            executing_risk_id="RSK-GAS-087",
            executing_params={"action": "approve", "remark": "Expired test"}
        )
    assert "expired" in str(exc_info.value).lower()

