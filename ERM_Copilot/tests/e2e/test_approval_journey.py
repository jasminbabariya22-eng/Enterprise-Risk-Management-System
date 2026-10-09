"""
End-to-End Conversational Journey: Sequential Governance Approval.
Simulates FH -> RM -> RH signoff sequencing with confirmation enforcement.
"""
import pytest
from unittest.mock import patch

from ERM_Copilot.agents.approval.graph import ApprovalWorkflowAgent
from ERM_Copilot.models.contracts import AgentRequest


def test_e2e_sequential_approval_fh_rm_rh(in_memory_db):
    agent = ApprovalWorkflowAgent()

    with patch("ERM_Copilot.agents.approval.tools.erm_db.approve_or_reject_risk", side_effect=in_memory_db.approve_or_reject_risk):
        # 1. STAGE 2: Functional Head Approval
        agent.clear_session("201")
        agent.process(AgentRequest(message="approve RSK-GAS-087", user_id="201", user_role="Functional Head", session_id="201"))
        agent.process(AgentRequest(message="FH Verified risk mitigations", user_id="201", user_role="Functional Head", session_id="201"))
        fh_resp = agent.process(AgentRequest(message="confirm", user_id="201", user_role="Functional Head", session_id="201"))
        assert "successfully" in fh_resp.response.lower() or "approved" in fh_resp.response.lower()
        assert in_memory_db.risks["RSK-GAS-087"]["risk_status"] == 3 # Stage 3 RM

        # 2. STAGE 3: Risk Manager Approval
        agent.clear_session("301")
        agent.process(AgentRequest(message="approve RSK-GAS-087", user_id="301", user_role="Risk Manager", session_id="301"))
        agent.process(AgentRequest(message="RM Evaluated risk matrix consistency", user_id="301", user_role="Risk Manager", session_id="301"))
        rm_resp = agent.process(AgentRequest(message="confirm", user_id="301", user_role="Risk Manager", session_id="301"))
        assert "successfully" in rm_resp.response.lower() or "approved" in rm_resp.response.lower()
        assert in_memory_db.risks["RSK-GAS-087"]["risk_status"] == 4 # Stage 4 RH

        # 3. STAGE 4: Risk Head Final Approval
        agent.clear_session("401")
        agent.process(AgentRequest(message="approve RSK-GAS-087", user_id="401", user_role="Risk Head", session_id="401"))
        agent.process(AgentRequest(message="RH Executive signoff completed", user_id="401", user_role="Risk Head", session_id="401"))
        rh_resp = agent.process(AgentRequest(message="confirm", user_id="401", user_role="Risk Head", session_id="401"))
        assert "successfully" in rh_resp.response.lower() or "approved" in rh_resp.response.lower()
        assert in_memory_db.risks["RSK-GAS-087"]["risk_status"] == 1 # Final Approved / Active
        assert len(in_memory_db.history) == 3
        assert len(in_memory_db.email_jobs) == 3
