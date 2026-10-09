"""
End-to-End Conversational Journey: Risk Rejection & Return.
Simulates rejecting a risk with mandatory justification, cancellation, and status return.
"""
import pytest
from unittest.mock import patch

from ERM_Copilot.agents.approval.graph import ApprovalWorkflowAgent
from ERM_Copilot.models.contracts import AgentRequest


def test_e2e_rejection_journey_with_mandatory_remark(in_memory_db):
    agent = ApprovalWorkflowAgent()
    user_id = "201"
    agent.clear_session(user_id)

    with patch("ERM_Copilot.agents.approval.tools.erm_db.approve_or_reject_risk", side_effect=in_memory_db.approve_or_reject_risk):
        # 1. User says "reject RSK-GAS-087" without reason
        req1 = AgentRequest(message="reject RSK-GAS-087", user_id=user_id, user_role="Functional Head", session_id=user_id)
        resp1 = agent.process(req1)
        assert "reason" in resp1.response.lower() or "remark" in resp1.response.lower()

        # 2. User supplies reason
        req2 = AgentRequest(message="Mitigation plan lacks emergency shutdown procedure.", user_id=user_id, user_role="Functional Head", session_id=user_id)
        resp2 = agent.process(req2)
        assert "confirm" in resp2.response.lower()

        # 3. User cancels first
        req3 = AgentRequest(message="cancel", user_id=user_id, user_role="Functional Head", session_id=user_id)
        resp3 = agent.process(req3)
        assert "cancelled" in resp3.response.lower()
        assert in_memory_db.risks["RSK-GAS-087"]["risk_status"] == 2 # Unchanged

        # 4. Repeat and confirm rejection
        agent.clear_session(user_id)
        agent.process(AgentRequest(message="reject RSK-GAS-087", user_id=user_id, user_role="Functional Head", session_id=user_id))
        agent.process(AgentRequest(message="Mitigation plan lacks emergency shutdown procedure.", user_id=user_id, user_role="Functional Head", session_id=user_id))
        final_resp = agent.process(AgentRequest(message="confirm rejection", user_id=user_id, user_role="Functional Head", session_id=user_id))
        
        assert "rejected" in final_resp.response.lower() or "returned" in final_resp.response.lower()
        assert in_memory_db.risks["RSK-GAS-087"]["risk_status"] == 5 # Returned / Rejected
        assert in_memory_db.risks["RSK-GAS-087"]["risk_function_head_approval_status"] == 2 # Rejected by FH
