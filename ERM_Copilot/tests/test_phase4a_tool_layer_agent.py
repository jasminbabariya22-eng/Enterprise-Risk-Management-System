"""
Phase 4A Test Suite: Real Tool Layer and Goal-Driven Risk Creation Agent.

Tests:
1. All required fields provided in initial message; unnecessary questions and tool calls skipped.
2. Only title and description provided; agent identifies remaining requirements.
3. Fields arrive in unusual order.
4. Agent selects owner-lookup tool only when useful.
5. Agent skips suggestions when user already supplied acceptable content.
6. Invalid rating rejected and never silently corrected.
7. Ineligible owner rejected.
8. Duplicate detection returns advisory results without changing database.
9. Tool returns a recoverable error and agent handles it safely.
10. Proposing unknown tool or invalid arguments fails validation in harness.
11. Forbidden or unauthorized tool call rejected by harness RBAC.
12. create_risk cannot be executed before explicit confirmation.
13. Modified draft invalidates stale confirmation evidence.
14. Repeated tool requests cannot cause an unbounded loop.
15. Checkpoint restoration preserves draft state and tool call history.
16. All 11 logical tools registered and executable through AI Harness.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from ERM_Copilot.agents.risk_creation.agent import RiskCreationAgent
from ERM_Copilot.agents.risk_creation.state import (
    RiskCreationSession,
    RiskCreationState,
)
from ERM_Copilot.agents.risk_creation.scoring import RiskMatrixCalculator
from ERM_Copilot.agents.risk_creation.payload import FinalRiskPayload, build_final_risk_payload
from ERM_Copilot.agents.risk_creation.validation import validate_risk_draft
from ERM_Copilot.ai_harness.confirmation import confirmation_manager
from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.ai_harness.exceptions import (
    AuthorizationError,
    ConfirmationMismatchError,
    ConfirmationRequiredError,
    ToolNotFoundError,
    ToolValidationError,
)
from ERM_Copilot.ai_harness.execution import ExecutionCoordinator
from ERM_Copilot.ai_harness.tool_registry import tool_registry
from ERM_Copilot.models.contracts import AgentRequest
from ERM_Copilot.services.db_service import erm_db


class TestPhase4AToolRegistry(unittest.TestCase):
    """Test registry and execution of all 11 canonical risk creation tools."""

    def setUp(self):
        self.context = HarnessContext.build_from_auth(
            user_id="101",
            user_role="Risk Owner",
            dept_id=2,
            dept_name="Gas Processing Facilities",
            session_id="test-registry-sess",
        )

    def test_tool_1_get_risk_creation_requirements(self):
        """Tool 1: get_risk_creation_requirements returns schema constraints and required fields."""
        res = ExecutionCoordinator.execute_tool(
            tool_name="get_risk_creation_requirements",
            arguments={"dept_id": 2},
            context=self.context,
        )
        self.assertTrue(res["success"])
        data = res["result"]
        self.assertEqual(data["status"], "success")
        self.assertIn("risk_name", data["required_user_fields"])
        self.assertIn("inherent_likelihood", data["required_user_fields"])
        self.assertIn("constraints", data)

    def test_tool_2_assess_risk_completeness(self):
        """Tool 2: assess_risk_completeness evaluates draft deterministically."""
        draft = {
            "risk_name": "Turbine Blade Crack",
            "risk_description": "Crack observed in HP turbine second stage rotor blade.",
        }
        res = ExecutionCoordinator.execute_tool(
            tool_name="assess_risk_completeness",
            arguments={"draft": draft, "dept_id": 2},
            context=self.context,
        )
        self.assertTrue(res["success"])
        data = res["result"]
        self.assertFalse(data["is_ready_for_review"])
        self.assertIn("inherent_likelihood", data["missing_required_fields"])
        self.assertIn("mitigation", data["missing_required_fields"])

    def test_tool_3_get_risk_reference_options(self):
        """Tool 3: get_risk_reference_options resolves dropdowns, statuses, and matrix criteria."""
        res = ExecutionCoordinator.execute_tool(
            tool_name="get_risk_reference_options",
            arguments={"dataset": "assessment_criteria"},
            context=self.context,
        )
        self.assertTrue(res["success"])
        data = res["result"]
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["dataset"], "assessment_criteria")
        self.assertEqual(len(data["likelihood_scales"]), 5)
        self.assertEqual(len(data["impact_scales"]), 5)

    def test_tool_4_get_eligible_risk_owners(self):
        """Tool 4: get_eligible_risk_owners looks up department action owners or co-owners."""
        res = ExecutionCoordinator.execute_tool(
            tool_name="get_eligible_risk_owners",
            arguments={"owner_type": "action_owner"},
            context=self.context,
        )
        self.assertTrue(res["success"])
        data = res["result"]
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["owner_type"], "action_owner")
        self.assertIn("owners", data)

    def test_tool_5_check_risk_duplicates(self):
        """Tool 5: check_risk_duplicates returns explainable advisory candidates."""
        res = ExecutionCoordinator.execute_tool(
            tool_name="check_risk_duplicates",
            arguments={"risk_title": "Compressor Gas Leakage"},
            context=self.context,
        )
        self.assertTrue(res["success"])
        data = res["result"]
        self.assertEqual(data["status"], "success")
        self.assertIn("candidates", data)
        self.assertIn("is_duplicate_suspected", data)

    def test_tool_6_generate_risk_description_suggestions(self):
        """Tool 6: generate_risk_description_suggestions returns curated suggestions."""
        res = ExecutionCoordinator.execute_tool(
            tool_name="generate_risk_description_suggestions",
            arguments={"risk_title": "Pump P-101 Mechanical Seal Failure"},
            context=self.context,
        )
        self.assertTrue(res["success"])
        data = res["result"]
        self.assertEqual(data["status"], "success")
        self.assertGreaterEqual(len(data["suggestions"]), 2)

    def test_tool_7_generate_mitigation_suggestions(self):
        """Tool 7: generate_mitigation_suggestions returns curated and historical suggestions."""
        res = ExecutionCoordinator.execute_tool(
            tool_name="generate_mitigation_suggestions",
            arguments={"risk_title": "Pipeline H2S Corrosion"},
            context=self.context,
        )
        self.assertTrue(res["success"])
        data = res["result"]
        self.assertEqual(data["status"], "success")
        self.assertGreaterEqual(len(data["suggestions"]), 2)

    def test_tool_8_generate_action_plan_suggestions(self):
        """Tool 8: generate_action_plan_suggestions returns actionable steps."""
        res = ExecutionCoordinator.execute_tool(
            tool_name="generate_action_plan_suggestions",
            arguments={"risk_title": "Electrical Transformer Overheating", "mitigation_strategy": "Install cooling fans"},
            context=self.context,
        )
        self.assertTrue(res["success"])
        data = res["result"]
        self.assertEqual(data["status"], "success")
        self.assertGreaterEqual(len(data["suggestions"]), 2)

    def test_tool_9_calculate_risk_scores(self):
        """Tool 9: calculate_risk_scores derives mathematical score and badge."""
        res = ExecutionCoordinator.execute_tool(
            tool_name="calculate_risk_scores",
            arguments={"likelihood": 4, "impact": 5},
            context=self.context,
        )
        self.assertTrue(res["success"])
        data = res["result"]
        self.assertEqual(data["score"], 20)
        self.assertEqual(data["level"], "CRITICAL")
        self.assertEqual(data["badge"], "[CRITICAL]")

    def test_tool_10_validate_risk_payload(self):
        """Tool 10: validate_risk_payload returns structured validation result."""
        valid_draft = {
            "risk_name": "Steam Boiler Overpressure Excursion",
            "risk_description": "Overpressure due to sudden safety release valve blockage.",
            "inherent_likelihood": 4,
            "inherent_impact": 5,
            "mitigation": "Install dual automated relief valves with DCS emergency vent trips.",
            "current_likelihood": 1,
            "current_impact": 2,
            "action_plan": "Execute quarterly valve pop test and recalibrate transmitter.",
            "user_id": 101,
            "dept_id": 2,
        }
        res = ExecutionCoordinator.execute_tool(
            tool_name="validate_risk_payload",
            arguments={"draft": valid_draft, "dept_id": 2},
            context=self.context,
        )
        self.assertTrue(res["success"])
        data = res["result"]
        self.assertTrue(data["is_valid"])
        self.assertTrue(data["is_ready_for_review"])
        self.assertEqual(data["calculated_scores"]["inherent_score"], 20)

    def test_tool_11_create_risk_requires_confirmation(self):
        """Tool 11: create_risk cannot be executed without valid confirmation."""
        with self.assertRaises(ConfirmationRequiredError):
            ExecutionCoordinator.execute_tool(
                tool_name="create_risk",
                arguments={
                    "risk_name": "Gas Leak at Valve 12",
                    "risk_description": "Flammable gas emission near compressor flange.",
                    "inherent_likelihood": 4,
                    "inherent_impact": 4,
                    "current_likelihood": 2,
                    "current_impact": 2,
                    "mitigation": "Tighten flange bolts and replace spiral wound gasket.",
                },
                context=self.context,
                bypass_confirmation=False,
            )


class TestPhase4AGoalDrivenAgent(unittest.TestCase):
    """Test the goal-driven execution loop and decision boundaries."""

    def setUp(self):
        self.agent = RiskCreationAgent()
        self.user_id = "101"
        self.dept_id = 2
        self.dept_name = "Gas Processing Facilities"
        self.meta = {
            "role": "Risk Owner",
            "user_id": self.user_id,
            "dept_id": self.dept_id,
            "dept_name": self.dept_name,
        }

    # Scenario 1
    def test_all_required_fields_provided_skips_unnecessary_questions(self):
        """Scenario 1: All required fields provided in initial message; questions & suggestions skipped."""
        full_msg = (
            "Create a new risk for Gas Leakage at Compressor P-101. "
            "Description: Mechanical seal wear causing continuous VOC venting. "
            "Inherent assessment: Likelihood 4, Impact 4. "
            "Current assessment: Likelihood 2, Impact 2. "
            "Mitigation: Upgrade to API 682 Plan 53B dual pressurized seal. "
            "Action plan: Execute seal replacement during scheduled outage."
        )
        req = AgentRequest(message=full_msg, user_id=self.user_id, metadata=self.meta)
        res = self.agent.process(req)

        self.assertEqual(res.metadata.get("wizard_step"), "WIZARD_CONFIRMATION")
        self.assertIn("Risk Creation – Final Review", res.response)
        self.assertIn("Compressor P-101", res.response)
        self.assertIn("Do you want to save this risk?", res.response)

        # Ensure no suggestion prompt was returned
        self.assertNotIn("Step 1/10", res.response)
        self.assertNotIn("Recommended Mitigation Options", res.response)

    # Scenario 2
    def test_only_title_and_description_identifies_remaining(self):
        """Scenario 2: Only title and description provided; agent identifies remaining requirements."""
        msg = "Create a risk for Turbine Bearing High Temperature. Description: Bearing temperature exceeded 110C during peak load."
        req = AgentRequest(message=msg, user_id=self.user_id, metadata=self.meta)
        res = self.agent.process(req)

        # Agent should accept title and description, and prompt for inherent assessment
        self.assertIn("Inherent Risk Assessment", res.response)
        self.assertEqual(res.metadata.get("wizard_step"), "STEP_INHERENT_ASSESSMENT")
        sess = self.agent.get_session(self.user_id)
        self.assertIsNotNone(sess.risk_name)
        self.assertIsNotNone(sess.risk_description)
        self.assertIsNone(sess.inherent_likelihood)

    # Scenario 3
    def test_fields_arrive_in_unusual_order(self):
        """Scenario 3: Fields arrive in unusual order (mitigation first, then title & ratings)."""
        r1 = AgentRequest(
            message="Create a new risk. Mitigation: Install optical flame detectors with deluge trip.",
            user_id="301",
            metadata={"role": "Risk Owner", "user_id": "301", "dept_id": 2, "dept_name": "Gas"}
        )
        res1 = self.agent.process(r1)
        sess = self.agent.get_session("301")
        self.assertIn("Install optical flame detectors with deluge trip", sess.mitigation)
        # Title is missing, so agent asks for title
        self.assertIn("Risk Name / Title", res1.response)

        r2 = AgentRequest(
            message="Risk Name: Flare Header Overpressure. Likelihood 4 Impact 5.",
            user_id="301",
            metadata={"role": "Risk Owner", "user_id": "301", "dept_id": 2, "dept_name": "Gas"}
        )
        res2 = self.agent.process(r2)
        sess = self.agent.get_session("301")
        self.assertEqual(sess.inherent_score, 20)
        self.assertEqual(sess.inherent_level, "CRITICAL")
        # Mitigation was already provided, so it doesn't prompt for mitigation again
        self.assertNotEqual(res2.metadata.get("wizard_step"), "STEP_MITIGATION")

    # Scenario 4
    def test_owner_lookup_tool_selected_only_when_requested(self):
        """Scenario 4: Owner lookup tool is selected only when requested."""
        r_start = AgentRequest(message="Create a new risk for cooling tower leak", user_id="401", metadata=self.meta)
        self.agent.process(r_start)

        sess = self.agent.get_session("401")
        initial_history_len = len(sess.tool_call_history)

        # User specifically asks for eligible action owners
        r_lookup = AgentRequest(message="Who can be action owner for this risk?", user_id="401", metadata=self.meta)
        res_lookup = self.agent.process(r_lookup)

        self.assertTrue(
            "Eligible Action Owner Candidates" in res_lookup.response
            or "No eligible action_owner found" in res_lookup.response
        )
        # Check tool_call_history recorded the invocation
        tool_names = [call["tool_name"] for call in sess.tool_call_history]
        self.assertIn("get_eligible_risk_owners", tool_names)

    # Scenario 5
    def test_skips_suggestions_when_user_supplied_content(self):
        """Scenario 5: Agent skips suggestions when user already supplied acceptable mitigation."""
        full_msg = (
            "Create risk for Vessel Shell Thinning. Description: Wall thickness reduced to 8mm. "
            "Inherent Likelihood 4 Impact 4. "
            "Mitigation: Install external weld overlay reinforcement. "
            "Current Likelihood 2 Impact 2. "
            "Action Plan: Complete NDT radiographic scan."
        )
        req = AgentRequest(message=full_msg, user_id=self.user_id, metadata=self.meta)
        res = self.agent.process(req)

        sess = self.agent.get_session(self.user_id)
        # Suggestion tools should NOT have been called
        tool_names = [call["tool_name"] for call in sess.tool_call_history]
        self.assertNotIn("generate_mitigation_suggestions", tool_names)
        self.assertNotIn("generate_action_plan_suggestions", tool_names)

    # Scenario 6
    def test_invalid_rating_rejected_never_silently_corrected(self):
        """Scenario 6: Invalid rating (e.g. 9 or 0) rejected and never silently clamped."""
        sess = RiskCreationSession(
            session_id="sess-invalid-test-01",
            user_id="601",
            user_role="Risk Owner",
            dept_id=2,
            risk_name="Crude Tank Leak",
            risk_description="Crude tank bottom plate corrosion.",
            state=RiskCreationState.AWAITING_INHERENT_ASSESSMENT,
        )
        self.agent.sessions["601"] = sess

        r_invalid = AgentRequest(message="Likelihood 9 and Impact 3", user_id="601", metadata=self.meta)
        res_invalid = self.agent.process(r_invalid)

        self.assertIn("Validation Notice", res_invalid.response)
        self.assertIn("must be integers between 1 and 5", res_invalid.response)
        # Verify rating was NOT clamped to 5
        self.assertIsNone(sess.inherent_likelihood)
        self.assertIsNone(sess.inherent_score)

    # Scenario 7
    def test_ineligible_owner_rejected(self):
        """Scenario 7: An ineligible owner is rejected with a clear explanation."""
        r_start = AgentRequest(message="Create a new risk for compressor fire", user_id="701", metadata=self.meta)
        self.agent.process(r_start)

        sess = self.agent.get_session("701")
        sess.state = RiskCreationState.AWAITING_ACTION_OWNER

        r_bad_owner = AgentRequest(message="Assign Action Owner NonexistentUser99", user_id="701", metadata=self.meta)
        res_bad_owner = self.agent.process(r_bad_owner)

        self.assertIn("Ineligible Action Owner", res_bad_owner.response)
        self.assertIn("NonexistentUser99", res_bad_owner.response)
        self.assertIsNone(sess.action_owner_id)

    # Scenario 8
    def test_duplicate_detection_returns_advisory_without_db_write(self):
        """Scenario 8: Duplicate detection returns advisory results without changing database."""
        r_start = AgentRequest(message="Create a new risk for Gas Leakage at Compressor", user_id="801", metadata=self.meta)
        self.agent.process(r_start)

        with patch.object(erm_db, "create_risk") as mock_save:
            r_dup = AgentRequest(message="Check for duplicates", user_id="801", metadata=self.meta)
            res_dup = self.agent.process(r_dup)

            mock_save.assert_not_called()
            self.assertTrue(
                "Duplicate Risk Check Results" in res_dup.response
                or "No Duplicate Risks Found" in res_dup.response
            )

    # Scenario 9
    def test_tool_recoverable_error_handled_safely(self):
        """Scenario 9: A tool returns a recoverable error and agent handles it safely."""
        sess = RiskCreationSession(
            session_id="sess-err-test-01",
            user_id="901",
            user_role="Risk Owner",
            dept_id=2,
            risk_name="Heat Exchanger Tube Leak",
            risk_description="Tube bundle corrosion causing bypass.",
            state=RiskCreationState.COLLECTING,
        )
        self.agent.sessions["901"] = sess

        with patch.object(erm_db, "find_potential_duplicate_risks", side_effect=RuntimeError("Connection timeout")):
            r_dup = AgentRequest(message="Check for duplicates", user_id="901", metadata=self.meta)
            res_dup = self.agent.process(r_dup)

            self.assertIn("could not be completed", res_dup.response)
            # Session is still active and draft not corrupted
            self.assertTrue(self.agent.is_session_active("901"))

    # Scenario 10
    def test_unknown_tool_or_invalid_args_rejected_by_harness(self):
        """Scenario 10: Model proposes unknown tool or invalid arguments; harness rejects call."""
        ctx = HarnessContext.build_from_auth(user_id="101", user_role="Risk Owner", dept_id=2)

        with self.assertRaises(ToolNotFoundError):
            ExecutionCoordinator.execute_tool(tool_name="nonexistent_harness_tool", arguments={}, context=ctx)

        with self.assertRaises(ToolValidationError):
            ExecutionCoordinator.execute_tool(
                tool_name="check_risk_duplicates",
                arguments={"risk_title": "x"},  # min_length is 3
                context=ctx
            )

    # Scenario 11
    def test_unauthorized_role_rejected_by_harness_rbac(self):
        """Scenario 11: Model attempts forbidden or unauthorized tool call; harness rejects it."""
        guest_ctx = HarnessContext.build_from_auth(user_id="999", user_role="guest", dept_id=2)

        with self.assertRaises(AuthorizationError):
            ExecutionCoordinator.execute_tool(
                tool_name="create_risk",
                arguments={"risk_name": "Test Risk", "risk_description": "Valid test risk description long enough"},
                context=guest_ctx
            )

    # Scenario 12
    def test_cannot_invoke_create_risk_before_confirmation(self):
        """Scenario 12: create_risk cannot be executed before confirmation."""
        ctx = HarnessContext.build_from_auth(user_id="101", user_role="Risk Owner", dept_id=2)

        with self.assertRaises(ConfirmationRequiredError):
            ExecutionCoordinator.execute_tool(
                tool_name="create_risk",
                arguments={
                    "risk_name": "Unconfirmed Risk",
                    "risk_description": "Attempting save before preview and confirmation.",
                },
                context=ctx
            )

    # Scenario 13
    def test_modified_draft_invalidates_stale_confirmation(self):
        """Scenario 13: Modified draft invalidates stale confirmation evidence."""
        agent = RiskCreationAgent()
        u_id = "1301"
        meta = {"role": "Risk Owner", "user_id": u_id, "dept_id": 2, "dept_name": "Gas"}

        sess = RiskCreationSession(
            session_id="sess-tamper-01",
            user_id=u_id,
            user_role="Risk Owner",
            dept_id=2,
            dept_name="Gas",
            risk_name="Reactor Temperature Excursion",
            risk_description="Excessive bed temperature risking thermal runaway.",
            inherent_likelihood=4,
            inherent_impact=5,
            inherent_score=20,
            inherent_level="CRITICAL",
            inherent_badge="[CRITICAL]",
            mitigation="Quench hydrogen injection and trip feed pumps.",
            current_likelihood=1,
            current_impact=2,
            current_score=2,
            current_level="LOW",
            current_badge="[LOW]",
            action_plan="Install emergency quench dump valve.",
            action_owner_id=5,
            action_owner_name="Sunil Yadav",
            target_date="2026-12-31",
            status_id=1,
            status_name="Draft",
            state=RiskCreationState.AWAITING_CONFIRMATION,
        )
        agent.sessions[u_id] = sess
        agent._bind_pending_confirmation(sess)
        self.assertIsNotNone(sess.pending_confirmation)

        # User edits mitigation
        r_edit = AgentRequest(message="Change mitigation to Manual nitrogen purge only", user_id=u_id, metadata=meta)
        agent.process(r_edit)

        # Fresh preview is required; old confirmation token was invalidated
        self.assertNotEqual(
            sess.pending_confirmation["parameters"]["mitigation"],
            "Quench hydrogen injection and trip feed pumps."
        )

    # Scenario 14
    def test_repeated_tool_requests_cannot_cause_unbounded_loop(self):
        """Scenario 14: Repeated tool requests in a turn cannot cause an unbounded loop."""
        sess = RiskCreationSession(
            session_id="sess-loop-01",
            user_id="1401",
            user_role="Risk Owner",
            dept_id=2,
            risk_name="Compressor P-101 Seal Failure",
            risk_description="Seal failure causing hydrocarbon release.",
        )
        # Execute duplicate check 3 times through governed tool
        for _ in range(3):
            self.agent.execute_governed_tool(
                tool_name="check_risk_duplicates",
                arguments={"risk_title": sess.risk_name, "risk_description": sess.risk_description, "dept_id": 2},
                session=sess,
            )
        # Tool call history records all executions without crashing or recursive loops
        self.assertEqual(len(sess.tool_call_history), 3)

    # Scenario 15
    def test_checkpoint_restoration_preserves_draft_and_tool_history(self):
        """Scenario 15: Checkpoint restoration does not lose draft state or tool call history."""
        sess = RiskCreationSession(
            session_id="sess-chk-01",
            user_id="1501",
            user_role="Risk Owner",
            dept_id=2,
            dept_name="Gas Facilities",
            risk_name="Crude Oil Column Flooding",
            risk_description="Downcomer backup causing tray damage.",
            inherent_likelihood=4,
            inherent_impact=4,
            inherent_score=16,
            inherent_level="CRITICAL",
            inherent_badge="[CRITICAL]",
            tool_call_history=[
                {"tool_name": "check_risk_duplicates", "success": True, "timestamp": "2026-10-21T10:00:00Z"}
            ]
        )
        data = sess.to_dict()
        self.assertIn("tool_call_history", data)
        self.assertEqual(len(data["tool_call_history"]), 1)

        restored = RiskCreationSession.from_dict(data)
        self.assertEqual(restored.risk_name, "Crude Oil Column Flooding")
        self.assertEqual(restored.inherent_score, 16)
        self.assertEqual(len(restored.tool_call_history), 1)
        self.assertEqual(restored.tool_call_history[0]["tool_name"], "check_risk_duplicates")


if __name__ == "__main__":
    unittest.main()
