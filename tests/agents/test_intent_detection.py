"""
Agent Tests: Intent Classification Across ERM Queries and User Roles.
"""
import pytest
from ERM_Copilot.agents.treatment.agent import TreatmentManagementAgent
from ERM_Copilot.agents.risk_creation.agent import RiskCreationAgent
from ERM_Copilot.agents.approval.nodes import extract_approval_request


@pytest.mark.agent
def test_treatment_intent_detection():
    assert TreatmentManagementAgent.is_add_treatment_trigger("add treatment for RSK-001") is True
    assert TreatmentManagementAgent.is_add_treatment_trigger("new action plan") is True
    assert TreatmentManagementAgent.is_cancellation("cancel") is True


@pytest.mark.agent
def test_risk_creation_intent_detection():
    assert RiskCreationAgent.is_start_trigger("create risk") is True
    assert RiskCreationAgent.is_start_trigger("create a new risk for pump failure") is True
    assert RiskCreationAgent.is_cancellation("abort") is True


@pytest.mark.agent
def test_approval_intent_parameter_extraction():
    state = {"last_user_message": "approve RSK-GAS-087 with remark Verified"}
    res_state = extract_approval_request(state)
    assert res_state.get("risk_id") == "RSK-GAS-087"
    assert res_state.get("action") == "approve"
    assert "Verified" in res_state.get("remark", "")
