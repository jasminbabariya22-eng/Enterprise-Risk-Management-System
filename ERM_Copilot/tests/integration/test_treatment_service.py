"""
Integration Tests for Treatment Management Operations.
Verifies treatment addition, progress updates, and data integrity.
"""
import pytest
from unittest.mock import patch

from ERM_Copilot.ai_harness.execution import ExecutionCoordinator


def test_add_treatment_integration(risk_owner_context, in_memory_db):
    with patch("ERM_Copilot.ai_harness.tool_registry.erm_db.add_risk_treatment", side_effect=in_memory_db.add_risk_treatment):
        result = ExecutionCoordinator.execute_tool(
            tool_name="add_risk_treatment",
            arguments={
                "risk_register_id": 87,
                "action_plan": "Replace faulty seal rings",
                "action_owner_id": 101,
                "target_date": "2026-11-30",
                "progress": 0,
                "action_status_id": 1,
                "created_by": 101
            },
            context=risk_owner_context,
            bypass_confirmation=True
        )
        assert result["success"] is True
        assert len(in_memory_db.risks["RSK-GAS-087"]["treatments"]) == 2


def test_update_treatment_progress_integration(risk_owner_context, in_memory_db):
    with patch("ERM_Copilot.ai_harness.tool_registry.erm_db.update_treatment_progress", side_effect=in_memory_db.update_treatment_progress):
        result = ExecutionCoordinator.execute_tool(
            tool_name="update_treatment_progress",
            arguments={
                "treatment_id": 1,
                "progress": 85,
                "modified_by": 101
            },
            context=risk_owner_context,
            bypass_confirmation=True
        )
        assert result["success"] is True
        assert in_memory_db.risks["RSK-GAS-087"]["treatments"][0]["progress"] == 85
