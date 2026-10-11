"""
Security Tests: Home Page RBAC & Scope Boundaries.
Verifies that:
- Home page workload is strictly scoped to authorized department / ownership boundaries.
- Unknown roles fallback safely to restricted viewer context.
- Dashboard remains protected from non-privileged roles.
"""
import pytest
from unittest.mock import MagicMock

from ERM_API.app.services.home_service import get_home_workload_and_summary
from ERM_API.app.core.dependencies import DASHBOARD_AUTHORIZED_ROLES


@pytest.mark.security
def test_dashboard_rbac_boundary_unchanged():
    """Verify that Dashboard remains strictly restricted to privileged governance roles."""
    assert "Admin" in DASHBOARD_AUTHORIZED_ROLES
    assert "Risk Manager" in DASHBOARD_AUTHORIZED_ROLES
    assert "Risk Head" in DASHBOARD_AUTHORIZED_ROLES
    assert "Functional Head" not in DASHBOARD_AUTHORIZED_ROLES
    assert "Risk Owner" not in DASHBOARD_AUTHORIZED_ROLES
    assert "Action Owner" not in DASHBOARD_AUTHORIZED_ROLES
    assert "Viewer" not in DASHBOARD_AUTHORIZED_ROLES


@pytest.mark.security
def test_functional_head_department_scoping():
    """Verify that Functional Head workload is strictly scoped to their department."""
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = 3
    db.query.return_value.options.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    user = {
        "id": 4,
        "role_name": "Functional Head",
        "department_id": 2
    }

    res = get_home_workload_and_summary(db, user)
    assert res["role_category"] == "functional_head"
    assert res["department_id"] == 2
    assert "Dept Stage 1 Approvals" in res["summary"]["card_1"]["label"]


@pytest.mark.security
def test_unknown_role_safe_fallback():
    """Verify that unknown or unassigned roles are handled safely without administrative privilege grant."""
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = 0
    db.query.return_value.options.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    user = {
        "id": 99,
        "role_name": "UnknownRoleXYZ",
        "department_id": 1
    }

    res = get_home_workload_and_summary(db, user)
    assert res["role_category"] == "viewer"
    assert "Risk Register Items" in res["summary"]["card_1"]["label"]
