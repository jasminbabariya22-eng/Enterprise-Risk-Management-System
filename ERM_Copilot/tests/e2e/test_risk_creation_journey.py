"""
End-to-End Conversational Journey: Risk Creation.
Simulates a complete interactive 14-step risk wizard journey including cancellation and successful save.
"""
import pytest
from unittest.mock import patch

from ERM_Copilot.agents.risk_creation.agent import RiskCreationAgent, risk_creation_agent
from ERM_Copilot.models.contracts import AgentRequest


def test_e2e_risk_creation_cancel_then_complete(in_memory_db):
    agent = RiskCreationAgent()
    user_id = "101"
    session_id = "sess-ro-journey-1"
    agent.clear_session(user_id)

    meta = {
        "role": "Risk Owner",
        "user_id": user_id,
        "dept_id": 2,
        "dept_name": "Gas Processing Facilities"
    }

    # 1. Start risk creation wizard with title
    req0 = AgentRequest(message="Create a new risk for gas leakage at compressor seal skid", user_id=user_id, user_role="Risk Owner", session_id=session_id, metadata=meta)
    resp0 = agent.process(req0)
    assert "Co-Owner" in resp0.response

    # 2. Cancel midway
    req_cancel = AgentRequest(message="cancel", user_id=user_id, user_role="Risk Owner", session_id=session_id, metadata=meta)
    resp_cancel = agent.process(req_cancel)
    assert "cancelled" in resp_cancel.response.lower()
    assert agent.is_session_active(user_id) is False

    # 3. Restart and run full sequence
    agent.clear_session(user_id)
    agent.process(AgentRequest(message="Create a new risk for gas leakage at compressor seal skid", user_id=user_id, user_role="Risk Owner", session_id=session_id, metadata=meta))
    agent.process(AgentRequest(message="none", user_id=user_id, user_role="Risk Owner", session_id=session_id, metadata=meta))
    agent.process(AgentRequest(message="High pressure gas escaping from compressor seal rings.", user_id=user_id, user_role="Risk Owner", session_id=session_id, metadata=meta))
    agent.process(AgentRequest(message="Likelihood 3, Impact 4", user_id=user_id, user_role="Risk Owner", session_id=session_id, metadata=meta))
    agent.process(AgentRequest(message="Regular maintenance and seal replacement.", user_id=user_id, user_role="Risk Owner", session_id=session_id, metadata=meta))
    agent.process(AgentRequest(message="Likelihood 2, Impact 2", user_id=user_id, user_role="Risk Owner", session_id=session_id, metadata=meta))
    agent.process(AgentRequest(message="Install dual mechanical dry gas seals", user_id=user_id, user_role="Risk Owner", session_id=session_id, metadata=meta))
    agent.process(AgentRequest(message="Karan Malhotra", user_id=user_id, user_role="Risk Owner", session_id=session_id, metadata=meta))
    agent.process(AgentRequest(message="2026-12-31", user_id=user_id, user_role="Risk Owner", session_id=session_id, metadata=meta))
    agent.process(AgentRequest(message="Draft", user_id=user_id, user_role="Risk Owner", session_id=session_id, metadata=meta))
    
    # Final confirmation and save
    with patch("ERM_Copilot.agents.risk_creation.agent.erm_db.create_risk", side_effect=in_memory_db.create_risk):
        save_resp = agent.process(AgentRequest(message="confirm and save", user_id=user_id, user_role="Risk Owner", session_id=session_id, metadata=meta))
        assert "Successfully" in save_resp.response
        assert len(in_memory_db.risks) == 2
        assert len(in_memory_db.history) == 1

