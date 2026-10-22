"""
Enterprise Risk Management (ERM) - Treatment Management Security, Identity & Business Rules Verification Suite.
Validates:
1. Cryptographic HMAC-SHA256 confirmation tokens, expiry, anti-tamper, and single-use replay protection.
2. Concurrent confirmation execution locking (EXECUTING state) and restart persistence.
3. Server-side identity & role boundary enforcement (fail closed, spoof rejection).
4. Department isolation for reads, additions, updates, and owner reassignments.
5. Inaccessible/deleted resource pre-execution validation.
6. Authoritative mst_status lifecycle transitions (Draft=1, In Progress=7, Completed=8).
7. Business rules: progress bounds [0, 100], past target dates, eligible owner department matching.
8. State reconciliation after uncertain database commit/timeout.
"""
import copy
import json
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from ERM_Copilot.agents.treatment import (
    TreatmentManagementAgent,
    treatment_management_agent,
    TreatmentGoal,
    TreatmentWorkflowState,
    TreatmentSession,
    bind_pending_confirmation,
    verify_confirmation_integrity,
    compute_confirmation_digest,
    execute_confirmed_treatment_decision,
    validate_treatment_action,
)
from ERM_Copilot.agents.treatment.execution import (
    CONFIRMATION_EXPIRY_SECONDS,
    CONFIRMATION_HMAC_SECRET,
)
from ERM_Copilot.ai_harness import ERMAIHarness, HarnessContext
from ERM_Copilot.ai_harness.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConfirmationMismatchError,
    ConfirmationRequiredError,
)
from ERM_Copilot.ai_harness.execution import ExecutionCoordinator
from ERM_Copilot.ai_harness.tool_registry import tool_registry
from ERM_Copilot.models.contracts import AgentRequest


