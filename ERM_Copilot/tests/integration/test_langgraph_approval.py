"""
Integration Tests for LangGraph Conversational Approval Workflow with AI Harness.
Verifies multi-turn state transitions, confirmation capture, and backend execution.
"""
import pytest
from unittest.mock import patch

from ERM_Copilot.agents.approval.graph import ApprovalWorkflowAgent, ApprovalWorkflowGraph
from ERM_Copilot.models.contracts import AgentRequest


def test_langgraph_approval_turn_sequence(functional_head_context, in_memory_db):
    agent = ApprovalWorkflowAgent()
    agent.clear_session("201")

    with patch("ERM_Copilot.agents.approval.tools.erm_db.approve_or_reject_risk", side_effect=in_memory_db.approve_or_reject_risk):
        # Turn 1: User says "approve RSK-GAS-087" without remark
        req1 = AgentRequest(
            message="approve RSK-GAS-087",
            user_id="201",
            user_role="Functional Head",
            session_id="201",
            metadata={"role": "Functional Head", "dept_id": 2, "user_id": "201"}
        )
        resp1 = agent.process(req1)
        assert "remark" in resp1.response.lower()
        assert resp1.metadata.get("intent") == "AWAITING_REMARK" or resp1.metadata.get("workflow_state") == "AWAITING_REMARK"

        # Turn 2: User provides remark -> receives confirmation prompt
        req2 = AgentRequest(
            message="Mitigation verified and pressure sensors checked.",
            user_id="201",
            user_role="Functional Head",
            session_id="201",
            metadata={"role": "Functional Head", "dept_id": 2, "user_id": "201"}
        )
        resp2 = agent.process(req2)
        assert "confirm" in resp2.response.lower()
        assert resp2.metadata.get("intent") == "AWAITING_CONFIRMATION" or resp2.metadata.get("workflow_state") == "AWAITING_CONFIRMATION"


        # Turn 3: User confirms -> backend executes and moves to Stage 3 RM
        req3 = AgentRequest(
            message="confirm and approve",
            user_id="201",
            user_role="Functional Head",
            session_id="201",
            metadata={"role": "Functional Head", "dept_id": 2, "user_id": "201"}
        )
        resp3 = agent.process(req3)
        assert "successfully" in resp3.response.lower() or "approved" in resp3.response.lower()
        assert in_memory_db.risks["RSK-GAS-087"]["risk_status"] == 3 # Stage 3 RM
        assert len(in_memory_db.history) == 1
        assert in_memory_db.history[0]["action"] == "approve"
