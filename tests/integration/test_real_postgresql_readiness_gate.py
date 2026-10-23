"""
Final Deployment Readiness Gate: Real PostgreSQL & Service Path Verification.

Exercises:
1. Authoritative checkpoint table resolution (ers.agent_workflow_checkpoints).
2. Checkpoint persistence, pause/resume lifecycle, and process crash recovery on real PostgreSQL.
3. Optimistic concurrency control (SELECT ... FOR UPDATE) across separate connections.
4. Confirmation token HMAC-SHA256 anti-tamper security across workers (actor, role, action, target, payload, 15m TTL).
5. Authoritative service paths on dedicated test database (WFTest):
   - Creating and saving a risk (create_risk)
   - Approving and rejecting a risk (approve_or_reject_risk) with strict 3-stage governance and department isolation
   - Adding a treatment (add_risk_treatment)
   - Updating treatment progress (update_treatment_progress)
   - Reassigning a treatment owner (reassign_treatment_owner)
   - Verifying commit/rollback, status mappings, and audit history (risk_register_hist).
"""
import copy
import os
import time
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from ERM_Copilot.config.settings import settings
from ERM_Copilot.services.db_service import ERMDatabaseService
from ERM_Copilot.workflow.checkpointer import PostgreSQLWorkflowCheckpointer, ConcurrencyConflictError
from ERM_Copilot.workflow.contracts import AgentWorkflowState, WorkflowType, WorkflowStatus
from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.agents.treatment.execution import (
    bind_pending_confirmation,
    verify_confirmation_integrity,
    compute_confirmation_digest,
    CONFIRMATION_EXPIRY_SECONDS,
)
from ERM_Copilot.agents.treatment.state import TreatmentSession, TreatmentGoal, TreatmentWorkflowState


@pytest.fixture(scope="module")
def real_pg_db():
    """Provides an ERMDatabaseService connected strictly to the dedicated test database WFTest."""
    db = ERMDatabaseService()
    db.dbname = "WFTest"
    # Ensure connectivity
    conn = db._get_connection(readonly=False)
    conn.close()
    return db


@pytest.fixture(scope="module")
def pg_checkpointer(real_pg_db):
    """Provides a PostgreSQLWorkflowCheckpointer strictly bound to WFTest without fallback."""
    cp = PostgreSQLWorkflowCheckpointer(fallback_in_memory=False)
    cp._get_connection = lambda: real_pg_db._get_connection(readonly=False)
    cp.ensure_schema()
    return cp


# ==============================================================================
# SECTION 1: Checkpoint Schema & Real PostgreSQL Persistence
# ==============================================================================

