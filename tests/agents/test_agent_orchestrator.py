"""
Agent Tests: Multi-Agent Orchestrator Delegation and State Transfer.
"""
import pytest
from unittest.mock import patch, MagicMock
from ERM_Copilot.agents.orchestrator.agent import ERMCopilotAgent
from ERM_Copilot.models.contracts import AgentRequest, AgentResponse


@pytest.mark.agent
def test_orchestrator_delegates_to_risk_creation(ro_context):
    agent = ERMCopilotAgent()
    req = AgentRequest(
        message="Create a new risk for turbine bearing leak",
        user_id=ro_context.user_id,
        user_role=ro_context.user_role,
        session_id=ro_context.session_id,
        metadata={"role": "Risk Owner", "dept_name": "Gas Processing Facilities"}
    )
    with patch("ERM_Copilot.agents.risk_creation.agent.risk_creation_agent.process") as mock_rc:
        mock_rc.return_value = AgentResponse(
            request_id="req-1",
            agent_id="risk_creation_agent",
            status="success",
            response="Step 2: Assign Co-Owner",
            metadata={"wizard_step": "STEP_CO_OWNER"}
        )
        resp = agent.process(req)
        assert resp.agent_id == "risk_creation_agent"
        mock_rc.assert_called_once()


@pytest.mark.agent
def test_orchestrator_delegates_to_approval_workflow(fh_context):
    agent = ERMCopilotAgent()
    req = AgentRequest(
        message="approve RSK-GAS-087",
        user_id=fh_context.user_id,
        user_role=fh_context.user_role,
        session_id=fh_context.session_id,
        metadata={"role": "Functional Head", "dept_id": 2, "user_id": "201"}
    )
    with patch("ERM_Copilot.agents.approval_workflow.agent.approval_workflow_agent.process") as mock_appr:
        mock_appr.return_value = AgentResponse(
            request_id="req-2",
            agent_id="agent_approval_workflow",
            status="success",
            response="Please provide your approval remark.",
            metadata={"intent": "AWAITING_REMARK"}
        )
        resp = agent.process(req)
        assert resp.agent_id == "agent_approval_workflow"
        mock_appr.assert_called_once()


@pytest.mark.agent
def test_orchestrator_delegates_to_treatment_management(ro_context):
    agent = ERMCopilotAgent()
    req = AgentRequest(
        message="Add action plan for RSK-GAS-049",
        user_id=ro_context.user_id,
        user_role=ro_context.user_role,
        session_id=ro_context.session_id,
        metadata={"role": "Risk Owner", "dept_id": 2, "user_id": "101"}
    )
    with patch("ERM_Copilot.agents.treatment.agent.treatment_management_agent.process") as mock_trt:
        mock_trt.return_value = AgentResponse(
            request_id="req-3",
            agent_id="treatment_management_agent",
            status="success",
            response="Please provide the action plan description.",
            metadata={"intent": "REQUEST_ACTION_PLAN"}
        )
        resp = agent.process(req)
        assert resp.agent_id == "treatment_management_agent"
        mock_trt.assert_called_once()

