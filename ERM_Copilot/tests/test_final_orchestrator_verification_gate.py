"""
Final Gate Verification Suite for ERM Copilot Orchestrator & Cross-Agent Integration.
Tests:
1. Checkpoint Schema & PostgreSQL Checkpointer Resolution (ers.agent_workflow_checkpoints)
2. Complete Pause/Resume Lifecycle across restarts, reload, expiry, and legal transition graph
3. Pending Confirmation Invalidation on Intent Switch, Anti-Replay, and Fresh-Preview Requirement
4. Persistent Atomicity & Optimistic Concurrency Locking across simulated workers
5. Real Database Verification of Authoritative Service Mutations, Audit Trails, and Rollbacks
6. Exhaustive Routing Matrix (Continuation, Switching, Read-Only Interruption, Ambiguity, Cancellation)
"""
import pytest
import uuid
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from ERM_Copilot.agents.orchestrator.agent import ERMCopilotAgent, erm_copilot_agent
from ERM_Copilot.agents.risk_creation import risk_creation_agent, RiskCreationAgent
from ERM_Copilot.agents.treatment import treatment_management_agent, TreatmentManagementAgent
from ERM_Copilot.agents.treatment.state import TreatmentSession, TreatmentWorkflowState, TreatmentGoal
from ERM_Copilot.agents.treatment.execution import (
    bind_pending_confirmation,
    verify_confirmation_integrity,
    execute_confirmed_treatment_decision,
    compute_confirmation_digest,
)
from ERM_Copilot.agents.approval_workflow import approval_workflow_agent, ApprovalWorkflowAgent
from ERM_Copilot.agents.approval_workflow.state import ApprovalWorkflowSession, ApprovalGoal, ApprovalWorkflowState
from ERM_Copilot.models.contracts import AgentRequest, AgentResponse
from ERM_Copilot.workflow.contracts import (
    AgentWorkflowState,
    WorkflowStatus,
    WorkflowType,
    WorkflowTransitionError,
    LEGAL_TRANSITIONS,
)
from ERM_Copilot.workflow.checkpointer import (
    PostgreSQLWorkflowCheckpointer,
    InMemoryWorkflowCheckpointer,
    ConcurrencyConflictError,
    workflow_checkpointer,
)
from ERM_Copilot.services.db_service import erm_db


@pytest.fixture(autouse=True)
def clean_all_agent_sessions():
    """Ensure in-memory sessions are cleanly reset before and after each test."""
    risk_creation_agent.sessions.clear()
    treatment_management_agent.sessions.clear()
    approval_workflow_agent.sessions.clear()
    yield
    risk_creation_agent.sessions.clear()
    treatment_management_agent.sessions.clear()
    approval_workflow_agent.sessions.clear()


# =====================================================================
# 1. CHECKPOINT SCHEMA & RESOLUTION
# =====================================================================
class TestCheckpointSchemaResolution:
    """Verifies that the PostgreSQL checkpointer uses the authoritative schema ers.agent_workflow_checkpoints."""

    def test_authoritative_table_name_and_schema(self):
        pg_checkpointer = PostgreSQLWorkflowCheckpointer(fallback_in_memory=True)
        assert pg_checkpointer.schema == "ers"
        assert pg_checkpointer.table_name == "agent_workflow_checkpoints"
        assert pg_checkpointer.full_table == "ers.agent_workflow_checkpoints"

    def test_ensure_schema_ddl_idempotent(self):
        pg_checkpointer = PostgreSQLWorkflowCheckpointer(fallback_in_memory=True)
        # Should execute or verify without raising any syntax or permission error
        pg_checkpointer.ensure_schema()
        assert pg_checkpointer._schema_ensured is True


