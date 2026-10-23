"""
Tests for Persistent PostgreSQL and In-Memory Workflow Checkpointers.
Verifies checkpoint save/load, optimistic locking concurrency conflicts,
session isolation, cross-process persistence, and cleanup.
"""
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.ai_harness.exceptions import AuthorizationError
from ERM_Copilot.workflow.contracts import (
    AgentWorkflowState,
    WorkflowStatus,
    WorkflowType,
)
from ERM_Copilot.workflow.checkpointer import (
    InMemoryWorkflowCheckpointer,
    PostgreSQLWorkflowCheckpointer,
    ConcurrencyConflictError,
)


@pytest.fixture
def in_memory_checkpointer():
    return InMemoryWorkflowCheckpointer()


@pytest.fixture
def pg_checkpointer():
    from ERM_Copilot.services.db_service import erm_db
    try:
        conn = erm_db._get_connection()
        conn.close()
    except Exception as e:
        pytest.skip(f"Live PostgreSQL database not available: {e}")
    cp = PostgreSQLWorkflowCheckpointer(fallback_in_memory=True)
    cp.ensure_schema()
    return cp


def test_in_memory_save_and_load(in_memory_checkpointer):
    """Verify basic save and load with user ownership."""
    state = AgentWorkflowState(
        session_id="101::sess_mem_1",
        owner_user_id="101",
        owner_role="Risk Owner",
        workflow_type=WorkflowType.RISK_CREATION,
        current_step="AWAITING_RISK_NAME",
        collected_fields={"title": "Compressor Vibration"}
    )
    saved = in_memory_checkpointer.save(state)
    assert saved.workflow_id == state.workflow_id

    ctx = HarnessContext(user_id="101", user_role="Risk Owner")
    loaded = in_memory_checkpointer.load(state.workflow_id, context=ctx)
    assert loaded is not None
    assert loaded.workflow_id == state.workflow_id
    assert loaded.collected_fields["title"] == "Compressor Vibration"


def test_optimistic_locking_conflict(in_memory_checkpointer):
    """Verify that updating with an outdated expected_version raises ConcurrencyConflictError."""
    state = AgentWorkflowState(
        session_id="101::sess_mem_2",
        owner_user_id="101",
        owner_role="Risk Owner",
        state_version=1
    )
    in_memory_checkpointer.save(state)

    # Simulate another worker updating the state to version 2
    state.state_version = 2
    in_memory_checkpointer.save(state)

    # First worker attempts to update expecting version 1 -> Concurrency Conflict
    with pytest.raises(ConcurrencyConflictError):
        in_memory_checkpointer.save(state, expected_version=1)


def test_unauthorized_cross_user_checkpoint_access_rejected(in_memory_checkpointer):
    """Verify that a user cannot load another user's checkpoint."""
    state = AgentWorkflowState(
        session_id="101::sess_mem_3",
        owner_user_id="101",
        owner_role="Risk Owner",
        collected_fields={"secret_data": "valuable_risk"}
    )
    in_memory_checkpointer.save(state)

    # Different user attempts to load
    attacker_ctx = HarnessContext(user_id="999", user_role="Risk Owner")
    with pytest.raises(AuthorizationError) as exc_info:
        in_memory_checkpointer.load(state.workflow_id, context=attacker_ctx)
    assert "Access Denied" in str(exc_info.value)


def test_super_admin_can_inspect_any_checkpoint(in_memory_checkpointer):
    """Verify that Super Admin can inspect user workflows for platform governance."""
    state = AgentWorkflowState(
        session_id="101::sess_mem_4",
        owner_user_id="101",
        owner_role="Risk Owner"
    )
    in_memory_checkpointer.save(state)

    admin_ctx = HarnessContext(user_id="1", user_role="Super Admin")
    loaded = in_memory_checkpointer.load(state.workflow_id, context=admin_ctx)
    assert loaded is not None
    assert loaded.workflow_id == state.workflow_id


def test_load_active_for_session(in_memory_checkpointer):
    """Verify finding the active workflow for a session key."""
    state = AgentWorkflowState(
        session_id="201::sess_active",
        owner_user_id="201",
        owner_role="Functional Head",
        workflow_type=WorkflowType.APPROVAL_GOVERNANCE,
        workflow_status=WorkflowStatus.RUNNING
    )
    in_memory_checkpointer.save(state)

    ctx = HarnessContext(user_id="201", user_role="Functional Head")
    active = in_memory_checkpointer.load_active_for_session("201::sess_active", context=ctx)
    assert active is not None
    assert active.workflow_id == state.workflow_id

    # If completed, load_active_for_session should return None
    state.transition_to(WorkflowStatus.COMPLETED)
    in_memory_checkpointer.save(state)
    active_after = in_memory_checkpointer.load_active_for_session("201::sess_active", context=ctx)
    assert active_after is None


def test_cleanup_expired_checkpoints(in_memory_checkpointer):
    """Verify expired checkpoint cleanup."""
    expired_state = AgentWorkflowState(
        session_id="101::sess_exp",
        owner_user_id="101",
        owner_role="Risk Owner",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=10)
    )
    in_memory_checkpointer.save(expired_state)

    valid_state = AgentWorkflowState(
        session_id="101::sess_val",
        owner_user_id="101",
        owner_role="Risk Owner",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30)
    )
    in_memory_checkpointer.save(valid_state)

    cleaned_count = in_memory_checkpointer.cleanup_expired()
    assert cleaned_count >= 1
    assert in_memory_checkpointer.load(expired_state.workflow_id) is None
    assert in_memory_checkpointer.load(valid_state.workflow_id) is not None


def test_pg_checkpointer_persistence_and_restore(pg_checkpointer):
    """Verify PostgreSQL checkpointer round-trip persistence and recovery."""
    wid = str(uuid.uuid4())
    state = AgentWorkflowState(
        workflow_id=wid,
        session_id=f"101::{wid}",
        owner_user_id="101",
        owner_role="Risk Owner",
        dept_id=2,
        dept_name="Gas Processing Facilities",
        workflow_type=WorkflowType.RISK_CREATION,
        current_step="AWAITING_INHERENT_ASSESSMENT",
        collected_fields={"risk_name": "Pipeline Overpressure", "dept_id": 2}
    )
    saved = pg_checkpointer.save(state)
    assert saved.workflow_id == wid

    # Create brand new checkpointer instance to verify persistence across restart
    fresh_cp = PostgreSQLWorkflowCheckpointer(fallback_in_memory=True)
    ctx = HarnessContext(user_id="101", user_role="Risk Owner", dept_id=2)
    loaded = fresh_cp.load(wid, context=ctx)

    assert loaded is not None
    assert loaded.workflow_id == wid
    assert loaded.current_step == "AWAITING_INHERENT_ASSESSMENT"
    assert loaded.collected_fields.get("risk_name") == "Pipeline Overpressure"
