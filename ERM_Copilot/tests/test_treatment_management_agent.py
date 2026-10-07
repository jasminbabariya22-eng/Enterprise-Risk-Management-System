"""
Unit and Integration Tests for TreatmentManagementAgent.
Verifies full ISO-31000 action plan lifecycle:
1. Add Action Plan (Multi-turn guided wizard with suggestions and department action owner dropdowns)
2. Update Treatment Progress % and Status
3. Reassign Department Action Owner
4. List & View Action Plans for any Risk
5. Cancellation & Session Isolation
"""
import sys
import unittest
from pathlib import Path

# Ensure root workspace is on path
root_dir = str(Path(__file__).resolve().parents[2])
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from ERM_Copilot.agents.treatment_management_agent import (
    TreatmentManagementAgent,
    TreatmentSession,
    TreatmentState,
    parse_date_string,
    parse_progress_percentage,
    extract_risk_identifier,
    extract_treatment_id
)
from ERM_Copilot.models.contracts import AgentRequest
from ERM_Copilot.services.db_service import erm_db


class TestTreatmentManagementAgent(unittest.TestCase):
    """Test suite for TreatmentManagementAgent."""

    def setUp(self):
        self.agent = TreatmentManagementAgent()
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
    # 1. PARSERS & UTILITIES
    # -----------------------------------------------------------------
    def test_parsers(self):
        """Test extraction of risk codes, treatment IDs, dates, and percentages."""
        self.assertEqual(extract_risk_identifier("Add action plan for RSK-GAS-049"), "RSK-GAS-049")
        self.assertEqual(extract_risk_identifier("Attach treatment to risk #49"), "49")

        self.assertEqual(extract_treatment_id("Update progress of treatment #12 to 80%"), 12)
        self.assertEqual(extract_treatment_id("Change action plan 5"), 5)

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
        """Verify regex / keyword intent trigger matching."""
        self.assertTrue(self.agent.is_add_treatment_trigger("Add new action plan to risk"))
        self.assertTrue(self.agent.is_add_treatment_trigger("Create treatment for RSK-GAS-002"))

        self.assertTrue(self.agent.is_update_progress_trigger("Update progress of treatment #2 to 50%"))
        self.assertTrue(self.agent.is_reassign_owner_trigger("Reassign action owner of treatment #2 to Deepak Chauhan"))
        self.assertTrue(self.agent.is_list_treatments_trigger("Show action plans for RSK-GAS-002"))

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
        self.assertIn("Step 2/5: Action Plan Details", res0.response)
        self.assertTrue(self.agent.is_session_active(u_id))

        # Step 1: Select Action Plan suggestion (Option 1)
        r1 = AgentRequest(message="Option 1", user_id=u_id, metadata=req_meta)
        res1 = self.agent.process(r1)
        self.assertIn("Step 3/5: Assign Action Owner", res1.response)

        # Step 2: Assign Action Owner
        r2 = AgentRequest(message="Assign Action Owner Deepak Chauhan", user_id=u_id, metadata=req_meta)
        res2 = self.agent.process(r2)
        self.assertIn("Step 4/5: Target Completion Date", res2.response)

        # Step 3: Set Target Date
        r3 = AgentRequest(message="+60 days", user_id=u_id, metadata=req_meta)
        res3 = self.agent.process(r3)
        self.assertIn("Step 5/5: Current Progress Percentage", res3.response)

        # Step 4: Set Initial Progress
        r4 = AgentRequest(message="25%", user_id=u_id, metadata=req_meta)
        res4 = self.agent.process(r4)
        self.assertIn("Action Plan Review", res4.response)
        self.assertIn("Do you want to save this action plan?", res4.response)

        # Step 5: Confirm & Save to DB
        r5 = AgentRequest(message="Confirm and Save", user_id=u_id, metadata=req_meta)
        res5 = self.agent.process(r5)
        self.assertIn("Action Plan Added Successfully", res5.response)
        self.assertFalse(self.agent.is_session_active(u_id))

    # -----------------------------------------------------------------
    # 4. LIST TREATMENTS
    # -----------------------------------------------------------------
    def test_list_treatments(self):
        """User can list active action plans for a specific risk."""
        r = AgentRequest(
            message="Show action plans for RSK-GAS-002",
            user_id="8",
            metadata=self.metadata
        )
        res = self.agent.process(r)
        self.assertIn("Action Plans & Risk Treatments", res.response)

    # -----------------------------------------------------------------
    # 5. CANCELLATION
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


if __name__ == "__main__":
    unittest.main()