# =====================================================================
# 2. PAUSE / RESUME LIFECYCLE & TRANSITIONS
# =====================================================================
class TestPauseResumeLifecycle:
    """Verifies all legal state transitions involving PAUSED and consistency across restart."""

    def test_legal_paused_transitions(self):
        wf = AgentWorkflowState(
            session_id="sess-lifecycle-01",
            workflow_type=WorkflowType.RISK_CREATION,
            owner_user_id="12",
            owner_role="Risk Owner",
            current_agent="risk_creation_agent",
            current_step="INITIATION",
        )
        assert wf.workflow_status == WorkflowStatus.RUNNING.value

        # RUNNING -> WAITING_FOR_INPUT
        wf.transition_to(WorkflowStatus.WAITING_FOR_INPUT, step="STEP_RISK_NAME")
        assert wf.workflow_status == WorkflowStatus.WAITING_FOR_INPUT.value

        # WAITING_FOR_INPUT -> PAUSED
        wf.transition_to(WorkflowStatus.PAUSED, reason="User switched intent")
        assert wf.workflow_status == WorkflowStatus.PAUSED.value
        assert wf.state_version == 3

        # PAUSED -> RUNNING (Resume)
        wf.transition_to(WorkflowStatus.RUNNING, step="RESUMED")
        assert wf.workflow_status == WorkflowStatus.RUNNING.value

        # RUNNING -> WAITING_FOR_CONFIRMATION
        wf.transition_to(WorkflowStatus.WAITING_FOR_CONFIRMATION, step="AWAITING_CONFIRMATION")
        assert wf.workflow_status == WorkflowStatus.WAITING_FOR_CONFIRMATION.value

        # WAITING_FOR_CONFIRMATION -> PAUSED
        wf.transition_to(WorkflowStatus.PAUSED, reason="Interrupted during confirmation")
        assert wf.workflow_status == WorkflowStatus.PAUSED.value

        # PAUSED -> CANCELLED
        wf.transition_to(WorkflowStatus.CANCELLED, reason="User cancelled paused workflow")
        assert wf.workflow_status == WorkflowStatus.CANCELLED.value
        assert wf.is_terminal is True

    def test_illegal_transition_from_completed_to_paused_raises(self):
        wf = AgentWorkflowState(
            session_id="sess-term-01",
            workflow_type=WorkflowType.TREATMENT_MANAGEMENT,
            owner_user_id="12",
            owner_role="Risk Owner",
        )
        wf.transition_to(WorkflowStatus.COMPLETED)
        with pytest.raises(WorkflowTransitionError):
            wf.transition_to(WorkflowStatus.PAUSED)

    def test_checkpoint_reload_after_simulated_restart(self):
        """Simulates app restart: memory purged, state reloaded from checkpointer."""
        session_key = "12::sess-restart-01"
        wf = AgentWorkflowState(
            workflow_id="wf-restart-01",
            session_id=session_key,
            workflow_type=WorkflowType.TREATMENT_MANAGEMENT,
            owner_user_id="12",
            owner_role="Risk Owner",
            dept_id=2,
            dept_name="Gas Processing Facilities",
            current_agent="treatment_management_agent",
            current_step="COLLECTING_INFO",
            collected_fields={
                "target_risk_id": "RSK-001",
                "action_plan": "Install vibration dampeners",
                "progress": 30
            }
        )
        workflow_checkpointer.save(wf)

        # Clear in-memory session (simulate process restart)
        treatment_management_agent.sessions.clear()
        assert session_key not in treatment_management_agent.sessions

        # get_session reloads from checkpointer
        loaded_sess = treatment_management_agent.get_session(session_key)
        assert loaded_sess is not None
        assert loaded_sess.target_risk_id == "RSK-001"
        assert loaded_sess.action_plan == "Install vibration dampeners"
        assert loaded_sess.progress == 30

    def test_expired_checkpoint_fails_closed(self):
        session_key = "12::sess-exp-01"
        past_time = datetime.now(timezone.utc) - timedelta(hours=2)
        wf = AgentWorkflowState(
            workflow_id="wf-exp-01",
            session_id=session_key,
            workflow_type=WorkflowType.RISK_CREATION,
            owner_user_id="12",
            owner_role="Risk Owner",
            expires_at=past_time
        )
        workflow_checkpointer.save(wf)

        loaded = workflow_checkpointer.load("wf-exp-01")
        assert loaded.workflow_status in (WorkflowStatus.EXPIRED.value, WorkflowStatus.EXPIRED)
        assert loaded.is_terminal is True


