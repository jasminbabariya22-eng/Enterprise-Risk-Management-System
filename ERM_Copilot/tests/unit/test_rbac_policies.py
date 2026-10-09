"""
Unit Tests for RBAC Policies and Governance Tier Mapping.
Verifies authorization checks across all 7 ERM roles.
"""
import pytest
from ERM_Copilot.ai_harness.policies import (
    normalize_role,
    is_role_authorized_for_tool,
    enforce_tool_rbac,
    ROLE_RISK_OWNER,
    ROLE_FUNCTIONAL_HEAD,
    ROLE_RISK_MANAGER,
    ROLE_RISK_HEADER,
    ROLE_AUDITOR,
    ROLE_SUPER_ADMIN,
    APPROVER_ROLES,
    CREATOR_ROLES,
)
from ERM_Copilot.ai_harness.exceptions import AuthorizationError


def test_normalize_role():
    assert normalize_role("Functional Head") == ROLE_FUNCTIONAL_HEAD
    assert normalize_role("FH") == ROLE_FUNCTIONAL_HEAD
    assert normalize_role("HOD") == ROLE_FUNCTIONAL_HEAD
    assert normalize_role("Risk Manager") == ROLE_RISK_MANAGER
    assert normalize_role("RM") == ROLE_RISK_MANAGER
    assert normalize_role("Risk Head") == ROLE_RISK_HEADER
    assert normalize_role("Auditor") == ROLE_AUDITOR
    assert normalize_role("Risk Owner") == ROLE_RISK_OWNER
    assert normalize_role("Super Admin") == ROLE_SUPER_ADMIN


def test_is_role_authorized_for_tool():
    # Approver roles can execute approve_or_reject_risk
    assert is_role_authorized_for_tool("Functional Head", APPROVER_ROLES) is True
    assert is_role_authorized_for_tool("Risk Manager", APPROVER_ROLES) is True
    assert is_role_authorized_for_tool("Risk Head", APPROVER_ROLES) is True
    assert is_role_authorized_for_tool("Super Admin", APPROVER_ROLES) is True

    # Risk Owner and Auditor CANNOT approve
    assert is_role_authorized_for_tool("Risk Owner", APPROVER_ROLES) is False
    assert is_role_authorized_for_tool("Auditor", APPROVER_ROLES) is False


def test_enforce_tool_rbac_raises_authorization_error():
    # Auditor attempting to save risk
    with pytest.raises(AuthorizationError) as exc_info:
        enforce_tool_rbac("save_risk", "Auditor", CREATOR_ROLES)
    assert "not authorized" in str(exc_info.value).lower()

    # Risk Owner attempting to approve risk
    with pytest.raises(AuthorizationError) as exc_info:
        enforce_tool_rbac("approve_or_reject_risk", "Risk Owner", APPROVER_ROLES)
    assert "not authorized" in str(exc_info.value).lower()
