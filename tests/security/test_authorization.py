"""
Security Tests: Authorization Enforcement and Least Privilege.
"""
import pytest
from ERM_Copilot.ai_harness.execution import ExecutionCoordinator
from ERM_Copilot.ai_harness.exceptions import AuthorizationError


@pytest.mark.security
def test_risk_owner_cannot_invoke_approval_tool(ro_context):
    with pytest.raises(AuthorizationError):
        ExecutionCoordinator.execute_tool(
            "approve_or_reject_risk",
            {"risk_id": "RSK-GAS-087", "action": "approve", "remark": "approved"},
            ro_context
        )


@pytest.mark.security
def test_auditor_cannot_mutate_risk_data(aud_context):
    with pytest.raises(AuthorizationError):
        ExecutionCoordinator.execute_tool(
            "save_risk",
            {"risk_name": "Auditor Risk", "dept_id": 1},
            aud_context
        )