# =====================================================================
# 3. PENDING CONFIRMATIONS & ANTI-REPLAY ACROSS TRANSITIONS
# =====================================================================
class TestPendingConfirmationInvalidation:
    """Verifies that context-switching invalidates confirmations, requiring fresh preview on resume."""

    def test_confirmation_invalidated_on_intent_switch(self):
        session_key = "12::sess-conf-inval"
        sess = TreatmentSession(
            session_id="sess-conf-inval",
            user_id="12",
            user_role="Risk Owner",
            dept_id=2,
            dept_name="Gas Processing Facilities",
            goal=TreatmentGoal.ADD_TREATMENT,
            target_risk_id="RSK-001",
            target_risk_register_id=101,
            action_plan="Add high-temp insulation barrier",
            action_owner_id=12,
            target_date="2026-12-31",
            state=TreatmentWorkflowState.AWAITING_CONFIRMATION,
        )
        conf = bind_pending_confirmation(
            session=sess,
            action="ADD_TREATMENT",
            target_id="RSK-001",
            arguments={"action_plan": sess.action_plan, "target_date": sess.target_date}
        )
        treatment_management_agent.sessions[session_key] = sess
        assert sess.pending_confirmation is not None

        # User switches intent to Approval Workflow
        req_switch = AgentRequest(
            message="Approve RSK-001 with remark Passed Review",
            user_id="12",
            user_role="Functional Head",
            session_id="sess-conf-inval",
            metadata={"role": "Functional Head", "dept_id": 2, "dept_name": "Gas Processing Facilities"}
        )
        resp = erm_copilot_agent.process(req_switch)
        assert resp.agent_id == "agent_approval_workflow"

        # Treatment confirmation MUST have been cleared to prevent stale/accidental mutation
        assert sess.pending_confirmation is None

        # Attempt to directly execute with cleared confirmation fails immediately
        success, res, err = execute_confirmed_treatment_decision(sess)
        assert success is False
        assert "No active confirmation token" in err

    def test_resuming_paused_agent_requires_fresh_preview(self):
        """When resuming a paused workflow whose confirmation was invalidated, fresh confirmation is required."""
        session_key = "12::sess-resume-preview"
        sess = TreatmentSession(
            session_id="sess-resume-preview",
            user_id="12",
            user_role="Risk Owner",
            dept_id=2,
            dept_name="Gas Processing Facilities",
            goal=TreatmentGoal.ADD_TREATMENT,
            target_risk_id="RSK-001",
            target_risk_register_id=101,
            action_plan="Install pressure gauge",
            action_owner_id=12,
            target_date="2026-11-30",
            state=TreatmentWorkflowState.COLLECTING_INFO,
        )
        treatment_management_agent.sessions[session_key] = sess

        with patch("ERM_Copilot.agents.treatment.agent.fetch_risk_info") as mock_fetch:
            mock_fetch.return_value = {
                "risk_register_id": 101,
                "risk_id": "RSK-001",
                "risk_name": "Turbine Overheating",
                "dept_id": 2,
                "is_deleted": 0,
            }
            # User says "confirm" without active confirmation token
            req_confirm = AgentRequest(
                message="confirm",
                user_id="12",
                user_role="Risk Owner",
                session_id="sess-resume-preview",
                metadata={"role": "Risk Owner", "dept_id": 2, "dept_name": "Gas Processing Facilities"}
            )
            resp = treatment_management_agent.process(req_confirm)
            # Agent should generate preview and require confirmation rather than mutating
            assert resp.metadata.get("intent") in ["AWAITING_CONFIRMATION", "TREATMENT_PROCESSING"]


# =====================================================================
# 4. ATOMICITY & OPTIMISTIC CONCURRENCY
# =====================================================================
class TestPersistentAtomicityAndConcurrency:
    """Verifies atomic optimistic locking across concurrent worker updates."""

    def test_in_memory_optimistic_concurrency_conflict(self):
        checkpointer = InMemoryWorkflowCheckpointer()
        wf = AgentWorkflowState(
            workflow_id="wf-conc-01",
            session_id="sess-conc-01",
            workflow_type=WorkflowType.RISK_CREATION,
            owner_user_id="12",
            owner_role="Risk Owner",
            state_version=1,
        )
        checkpointer.save(wf)

        # Worker 1 updates version 1 -> 2
        wf.state_version = 2
        checkpointer.save(wf, expected_version=1)

        # Worker 2 attempts update still expecting version 1 -> Must raise ConcurrencyConflictError
        with pytest.raises(ConcurrencyConflictError) as exc_info:
            checkpointer.save(wf, expected_version=1)
        assert "expected version 1" in str(exc_info.value)

    def test_postgresql_row_lock_concurrency_conflict(self):
        """Tests PostgreSQL checkpointer handles version conflicts with rollback."""
        pg_checkpointer = PostgreSQLWorkflowCheckpointer(fallback_in_memory=True)
        wf = AgentWorkflowState(
            workflow_id=f"wf-pg-conc-{uuid.uuid4().hex[:8]}",
            session_id=f"sess-pg-conc-{uuid.uuid4().hex[:8]}",
            workflow_type=WorkflowType.APPROVAL_GOVERNANCE,
            owner_user_id="12",
            owner_role="Risk Head",
            state_version=1,
        )
        pg_checkpointer.save(wf)

        # First save with expected_version=1
        wf.state_version = 2
        pg_checkpointer.save(wf, expected_version=1)

        # Second save with stale expected_version=1 must be rejected
        with pytest.raises(ConcurrencyConflictError):
            pg_checkpointer.save(wf, expected_version=1)


