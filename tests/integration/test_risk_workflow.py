"""
Integration Tests: Risk Creation Lifecycle & Database Verification.
"""
import pytest
from unittest.mock import patch
from ERM_Copilot.ai_harness.execution import ExecutionCoordinator


@pytest.mark.integration
def test_risk_creation_persistence_workflow(ro_context, in_memory_db):
    with patch("ERM_Copilot.ai_harness.tool_registry.erm_db.create_risk", side_effect=in_memory_db.create_risk):
        result = ExecutionCoordinator.execute_tool(
            tool_name="save_risk",
            arguments={"risk_name": "Pipeline Cavitation", "dept_id": 2},
            context=ro_context,
            bypass_confirmation=True
        )
        assert result["success"] is True
        saved = result["result"]
        assert saved["status"] == "success"
        assert len(in_memory_db.risks) == 3
        assert len(in_memory_db.history) == 1
