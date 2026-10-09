"""
Integration Tests: Email Notification Triggering and Job Queue Insertion.
"""
import pytest
from unittest.mock import patch
from ERM_Copilot.ai_harness.execution import ExecutionCoordinator


@pytest.mark.integration
def test_email_queued_on_risk_rejection(fh_context, in_memory_db):
    with patch("ERM_Copilot.ai_harness.tool_registry.erm_db.approve_or_reject_risk", side_effect=in_memory_db.approve_or_reject_risk):
        res = ExecutionCoordinator.execute_tool(
            "approve_or_reject_risk",
            {"risk_id": "RSK-GAS-087", "action": "reject", "remark": "Action plan incomplete"},
            fh_context,
            bypass_confirmation=True
        )
        assert res["success"] is True
        assert len(in_memory_db.email_jobs) == 1
        assert in_memory_db.email_jobs[0]["action"] == "reject"
        assert in_memory_db.email_jobs[0]["recipient_role"] == "Risk Owner"
