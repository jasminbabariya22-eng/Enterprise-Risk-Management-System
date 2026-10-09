"""
Security Tests: Input Sanitization and Exploit Pattern Defense.
"""
import pytest
from ERM_Copilot.ai_harness.guardrails import HarnessGuardrails
from ERM_Copilot.ai_harness.exceptions import GuardrailViolationError


@pytest.mark.security
def test_sql_injection_patterns_blocked():
    attacks = [
        "DROP TABLE tbl_risk_register;",
        "SELECT * FROM passwords WHERE '1'='1'",
        "UPDATE tbl_user SET role_id=1;"
    ]
    for attack in attacks:
        with pytest.raises(GuardrailViolationError):
            HarnessGuardrails.validate_input(attack, user_role="Risk Owner")


@pytest.mark.security
def test_clean_input_passes_validation():
    clean_msg = "Please list all open high severity risks."
    assert HarnessGuardrails.validate_input(clean_msg, user_role="Risk Owner") == clean_msg
