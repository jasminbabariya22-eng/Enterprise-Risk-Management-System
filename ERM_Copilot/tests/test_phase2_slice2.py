"""
Phase 2 Slice 2 Tests:
1. get_mitigation_suggestions tool & governance:
   - Valid input returns structured suggestions (curated & hybrid).
   - Historical treatment retrieval scoping & graceful degradation.
   - Role authorization & RBAC enforcement (Creator roles vs unauthorized).
   - Input validation (risk_title >= 3 characters).
   - Read-only safety (zero database writes).
2. get_action_plan_suggestions tool & governance:
   - Valid input with mitigation context.
   - Missing optional mitigation context.
   - Empty/error provider handling.
   - Role authorization & input validation.
   - Read-only safety.
3. Conversational Agent Integration:
   - Selective tool invocation on explicit suggestion request.
   - Contextual suggestion request in AWAITING_MITIGATION and AWAITING_ACTION_PLAN.
   - Non-destructive display (draft is NOT mutated on suggestion lookup).
   - User option selection commits to draft with provenance 'user_selected_suggestion'.
   - Custom user input commits to draft with provenance 'user_stated'.
   - Declining suggestions preserves manual entry path.
   - Checkpoint serialization preserves options and provenance.
   - Confirmation integrity and database safety intact.
"""
import unittest
from unittest.mock import MagicMock, patch

from ERM_Copilot.agents.risk_creation.agent import RiskCreationAgent
from ERM_Copilot.agents.risk_creation.state import RiskCreationSession, RiskCreationState
from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.ai_harness.exceptions import (
    AuthorizationError,
    ToolValidationError,
)
from ERM_Copilot.ai_harness.execution import ExecutionCoordinator
from ERM_Copilot.ai_harness.policies import (
    ROLE_ADMIN,
    ROLE_RISK_OWNER,
    ROLE_SUPER_ADMIN,
    ROLE_AUDITOR,
    ROLE_BOARD_AUDIT,
)
from ERM_Copilot.ai_harness.tool_registry import tool_registry
from ERM_Copilot.models.contracts import AgentRequest
from ERM_Copilot.services.db_service import erm_db


