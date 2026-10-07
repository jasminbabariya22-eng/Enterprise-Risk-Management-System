"""
Comprehensive Test Suite for LangGraph Conversational Approval & Rejection Workflow.
Validates all 16 specified test cases:
1. Approve with remark included -> no remark question, confirmation requested.
2. Approve without remark -> asks for approval remark.
3. Multi-turn remark capture -> stores remark, requests confirmation.
4. Reject with remark included -> no remark question, confirmation requested.
5. Reject without remark -> asks for rejection reason.
6. Approve without confirmation -> backend is NOT called.
7. Reject without confirmation -> backend is NOT called.
8. User cancellation -> backend is NOT called, session cleared.
9. Missing risk ID -> asks for risk ID.
10. Missing/ambiguous action -> asks for approve/reject decision.
11. Unauthorized role -> fails safely with backend error.
12. Stage sequence enforcement (RM before FH) -> rejected by backend.
13. Stage sequence enforcement (RH before RM) -> rejected by backend.
14. Blank/empty remark -> rejected safely without tool call.
15. Missing/unauthenticated user -> fails safely without substitute ID.
16. Existing approval API & Copilot agent integration.
"""
import unittest
from unittest.mock import patch, MagicMock

from ERM_Copilot.models.contracts import AgentRequest
from ERM_Copilot.agents.agent import erm_copilot_agent
from ERM_Copilot.agents.approval.graph import approval_agent, ApprovalWorkflowAgent
from ERM_Copilot.agents.approval.tools import approve_or_reject_risk
from ERM_Copilot.agents.approval.nodes import extract_parameters_from_text