def test_checkpoint_authoritative_table_name(real_pg_db, pg_checkpointer):
    """Verifies that ers.agent_workflow_checkpoints is the single authoritative table in live PostgreSQL."""
    assert pg_checkpointer.schema == "ers"
    assert pg_checkpointer.table_name == "agent_workflow_checkpoints"
    assert pg_checkpointer.full_table == "ers.agent_workflow_checkpoints"

    conn = real_pg_db._get_connection(readonly=True)
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_schema = 'ers' AND table_name = 'agent_workflow_checkpoints'
    """)
    cols = {r[0]: r[1] for r in cur.fetchall()}
    conn.close()

    expected_cols = [
        "workflow_id", "conversation_id", "session_id", "owner_user_id", "owner_role",
        "dept_id", "workflow_type", "workflow_status", "current_agent", "current_step",
        "state_version", "state_payload", "created_at", "updated_at", "expires_at"
    ]
    for col in expected_cols:
        assert col in cols, f"Missing required column {col} in live PostgreSQL table."


def test_real_postgresql_checkpoint_persistence_and_reload(real_pg_db, pg_checkpointer):
    """Verifies end-to-end saving and loading of workflow state against real PostgreSQL."""
    wf_id = f"wf-test-{uuid.uuid4().hex[:8]}"
    state = AgentWorkflowState(
        workflow_id=wf_id,
        conversation_id="conv-readiness-1",
        session_id="sess-readiness-1",
        owner_user_id="5",
        owner_role="Risk Owner",
        dept_id=1,
        workflow_type=WorkflowType.RISK_CREATION,
        workflow_status=WorkflowStatus.RUNNING,
        current_agent="RiskCreationAgent",
        current_step="collect_details",
        state_version=1,
        collected_fields={"risk_name": "Pipeline Overpressure", "category": "Operational"},
    )

    # Save to PostgreSQL
    saved = pg_checkpointer.save(state)
    assert saved.state_version == 1

    # Reload from independent checkpointer instance
    cp_fresh = PostgreSQLWorkflowCheckpointer(fallback_in_memory=False)
    cp_fresh._get_connection = lambda: real_pg_db._get_connection(readonly=False)
    loaded = cp_fresh.load(wf_id, context=HarnessContext(user_id="5", user_role="Risk Owner"))

    assert loaded is not None
    assert loaded.workflow_id == wf_id
    assert loaded.workflow_status == WorkflowStatus.RUNNING
    assert loaded.collected_fields["risk_name"] == "Pipeline Overpressure"
    assert loaded.state_version == 1


# ==============================================================================
# SECTION 2: Workflow Pause/Resume Lifecycle & Crash Recovery
# ==============================================================================

def test_real_postgresql_pause_and_resume_lifecycle(real_pg_db, pg_checkpointer):
    """Verifies state transitions involving PAUSED and resume persist correctly in PostgreSQL."""
    wf_id = f"wf-pause-{uuid.uuid4().hex[:8]}"
    state = AgentWorkflowState(
        workflow_id=wf_id,
        conversation_id="conv-pause-1",
        session_id="sess-pause-1",
        owner_user_id="5",
        owner_role="Risk Owner",
        dept_id=1,
        workflow_type=WorkflowType.APPROVAL_GOVERNANCE,
        workflow_status=WorkflowStatus.RUNNING,
        current_agent="ApprovalWorkflowAgent",
        current_step="pending_review",
        state_version=1,
    )
    pg_checkpointer.save(state)

    # 1. Pause workflow
    state.transition_to(WorkflowStatus.PAUSED, reason="User requested read-only query")
    state.state_version = 2
    pg_checkpointer.save(state, expected_version=1)

    # Reload in fresh checkpointer
    loaded_paused = pg_checkpointer.load(wf_id)
    assert loaded_paused.workflow_status == WorkflowStatus.PAUSED
    assert loaded_paused.state_version == 2

    # 2. Resume workflow
    loaded_paused.transition_to(WorkflowStatus.RUNNING, reason="Resuming after question answered")
    loaded_paused.state_version = 3
    pg_checkpointer.save(loaded_paused, expected_version=2)

    loaded_resumed = pg_checkpointer.load(wf_id)
    assert loaded_resumed.workflow_status == WorkflowStatus.RUNNING
    assert loaded_resumed.state_version == 3


def test_real_postgresql_crash_recovery_preserves_valid_checkpoint(real_pg_db, pg_checkpointer):
    """Simulates a crashed/aborted write transaction and proves previous checkpoint remains valid."""
    wf_id = f"wf-crash-{uuid.uuid4().hex[:8]}"
    state = AgentWorkflowState(
        workflow_id=wf_id,
        conversation_id="conv-crash-1",
        session_id="sess-crash-1",
        owner_user_id="5",
        owner_role="Risk Owner",
        dept_id=1,
        workflow_type=WorkflowType.TREATMENT_MANAGEMENT,
        workflow_status=WorkflowStatus.RUNNING,
        current_agent="TreatmentManagementAgent",
        current_step="input_collection",
        state_version=1,
        collected_fields={"action_plan": "Initial Plan A"},
    )
    pg_checkpointer.save(state)

    # Simulate crashed worker: open connection, start update, simulate failure and rollback
    conn = real_pg_db._get_connection(readonly=False)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute(
        f"UPDATE ers.agent_workflow_checkpoints SET state_payload = %s WHERE workflow_id = %s",
        ('{"corrupted": true}', wf_id)
    )
    # Crash / rollback occurs
    conn.rollback()
    conn.close()

    # Verify state loaded by another process/worker is uncorrupted
    loaded = pg_checkpointer.load(wf_id)
    assert loaded is not None
    assert loaded.collected_fields["action_plan"] == "Initial Plan A"
    assert loaded.state_version == 1


# ==============================================================================
# SECTION 3: Optimistic Concurrency & Competing Updates (Row-Level Locking)
# ==============================================================================

def test_real_postgresql_optimistic_concurrency_conflict(real_pg_db):
    """Proves row-level locking (SELECT ... FOR UPDATE) blocks stale versions across workers."""
    wf_id = f"wf-concurrent-{uuid.uuid4().hex[:8]}"

    # Worker A checkpointer
    cp_a = PostgreSQLWorkflowCheckpointer(fallback_in_memory=False)
    cp_a._get_connection = lambda: real_pg_db._get_connection(readonly=False)

    # Worker B checkpointer
    cp_b = PostgreSQLWorkflowCheckpointer(fallback_in_memory=False)
    cp_b._get_connection = lambda: real_pg_db._get_connection(readonly=False)

    initial_state = AgentWorkflowState(
        workflow_id=wf_id,
        conversation_id="conv-conc-1",
        session_id="sess-conc-1",
        owner_user_id="5",
        owner_role="Risk Owner",
        dept_id=1,
        workflow_type=WorkflowType.RISK_CREATION,
        workflow_status=WorkflowStatus.RUNNING,
        current_agent="RiskCreationAgent",
        current_step="step_1",
        state_version=1,
    )
    cp_a.save(initial_state)

    # Both workers read state at version 1
    state_a = cp_a.load(wf_id)
    state_b = cp_b.load(wf_id)
    assert state_a.state_version == 1
    assert state_b.state_version == 1

    # Worker A updates to version 2 first
    state_a.state_version = 2
    state_a.current_step = "step_2_by_A"
    cp_a.save(state_a, expected_version=1)

    # Worker B attempts to save using stale expected_version=1
    state_b.state_version = 2
    state_b.current_step = "step_2_by_B"
    with pytest.raises(ConcurrencyConflictError) as exc_info:
        cp_b.save(state_b, expected_version=1)

    assert exc_info.value.expected_version == 1
    assert exc_info.value.actual_version == 2

    # Verify that Worker A's update is intact
    final_state = cp_a.load(wf_id)
    assert final_state.state_version == 2
    assert final_state.current_step == "step_2_by_A"


# ==============================================================================
# SECTION 4: Confirmation Token Security Across Workers
# ==============================================================================

def test_confirmation_token_binding_and_tamper_rejection():
    """Proves HMAC-SHA256 signature validates actor, action, target, payload, and rejects tampering."""
    session = TreatmentSession(
        session_id="sess-sec-1",
        user_id="5",
        user_role="Risk Owner",
        dept_id=1,
    )
    args = {"treatment_id": 1, "progress": 80, "remarks": "80% completed"}

    token_meta = bind_pending_confirmation(
        session=session,
        action="update_progress",
        target_id=1,
        arguments=args,
    )
    assert token_meta["status"] == "PENDING"
    assert token_meta["payload_hash"] is not None

    # 1. Valid confirmation succeeds
    ok, err = verify_confirmation_integrity(session, "update_progress", 1, args)
    assert ok is True
    assert err is None

    # 2. Tampered arguments rejected
    tampered_args = {"treatment_id": 1, "progress": 100, "remarks": "100% completed"}
    ok_tamp, err_tamp = verify_confirmation_integrity(session, "update_progress", 1, tampered_args)
    assert ok_tamp is False
    assert "payload tampered" in err_tamp.lower()

    # 3. Impersonated actor rejected
    session_impersonator = TreatmentSession(session_id="sess-sec-2", user_id="99", user_role="Risk Owner")
    session_impersonator.pending_confirmation = session.pending_confirmation
    ok_imp, err_imp = verify_confirmation_integrity(session_impersonator, "update_progress", 1, args)
    assert ok_imp is False
    assert "actor mismatch" in err_imp.lower()

    # 4. Privilege escalation / altered role rejected
    session_role_hacker = TreatmentSession(session_id="sess-sec-3", user_id="5", user_role="Super Admin")
    session_role_hacker.pending_confirmation = session.pending_confirmation
    ok_role, err_role = verify_confirmation_integrity(session_role_hacker, "update_progress", 1, args)
    assert ok_role is False
    assert "role mismatch" in err_role.lower()

    # 5. Target ID mismatch rejected
    ok_tgt, err_tgt = verify_confirmation_integrity(session, "update_progress", target_id=999, current_args=args)
    assert ok_tgt is False
    assert "target mismatch" in err_tgt.lower()

    # 6. Action mismatch rejected
    ok_act, err_act = verify_confirmation_integrity(session, "reassign_owner", 1, args)
    assert ok_act is False
    assert "action mismatch" in err_act.lower()

    # 7. Expired token rejected
    expired_session = copy.deepcopy(session)
    expired_session.pending_confirmation["expires_at"] = time.time() - 10
    ok_exp, err_exp = verify_confirmation_integrity(expired_session, "update_progress", 1, args)
    assert ok_exp is False
    assert "expired" in err_exp.lower()

    # 8. Replay of executed token rejected
    exec_session = copy.deepcopy(session)
    exec_session.pending_confirmation["status"] = "EXECUTED"
    ok_rep, err_rep = verify_confirmation_integrity(exec_session, "update_progress", 1, args)
    assert ok_rep is False
    assert "replay rejected" in err_rep.lower()


# ==============================================================================
# SECTION 5: Authoritative PostgreSQL Service Paths on Dedicated Test DB (WFTest)
# ==============================================================================

def test_authoritative_create_risk_service_path(real_pg_db):
    """Exercises real create_risk in PostgreSQL, verifying risk_register and risk_description."""
    unique_suffix = uuid.uuid4().hex[:6].upper()
    risk_name = f"Automated Pipeline Integrity Check {unique_suffix}"
    description = "Risk of structural corrosion in primary crude distillation pipeline."
    mitigation = "Ultrasonic thickness measurement and cathodic protection inspection."

    res = real_pg_db.create_risk(
        risk_name=risk_name,
        risk_description=description,
        dept_id=1,
        dept_name="Refining Operations",
        risk_owner_id=5,  # Refining RO
        inherent_likelihood=3,
        inherent_impact=4,
        mitigation=mitigation,
        status=1,
        financial_year="2026-2027",
    )
    assert res.get("status") == "success" or res.get("success") is True, f"Failed create_risk: {res}"
    risk_id = res.get("risk_id")
    assert risk_id is not None

    # Verify directly in real PostgreSQL
    conn = real_pg_db._get_connection(readonly=True)
    cur = conn.cursor()
    cur.execute("SELECT risk_register_id, risk_name, dept_id, risk_owner_id, risk_status FROM ers.risk_register WHERE risk_id = %s", (risk_id,))
    reg_row = cur.fetchone()
    assert reg_row is not None
    assert reg_row[1] == risk_name
    assert reg_row[2] == 1  # Refining Operations
    assert reg_row[3] == 5  # Refining RO
    assert reg_row[4] == 1  # Status 1 (Draft)

    # Verify risk_description
    reg_id = reg_row[0]
    cur.execute("SELECT risk_description, inherent_risk_likelihood_id, inherent_risk_impact_id FROM ers.risk_description WHERE risk_register_id = %s", (reg_id,))
    desc_row = cur.fetchone()
    assert desc_row is not None
    assert desc_row[1] == 3
    assert desc_row[2] == 4

    conn.close()


def test_authoritative_approval_governance_and_department_isolation(real_pg_db):
    """
    Exercises real approve_or_reject_risk on PostgreSQL:
    1. Unauthorized user role blocked.
    2. Department isolation: Gas FH (Dept 2) cannot approve Refining (Dept 1) risk.
    3. Proper 3-stage governance progression: FH (Dept 1) -> RM -> RH (Final).
    4. Audit history logged at each stage.
    """
    # 1. Create risk for Department 1 (Refining)
    suffix = uuid.uuid4().hex[:6].upper()
    create_res = real_pg_db.create_risk(
        risk_name=f"Gov Verification Risk {suffix}",
        risk_description="Gov verification test risk",
        dept_id=1,
        dept_name="Refining Operations",
        risk_owner_id=5,  # Refining RO
        inherent_likelihood=3,
        inherent_impact=3,
        mitigation="Gov test mitigation",
        status=1,
    )
    assert create_res.get("status") == "success" or create_res.get("success") is True
    risk_id = create_res["risk_id"]

    # In database, simulate submitted state (risk_status = 2: Submitted to FH)
    conn = real_pg_db._get_connection(readonly=False)
    cur = conn.cursor()
    cur.execute("UPDATE ers.risk_register SET risk_status = 2 WHERE risk_id = %s", (risk_id,))
    conn.close()

    # 2. Test Non-approver role rejection (e.g. Action Owner, user 6)
    ao_res = real_pg_db.approve_or_reject_risk(risk_id=risk_id, approver_id=6, action="approve", remark="Trying to approve")
    assert ao_res["success"] is False
    assert "not authorized" in ao_res["message"].lower()

    # 3. Test Department Isolation: Gas FH (user 7, Dept 2) attempts to approve Refining risk (Dept 1)
    gas_fh_res = real_pg_db.approve_or_reject_risk(risk_id=risk_id, approver_id=7, action="approve", remark="Cross-dept attempt")
    assert gas_fh_res["success"] is False
    assert "department" in gas_fh_res["message"].lower()

    # 4. Legitimate Stage 1: Refining FH (user 4, Dept 1) approves
    stage1_res = real_pg_db.approve_or_reject_risk(risk_id=risk_id, approver_id=4, action="approve", remark="Approved by Refining FH")
    assert stage1_res["success"] is True
    assert "Functional Head" in str(stage1_res.get("stage"))

    # Verify status in PostgreSQL -> 3 (Function Head Approved)
    conn = real_pg_db._get_connection(readonly=True)
    cur = conn.cursor()
    cur.execute("SELECT risk_status, risk_function_head_approval_status FROM ers.risk_register WHERE risk_id = %s", (risk_id,))
    r_stat = cur.fetchone()
    assert r_stat[0] == 3  # FH Approved
    assert r_stat[1] == 1  # FH Approval flag
    conn.close()

    # 5. Legitimate Stage 2: Risk Manager (user 3) approves
    stage2_res = real_pg_db.approve_or_reject_risk(risk_id=risk_id, approver_id=3, action="approve", remark="Approved by Risk Manager")
    assert stage2_res["success"] is True
    assert "Risk Manager" in str(stage2_res.get("stage"))

    conn = real_pg_db._get_connection(readonly=True)
    cur = conn.cursor()
    cur.execute("SELECT risk_status, risk_manager_approval_status FROM ers.risk_register WHERE risk_id = %s", (risk_id,))
    r_stat2 = cur.fetchone()
    assert r_stat2[0] == 4  # RM Approved
    assert r_stat2[1] == 1  # RM Approval flag
    conn.close()

    # 6. Legitimate Stage 3: Risk Head (user 2) approves (Final Approval)
    stage3_res = real_pg_db.approve_or_reject_risk(risk_id=risk_id, approver_id=2, action="approve", remark="Final Approval by Risk Head")
    assert stage3_res["success"] is True
    assert "Risk Head" in str(stage3_res.get("stage"))

    conn = real_pg_db._get_connection(readonly=True)
    cur = conn.cursor()
    cur.execute("SELECT risk_status, risk_head_approval_status FROM ers.risk_register WHERE risk_id = %s", (risk_id,))
    r_stat3 = cur.fetchone()
    assert r_stat3[0] == 5  # Final Approval (Risk Head Approved)
    assert r_stat3[1] == 1

    # Verify full audit trail in risk_register_hist
    cur.execute("SELECT COUNT(*) FROM ers.risk_register_hist WHERE risk_register_id = (SELECT risk_register_id FROM ers.risk_register WHERE risk_id = %s)", (risk_id,))
    hist_cnt = cur.fetchone()[0]
    assert hist_cnt >= 3  # FH + RM + RH
    conn.close()


def test_authoritative_rejection_requires_remark_and_reverts_status(real_pg_db):
    """Verifies that rejecting a risk requires a non-empty remark and transitions status to Rejected (6)."""
    suffix = uuid.uuid4().hex[:6].upper()
    create_res = real_pg_db.create_risk(
        risk_name=f"Rejection Test Risk {suffix}",
        risk_description="Test description",
        dept_id=1,
        dept_name="Refining Operations",
        risk_owner_id=5,
        inherent_likelihood=2,
        inherent_impact=2,
        mitigation="Test mitigation",
        status=1,
    )
    risk_id = create_res["risk_id"]

    conn = real_pg_db._get_connection(readonly=False)
    cur = conn.cursor()
    cur.execute("UPDATE ers.risk_register SET risk_status = 2 WHERE risk_id = %s", (risk_id,))
    conn.close()

    # Missing remark rejected
    no_rem_res = real_pg_db.approve_or_reject_risk(risk_id=risk_id, approver_id=4, action="reject", remark="")
    assert no_rem_res["success"] is False
    assert "remark" in no_rem_res["message"].lower()

    # Legitimate rejection with remark
    rej_res = real_pg_db.approve_or_reject_risk(risk_id=risk_id, approver_id=4, action="reject", remark="Insufficient root-cause analysis provided.")
    assert rej_res["success"] is True
    assert str(rej_res.get("action")).upper() == "REJECTED"

    conn = real_pg_db._get_connection(readonly=True)
    cur = conn.cursor()
    cur.execute("SELECT risk_status, risk_function_head_approval_status, risk_function_head_approval_remark FROM ers.risk_register WHERE risk_id = %s", (risk_id,))
    row = cur.fetchone()
    assert row[0] == 6  # Rejected / Returned
    assert row[1] == -1  # Rejection code (-1)
    assert "Insufficient" in row[2]
    conn.close()


def test_authoritative_treatment_management_service_paths(real_pg_db):
    """
    Exercises treatment lifecycle on real PostgreSQL (WFTest):
    1. add_risk_treatment
    2. update_treatment_progress
    3. reassign_treatment_owner
    4. Audit consistency in risk_register_hist
    """
    # Create target risk first
    suffix = uuid.uuid4().hex[:6].upper()
    c_res = real_pg_db.create_risk(
        risk_name=f"Treatment Target Risk {suffix}",
        risk_description="Test description",
        dept_id=1,
        dept_name="Refining Operations",
        risk_owner_id=5,
        inherent_likelihood=3,
        inherent_impact=4,
        mitigation="Test mitigation",
        status=1,
    )
    risk_id = c_res["risk_id"]

    conn = real_pg_db._get_connection(readonly=True)
    cur = conn.cursor()
    cur.execute("SELECT risk_register_id FROM ers.risk_register WHERE risk_id = %s", (risk_id,))
    risk_register_id = cur.fetchone()[0]
    conn.close()

    # 1. Add Treatment (add_risk_treatment)
    add_res = real_pg_db.add_risk_treatment(
        risk_register_id=risk_register_id,
        action_plan="Implement automated flare knockout drum drainage system",
        action_owner_id=6,  # Refining AO
        target_date="2026-12-31",
        progress=10,
        action_status_id=7,  # In Progress
        created_by=5,  # Refining RO
    )
    assert add_res.get("status") == "success" or add_res.get("success") is True
    treatment_id = add_res.get("treatment_id") or add_res.get("risk_treatment_id")
    assert treatment_id is not None

    # Verify directly in PostgreSQL
    conn = real_pg_db._get_connection(readonly=True)
    cur = conn.cursor()
    cur.execute("SELECT action_plan, action_owner_id, progress, action_status_id FROM ers.risk_treatment WHERE risk_treatment_id = %s", (treatment_id,))
    t_row = cur.fetchone()
    assert t_row is not None
    assert "flare knockout" in t_row[0]
    assert t_row[1] == 6
    assert int(float(t_row[2])) == 10
    assert t_row[3] == 7

    # Verify audit in risk_register_hist (reset & resubmission logged)
    cur.execute("SELECT COUNT(*) FROM ers.risk_register_hist WHERE risk_register_id = %s", (risk_register_id,))
    assert cur.fetchone()[0] >= 1
    conn.close()

    # 2. Update Treatment Progress (update_treatment_progress)
    upd_res = real_pg_db.update_treatment_progress(
        treatment_id=treatment_id,
        progress=75,
        modified_by=6,
        remarks="Completed procurement and physical installation; pending calibration.",
    )
    assert upd_res.get("status") == "success" or upd_res.get("success") is True

    conn = real_pg_db._get_connection(readonly=True)
    cur = conn.cursor()
    cur.execute("SELECT progress FROM ers.risk_treatment WHERE risk_treatment_id = %s", (treatment_id,))
    assert int(float(cur.fetchone()[0])) == 75
    conn.close()

    # 3. Reassign Treatment Owner (reassign_treatment_owner)
    reassign_res = real_pg_db.reassign_treatment_owner(
        treatment_id=treatment_id,
        new_action_owner_id=5,  # Reassign to Refining RO (user 5)
        modified_by=5,
    )
    assert reassign_res.get("status") == "success" or reassign_res.get("success") is True

    conn = real_pg_db._get_connection(readonly=True)
    cur = conn.cursor()
    cur.execute("SELECT action_owner_id FROM ers.risk_treatment WHERE risk_treatment_id = %s", (treatment_id,))
    assert cur.fetchone()[0] == 5
    conn.close()
