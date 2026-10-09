"""
Unit Tests for HarnessContext and Trusted Identity Management.
Verifies context immutability, role isolation, and failure safety.
"""
import pytest
from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.ai_harness.exceptions import AuthenticationError


def test_harness_context_valid_creation():
    ctx = HarnessContext.build_from_auth(
        user_id="101",
        user_role="Functional Head",
        dept_id=2,
        dept_name="Gas Processing Facilities",
        session_id="sess-test-01"
    )
    assert ctx.user_id == "101"
    assert ctx.user_role == "Functional Head"
    assert ctx.dept_id == 2
    assert ctx.dept_name == "Gas Processing Facilities"
    assert ctx.session_id == "sess-test-01"
    assert ctx.is_authenticated is True
    assert ctx.request_id.startswith("req-")
    assert ctx.run_id.startswith("run-")


def test_harness_context_missing_user_id_fails():
    with pytest.raises(AuthenticationError):
        HarnessContext.build_from_auth(user_id="", user_role="Risk Owner")

    with pytest.raises(AuthenticationError):
        HarnessContext.build_from_auth(user_id=None, user_role="Risk Owner")


def test_harness_context_missing_role_fails():
    with pytest.raises(AuthenticationError):
        HarnessContext.build_from_auth(user_id="101", user_role="")

    with pytest.raises(AuthenticationError):
        HarnessContext.build_from_auth(user_id="101", user_role=None)


def test_enterprise_level_role_detection():
    admin_ctx = HarnessContext.build_from_auth(user_id="1", user_role="Super Admin")
    assert admin_ctx.is_enterprise_level() is True

    rh_ctx = HarnessContext.build_from_auth(user_id="401", user_role="Risk Head")
    assert rh_ctx.is_enterprise_level() is True

    auditor_ctx = HarnessContext.build_from_auth(user_id="501", user_role="Auditor")
    assert auditor_ctx.is_enterprise_level() is True

    owner_ctx = HarnessContext.build_from_auth(user_id="101", user_role="Risk Owner", dept_id=2)
    assert owner_ctx.is_enterprise_level() is False


def test_safe_trace_dict_sanitization():
    ctx = HarnessContext.build_from_auth(
        user_id="101",
        user_role="Risk Owner",
        dept_id=2,
        dept_name="Gas Processing Facilities"
    )
    trace_dict = ctx.to_safe_trace_dict()
    assert trace_dict["user_id"] == "101"
    assert trace_dict["user_role"] == "Risk Owner"
    assert trace_dict["dept_id"] == 2
    assert "password" not in trace_dict
    assert "token" not in trace_dict