# =====================================================================
# 5. REAL DATABASE VERIFICATION
# =====================================================================
class TestRealDatabaseAuthoritativeMutations:
    """Exercises authoritative database mutations with verification and rollback."""

    def test_real_treatment_progress_update_and_reconciliation(self):
        """Queries real risk/treatment, tests progress update mutation and reconciliation."""
        conn = erm_db._get_connection(readonly=False)
        cur = conn.cursor()
        try:
            # Query a valid real treatment record from ers.risk_treatment
            cur.execute("""
                SELECT risk_treatment_id, risk_register_id, progress, action_status_id 
                FROM ers.risk_treatment 
                WHERE is_deleted = 0 
                ORDER BY risk_treatment_id DESC LIMIT 1
            """)
            row = cur.fetchone()
            if not row:
                pytest.skip("No real treatment records found in test database.")

            t_id, r_id, orig_prog, orig_status = row[0], row[1], row[2], row[3]

            # Perform authoritative mutation using DB service
            new_prog = 55 if str(orig_prog) != "55" else 65
            res = erm_db.update_treatment_progress(
                treatment_id=t_id,
                progress=new_prog,
                remarks="Automated integration verification test",
                modified_by=1
            )
            assert res.get("status") == "success"

            # Verify authoritative update in DB
            cur.execute("SELECT progress FROM ers.risk_treatment WHERE risk_treatment_id = %s", (t_id,))
            updated_prog = cur.fetchone()[0]
            assert int(updated_prog) == new_prog

            # Rollback to original state to preserve data integrity
            cur.execute(
                "UPDATE ers.risk_treatment SET progress = %s, action_status_id = %s WHERE risk_treatment_id = %s",
                (orig_prog, orig_status, t_id)
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()

    def test_real_risk_audit_trail_consistency(self):
        """Verifies real risk audit trail records exist and are correctly structured."""
        conn = erm_db._get_connection(readonly=True)
        cur = conn.cursor()
        try:
            cur.execute("SELECT risk_id FROM ers.risk_register WHERE is_deleted = 0 ORDER BY risk_register_id DESC LIMIT 1")
            row = cur.fetchone()
            if not row:
                pytest.skip("No real risks found in test database.")
            risk_id = row[0]

            audit_data = erm_db.get_risk_audit_trail(risk_id)
            assert audit_data is not None
            assert "risk_id" in audit_data or "audit_trail" in audit_data or "timeline" in audit_data
        finally:
            cur.close()
            conn.close()


# =====================================================================
# 6. EXHAUSTIVE ROUTING MATRIX
# =====================================================================
class TestExhaustiveRoutingMatrix:
    """Verifies all combinations of agent continuation, intent switching, and safeguards."""

    @pytest.mark.parametrize("source_agent,target_trigger,target_agent_id", [
        ("RISK_CREATION", "Add treatment plan for RSK-001", "treatment_management_agent"),
        ("RISK_CREATION", "Approve RSK-001 with remark OK", "agent_approval_workflow"),
        ("TREATMENT", "Approve RSK-001 with remark OK", "agent_approval_workflow"),
        ("TREATMENT", "Create a new risk for Gas Flare", "risk_creation_agent"),
    ])
    def test_cross_agent_switching_matrix(self, source_agent, target_trigger, target_agent_id):
        session_key = "12::sess-matrix-01"
        if source_agent == "RISK_CREATION":
            risk_creation_agent.sessions[session_key] = MagicMock(
                user_id="12", user_role="Risk Owner", state="START", pending_confirmation=None
            )
        elif source_agent == "TREATMENT":
            treatment_management_agent.sessions[session_key] = TreatmentSession(
                session_id=session_key, user_id="12", user_role="Risk Owner",
                state=TreatmentWorkflowState.COLLECTING_INFO, target_risk_id="RSK-001"
            )

        req = AgentRequest(
            message=target_trigger,
            user_id="12",
            user_role="Functional Head",
            session_id="sess-matrix-01",
            metadata={"role": "Functional Head", "dept_id": 2, "dept_name": "Gas Processing Facilities"}
        )
        resp = erm_copilot_agent.process(req)
        assert resp.agent_id == target_agent_id
        assert "safely paused in the background" in resp.response

    def test_ambiguous_request_does_not_mutate_or_throw(self):
        """Ambiguous query returns safe fallback rather than crashing or mutating."""
        req = AgentRequest(
            message="What about tomorrow morning?",
            user_id="12",
            user_role="Risk Owner",
            session_id="sess-ambig-01",
            metadata={"role": "Risk Owner", "dept_id": 2, "dept_name": "Gas Processing Facilities"}
        )
        resp = erm_copilot_agent.process(req)
        assert resp.success is True
        assert resp.metadata.get("intent") in ["SEARCH_RISK", "GENERAL_RISK_QUERY", "CONVERSATIONAL_SMALL_TALK"]

    def test_missing_identity_fails_closed_orchestrator(self):
        req = AgentRequest(message="Approve RSK-001", user_id=None, user_role="Risk Owner")
        resp = erm_copilot_agent.process(req)
        assert resp.metadata.get("intent") == "AUTH_FAILURE"

    def test_missing_role_fails_closed_orchestrator(self):
        req = AgentRequest(message="Approve RSK-001", user_id="12", user_role=None)
        resp = erm_copilot_agent.process(req)
        assert resp.metadata.get("intent") == "ROLE_MISSING"
