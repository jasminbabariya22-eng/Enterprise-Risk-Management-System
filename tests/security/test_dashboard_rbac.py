"""
Security Tests: Dashboard RBAC Verification.
Verifies that Dashboard access is strictly restricted to:
- Admin (and Super Admin)
- Risk Manager
- Risk Head
And denied for all other roles (Risk Owner, Functional Head, Auditor, Viewer, etc.).
"""
import pytest
from fastapi import HTTPException

from ERM_API.app.core.dependencies import require_dashboard_access, DASHBOARD_AUTHORIZED_ROLES


@pytest.mark.security
def test_dashboard_authorized_roles_list():
    assert "Admin" in DASHBOARD_AUTHORIZED_ROLES
    assert "Super Admin" in DASHBOARD_AUTHORIZED_ROLES
    assert "Risk Manager" in DASHBOARD_AUTHORIZED_ROLES
    assert "Risk Head" in DASHBOARD_AUTHORIZED_ROLES
    assert "Risk Owner" not in DASHBOARD_AUTHORIZED_ROLES
    assert "Functional Head" not in DASHBOARD_AUTHORIZED_ROLES


@pytest.mark.security
@pytest.mark.parametrize("role", ["Admin", "Super Admin", "Risk Manager", "Risk Head", "admin", "risk manager", "risk head"])
def test_require_dashboard_access_allowed_roles(role):
    current_user = {
        "id": 1,
        "role_name": role,
        "user_type_name": role
    }
    result = require_dashboard_access(current_user=current_user)
    assert result == current_user


@pytest.mark.security
@pytest.mark.parametrize("role", ["Risk Owner", "Functional Head", "Function Head", "Auditor", "Viewer", "Action Owner", ""])
def test_require_dashboard_access_forbidden_roles(role):
    current_user = {
        "id": 5,
        "role_name": role,
        "user_type_name": role
    }
    with pytest.raises(HTTPException) as exc_info:
        require_dashboard_access(current_user=current_user)
    assert exc_info.value.status_code == 403
    assert "Forbidden" in exc_info.value.detail
