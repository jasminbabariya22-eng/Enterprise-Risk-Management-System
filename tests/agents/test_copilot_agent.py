"""
Agent Tests: ERMCopilotAgent Core Capabilities and Orchestration.
"""
import pytest
from unittest.mock import patch, MagicMock
from ERM_Copilot.agents.orchestrator.agent import ERMCopilotAgent
from ERM_Copilot.models.contracts import AgentRequest, AgentResponse


@pytest.mark.agent
def test_copilot_agent_initialization():
    agent = ERMCopilotAgent()
    assert agent.agent_id == "erm_copilot_agent"
    assert len(agent.capabilities) >= 5


@pytest.mark.agent
def test_copilot_agent_role_awareness(ro_context):
    agent = ERMCopilotAgent()
    req = AgentRequest(
        message="Show top risks",
        user_id=ro_context.user_id,
        user_role=ro_context.user_role,
        session_id=ro_context.session_id,
        metadata={"role": "Risk Owner", "dept_name": "Gas Processing Facilities"}
    )
    resp = agent.process(req)
    assert resp.success is True
    assert resp.response is not None
