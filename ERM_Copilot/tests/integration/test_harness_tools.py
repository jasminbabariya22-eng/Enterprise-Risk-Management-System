"""
Integration Tests for ERM AI Harness with Governed Tools.
Verifies complete flow from HarnessContext -> Policy -> ExecutionCoordinator -> Tool Handlers.
"""
import pytest
from unittest.mock import patch

from ERM_Copilot.ai_harness.harness import ERMAIHarness
from ERM_Copilot.ai_harness.execution import ExecutionCoordinator
from ERM_Copilot.ai_harness.exceptions import (
    AuthorizationError,
    ConfirmationRequiredError,
    ToolValidationError,
)


def test_harness_executes_search_risks_integration(risk_owner_context, in_memory_db):
    with patch("ERM_Copilot.ai_harness.tool_registry.erm_db.search_risks", return_value=[in_memory_db.risks["RSK-GAS-087"]]):
        result = ExecutionCoordinator.execute_tool(
            tool_name="search_risks",
            arguments={"query": "pipeline", "dept_id": 2},
            context=risk_owner_context
        )
        assert result["success"] is True
        items = result["result"]
        assert len(items) >= 1
        assert items[0]["risk_id"] == "RSK-GAS-087"



def test_harness_blocks_unauthorized_tool_execution(auditor_context):
    with pytest.raises(AuthorizationError):
        ExecutionCoordinator.execute_tool(
            tool_name="approve_or_reject_risk",
            arguments={"risk_id": "RSK-GAS-087", "action": "approve", "remark": "OK"},
            context=auditor_context
        )


def test_harness_enforces_mandatory_remark(functional_head_context):
    with pytest.raises(ToolValidationError):
        ExecutionCoordinator.execute_tool(
            tool_name="approve_or_reject_risk",
            arguments={"risk_id": "RSK-GAS-087", "action": "approve", "remark": "   "},
            context=functional_head_context
        )