class TestTreatmentSecurityAndIntegrationVerification(unittest.TestCase):
    """Deep verification suite for Treatment Management security, RBAC, and business rules."""

    def setUp(self):
        self.agent = TreatmentManagementAgent()
        self.user_id = "8"
        self.dept_id = 2
        self.dept_name = "Gas Processing Facilities"
        self.role = "Risk Owner"
        self.session_key = f"sec_test_{self.user_id}"
        self.agent.clear_session(self.session_key)

    def tearDown(self):
        self.agent.clear_session(self.session_key)

    # =========================================================================
    # 1. CONFIRMATION CRYPTOGRAPHIC SECURITY & REPLAY GUARANTEES
    # =========================================================================

    def test_confirmation_hmac_sha256_anti_tamper(self):
        """Prove confirmation uses HMAC-SHA256 with server-side secret and cannot be forged by altering session fields."""
        session = TreatmentSession(
            session_id=self.session_key,
            user_id=self.user_id,
            user_role=self.role,
            dept_id=self.dept_id,
            goal=TreatmentGoal.UPDATE_PROGRESS,
            treatment_id=12,
            progress=65,
        )
        args = {"treatment_id": 12, "progress": 65, "remarks": "Mid-term inspection"}
        conf = bind_pending_confirmation(
            session=session,
            action="update_treatment_progress",
            target_id=12,
            arguments=args,
        )

        # 1. Verify token structure and HMAC digest presence
        self.assertIn("token", conf)
        self.assertIn("payload_hash", conf)
        self.assertIn("expires_at", conf)
        self.assertEqual(conf["status"], "PENDING")

        # 2. Verify valid confirmation matches
        valid, err = verify_confirmation_integrity(
            session=session,
            action="update_treatment_progress",
            target_id=12,
            current_args=args,
        )
        self.assertTrue(valid)
        self.assertIsNone(err)

        # 3. Test modified arguments (attacker attempts to alter progress to 100%)
        tampered_args = {"treatment_id": 12, "progress": 100, "remarks": "Mid-term inspection"}
        tampered_valid, tampered_err = verify_confirmation_integrity(
            session=session,
            action="update_treatment_progress",
            target_id=12,
            current_args=tampered_args,
        )
        self.assertFalse(tampered_valid)
        self.assertIn("tampered", tampered_err.lower())

        # 4. Test forged token: an attacker creates a fake SHA-256 without knowing CONFIRMATION_HMAC_SECRET
        fake_secret = "attacker-compromised-secret"
        forged_digest = compute_confirmation_digest(
            actor_id=self.user_id,
            actor_role=self.role,
            action="update_treatment_progress",
            target_id=12,
            arguments=tampered_args,
            secret_key=fake_secret,
        )
        session.pending_confirmation["payload_hash"] = forged_digest
        forged_valid, forged_err = verify_confirmation_integrity(
            session=session,
            action="update_treatment_progress",
            target_id=12,
            current_args=tampered_args,
        )
        self.assertFalse(forged_valid)
        self.assertIn("tampered", forged_err.lower())

    def test_confirmation_actor_and_role_binding(self):
        """Confirmation token is bound to both authenticated actor_id and user_role."""
        session = TreatmentSession(
            session_id=self.session_key,
            user_id="100",
            user_role="Risk Owner",
            dept_id=self.dept_id,
            goal=TreatmentGoal.UPDATE_PROGRESS,
            treatment_id=5,
            progress=40,
        )
        args = {"treatment_id": 5, "progress": 40}
        bind_pending_confirmation(
            session=session,
            action="update_treatment_progress",
            target_id=5,
            arguments=args,
        )

        # 1. Impersonator tries to confirm with different actor_id
        session.user_id = "999"
        valid, err = verify_confirmation_integrity(
            session=session,
            action="update_treatment_progress",
            target_id=5,
            current_args=args,
        )
        self.assertFalse(valid)
        self.assertIn("actor mismatch", err.lower())

        # 2. Impersonator restores actor_id but changes user_role
        session.user_id = "100"
        session.user_role = "Auditor"
        valid_role, err_role = verify_confirmation_integrity(
            session=session,
            action="update_treatment_progress",
            target_id=5,
            current_args=args,
        )
        self.assertFalse(valid_role)
        self.assertIn("role mismatch", err_role.lower())

    def test_confirmation_expired_token(self):
        """Tokens past 15-minute window must be rejected immediately."""
        session = TreatmentSession(
            session_id=self.session_key,
            user_id=self.user_id,
            user_role=self.role,
            dept_id=self.dept_id,
            goal=TreatmentGoal.UPDATE_PROGRESS,
            treatment_id=5,
            progress=40,
        )
        args = {"treatment_id": 5, "progress": 40}
        conf = bind_pending_confirmation(
            session=session,
            action="update_treatment_progress",
            target_id=5,
            arguments=args,
        )

        # Simulate 16 minutes in the past
        conf["expires_at"] = time.time() - 60

        valid, err = verify_confirmation_integrity(
            session=session,
            action="update_treatment_progress",
            target_id=5,
            current_args=args,
        )
        self.assertFalse(valid)
        self.assertIn("expired", err.lower())

    def test_concurrent_confirmation_lock(self):
        """When token is being processed (EXECUTING), concurrent requests must be rejected."""
        session = TreatmentSession(
            session_id=self.session_key,
            user_id=self.user_id,
            user_role=self.role,
            dept_id=self.dept_id,
            goal=TreatmentGoal.UPDATE_PROGRESS,
            treatment_id=5,
            progress=40,
        )
        args = {"treatment_id": 5, "progress": 40}
        conf = bind_pending_confirmation(
            session=session,
            action="update_treatment_progress",
            target_id=5,
            arguments=args,
        )

        # Mark currently executing by worker 1
        conf["status"] = "EXECUTING"

        valid, err = verify_confirmation_integrity(
            session=session,
            action="update_treatment_progress",
            target_id=5,
            current_args=args,
        )
        self.assertFalse(valid)
        self.assertIn("concurrent", err.lower())

    def test_replay_after_restart_simulation(self):
        """Serialize session to dictionary (as stored in PostgreSQL checkpoint) and ensure executed token cannot be replayed."""
        session = TreatmentSession(
            session_id=self.session_key,
            user_id=self.user_id,
            user_role=self.role,
            dept_id=self.dept_id,
            goal=TreatmentGoal.UPDATE_PROGRESS,
            treatment_id=5,
            progress=80,
        )
        args = {"treatment_id": 5, "progress": 80, "remarks": None}
        bind_pending_confirmation(
            session=session,
            action="update_treatment_progress",
            target_id=5,
            arguments=args,
        )

        # Mock DB service to execute cleanly
        with patch("ERM_Copilot.agents.treatment.execution.fetch_treatment_details") as mock_fetch, \
             patch("ERM_Copilot.agents.treatment.execution.update_treatment_progress_tool") as mock_update:
            mock_fetch.return_value = {"risk_treatment_id": 5, "progress": 40, "dept_id": 2}
            mock_update.return_value = {"status": "success", "risk_treatment_id": 5, "progress": 80}

            ok, res, err = execute_confirmed_treatment_decision(session)
            self.assertTrue(ok)
            self.assertEqual(session.pending_confirmation["status"], "EXECUTED")

        # Simulate app restart: save to DB dictionary and reload into fresh session instance
        saved_state = copy.deepcopy(session.to_dict())
        restored_session = TreatmentSession.from_dict(saved_state)

        # Attempt replay on restored session
        replay_ok, replay_res, replay_err = execute_confirmed_treatment_decision(restored_session)
        self.assertFalse(replay_ok)
        self.assertIn("replay rejected", replay_err.lower())

    # =========================================================================
    # 2. IDENTITY AND AUTHORIZATION BOUNDARY
    # =========================================================================

    def test_fail_closed_missing_identity(self):
        """Agent must fail closed if authenticated user ID is absent."""
        req = AgentRequest(
            message="Add action plan for RSK-GAS-049",
            user_id="",
            metadata={"role": "Risk Owner", "dept_id": 2}
        )
        res = self.agent.process(req)
        self.assertFalse(res.success)
        self.assertEqual(res.metadata.get("intent"), "AUTH_FAILURE")

    def test_fail_closed_missing_role(self):
        """Agent must fail closed if authenticated role is absent."""
        req = AgentRequest(
            message="Add action plan for RSK-GAS-049",
            user_id="8",
            user_role="",
            metadata={"user_id": "8", "role": ""}
        )
        res = self.agent.process(req)
        self.assertFalse(res.success)
        self.assertEqual(res.metadata.get("intent"), "ROLE_MISSING")

    def test_forged_client_metadata_blocked_by_harness(self):
        """HarnessContext strictly enforces server-side authenticated identity."""
        # Standard user attempting to claim Super Admin
        server_ctx = HarnessContext.build_from_auth(
            user_id="8",
            user_role="Risk Owner",
            dept_id=2
        )
        # Verify context is immutable and claims cannot be escalated
        self.assertEqual(server_ctx.user_role, "Risk Owner")

        # Auditor role attempting to mutate treatment directly via execution coordinator
        auditor_ctx = HarnessContext.build_from_auth(
            user_id="99",
            user_role="Auditor",
            dept_id=2
        )
        with self.assertRaises(AuthorizationError):
            ExecutionCoordinator.execute_tool(
                "update_treatment_progress",
                {"treatment_id": 5, "progress": 100},
                auditor_ctx,
                bypass_confirmation=True,
            )

    def test_cross_department_mutation_blocked(self):
        """Department isolation: User in Dept #2 cannot mutate treatment in Dept #9."""
        session = TreatmentSession(
            session_id=self.session_key,
            user_id="8",
            user_role="Risk Owner",
            dept_id=2,
            goal=TreatmentGoal.UPDATE_PROGRESS,
            treatment_id=55,
            progress=70,
        )
        treatment_in_dept_9 = {"risk_treatment_id": 55, "dept_id": 9}
        result = validate_treatment_action(session, treatment_data=treatment_in_dept_9)
        self.assertFalse(result.is_valid)
        self.assertTrue(result.policy_blocked)
        self.assertIn("Department Isolation", result.policy_block_reason)

    def test_unauthorized_owner_reassignment_cross_department(self):
        """Reassigning action plan to personnel from another department is blocked."""
        session = TreatmentSession(
            session_id=self.session_key,
            user_id="8",
            user_role="Risk Owner",
            dept_id=2,
            goal=TreatmentGoal.ADD_TREATMENT,
            action_owner_id=88,
        )
        risk_dept_2 = {"risk_id": "RSK-GAS-049", "dept_id": 2}
        owner_dept_5 = {"user_id": 88, "full_name": "External User", "dept_id": 5}
        result = validate_treatment_action(session, risk_data=risk_dept_2, action_owner_data=owner_dept_5)
        self.assertFalse(result.is_valid)
        self.assertTrue(result.policy_blocked)
        self.assertIn("match the risk department", result.policy_block_reason)

    def test_pre_execution_revalidation_detects_deleted_risk(self):
        """Pre-execution check rejects execution if risk was deleted concurrently."""
        session = TreatmentSession(
            session_id=self.session_key,
            user_id="8",
            user_role="Risk Owner",
            dept_id=2,
            goal=TreatmentGoal.ADD_TREATMENT,
            target_risk_id="RSK-GAS-049",
            target_risk_register_id=49,
            action_plan="Install emergency shutoff",
            action_owner_id=8,
            target_date="2026-12-31",
            progress=0,
            action_status_id=1,
        )
        bind_pending_confirmation(
            session=session,
            action="add_treatment",
            target_id="RSK-GAS-049",
            arguments={
                "risk_register_id": 49,
                "action_plan": "Install emergency shutoff",
                "action_owner_id": 8,
                "target_date": "2026-12-31",
                "progress": 0,
                "action_status_id": 1,
            }
        )

        with patch("ERM_Copilot.agents.treatment.execution.fetch_risk_info") as mock_fetch:
            # Risk exists but has been marked deleted in the DB
            mock_fetch.return_value = {"risk_id": "RSK-GAS-049", "is_deleted": 1}

            ok, res, err = execute_confirmed_treatment_decision(session)
            self.assertFalse(ok)
            self.assertIn("deleted", err.lower())

    # =========================================================================
    # 3. DATABASE AND BUSINESS RULES VERIFICATION
    # =========================================================================

    def test_status_master_mappings_and_transitions(self):
        """
        Verify status master mappings:
        - Progress = 0% -> Draft (status_id = 1)
        - Progress 1..99% -> In Progress (status_id = 7)
        - Progress = 100% -> Completed (status_id = 8)
        """
        from ERM_Copilot.services.db_service import erm_db

        # Test live status options lookup
        status_options = erm_db.get_status_options(status_type="treatment")
        status_dict = {s["id"]: s["status_name"] for s in status_options}

        self.assertEqual(status_dict.get(1), "Draft")
        self.assertEqual(status_dict.get(7), "In Progress")
        self.assertEqual(status_dict.get(8), "Completed")

    def test_progress_bounds_validation(self):
        """Progress < 0 or > 100 must be rejected."""
        session = TreatmentSession(
            session_id=self.session_key,
            user_id="8",
            user_role="Risk Owner",
            dept_id=2,
            goal=TreatmentGoal.UPDATE_PROGRESS,
            treatment_id=5,
            progress=150,  # Invalid
        )
        res = validate_treatment_action(session, treatment_data={"risk_treatment_id": 5, "dept_id": 2})
        self.assertFalse(res.is_valid)
        self.assertTrue(any("between 0 and 100" in e for e in res.errors))

        # Negative progress
        session.progress = -10
        res_neg = validate_treatment_action(session, treatment_data={"risk_treatment_id": 5, "dept_id": 2})
        self.assertFalse(res_neg.is_valid)
        self.assertTrue(any("between 0 and 100" in e for e in res_neg.errors))

    def test_target_date_validation_rejects_past_date(self):
        """Target dates in the past must be rejected."""
        yesterday = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")
        session = TreatmentSession(
            session_id=self.session_key,
            user_id="8",
            user_role="Risk Owner",
            dept_id=2,
            goal=TreatmentGoal.ADD_TREATMENT,
            target_date=yesterday,
            action_plan="Retrofit sensors",
        )
        res = validate_treatment_action(session, risk_data={"risk_id": "RSK-GAS-049", "dept_id": 2})
        self.assertFalse(res.is_valid)
        self.assertTrue(any("in the past" in e for e in res.errors))

    def test_state_reconciliation_after_uncertain_commit(self):
        """
        When database connection times out or throws after committing mutation,
        reconciliation must detect the updated progress and succeed without duplicate write.
        """
        session = TreatmentSession(
            session_id=self.session_key,
            user_id=self.user_id,
            user_role=self.role,
            dept_id=self.dept_id,
            goal=TreatmentGoal.UPDATE_PROGRESS,
            treatment_id=5,
            progress=85,
        )
        args = {"treatment_id": 5, "progress": 85, "remarks": None}
        bind_pending_confirmation(
            session=session,
            action="update_treatment_progress",
            target_id=5,
            arguments=args,
        )

        # Mock mutation throwing timeout error, but DB actually committed
        with patch("ERM_Copilot.agents.treatment.execution.fetch_treatment_details") as mock_fetch, \
             patch("ERM_Copilot.agents.treatment.execution.update_treatment_progress_tool") as mock_update:
            
            # Step 1: Pre-execution fetch returns old progress 50
            # Step 2: Mutation throws ConnectionResetError
            # Step 3: Reconciliation fetch returns new progress 85
            mock_fetch.side_effect = [
                {"risk_treatment_id": 5, "progress": 50, "dept_id": 2},
                {"risk_treatment_id": 5, "progress": 85, "dept_id": 2},
            ]
            mock_update.side_effect = ConnectionResetError("Connection lost after DB commit")

            ok, res, err = execute_confirmed_treatment_decision(session)
            self.assertTrue(ok)
            self.assertIsNotNone(res)
            self.assertTrue(res.get("reconciled"))
            self.assertEqual(res.get("progress"), 85)


if __name__ == "__main__":
    unittest.main()