class TestMitigationSuggestionsTool(unittest.TestCase):
    """Governance and handler tests for get_mitigation_suggestions."""

    def setUp(self):
        self.valid_context = HarnessContext.build_from_auth(
            user_id="101",
            user_role=ROLE_RISK_OWNER,
            dept_id=2,
            dept_name="Operations",
            session_id="test-sess-mit-001"
        )

    def test_tool_registered_with_correct_governance(self):
        tool = tool_registry.get("get_mitigation_suggestions")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.category.value, "read_only")
        self.assertFalse(tool.is_state_changing)
        self.assertTrue(tool.is_idempotent)
        self.assertFalse(tool.requires_confirmation)
        self.assertIn(ROLE_RISK_OWNER, tool.allowed_roles)
        self.assertIn(ROLE_ADMIN, tool.allowed_roles)
        self.assertNotIn(ROLE_AUDITOR, tool.allowed_roles)
        self.assertNotIn(ROLE_BOARD_AUDIT, tool.allowed_roles)

    def test_valid_input_returns_curated_suggestions(self):
        with patch.object(erm_db, "get_historical_treatments", return_value=[]):
            res = ExecutionCoordinator.execute_tool(
                tool_name="get_mitigation_suggestions",
                arguments={"risk_title": "Centrifugal Pump Overheating", "include_historical": False},
                context=self.valid_context
            )
            self.assertTrue(res.get("success"))
            result_data = res.get("result", {})
            self.assertEqual(result_data.get("status"), "success")
            self.assertEqual(result_data.get("risk_title"), "Centrifugal Pump Overheating")
            self.assertEqual(result_data.get("source"), "curated")
            self.assertIsInstance(result_data.get("suggestions"), list)
            self.assertGreaterEqual(len(result_data.get("suggestions")), 1)

    def test_include_historical_produces_hybrid_source(self):
        mock_treatments = [
            {
                "risk_name": "Pump Bearing Overheating",
                "action_plan": "Install infrared temperature sensors and daily thermal scan",
                "status": "Completed"
            }
        ]
        with patch.object(erm_db, "get_historical_treatments", return_value=mock_treatments) as mock_hist:
            res = ExecutionCoordinator.execute_tool(
                tool_name="get_mitigation_suggestions",
                arguments={"risk_title": "Centrifugal Pump Overheating", "include_historical": True},
                context=self.valid_context
            )
            mock_hist.assert_called_once()
            result_data = res.get("result", {})
            self.assertEqual(result_data.get("source"), "hybrid")
            self.assertEqual(len(result_data.get("historical_evidence")), 1)
            self.assertEqual(
                result_data["historical_evidence"][0]["historical_action"],
                "Install infrared temperature sensors and daily thermal scan"
            )

    def test_historical_lookup_failure_gracefully_degrades(self):
        with patch.object(erm_db, "get_historical_treatments", side_effect=Exception("DB connection timeout")):
            res = ExecutionCoordinator.execute_tool(
                tool_name="get_mitigation_suggestions",
                arguments={"risk_title": "Centrifugal Pump Overheating", "include_historical": True},
                context=self.valid_context
            )
            self.assertTrue(res.get("success"))
            result_data = res.get("result", {})
            self.assertEqual(result_data.get("source"), "curated")
            self.assertGreaterEqual(len(result_data.get("suggestions")), 1)

    def test_unauthorized_role_rejected(self):
        auditor_context = HarnessContext.build_from_auth(
            user_id="202",
            user_role=ROLE_AUDITOR,
            dept_id=2,
            dept_name="Operations",
            session_id="test-sess-auditor"
        )
        with self.assertRaises(AuthorizationError):
            ExecutionCoordinator.execute_tool(
                tool_name="get_mitigation_suggestions",
                arguments={"risk_title": "Centrifugal Pump Overheating"},
                context=auditor_context
            )

    def test_invalid_input_short_title_rejected(self):
        with self.assertRaises(ToolValidationError):
            ExecutionCoordinator.execute_tool(
                tool_name="get_mitigation_suggestions",
                arguments={"risk_title": "ab"},
                context=self.valid_context
            )

    def test_no_database_writes_occur(self):
        with patch.object(erm_db, "create_risk") as mock_write:
            ExecutionCoordinator.execute_tool(
                tool_name="get_mitigation_suggestions",
                arguments={"risk_title": "Turbine Blade Vibration"},
                context=self.valid_context
            )
            mock_write.assert_not_called()


