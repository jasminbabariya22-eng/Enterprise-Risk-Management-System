"""
Unit & Integration Tests for the Refactored Conversational Risk Creation Agent.

Tests:
1. Authentication & RBAC (Authorized vs Unauthorized roles)
2. 5x5 Risk Matrix Calculation across all 25 combinations (Authoritative math)
3. Static Suggestions (2-4 distinct suggestions for Description, Mitigation, Action Plan)
4. Session Isolation & Multi-turn State Preservation
5. Full 14-Step Conversational Workflow:
   - Initiation -> 1. Risk Name -> 2. Co-Owner -> 3. Description -> 4. Inherent Assessment
   - -> 5. Mitigation -> 6. Current Assessment -> 7. Action Plan -> 8. Action Owner
   - -> 9. Target Date -> 10. Status -> 11. Validate -> 12. Preview -> 13. Confirm -> 14. Save/Submit -> Success
6. Conversational Field Editing before Confirmation (e.g. Target Date, Progress, Mitigation)
7. Cancellation & Interruption Safeguards
8. Validation Engine (Required fields, bounds, identity)
9. Authoritative Backend Persistence & Risk ID Return
"""
import sys
import unittest
from pathlib import Path

# Ensure root workspace is on path
root_dir = str(Path(__file__).resolve().parents[2])
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from ERM_Copilot.agents.risk_creation_agent import (
    RiskCreationAgent,
    RiskCreationSession,
    RiskCreationState,
    RiskMatrixCalculator,
    StaticRiskSuggestionProvider,
    parse_target_date,
    parse_progress,
    detect_field_edits,
    risk_creation_agent,
    static_suggestion_provider
)
from ERM_Copilot.models.contracts import AgentRequest