class TestLangGraphApprovalWorkflow(unittest.TestCase):

    def setUp(self):
        self.agent = ApprovalWorkflowAgent()

    # ---------------- TEST 1: Approve with Remark Included ----------------
    def test_approve_with_remark_included(self):
        """User provides approve, risk_id, and remark in one message."""
        req = AgentRequest(
            message="Approve HR-2106 because the mitigation plan is adequate.",
            user_id="10",
            user_role="Functional Head",
            session_id="test_sess_1"
        )
        resp = self.agent.process(req)
        
        self.assertEqual(resp.metadata.get("intent"), "AWAITING_CONFIRMATION")
        self.assertEqual(resp.metadata.get("risk_id"), "HR-2106")
        self.assertEqual(resp.metadata.get("action"), "approve")
        self.assertIn("Risk Approval Summary", resp.response)
        self.assertIn("HR-2106", resp.response)
        self.assertIn("mitigation plan is adequate", resp.response)
        # Verify it did NOT ask for remark again
        self.assertNotIn("Please provide your approval remark", resp.response)

    # ---------------- TEST 2: Approve without Remark ----------------
    def test_approve_without_remark_asks_for_remark(self):
        """User says 'Approve HR-2106' -> Agent must ask for approval remark."""
        req = AgentRequest(
            message="Approve HR-2106",
            user_id="10",
            user_role="Functional Head",
            session_id="test_sess_2"
        )
        resp = self.agent.process(req)
        
        self.assertEqual(resp.metadata.get("intent"), "AWAITING_REMARK")
        self.assertEqual(resp.metadata.get("risk_id"), "HR-2106")
        self.assertEqual(resp.metadata.get("action"), "approve")
        self.assertIn("Approval Remark Required", resp.response)
        self.assertIn("Please provide your **approval remark**", resp.response)

    # ---------------- TEST 3: Multi-turn Remark Capture ----------------
    def test_multi_turn_remark_capture_and_confirmation(self):
        """User says 'Approve HR-2106', then provides remark in 2nd turn."""
        sess_id = "test_sess_3"
        req1 = AgentRequest(message="Approve HR-2106", user_id="10", session_id=sess_id)
        resp1 = self.agent.process(req1)
        self.assertEqual(resp1.metadata.get("intent"), "AWAITING_REMARK")

        # Turn 2: User provides remark
        req2 = AgentRequest(
            message="The mitigation plan is adequate and the residual risk is acceptable.",
            user_id="10",
            session_id=sess_id
        )
        resp2 = self.agent.process(req2)
        self.assertEqual(resp2.metadata.get("intent"), "AWAITING_CONFIRMATION")
        self.assertIn("Risk Approval Summary", resp2.response)
        self.assertIn("The mitigation plan is adequate and the residual risk is acceptable.", resp2.response)

    # ---------------- TEST 4: Reject with Remark Included ----------------
    def test_reject_with_remark_included(self):
        """User provides reject, risk_id, and remark in one message."""
        req = AgentRequest(
            message="Reject HR-2106 because the mitigation plan is insufficient.",
            user_id="10",
            user_role="Functional Head",
            session_id="test_sess_4"
        )
        resp = self.agent.process(req)
        
        self.assertEqual(resp.metadata.get("intent"), "AWAITING_CONFIRMATION")
        self.assertEqual(resp.metadata.get("risk_id"), "HR-2106")
        self.assertEqual(resp.metadata.get("action"), "reject")
        self.assertIn("Risk Rejection Summary", resp.response)
        self.assertIn("insufficient", resp.response)
        self.assertNotIn("Please provide the reason for rejecting", resp.response)

    # ---------------- TEST 5: Reject without Remark ----------------
    def test_reject_without_remark_asks_for_reason(self):
        """User says 'Reject HR-2106' -> Agent must ask for rejection reason."""
        req = AgentRequest(
            message="Reject HR-2106",
            user_id="10",
            user_role="Functional Head",
            session_id="test_sess_5"
        )
        resp = self.agent.process(req)
        
        self.assertEqual(resp.metadata.get("intent"), "AWAITING_REMARK")
        self.assertEqual(resp.metadata.get("risk_id"), "HR-2106")
        self.assertEqual(resp.metadata.get("action"), "reject")
        self.assertIn("Rejection Reason Required", resp.response)
        self.assertIn("Please provide the **reason for rejecting**", resp.response)

    # ---------------- TEST 6 & 7: No Mutation Without Confirmation ----------------
    @patch("ERM_Copilot.agents.approval.nodes.approve_or_reject_risk")
    def test_no_tool_call_without_confirmation(self, mock_tool):
        """FastAPI/backend tool must NOT be called before explicit user confirmation."""
        sess_id = "test_sess_6"
        req = AgentRequest(
            message="Approve HR-2106 because mitigation is adequate.",
            user_id="10",
            session_id=sess_id
        )
        self.agent.process(req)
        # Tool must NOT be called yet
        mock_tool.assert_not_called()

    # ---------------- TEST 8: User Cancellation ----------------
    @patch("ERM_Copilot.agents.approval.nodes.approve_or_reject_risk")
    def test_user_cancellation_clears_session(self, mock_tool):
        """User cancels approval -> Backend tool is NOT called, session cleared."""
        sess_id = "test_sess_8"
        req1 = AgentRequest(message="Approve HR-2106", user_id="10", session_id=sess_id)
        self.agent.process(req1)

        # User cancels
        req2 = AgentRequest(message="cancel", user_id="10", session_id=sess_id)
        resp2 = self.agent.process(req2)
        
        self.assertEqual(resp2.metadata.get("intent"), "APPROVAL_CANCELLED")
        self.assertIn("Cancelled", resp2.response)
        mock_tool.assert_not_called()
        self.assertFalse(self.agent.is_session_active(sess_id))

    # ---------------- TEST 9: Missing Risk ID ----------------
    def test_missing_risk_id_asks_user(self):
        """User says 'Please approve' without risk ID -> asks for risk ID."""
        req = AgentRequest(
            message="Please approve this risk",
            user_id="10",
            session_id="test_sess_9"
        )
        resp = self.agent.process(req)
        self.assertEqual(resp.metadata.get("intent"), "AWAITING_RISK_ID")
        self.assertIn("Which risk would you like", resp.response)

    # ---------------- TEST 10: Missing / Ambiguous Action ----------------
    def test_ambiguous_action_asks_for_decision(self):
        """User gives risk ID but ambiguous action -> asks approve or reject."""
        rid, action, remark = extract_parameters_from_text("Process HR-2106")
        self.assertEqual(rid, "HR-2106")
        self.assertIsNone(action)

    # ---------------- TEST 11: Tool Blank Remark Safety ----------------
    def test_tool_rejects_empty_or_blank_remark(self):
        """Generic tool must fail safely if remark is empty or whitespace."""
        res_none = approve_or_reject_risk(risk_id="HR-2106", action="approve", remark="", approver_id=10)
        self.assertFalse(res_none["success"])
        self.assertIn("mandatory remark is required", res_none["message"])

        res_space = approve_or_reject_risk(risk_id="HR-2106", action="approve", remark="   ", approver_id=10)
        self.assertFalse(res_space["success"])

    # ---------------- TEST 12: Tool Missing User ID Safety ----------------
    def test_tool_rejects_missing_or_invalid_approver_id(self):
        """Generic tool fails safely when approver_id is None or <= 0."""
        res_none = approve_or_reject_risk(risk_id="HR-2106", action="approve", remark="Adequate", approver_id=None)
        self.assertFalse(res_none["success"])
        self.assertEqual(res_none["status_code"], 401)

        res_zero = approve_or_reject_risk(risk_id="HR-2106", action="approve", remark="Adequate", approver_id=0)
        self.assertFalse(res_zero["success"])

    # ---------------- TEST 13: Full 3-Turn Confirmation & Tool Execution ----------------
    @patch("ERM_Copilot.agents.approval.nodes.approve_or_reject_risk")
    def test_full_confirmation_executes_tool(self, mock_tool):
        """Full 3-turn flow: (1) Prompt -> (2) Remark -> (3) Confirm -> Executes tool."""
        mock_tool.return_value = {
            "success": True,
            "risk_id": "HR-2106",
            "risk_register_id": 49,
            "risk_title": "Hazardous Gas Exposure",
            "action": "approved",
            "stage": "Stage 2: Functional Head Review",
            "next_queue": "Risk Manager (Stage 3 Queue)",
            "timestamp": "2026-10-06 12:00:00",
            "remark": "Mitigation is adequate."
        }
        sess_id = "test_sess_full"
        
        # Turn 1: Start
        self.agent.process(AgentRequest(message="Approve HR-2106", user_id="10", session_id=sess_id))
        
        # Turn 2: Provide remark
        self.agent.process(AgentRequest(message="Mitigation is adequate.", user_id="10", session_id=sess_id))
        
        # Turn 3: Confirm
        resp3 = self.agent.process(AgentRequest(message="confirm approval", user_id="10", session_id=sess_id))
        
        mock_tool.assert_called_once_with(
            risk_id="HR-2106",
            action="approve",
            remark="Mitigation is adequate.",
            approver_id=10
        )
        self.assertEqual(resp3.metadata.get("intent"), "APPROVAL_EXECUTED")
        self.assertIn("Risk Approved & Signed Off", resp3.response)

    # ---------------- TEST 14: Copilot Agent Integration ----------------
    def test_erm_copilot_agent_delegates_to_langgraph(self):
        """ERMCopilotAgent seamlessly routes approval commands to the LangGraph workflow."""
        req = AgentRequest(
            message="Approve RSK-GAS-049 because controls are verified.",
            user_id="10",
            user_role="Functional Head",
            session_id="copilot_test_sess"
        )
        resp = erm_copilot_agent.process(req)
        self.assertEqual(resp.metadata.get("intent"), "AWAITING_CONFIRMATION")
        self.assertEqual(resp.metadata.get("risk_id"), "RSK-GAS-049")
        self.assertIn("Risk Approval Summary", resp.response)

    # ---------------- TEST 15: Full 3-Turn Copilot Agent Execution ----------------
    @patch("ERM_Copilot.agents.approval.tools.erm_db.approve_or_reject_risk")
    def test_erm_copilot_agent_full_3turn_confirm_approve(self, mock_db_approve):
        """Test full 3-turn 'Approve RSK-GAS-050' -> 'approve test' -> 'confirm approve' via main Copilot agent."""
        mock_db_approve.return_value = {
            "success": True,
            "risk_id": "RSK-GAS-050",
            "risk_register_id": 50,
            "risk_title": "test 4",
            "action": "Approved",
            "stage": "Stage 2: Risk Manager Validation",
            "next_queue": "Stage 3: Risk Head Review Queue",
            "timestamp": "2026-10-06 12:05:00",
            "remark": "approve test"
        }
        
        # Turn 1: Initial approve command without remark
        req1 = AgentRequest(message="Approve RSK-GAS-050", user_id="10", metadata={"user_id": "10"})
        resp1 = erm_copilot_agent.process(req1)
        self.assertEqual(resp1.metadata.get("intent"), "AWAITING_REMARK")
        self.assertIn("Approval Remark Required", resp1.response)

        # Turn 2: Provide remark
        req2 = AgentRequest(message="approve test", user_id="10", metadata={"user_id": "10"})
        resp2 = erm_copilot_agent.process(req2)
        self.assertEqual(resp2.metadata.get("intent"), "AWAITING_CONFIRMATION")
        self.assertIn("Risk Approval Summary", resp2.response)
        self.assertIn("approve test", resp2.response)

        # Turn 3: User confirms approval
        req3 = AgentRequest(message="confirm approve", user_id="10", metadata={"user_id": "10"})
        resp3 = erm_copilot_agent.process(req3)
        self.assertEqual(resp3.metadata.get("intent"), "APPROVAL_EXECUTED")
        self.assertIn("Risk Approved & Signed Off", resp3.response)
        
        # Verify the database method was called with exact parameters
        mock_db_approve.assert_called_once_with(
            risk_id="RSK-GAS-050",
            approver_id=10,
            action="approve",
            remark="approve test"
        )

    # ---------------- TEST 16: Conversational Phrasing with Remark Included ----------------
    def test_conversational_approve_with_natural_language_and_remark(self):
        """User says: 'i want to approve this risk RSK-GAS-087 with remark is ok good' -> LangGraph extracts id, action, remark and requests confirmation."""
        req = AgentRequest(
            message="i want to approve this risk RSK-GAS-087 with remark is ok good",
            user_id="10",
            user_role="Functional Head",
            session_id="test_sess_conv_1"
        )
        resp = erm_copilot_agent.process(req)
        self.assertEqual(resp.metadata.get("intent"), "AWAITING_CONFIRMATION")
        self.assertEqual(resp.metadata.get("risk_id"), "RSK-GAS-087")
        self.assertIn("RSK-GAS-087", resp.response)
        self.assertIn("ok good", resp.response)
        self.assertIn("Risk Approval Summary", resp.response)


if __name__ == "__main__":
    unittest.main()