class TestActionPlanSuggestionsTool(unittest.TestCase):
    """Governance and handler tests for get_action_plan_suggestions."""

    def setUp(self):
        self.valid_context = HarnessContext.build_from_auth(
            user_id="101",
            user_role=ROLE_RISK_OWNER,
            dept_id=2,
            dept_name="Operations",
            session_id="test-sess-act-001"
        )

    def test_tool_registered_with_correct_governance(self):
        tool = tool_registry.get("get_action_plan_suggestions")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.category.value, "read_only")
        self.assertFalse(tool.is_state_changing)
        self.assertTrue(tool.is_idempotent)
        self.assertFalse(tool.requires_confirmation)
        self.assertIn(ROLE_RISK_OWNER, tool.allowed_roles)
        self.assertNotIn(ROLE_AUDITOR, tool.allowed_roles)

    def test_valid_input_with_mitigation_context(self):
        res = ExecutionCoordinator.execute_tool(
            tool_name="get_action_plan_suggestions",
            arguments={
                "risk_title": "High Pressure Gas Pipeline Leak",
                "mitigation_strategy": "Install automated shutoff valves with acoustic sensors"
            },
            context=self.valid_context
        )
        self.assertTrue(res.get("success"))
        result_data = res.get("result", {})
        self.assertEqual(result_data.get("status"), "success")
        self.assertEqual(result_data.get("source"), "curated")
        self.assertIsInstance(result_data.get("suggestions"), list)
        self.assertGreaterEqual(len(result_data.get("suggestions")), 1)

    def test_valid_input_without_mitigation_context(self):
        res = ExecutionCoordinator.execute_tool(
            tool_name="get_action_plan_suggestions",
            arguments={"risk_title": "High Pressure Gas Pipeline Leak"},
            context=self.valid_context
        )
        self.assertTrue(res.get("success"))
        result_data = res.get("result", {})
        self.assertGreaterEqual(len(result_data.get("suggestions")), 1)

    def test_unauthorized_role_rejected(self):
        board_context = HarnessContext.build_from_auth(
            user_id="303",
            user_role=ROLE_BOARD_AUDIT,
            dept_id=1,
            dept_name="General",
            session_id="test-sess-board"
        )
        with self.assertRaises(AuthorizationError):
            ExecutionCoordinator.execute_tool(
                tool_name="get_action_plan_suggestions",
                arguments={"risk_title": "Pipeline Corrosion"},
                context=board_context
            )

    def test_invalid_input_short_title_rejected(self):
        with self.assertRaises(ToolValidationError):
            ExecutionCoordinator.execute_tool(
                tool_name="get_action_plan_suggestions",
                arguments={"risk_title": "x"},
                context=self.valid_context
            )

    def test_no_database_writes_occur(self):
        with patch.object(erm_db, "create_risk") as mock_write:
            ExecutionCoordinator.execute_tool(
                tool_name="get_action_plan_suggestions",
                arguments={"risk_title": "Boiler Pressure Spike"},
                context=self.valid_context
            )
            mock_write.assert_not_called()


