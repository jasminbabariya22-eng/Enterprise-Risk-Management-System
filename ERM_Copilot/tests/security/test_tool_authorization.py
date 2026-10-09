"""
Security Tests: Tool Authorization, RBAC Boundaries, and Data Isolation.
Verifies role boundaries, department barriers, and injection resistance.
"""
import pytest
from ERM_Copilot.ai_harness.execution import ExecutionCoordinator
from ERM_Copilot.ai_harness.exceptions import AuthorizationError, ToolNotFoundError, GuardrailViolationError
from ERM_Copilot.ai_harness.guardrails import HarnessGuardrails


def test_auditor_blocked_from_mutating_state(auditor_context):
    # Cannot save risk
    with pytest.raises(AuthorizationError):
        ExecutionCoordinator.execute_tool("save_risk", {"risk_name": "Test", "dept_id": 1}, auditor_context)

    # Cannot update treatment
    with pytest.raises(AuthorizationError):
        ExecutionCoordinator.execute_tool("update_treatment_progress", {"treatment_id": 1, "progress": 100}, auditor_context)

    # Cannot approve risk
    with pytest.raises(AuthorizationError):
        ExecutionCoordinator.execute_tool("approve_or_reject_risk", {"risk_id": "RSK-001", "action": "approve", "remark": "OK"}, auditor_context)


def test_sql_injection_payload_in_query_blocked():
    with pytest.raises(GuardrailViolationError):
        HarnessGuardrails.validate_input("DROP TABLE tbl_risk_register; SELECT * FROM users;", user_role="Risk Owner")


def test_arbitrary_python_tool_blocked(admin_context):
    with pytest.raises(ToolNotFoundError):
        ExecutionCoordinator.execute_tool("execute_arbitrary_python", {"code": "import os; os.system('ls')"}, admin_context)
