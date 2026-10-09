"""
Unit Tests for User Entity Resolution, Department Mapping, and Roles.
"""
import pytest
from tests.fixtures.users import TEST_USERS
from ERM_Copilot.ai_harness.policies import normalize_role


@pytest.mark.unit
def test_all_7_erm_roles_defined():
    expected_roles = {
        "Risk Owner", "Functional Head", "Risk Manager", "Risk Head",
        "Auditor", "Executive / CEO", "Super Admin"
    }
    actual_roles = {u["role_name"] for u in TEST_USERS.values()}
    assert expected_roles.issubset(actual_roles)


@pytest.mark.unit
def test_user_role_normalization():
    assert normalize_role("Risk Owner") == "Risk Owner"
    assert normalize_role("HOD") == "Functional Head"
    assert normalize_role("FH") == "Functional Head"
    assert normalize_role("Risk Manager") == "Risk Manager"
    assert normalize_role("RM") == "Risk Manager"
    assert normalize_role("Risk Head") == "Risk Header"
    assert normalize_role("Super Admin") == "Super Admin"
    assert normalize_role("Auditor") == "Auditor"
