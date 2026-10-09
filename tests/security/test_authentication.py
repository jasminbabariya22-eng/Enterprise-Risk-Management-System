"""
Security Tests: Authentication, Token Integrity, and Header Validation.
"""
import pytest
from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.ai_harness.exceptions import AuthenticationError


@pytest.mark.security
def test_missing_or_empty_auth_fails():
    with pytest.raises(AuthenticationError):
        HarnessContext.build_from_auth(user_id="", user_role="Risk Owner")

    with pytest.raises(AuthenticationError):
        HarnessContext.build_from_auth(user_id=None, user_role="Risk Owner")

    with pytest.raises(AuthenticationError):
        HarnessContext.build_from_auth(user_id="101", user_role="")


@pytest.mark.security
def test_null_string_auth_rejected():
    with pytest.raises(AuthenticationError):
        HarnessContext.build_from_auth(user_id="null", user_role="Risk Owner")
