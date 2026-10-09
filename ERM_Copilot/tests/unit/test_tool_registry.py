"""
Unit Tests for ToolRegistry and Tool Definitions.
Verifies tool registration, argument schema validation, and tool lookup constraints.
"""
import pytest
from ERM_Copilot.ai_harness.tool_registry import ToolRegistry, ToolDefinition, ToolCategory, tool_registry
from ERM_Copilot.ai_harness.exceptions import ToolNotFoundError, ToolValidationError


def test_tool_registry_lookup_registered_tools():
    assert tool_registry.has("search_risks") is True
    assert tool_registry.has("approve_or_reject_risk") is True
    assert tool_registry.has("save_risk") is True
    assert tool_registry.has("add_risk_treatment") is True
    assert tool_registry.has("calculate_risk_assessment") is True

    tool = tool_registry.get("search_risks")
    assert tool.name == "search_risks"
    assert tool.category == ToolCategory.SEARCH
    assert tool.is_state_changing is False
    assert tool.requires_confirmation is False


def test_tool_registry_unknown_tool_raises():
    with pytest.raises(ToolNotFoundError) as exc_info:
        tool_registry.get("unregistered_malicious_tool")
    assert "not registered" in str(exc_info.value).lower()


def test_tool_registry_list_tools_filtering():
    all_tools = tool_registry.list_tools()
    assert len(all_tools) >= 8

    # Filter by Risk Owner (cannot approve risks)
    ro_tools = [t.name for t in tool_registry.list_tools(user_role="Risk Owner")]
    assert "search_risks" in ro_tools
    assert "save_risk" in ro_tools
    assert "approve_or_reject_risk" not in ro_tools

    # Filter by Functional Head (can approve risks)
    fh_tools = [t.name for t in tool_registry.list_tools(user_role="Functional Head")]
    assert "approve_or_reject_risk" in fh_tools


def test_tool_registry_validate_arguments_approve():
    # Valid arguments
    valid_args = {"risk_id": "RSK-GAS-087", "action": "approve", "remark": "Mitigation reviewed"}
    assert tool_registry.validate_arguments("approve_or_reject_risk", valid_args) == valid_args

    # Missing remark
    with pytest.raises(ToolValidationError):
        tool_registry.validate_arguments("approve_or_reject_risk", {"risk_id": "RSK-001", "action": "approve", "remark": ""})

    # Invalid action
    with pytest.raises(ToolValidationError):
        tool_registry.validate_arguments("approve_or_reject_risk", {"risk_id": "RSK-001", "action": "delete", "remark": "test"})


def test_tool_registry_validate_arguments_save_risk():
    with pytest.raises(ToolValidationError):
        tool_registry.validate_arguments("save_risk", {"dept_id": 2}) # Missing risk_name
