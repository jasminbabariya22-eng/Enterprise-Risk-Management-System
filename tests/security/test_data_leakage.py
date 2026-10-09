"""
Security Tests: Prevention of Data Leakage, Secret Masking, and Credential Protection.
"""
import pytest
from ERM_Copilot.ai_harness.observability import sanitize_trace_payload
from ERM_Copilot.ai_harness.guardrails import HarnessGuardrails


@pytest.mark.security
def test_trace_payload_redacts_credentials():
    payload = {
        "user_id": "101",
        "password": "ProductionPassword123!",
        "api_key": "pk_live_secret_value",
        "auth_token": "Bearer eyJhbGciOiJIUzI1NiJ9.token",
        "db_connection": "postgresql://postgres:secret@localhost/ers"
    }
    sanitized = sanitize_trace_payload(payload)
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["auth_token"] == "[REDACTED]"


@pytest.mark.security
def test_output_guardrail_masks_bearer_tokens():
    raw_response = "Here is the result: Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token_payload"
    sanitized = HarnessGuardrails.sanitize_output(raw_response)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized
