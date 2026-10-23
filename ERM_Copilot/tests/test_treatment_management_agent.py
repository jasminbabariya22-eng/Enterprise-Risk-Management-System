"""
Enterprise Risk Management (ERM) - Comprehensive Treatment Management Agent Test Suite.
Verifies:
1. Parsers & Entity Extractors (dates, percentages, risk IDs, treatment IDs)
2. Intent Triggers (add, update progress, reassign owner, list, inspect details)
3. Multi-turn Guided Action Plan Addition Flow
4. Single-turn Autonomous Goal Execution (all parameters in initial message)
5. Treatment Progress Updates (including milestone % and status transitions)
6. Action Owner Reassignment
7. Treatment Listing & Scoped Inspection
8. Security & Governance: Fail-closed authentication, missing role, read-only auditor block, and department isolation
9. Confirmation Anti-Tamper & Single-Use Replay Protection
10. Session Cancellation & In-Memory / Checkpoint Cleanup
11. Legacy Forwarder & Package Import Compatibility
"""
import copy
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

# Ensure root workspace is on path
root_dir = str(Path(__file__).resolve().parents[2])
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from ERM_Copilot.agents.treatment import (
    TreatmentManagementAgent,
    treatment_management_agent,
    TreatmentGoal,
    TreatmentWorkflowState,
    TreatmentSession,
    parse_date_string,
    parse_progress_percentage,
    extract_risk_identifier,
    extract_treatment_id,
    extract_treatment_inputs,
    is_add_treatment_trigger,
    is_update_progress_trigger,
    is_reassign_owner_trigger,
    is_list_treatments_trigger,
    is_show_details_trigger,
    is_user_cancelling,
    is_user_confirming,
    validate_treatment_action,
    bind_pending_confirmation,
    execute_confirmed_treatment_decision,
    verify_confirmation_integrity,
    compute_confirmation_digest,
)
from ERM_Copilot.models.contracts import AgentRequest
from ERM_Copilot.services.db_service import erm_db


