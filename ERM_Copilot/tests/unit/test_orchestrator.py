"""
Unit Tests for ERMCopilotAgent Master Orchestrator.
Verifies query transformation, routing to specialized subagents, and response contracts.
"""
import pytest
from unittest.mock import MagicMock, patch

from ERM_Copilot.agents.orchestrator.agent import ERMCopilotAgent, erm_copilot_agent
from ERM_Copilot.models.contracts import AgentRequest, AgentResponse


def test_orchestrator_initialization():
    agent = ERMCopilotAgent()
    assert agent.agent_id == "erm_copilot_agent"
    assert "search_risk_register" in agent.capabilities
    assert "get_approval_queues" in agent.capabilities


def test_orchestrator_greeting_response(risk_owner_context):
    req = AgentRequest(
        message="hello",
        user_id=risk_owner_context.user_id,
        user_role=risk_owner_context.user_role,
        session_id=risk_owner_context.session_id,
        metadata={"role": "Risk Owner", "dept_name": "Gas Processing Facilities"}
    )
    resp = erm_copilot_agent.process(req)
    assert resp.success is True
    assert "Risk Owner" in resp.response or "Risk" in resp.response


def test_orchestrator_routes_to_treatment_management(risk_owner_context):
    req = AgentRequest(
        message="add treatment plan for RSK-GAS-087",
        user_id=risk_owner_context.user_id,
        user_role=risk_owner_context.user_role,
        session_id=risk_owner_context.session_id,
        metadata={"role": "Risk Owner", "dept_name": "Gas Processing Facilities"}
    )
    with patch("ERM_Copilot.agents.treatment.treatment_management_agent.process") as mock_treat:
        mock_treat.return_value = AgentResponse(
            request_id="req-test",
            agent_id="treatment_management_agent",
            status="success",
            response="Please enter the action plan description.",
            metadata={"intent": "ADD_TREATMENT"}
        )
        resp = erm_copilot_agent.process(req)
        assert resp.agent_id == "treatment_management_agent"
        mock_treat.assert_called_once()
