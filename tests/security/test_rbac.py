"""
Security Tests: RBAC Barriers and Cross-Department Isolation.
"""
import pytest
from ERM_Copilot.ai_harness.policies import is_role_authorized_for_tool, APPROVER_ROLES, CREATOR_ROLES
from ERM_Copilot.ai_harness.guardrails import HarnessGuardrails


@pytest.mark.security
def test_cross_role_tool_isolation():
    # Only approver roles authorized for approval tool
    assert is_role_authorized_for_tool("Functional Head", APPROVER_ROLES) is True
    assert is_role_authorized_for_tool("Risk Manager", APPROVER_ROLES) is True
    assert is_role_authorized_for_tool("Risk Head", APPROVER_ROLES) is True
    assert is_role_authorized_for_tool("Risk Owner", APPROVER_ROLES) is False
    assert is_role_authorized_for_tool("Auditor", APPROVER_ROLES) is False


@pytest.mark.security
def test_cross_department_cache_isolation():
    key_gas = HarnessGuardrails.generate_isolated_cache_key("101", 2, "Risk Owner", "Show open risks")
    key_refining = HarnessGuardrails.generate_isolated_cache_key("101", 3, "Risk Owner", "Show open risks")
    assert key_gas != key_refining
