"""
Agent Tests: Tool Selection, Schemas, and Permission Check Integration.
"""
import pytest
from ERM_Copilot.ai_harness.tool_registry import tool_registry
from ERM_Copilot.ai_harness.execution import ExecutionCoordinator
from ERM_Copilot.ai_harness.exceptions import AuthorizationError, ToolNotFoundError


@pytest.mark.agent
def test_tool_registry_contains_governance_tools():
    assert tool_registry.has("approve_or_reject_risk") is True
    assert tool_registry.has("search_risks") is True
    assert tool_registry.has("calculate_risk_assessment") is True
    assert tool_registry.has("save_risk") is True


@pytest.mark.agent
def test_tool_selection_validates_required_parameters(fh_context):
    # Attempt execution with missing action
    with pytest.raises(Exception):
        ExecutionCoordinator.execute_tool(
            "approve_or_reject_risk",
            {"risk_id": "RSK-001", "remark": "approved"},
            fh_context
        )