class TestAgentSuggestionIntegration(unittest.TestCase):
    """Integration tests for RiskCreationAgent using suggestion tools."""

    def setUp(self):
        self.agent = RiskCreationAgent()
        self.agent.sessions.clear()

    def _make_req(self, msg: str, user_id: str, session_id: str) -> AgentRequest:
        return AgentRequest(
            message=msg,
            user_id=user_id,
            session_id=session_id,
            metadata={
                "role": "Risk Owner",
                "user_id": user_id,
                "dept_id": 1,
                "dept_name": "Operations",
            }
        )

    def test_explicit_mitigation_suggestion_does_not_mutate_draft(self):
        # 1. Start wizard with title
        req1 = self._make_req("Create a new risk for Gas Turbine Overheating", "user_test_101", "sugg_sess_1")
        resp1 = self.agent.process(req1)
        session_key = self.agent.get_session_key(req1)
        session = self.agent.get_session(session_key)
        self.assertEqual(session.risk_name, "Gas Turbine Overheating")
        self.assertIsNone(session.mitigation)

        # 2. Ask for mitigation suggestions explicitly
        req2 = self._make_req("Please suggest mitigations for this risk", "user_test_101", "sugg_sess_1")
        resp2 = self.agent.process(req2)
        self.assertIn("Recommended Mitigation Options", resp2.response)
        self.assertIn("Option 1", resp2.response)

        # 3. Verify draft mitigation is NOT automatically mutated
        session = self.agent.get_session(session_key)
        self.assertIsNone(session.mitigation)
        self.assertGreaterEqual(len(session.mitigation_options), 1)

    def test_user_selecting_option_updates_draft_with_provenance(self):
        # 1. Start session & request suggestions
        req1 = self._make_req("Create risk: Gas Turbine Overheating", "user_test_102", "sugg_sess_2")
        self.agent.process(req1)

        req2 = self._make_req("Give me mitigation suggestions", "user_test_102", "sugg_sess_2")
        self.agent.process(req2)
        session_key = self.agent.get_session_key(req2)
        session = self.agent.get_session(session_key)
        expected_option_1 = session.mitigation_options[0]

        # 2. User selects Option 1
        req3 = self._make_req("Option 1", "user_test_102", "sugg_sess_2")
        resp3 = self.agent.process(req3)
        session = self.agent.get_session(session_key)

        # Verify mitigation committed and provenance recorded
        self.assertEqual(session.mitigation, expected_option_1)
        self.assertEqual(session.field_provenance.get("mitigation"), "user_selected_suggestion")

    def test_user_custom_input_records_user_stated_provenance(self):
        # 1. Start session & request suggestions
        req1 = self._make_req("Create risk: Electrical Panel Short Circuit", "user_test_103", "sugg_sess_3")
        self.agent.process(req1)

        req2 = self._make_req("Suggest mitigations", "user_test_103", "sugg_sess_3")
        self.agent.process(req2)

        # 2. User types custom mitigation
        custom_mitigation = "Install arc flash relays and weekly infrared inspection protocol"
        req3 = self._make_req(custom_mitigation, "user_test_103", "sugg_sess_3")
        self.agent.process(req3)
        session_key = self.agent.get_session_key(req3)
        session = self.agent.get_session(session_key)

        self.assertEqual(session.mitigation, custom_mitigation)
        self.assertEqual(session.field_provenance.get("mitigation"), "user_stated")

    def test_declining_suggestions_preserves_manual_entry_state(self):
        req1 = self._make_req("Create risk: Conveyor Belt Misalignment", "user_test_104", "sugg_sess_4")
        self.agent.process(req1)

        # Trigger suggestions
        req2 = self._make_req("Suggest mitigations", "user_test_104", "sugg_sess_4")
        self.agent.process(req2)

        # Decline suggestions
        req3 = self._make_req("no suggestions, write my own", "user_test_104", "sugg_sess_4")
        resp3 = self.agent.process(req3)
        self.assertIn("custom **Mitigation Strategy**", resp3.response)
        session_key = self.agent.get_session_key(req3)
        session = self.agent.get_session(session_key)
        self.assertIsNone(session.mitigation)

    def test_explicit_action_plan_suggestion_workflow(self):
        req1 = self._make_req(
            "Create risk: Fuel Tank Overflow. Mitigation is Install ultrasonic level sensor.",
            "user_test_105",
            "sugg_sess_5"
        )
        self.agent.process(req1)

        # Explicit action plan suggestion request
        req2 = self._make_req("Suggest action plan implementation steps", "user_test_105", "sugg_sess_5")
        resp2 = self.agent.process(req2)
        self.assertIn("Recommended Action Plan Options", resp2.response)
        self.assertIn("Option 1", resp2.response)

        session_key = self.agent.get_session_key(req2)
        session = self.agent.get_session(session_key)
        self.assertIsNone(session.action_plan)
        expected_act_1 = session.action_plan_options[0]

        # Select option 1
        req3 = self._make_req("Use Option 1", "user_test_105", "sugg_sess_5")
        resp3 = self.agent.process(req3)
        session = self.agent.get_session(session_key)
        self.assertEqual(session.action_plan, expected_act_1)
        self.assertEqual(session.field_provenance.get("action_plan"), "user_selected_suggestion")

    def test_checkpoint_serialization_preserves_options_and_provenance(self):
        session = RiskCreationSession(
            session_id="chk-sess-1",
            user_id=101,
            user_role="Risk Owner",
            dept_id=1,
            dept_name="Operations",
            risk_name="Pump Cavitation",
            mitigation="Install inlet booster",
            mitigation_options=["Option A", "Option B"],
            action_plan_options=["Step 1", "Step 2"],
            field_provenance={"mitigation": "user_selected_suggestion"}
        )
        d = session.to_dict()
        restored = RiskCreationSession.from_dict(d)
        self.assertEqual(restored.mitigation_options, ["Option A", "Option B"])
        self.assertEqual(restored.action_plan_options, ["Step 1", "Step 2"])
        self.assertEqual(restored.field_provenance.get("mitigation"), "user_selected_suggestion")


if __name__ == "__main__":
    unittest.main()
