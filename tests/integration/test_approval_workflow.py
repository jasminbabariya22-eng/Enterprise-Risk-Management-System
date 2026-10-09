"""
Integration Tests: Multi-Stage Approval Governance Sequence (FH -> RM -> RH).
"""
import pytest
from unittest.mock import patch
from ERM_Copilot.ai_harness.execution import ExecutionCoordinator


@pytest.mark.integration
def test_three_stage_approval_sequence(fh_context, rm_context, rh_context, in_memory_db):
    with patch("ERM_Copilot.ai_harness.tool_registry.erm_db.approve_or_reject_risk", side_effect=in_memory_db.approve_or_reject_risk):
        # Stage 2: Functional Head
        res_fh = ExecutionCoordinator.execute_tool(
            "approve_or_reject_risk",
            {"risk_id": "RSK-GAS-087", "action": "approve", "remark": "FH signoff"},
            fh_context,
            bypass_confirmation=True
        )
        assert res_fh["success"] is True
        assert in_memory_db.risks["RSK-GAS-087"]["risk_status"] == 3

        # Stage 3: Risk Manager
        res_rm = ExecutionCoordinator.execute_tool(
            "approve_or_reject_risk",
            {"risk_id": "RSK-GAS-087", "action": "approve", "remark": "RM signoff"},
            rm_context,
            bypass_confirmation=True
        )
        assert res_rm["success"] is True
        assert in_memory_db.risks["RSK-GAS-087"]["risk_status"] == 4

        # Stage 4: Risk Head
        res_rh = ExecutionCoordinator.execute_tool(
            "approve_or_reject_risk",
            {"risk_id": "RSK-GAS-087", "action": "approve", "remark": "RH signoff"},
            rh_context,
            bypass_confirmation=True
        )
        assert res_rh["success"] is True
        assert in_memory_db.risks["RSK-GAS-087"]["risk_status"] == 1 # Final active
