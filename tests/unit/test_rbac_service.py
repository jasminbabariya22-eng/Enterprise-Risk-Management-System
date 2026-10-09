"""
Unit Tests for RBAC Decision Service, Tool Execution Policies, and Stage Sequences.
"""
import pytest
from ERM_Copilot.ai_harness.policies import (
    is_role_authorized_for_tool,
    enforce_tool_rbac,
    APPROVER_ROLES,
    CREATOR_ROLES
)
from ERM_Copilot.ai_harness.exceptions import AuthorizationError


@pytest.mark.unit
def test_approver_rbac_decisions():
    # Only approver roles can approve
    assert is_role_authorized_for_tool("Functional Head", APPROVER_ROLES) is True
    assert is_role_authorized_for_tool("Risk Manager", APPROVER_ROLES) is True
    assert is_role_authorized_for_tool("Risk Head", APPROVER_ROLES) is True
    assert is_role_authorized_for_tool("Super Admin", APPROVER_ROLES) is True

    # Non-approvers must be rejected
    assert is_role_authorized_for_tool("Risk Owner", APPROVER_ROLES) is False
    assert is_role_authorized_for_tool("Auditor", APPROVER_ROLES) is False


@pytest.mark.unit
def test_creator_rbac_decisions():
    # Creators can save risks and treatments
    assert is_role_authorized_for_tool("Risk Owner", CREATOR_ROLES) is True
    assert is_role_authorized_for_tool("Functional Head", CREATOR_ROLES) is True

    # Auditor cannot save or modify
    assert is_role_authorized_for_tool("Auditor", CREATOR_ROLES) is False


@pytest.mark.unit
def test_enforce_rbac_raises_authorization_error():
    with pytest.raises(AuthorizationError):
        enforce_tool_rbac("approve_or_reject_risk", "Auditor", APPROVER_ROLES)
