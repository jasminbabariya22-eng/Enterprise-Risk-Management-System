"""
Integration Tests for Risk Service Operations.
Verifies risk creation persistence, authoritative risk scoring, and ID generation.
"""
import pytest
from unittest.mock import patch

from ERM_Copilot.ai_harness.execution import ExecutionCoordinator


def test_risk_creation_persistence_integration(risk_owner_context, in_memory_db):
    with patch("ERM_Copilot.ai_harness.tool_registry.erm_db.create_risk", side_effect=in_memory_db.create_risk):
        result = ExecutionCoordinator.execute_tool(
            tool_name="save_risk",
            arguments={"risk_name": "Turbine Overheating", "dept_id": 2},
            context=risk_owner_context,
            bypass_confirmation=True
        )
        assert result["success"] is True
        saved = result["result"]
        assert saved["status"] == "success"
        assert saved["risk_id"].startswith("RSK-GEN-")
        assert len(in_memory_db.risks) == 2


def test_authoritative_scoring_calculation(risk_owner_context):
    result = ExecutionCoordinator.execute_tool(
        tool_name="calculate_risk_assessment",
        arguments={"likelihood_id": 3, "impact_id": 4},
        context=risk_owner_context
    )
    score, level, badge = result["result"]
    assert score == 12
    assert level == "HIGH"
