"""
Integration Tests for Audit Trail Logging and Email Job Queue Dispatch.
Verifies that governance decisions record immutable history and trigger asynchronous notification jobs.
"""
import pytest
from unittest.mock import patch

from ERM_Copilot.ai_harness.execution import ExecutionCoordinator


def test_audit_and_email_queue_on_approval(functional_head_context, in_memory_db):
    with patch("ERM_Copilot.ai_harness.tool_registry.erm_db.approve_or_reject_risk", side_effect=in_memory_db.approve_or_reject_risk):
        result = ExecutionCoordinator.execute_tool(
            tool_name="approve_or_reject_risk",
            arguments={"risk_id": "RSK-GAS-087", "action": "approve", "remark": "Signed off after audit"},
            context=functional_head_context,
            bypass_confirmation=True
        )
        assert result["success"] is True

        # Check Audit Trail Record
        assert len(in_memory_db.history) == 1
        hist = in_memory_db.history[0]
        assert hist["risk_id"] == "RSK-GAS-087"
        assert hist["approver_id"] == 201
        assert hist["action"] == "approve"
        assert hist["remark"] == "Signed off after audit"

        # Check Email Notification Job Queue
        assert len(in_memory_db.email_jobs) == 1
        job = in_memory_db.email_jobs[0]
        assert job["risk_id"] == "RSK-GAS-087"
        assert job["action"] == "approve"
        assert job["recipient_role"] == "Stage 3 RM"