class TestTreatmentManagementAgent(unittest.TestCase):
    """Test suite for upgraded TreatmentManagementAgent."""

    @classmethod
    def setUpClass(cls):
        try:
            conn = erm_db._get_connection()
            conn.close()
        except Exception as e:
            raise unittest.SkipTest(f"Live PostgreSQL database not available: {e}")

    def setUp(self):
        self.agent = TreatmentManagementAgent()
        for k in ["test_user_ao", "single_turn_user", "progress_updater", "reassigner_user", "canceller_user", "8"]:
            self.agent.clear_session(k)
        self.user_id = 8
        self.dept_id = 2
        self.dept_name = "Gas Processing Facilities"
        self.metadata = {
            "role": "Risk Owner",
            "user_id": str(self.user_id),
            "dept_id": self.dept_id,
            "dept_name": self.dept_name
        }

    # -----------------------------------------------------------------
    # 1. PARSERS & EXTRACTORS
    # -----------------------------------------------------------------
    def test_parsers(self):
        """Test extraction of risk codes, treatment IDs, dates, and percentages."""
        self.assertEqual(extract_risk_identifier("Add action plan for RSK-GAS-049"), "RSK-GAS-049")
        self.assertEqual(extract_risk_identifier("Attach treatment to risk #49"), "49")

        self.assertEqual(extract_treatment_id("Update progress of treatment #12 to 80%"), 12)
        self.assertEqual(extract_treatment_id("Change action plan TRT-5"), 5)

        self.assertEqual(parse_progress_percentage("75%"), 75)
        self.assertEqual(parse_progress_percentage("progress is 100%"), 100)

        d1 = parse_date_string("2026-12-31")
        self.assertEqual(d1, "2026-12-31")

        d2 = parse_date_string("+60 days")
        self.assertIsNotNone(d2)
        self.assertEqual(len(d2), 10)

    # -----------------------------------------------------------------
    # 2. INTENT TRIGGERS
    # -----------------------------------------------------------------
    def test_triggers(self):
        """Verify regex and keyword intent trigger matching."""
        self.assertTrue(self.agent.is_add_treatment_trigger("Add new action plan to risk"))
        self.assertTrue(self.agent.is_add_treatment_trigger("Create treatment for RSK-GAS-002"))

        self.assertTrue(self.agent.is_update_progress_trigger("Update progress of treatment #2 to 50%"))
        self.assertTrue(self.agent.is_reassign_owner_trigger("Reassign action owner of treatment #2 to Deepak Chauhan"))
        self.assertTrue(self.agent.is_list_treatments_trigger("Show action plans for RSK-GAS-002"))
        self.assertTrue(self.agent.is_treatment_trigger("Show treatment details for TRT-5"))

    # -----------------------------------------------------------------
    # 3. MULTI-TURN ADD TREATMENT WORKFLOW
    # -----------------------------------------------------------------
    def test_add_treatment_multi_turn_flow(self):
        """Complete conversational flow to attach an action plan to a risk."""
        u_id = "test_user_ao"
        req_meta = {
            "role": "Risk Owner",
            "user_id": u_id,
            "dept_id": self.dept_id,
            "dept_name": self.dept_name
        }

        # Step 0: User triggers Add Action Plan with Risk ID
        r0 = AgentRequest(
            message="Add action plan to risk RSK-GAS-002",
            user_id=u_id,
            metadata=req_meta
        )
        res0 = self.agent.process(r0)
        self.assertTrue(self.agent.is_session_active(u_id))
        self.assertIn("Action Plan Details", res0.response)

        # Step 1: Select Action Plan suggestion (Option 1)
        r1 = AgentRequest(message="Option 1", user_id=u_id, metadata=req_meta)
        res1 = self.agent.process(r1)
        self.assertIn("Assign Action Owner", res1.response)

        # Step 2: Assign Action Owner
        r2 = AgentRequest(message="Assign Action Owner Deepak Chauhan", user_id=u_id, metadata=req_meta)
        res2 = self.agent.process(r2)
        # Should show review/confirmation preview because defaults (+30d, 0%) are applied
        self.assertIn("Action Plan Review", res2.response)
        self.assertIn("Confirm", res2.response)

        # Step 3: Confirm & Save to DB
        r3 = AgentRequest(message="Confirm and Save", user_id=u_id, metadata=req_meta)
        res3 = self.agent.process(r3)
        self.assertIn("Action Plan Successfully Added", res3.response)
        self.assertFalse(self.agent.is_session_active(u_id))

    # -----------------------------------------------------------------
    # 4. SINGLE-TURN ALL FIELDS PROVIDED
    # -----------------------------------------------------------------
    def test_add_treatment_single_turn_all_fields(self):
        """When user provides all required fields in the very first turn, proceed immediately to confirmation."""
        u_id = "single_turn_user"
        msg = "Add action plan for RSK-GAS-002: inspect compressor seal skids and replace seals, assign it to Deepak Chauhan, target it in 60 days, and start at 0%."
        req = AgentRequest(
            message=msg,
            user_id=u_id,
            metadata={
                "role": "Risk Owner",
                "user_id": u_id,
                "dept_id": self.dept_id,
                "dept_name": self.dept_name
            }
        )
        res = self.agent.process(req)
        # Agent should directly display the confirmation preview card without asking redundant questions
        self.assertIn("Action Plan Review", res.response)
        self.assertIn("inspect compressor seal skids", res.response)
        self.assertIn("Deepak Chauhan", res.response)
        self.assertTrue(self.agent.is_session_active(u_id))

    # -----------------------------------------------------------------
    # 5. UPDATE TREATMENT PROGRESS
    # -----------------------------------------------------------------
    def test_update_treatment_progress(self):
        """Update progress on an existing treatment with confirmation and remark."""
        u_id = "progress_updater"
        req_meta = {
            "role": "Risk Owner",
            "user_id": u_id,
            "dept_id": self.dept_id,
            "dept_name": self.dept_name
        }

        # Step 1: Request progress update
        r1 = AgentRequest(
            message="Update progress of treatment #5 to 75% with remark: NDT inspection completed",
            user_id=u_id,
            metadata=req_meta
        )
        res1 = self.agent.process(r1)
        self.assertIn("Confirm Treatment Progress Update", res1.response)
        self.assertIn("75%", res1.response)
        self.assertTrue(self.agent.is_session_active(u_id))

        # Step 2: Confirm update
        r2 = AgentRequest(message="Confirm", user_id=u_id, metadata=req_meta)
        res2 = self.agent.process(r2)
        self.assertIn("Treatment Progress Updated", res2.response)
        self.assertFalse(self.agent.is_session_active(u_id))

    # -----------------------------------------------------------------
    # 6. REASSIGN ACTION OWNER
    # -----------------------------------------------------------------
    def test_reassign_action_owner(self):
        """Reassign designated action owner on an existing treatment."""
        u_id = "reassigner_user"
        req_meta = {
            "role": "Risk Owner",
            "user_id": u_id,
            "dept_id": self.dept_id,
            "dept_name": self.dept_name
        }

        r1 = AgentRequest(
            message="Reassign action owner of treatment #5 to Deepak Chauhan",
            user_id=u_id,
            metadata=req_meta
        )
        res1 = self.agent.process(r1)
        self.assertIn("Confirm Action Owner Reassignment", res1.response)
        self.assertIn("Deepak Chauhan", res1.response)
        self.assertTrue(self.agent.is_session_active(u_id))

        r2 = AgentRequest(message="Confirm", user_id=u_id, metadata=req_meta)
        res2 = self.agent.process(r2)
        self.assertIn("Action Owner Successfully Reassigned", res2.response)
        self.assertFalse(self.agent.is_session_active(u_id))

    # -----------------------------------------------------------------
    # 7. LIST TREATMENTS & VIEW DETAILS
    # -----------------------------------------------------------------
    def test_list_and_details_treatments(self):
        """User can list active action plans for a specific risk and inspect details."""
        # List treatments
        r_list = AgentRequest(
            message="Show action plans for RSK-GAS-002",
            user_id="8",
            metadata=self.metadata
        )
        res_list = self.agent.process(r_list)
        self.assertIn("Active Action Plans", res_list.response)
        self.assertIn("RSK-GAS-002", res_list.response)

        # Show details
        r_det = AgentRequest(
            message="Show treatment details for TRT-5",
            user_id="8",
            metadata=self.metadata
        )
        res_det = self.agent.process(r_det)
        self.assertIn("Treatment #5 Details", res_det.response)

    # -----------------------------------------------------------------
    # 8. SECURITY & GOVERNANCE: FAIL CLOSED CHECKS
    # -----------------------------------------------------------------
    def test_security_fail_closed_unauthenticated(self):
        """Missing authenticated user ID must fail closed."""
        req = AgentRequest(
            message="Add action plan to risk RSK-GAS-002",
            user_id="",
            metadata={"role": "Risk Owner"}
        )
        res = self.agent.process(req)
        self.assertFalse(res.success)
        self.assertEqual(res.metadata.get("intent"), "AUTH_FAILURE")
        self.assertIn("Authentication Failure", res.response)

    def test_security_fail_closed_missing_role(self):
        """Missing authenticated role must fail closed."""
        req = AgentRequest(
            message="Add action plan to risk RSK-GAS-002",
            user_id="99",
            metadata={"user_id": "99", "role": ""}
        )
        res = self.agent.process(req)
        self.assertFalse(res.success)
        self.assertEqual(res.metadata.get("intent"), "ROLE_MISSING")
        self.assertIn("Authorization Failure", res.response)

    def test_security_read_only_auditor_blocked(self):
        """Auditor role cannot create, update, or reassign treatments."""
        req = AgentRequest(
            message="Add action plan for RSK-GAS-002: install new pressure safety valves, assign to Deepak Chauhan",
            user_id="101",
            metadata={"user_id": "101", "role": "Auditor", "dept_id": self.dept_id}
        )
        res = self.agent.process(req)
        self.assertIn("Action Blocked by Governance Policy", res.response)
        self.assertIn("Auditor", res.response)

    def test_security_cross_department_blocked(self):
        """Non-enterprise role in Dept #3 cannot attach action plan to Dept #2 risk."""
        req = AgentRequest(
            message="Add action plan for RSK-GAS-002: install vibration monitors, assign to Deepak Chauhan",
            user_id="102",
            metadata={"user_id": "102", "role": "Risk Owner", "dept_id": 999}
        )
        res = self.agent.process(req)
        self.assertIn("Department Isolation", res.response)

    # -----------------------------------------------------------------
    # 9. CONFIRMATION ANTI-TAMPER & REPLAY PROTECTION
    # -----------------------------------------------------------------
    def test_confirmation_anti_tamper_and_replay(self):
        """Test SHA-256 confirmation digest verification and single-use replay protection."""
        session = TreatmentSession(
            session_id="tamper_test_session",
            user_id="8",
            user_role="Risk Owner",
            dept_id=2,
            dept_name="Gas Processing Facilities",
            goal=TreatmentGoal.UPDATE_PROGRESS,
            treatment_id=5,
            progress=50
        )
        conf = bind_pending_confirmation(
            session=session,
            action="update_treatment_progress",
            target_id=5,
            arguments={"progress": 50, "treatment_id": 5}
        )
        self.assertIsNotNone(conf.get("payload_hash"))

        # Valid arguments verification
        valid, err = verify_confirmation_integrity(
            session=session,
            action="update_treatment_progress",
            target_id=5,
            current_args={"progress": 50, "treatment_id": 5}
        )
        self.assertTrue(valid)
        self.assertIsNone(err)

        # Tampered argument (progress secretly changed from 50 to 99)
        tampered_valid, tampered_err = verify_confirmation_integrity(
            session=session,
            action="update_treatment_progress",
            target_id=5,
            current_args={"progress": 99, "treatment_id": 5}
        )
        self.assertFalse(tampered_valid)
        self.assertIn("tampered", tampered_err.lower())

        # Replay protection: once executed, token cannot be re-verified
        session.pending_confirmation["status"] = "EXECUTED"
        replay_valid, replay_err = verify_confirmation_integrity(
            session=session,
            action="update_treatment_progress",
            target_id=5,
            current_args={"progress": 50, "treatment_id": 5}
        )
        self.assertFalse(replay_valid)
        self.assertIn("replay", replay_err.lower())

    # -----------------------------------------------------------------
    # 10. CANCELLATION
    # -----------------------------------------------------------------
    def test_cancellation(self):
        """User can cancel an in-progress treatment session."""
        u_id = "canceller_user"
        r0 = AgentRequest(message="Add action plan", user_id=u_id, metadata={"role": "Risk Owner", "user_id": u_id})
        self.agent.process(r0)
        self.assertTrue(self.agent.is_session_active(u_id))

        r_cancel = AgentRequest(message="cancel", user_id=u_id, metadata={"role": "Risk Owner", "user_id": u_id})
        res_cancel = self.agent.process(r_cancel)
        self.assertIn("Cancelled", res_cancel.response)
        self.assertFalse(self.agent.is_session_active(u_id))

    # -----------------------------------------------------------------
    # 11. BACKWARD COMPATIBILITY IMPORT TEST
    # -----------------------------------------------------------------
    def test_legacy_import_compatibility(self):
        """Ensure legacy module exports all expected symbols."""
        from ERM_Copilot.agents.treatment_management_agent import (
            TreatmentManagementAgent as LegacyAgent,
            treatment_management_agent as legacy_instance,
            TreatmentSession as LegacySession,
            TreatmentState as LegacyState,
            TreatmentGoal as LegacyGoal,
            parse_date_string as legacy_parse_date,
        )
        self.assertIs(LegacyAgent, TreatmentManagementAgent)
        self.assertIs(legacy_instance, treatment_management_agent)
        self.assertIs(LegacySession, TreatmentSession)
        self.assertIs(LegacyGoal, TreatmentGoal)


if __name__ == "__main__":
    unittest.main()
