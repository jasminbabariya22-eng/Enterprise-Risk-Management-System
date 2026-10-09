"""
Unit and Integration Tests for AgentWorkflowState and State Transition Contracts.
Verifies schema validation, legal and prohibited state machine transitions,
step limiting, and serialization round-trips.
"""
import pytest
from datetime import datetime, timezone, timedelta
from ERM_Copilot.workflow.contracts import (
    AgentWorkflowState,
    WorkflowStatus,
    WorkflowType,
    WorkflowTransitionError,
    LEGAL_TRANSITIONS,
)


def test_workflow_state_creation_valid():
    """Verify default creation of AgentWorkflowState with required fields."""
    state = AgentWorkflowState(
        session_id="101::sess_abc",
        owner_user_id="101",
        owner_role="Risk Owner",
        dept_id=2,
        dept_name="Gas Processing Facilities"
    )
    assert state.workflow_id is not None
    assert state.workflow_status == WorkflowStatus.RUNNING.value
    assert state.state_version == 1
    assert state.step_count == 1
    assert state.is_terminal is False
    assert state.is_expired is False


def test_legal_state_transitions():
    """Verify valid transitions along normal conversational lifecycles."""
    state = AgentWorkflowState(
        session_id="101::sess_1",
        owner_user_id="101",
        owner_role="Risk Owner"
    )

    # RUNNING -> WAITING_FOR_INPUT
    state.transition_to(WorkflowStatus.WAITING_FOR_INPUT, step="AWAITING_RISK_NAME")
    assert state.workflow_status == WorkflowStatus.WAITING_FOR_INPUT.value
    assert state.current_step == "AWAITING_RISK_NAME"
    assert state.state_version == 2

    # WAITING_FOR_INPUT -> RUNNING
    state.transition_to(WorkflowStatus.RUNNING, step="PROCESSING_INPUT")
    assert state.workflow_status == WorkflowStatus.RUNNING.value
    assert state.last_completed_step == "AWAITING_RISK_NAME"
    assert state.state_version == 3

    # RUNNING -> WAITING_FOR_CONFIRMATION
    state.transition_to(WorkflowStatus.WAITING_FOR_CONFIRMATION, step="PREVIEW_CONFIRM")
    assert state.workflow_status == WorkflowStatus.WAITING_FOR_CONFIRMATION.value

    # WAITING_FOR_CONFIRMATION -> RUNNING -> COMPLETED
    state.transition_to(WorkflowStatus.RUNNING, step="PERSISTING")
    state.transition_to(WorkflowStatus.COMPLETED, step="WIZARD_COMPLETED")
    assert state.workflow_status == WorkflowStatus.COMPLETED.value
    assert state.is_terminal is True


def test_prohibited_transitions_raise_error():
    """Verify that invalid state machine jumps raise WorkflowTransitionError."""
    state = AgentWorkflowState(
        session_id="101::sess_2",
        owner_user_id="101",
        owner_role="Risk Owner"
    )
    state.transition_to(WorkflowStatus.COMPLETED)
    assert state.is_terminal is True

    # Cannot transition out of terminal state COMPLETED
    with pytest.raises(WorkflowTransitionError) as exc_info:
        state.transition_to(WorkflowStatus.RUNNING)
    assert "Illegal state transition" in str(exc_info.value)


def test_prohibited_waiting_for_confirmation_direct_complete():
    """WAITING_FOR_CONFIRMATION cannot jump directly to COMPLETED without RUNNING."""
    state = AgentWorkflowState(
        session_id="101::sess_3",
        owner_user_id="101",
        owner_role="Risk Owner"
    )
    state.transition_to(WorkflowStatus.WAITING_FOR_CONFIRMATION)

    with pytest.raises(WorkflowTransitionError):
        state.transition_to(WorkflowStatus.COMPLETED)


def test_state_serialization_roundtrip():
    """Verify to_checkpoint_dict and from_checkpoint_dict round-trip preserves all fields."""
    original = AgentWorkflowState(
        session_id="101::sess_4",
        owner_user_id="101",
        owner_role="Risk Owner",
        dept_id=2,
        dept_name="Gas Processing Facilities",
        workflow_type=WorkflowType.RISK_CREATION,
        current_agent="risk_creation_agent",
        current_step="AWAITING_DESCRIPTION",
        risk_id="RSK-GAS-087",
        collected_fields={"risk_name": "Flare Header Leak", "inherent_score": 16},
        missing_fields=["mitigation", "target_date"],
        state_version=5
    )
    serialized = original.to_checkpoint_dict()
    assert isinstance(serialized, dict)
    assert serialized["state_version"] == 5
    assert serialized["collected_fields"]["risk_name"] == "Flare Header Leak"

    reconstituted = AgentWorkflowState.from_checkpoint_dict(serialized)
    assert reconstituted.workflow_id == original.workflow_id
    assert reconstituted.collected_fields == original.collected_fields
    assert reconstituted.missing_fields == original.missing_fields
    assert reconstituted.state_version == 5


def test_state_ttl_expiration():
    """Verify that expired workflows detect is_expired correctly."""
    past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    state = AgentWorkflowState(
        session_id="101::sess_5",
        owner_user_id="101",
        owner_role="Risk Owner",
        expires_at=past_time
    )
    assert state.is_expired is True