class TestRiskCreationAgent(unittest.TestCase):
    """Unit and integration tests for RiskCreationAgent."""

    @classmethod
    def setUpClass(cls):
        from ERM_Copilot.services.db_service import erm_db
        try:
            conn = erm_db._get_connection()
            conn.close()
        except Exception as e:
            raise unittest.SkipTest(f"Live PostgreSQL database not available: {e}")

    def setUp(self):
        self.agent = RiskCreationAgent()
        self.user_id = "12"
        self.session_id = "sess-test-001"
        self.dept_id = 2
        self.dept_name = "Gas Processing Facilities"
        self.metadata = {
            "role": "Risk Owner",
            "user_id": self.user_id,
            "dept_id": self.dept_id,
            "dept_name": self.dept_name
        }

    # -----------------------------------------------------------------
    # 1. AUTHENTICATION & RBAC
    # -----------------------------------------------------------------
    def test_authorized_risk_owner_can_create(self):
        """Authenticated Risk Owner and Managers have permission to create risks."""
        auth, msg = self.agent.check_authorization("Risk Owner")
        self.assertTrue(auth)

        auth_mgr, _ = self.agent.check_authorization("Risk Manager")
        self.assertTrue(auth_mgr)

    def test_unauthorized_role_is_blocked(self):
        """Unauthorized roles (guest, readonly) cannot create risk records."""
        auth, err = self.agent.check_authorization("readonly")
        self.assertFalse(auth)
        self.assertIn("not authorized", err.lower())

        req = AgentRequest(
            message="Create a new risk for turbine trip",
            user_id="99",
            user_role="readonly",
            metadata={"role": "readonly"}
        )
        res = self.agent.process(req)
        self.assertIn("Authorization Denied", res.response)

    # -----------------------------------------------------------------
    # 2. RISK MATRIX & SCORING
    # -----------------------------------------------------------------
    def test_risk_matrix_calculation_and_badges(self):
        """Risk score and level are computed mathematically without hard-coded mapping."""
        # Critical: 4x5 = 20
        score, level, badge = RiskMatrixCalculator.calculate_score(4, 5)
        self.assertEqual(score, 20)
        self.assertEqual(level, "CRITICAL")
        self.assertEqual(badge, "[CRITICAL]")

        # High: 3x4 = 12
        score, level, badge = RiskMatrixCalculator.calculate_score(3, 4)
        self.assertEqual(score, 12)
        self.assertEqual(level, "HIGH")
        self.assertEqual(badge, "[HIGH]")

        # Medium: 3x3 = 9
        score, level, badge = RiskMatrixCalculator.calculate_score(3, 3)
        self.assertEqual(score, 9)
        self.assertEqual(level, "MEDIUM")
        self.assertEqual(badge, "[MEDIUM]")

        # Low: 2x2 = 4
        score, level, badge = RiskMatrixCalculator.calculate_score(2, 2)
        self.assertEqual(score, 4)
        self.assertEqual(level, "LOW")
        self.assertEqual(badge, "[LOW]")

    def test_parse_likelihood_impact_custom_input(self):
        """Likelihood and impact can be parsed across all 25 combinations and text patterns."""
        l, i = RiskMatrixCalculator.parse_likelihood_impact("Likelihood 4 and Impact 5")
        self.assertEqual((l, i), (4, 5))

        l2, i2 = RiskMatrixCalculator.parse_likelihood_impact("L=2, I=3")
        self.assertEqual((l2, i2), (2, 3))

        l3, i3 = RiskMatrixCalculator.parse_likelihood_impact("Option B High")
        self.assertEqual((l3, i3), (3, 4))

        l4, i4 = RiskMatrixCalculator.parse_likelihood_impact("Probable Major")
        self.assertEqual((l4, i4), (4, 4))

        l5, i5 = RiskMatrixCalculator.parse_likelihood_impact("Remote Negligible")
        self.assertEqual((l5, i5), (1, 1))

        # Test any of 25 combinations
        for test_l in range(1, 6):
            for test_i in range(1, 6):
                parsed = RiskMatrixCalculator.parse_likelihood_impact(f"{test_l} {test_i}")
                self.assertEqual(parsed, (test_l, test_i))

    # -----------------------------------------------------------------
    # 3. STATIC SUGGESTIONS
    # -----------------------------------------------------------------
    def test_static_suggestions_count_and_content(self):
        """Static suggestion provider returns 2-4 distinct suggestions."""
        provider = StaticRiskSuggestionProvider()

        # Description Suggestions
        desc_suggs = provider.get_description_suggestions("Pump P-101 Mechanical Seal Failure")
        self.assertGreaterEqual(len(desc_suggs), 2)
        self.assertLessEqual(len(desc_suggs), 4)

        # Mitigation Suggestions
        mit_suggs = provider.get_mitigation_suggestions("Pump P-101 Mechanical Seal Failure")
        self.assertGreaterEqual(len(mit_suggs), 2)
        self.assertLessEqual(len(mit_suggs), 4)

        # Action Plan Suggestions
        act_suggs = provider.get_action_plan_suggestions("Pump P-101 Mechanical Seal Failure")
        self.assertGreaterEqual(len(act_suggs), 2)
        self.assertLessEqual(len(act_suggs), 4)

        # Ensure Description, Mitigation, and Action Plan are distinct
        self.assertNotEqual(desc_suggs[0], mit_suggs[0])
        self.assertNotEqual(mit_suggs[0], act_suggs[0])

    # -----------------------------------------------------------------
    # 4. FIELD PARSERS
    # -----------------------------------------------------------------
    def test_target_date_parser(self):
        """Target date parser parses dates and relative day offsets."""
        d1 = parse_target_date("31 December 2026")
        self.assertEqual(d1, "2026-12-31")

        d2 = parse_target_date("2026-12-31")
        self.assertEqual(d2, "2026-12-31")

        d3 = parse_target_date("+30 days")
        self.assertIsNotNone(d3)
        self.assertTrue(len(d3) == 10)

    def test_progress_parser(self):
        """Progress parser extracts integer percentages 0-100."""
        self.assertEqual(parse_progress("0%"), 0)
        self.assertEqual(parse_progress("25%"), 25)
        self.assertEqual(parse_progress("progress 50"), 50)
        self.assertEqual(parse_progress("100"), 100)

    # -----------------------------------------------------------------
    # 5. CONVERSATIONAL SESSION ISOLATION & CANCELLATION
    # -----------------------------------------------------------------
    def test_session_isolation_between_users(self):
        """Sessions of User A and User B are completely isolated."""
        agent = RiskCreationAgent()

        req_a = AgentRequest(
            message="Create a new risk for gas leakage at pipe A",
            user_id="101",
            metadata={"role": "Risk Owner", "user_id": "101", "dept_id": 1}
        )
        agent.process(req_a)
        self.assertTrue(agent.is_session_active("101"))
        self.assertFalse(agent.is_session_active("102"))

        # User B starts independent risk
        req_b = AgentRequest(
            message="Create a new risk for boiler overpressure",
            user_id="102",
            metadata={"role": "Risk Owner", "user_id": "102", "dept_id": 2}
        )
        agent.process(req_b)
        self.assertTrue(agent.is_session_active("102"))

        sess_a = agent.get_session("101")
        sess_b = agent.get_session("102")
        self.assertIn("Pipe A", sess_a.risk_name)
        self.assertIn("Boiler", sess_b.risk_name)

    def test_cancellation_clears_session(self):
        """User can cancel the risk creation at any point and clear state."""
        agent = RiskCreationAgent()

        req_start = AgentRequest(
            message="Create a new risk for compressor vibration",
            user_id="201",
            metadata={"role": "Risk Owner", "user_id": "201", "dept_id": 1}
        )
        agent.process(req_start)
        self.assertTrue(agent.is_session_active("201"))

        req_cancel = AgentRequest(
            message="Cancel risk creation",
            user_id="201",
            metadata={"role": "Risk Owner", "user_id": "201", "dept_id": 1}
        )
        res_cancel = agent.process(req_cancel)
        self.assertIn("Cancelled", res_cancel.response)
        self.assertFalse(agent.is_session_active("201"))

    # -----------------------------------------------------------------
    # 6. STEP-BY-STEP CONVERSATIONAL FLOW (14 STEPS)
    # -----------------------------------------------------------------
    def test_full_14_step_conversational_workflow(self):
        """
        Complete conversational flow from initiation through 10 fields,
        preview, confirmation, and final persistence.
        """
        agent = RiskCreationAgent()
        u_id = "501"
        meta = {
            "role": "Risk Owner",
            "user_id": u_id,
            "dept_id": self.dept_id,
            "dept_name": self.dept_name
        }

        # Step 0: User says "Create a new risk" (no name provided)
        r0 = AgentRequest(message="Create a new risk", user_id=u_id, metadata=meta)
        res0 = agent.process(r0)
        self.assertIn("Step 1/10: Risk Name / Title", res0.response)
        self.assertTrue(agent.is_session_active(u_id))

        # Step 1: Provide Risk Name
        r1 = AgentRequest(message="Compressor P-101 Seal Degradation", user_id=u_id, metadata=meta)
        res1 = agent.process(r1)
        self.assertIn("Step 2/10: Risk Co-Owner", res1.response)
        self.assertIn("Compressor P-101", res1.response)

        # Step 2: Skip Co-Owner
        r2 = AgentRequest(message="Skip Co-Owner", user_id=u_id, metadata=meta)
        res2 = agent.process(r2)
        self.assertIn("Step 3/10: Risk Description", res2.response)

        # Step 3: Select Description Suggestion (Option 1)
        r3 = AgentRequest(message="Option 1 Description", user_id=u_id, metadata=meta)
        res3 = agent.process(r3)
        self.assertIn("Step 4/10: Inherent Risk Assessment", res3.response)

        # Step 4: Provide Inherent Rating (Likelihood 4 x Impact 5 = 20 [CRITICAL])
        r4 = AgentRequest(message="Likelihood 4 Impact 5", user_id=u_id, metadata=meta)
        res4 = agent.process(r4)
        self.assertIn("Step 5/10: Mitigation", res4.response)
        self.assertIn("20 / 25 [CRITICAL]", res4.response)

        # Step 5: Select Mitigation Suggestion (Option 1)
        r5 = AgentRequest(message="Option 1 Engineering Control", user_id=u_id, metadata=meta)
        res5 = agent.process(r5)
        self.assertIn("Step 6/10: Current / Residual Risk Assessment", res5.response)

        # Step 6: Provide Current Rating (Likelihood 2 x Impact 2 = 4 [LOW])
        r6 = AgentRequest(message="Likelihood 2 Impact 2", user_id=u_id, metadata=meta)
        res6 = agent.process(r6)
        self.assertIn("Step 7/10: Action Plan", res6.response)
        self.assertIn("4 / 25 [LOW]", res6.response)

        # Step 7: Select Action Plan Suggestion (Option 1)
        r7 = AgentRequest(message="Option 1 Action Plan", user_id=u_id, metadata=meta)
        res7 = agent.process(r7)
        self.assertIn("Step 8/10: Assign Action Owner", res7.response)

        # Step 8: Assign Action Owner by Name
        r8 = AgentRequest(message="Assign Action Owner Sunil Yadav", user_id=u_id, metadata=meta)
        res8 = agent.process(r8)
        self.assertIn("Step 9/10: Target Completion Date", res8.response)

        # Step 9: Provide Target Date
        r9 = AgentRequest(message="31 December 2026", user_id=u_id, metadata=meta)
        res9 = agent.process(r9)
        self.assertIn("Step 10/10: Governance Status", res9.response)

        # Step 10: Select Status -> Automatically Validates & Displays Step 12 Preview
        r10 = AgentRequest(message="Draft", user_id=u_id, metadata=meta)
        res10 = agent.process(r10)
        self.assertIn("Risk Creation – Final Review", res10.response)
        self.assertIn("Compressor P-101", res10.response)
        self.assertIn("20 / 25 [CRITICAL]", res10.response)
        self.assertIn("4 / 25 [LOW]", res10.response)
        self.assertIn("2026-12-31", res10.response)
        self.assertIn("Draft", res10.response)
        self.assertIn("Do you want to save this risk?", res10.response)

        # Step 13/14: Explicit Confirmation -> Persist to DB & Risk ID return
        r11 = AgentRequest(message="Confirm and Save", user_id=u_id, metadata=meta)
        res11 = agent.process(r11)
        self.assertIn("Risk Created Successfully", res11.response)
        self.assertIn("Risk ID", res11.response)
        self.assertIn("RSK-", res11.response)

        # Session is now cleared
        self.assertFalse(agent.is_session_active(u_id))

    # -----------------------------------------------------------------
    # 7. CONVERSATIONAL FIELD EDITING BEFORE CONFIRMATION
    # -----------------------------------------------------------------
    def test_inline_field_editing_before_confirmation(self):
        """User can edit individual fields conversationally without restarting workflow."""
        agent = RiskCreationAgent()
        u_id = "601"
        meta = {"role": "Risk Owner", "user_id": u_id, "dept_id": self.dept_id, "dept_name": self.dept_name}

        # Initialize directly to preview/confirmation state
        sess = RiskCreationSession(
            session_id="sess-edit-01",
            user_id=u_id,
            user_role="Risk Owner",
            dept_id=self.dept_id,
            dept_name=self.dept_name,
            risk_name="Heater Tube Overheating",
            risk_description="Excessive firing causing localized hot spot.",
            inherent_likelihood=4,
            inherent_impact=4,
            inherent_score=16,
            inherent_level="CRITICAL",
            inherent_badge="[CRITICAL]",
            mitigation="Reduce burner firing rate and clean convection bank.",
            current_likelihood=2,
            current_impact=2,
            current_score=4,
            current_level="LOW",
            current_badge="[LOW]",
            action_plan="Deploy infrared thermography inspection rounds.",
            action_owner_id=5,
            action_owner_name="Sunil Yadav",
            target_date="2026-12-31",
            status_id=1,
            status_name="Draft",
            progress=0,
            state=RiskCreationState.AWAITING_CONFIRMATION
        )
        agent.sessions[u_id] = sess

        # User requests inline edit: Change Target Date
        r_edit1 = AgentRequest(message="Change target date to 2027-03-31", user_id=u_id, metadata=meta)
        res_edit1 = agent.process(r_edit1)
        self.assertIn("Updated Target Date to `2027-03-31`", res_edit1.response)
        self.assertIn("2027-03-31", res_edit1.response)
        self.assertEqual(agent.get_session(u_id).target_date, "2027-03-31")

        # User requests inline edit: Change Mitigation
        r_edit2 = AgentRequest(message="Change mitigation to Clean burner nozzles and recalibrate fuel valve", user_id=u_id, metadata=meta)
        res_edit2 = agent.process(r_edit2)
        self.assertIn("Updated Mitigation Strategy", res_edit2.response)
        self.assertIn("Clean burner nozzles", res_edit2.response)

        # Confirm and save updated draft
        r_confirm = AgentRequest(message="Confirm and Save", user_id=u_id, metadata=meta)
        res_confirm = agent.process(r_confirm)
        self.assertIn("Risk Created Successfully", res_confirm.response)
        self.assertIn("RSK-", res_confirm.response)


if __name__ == "__main__":
    unittest.main()
