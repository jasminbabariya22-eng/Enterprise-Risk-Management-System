"""
Agent Tests: Guardrail Processing and Sanitization.
"""
import pytest
from ERM_Copilot.guardrails.manager import GuardrailManager
from ERM_Copilot.models.contracts import AgentRequest


@pytest.mark.agent
def test_guardrail_input_processing_clean_text():
    req = AgentRequest(message="What are the risks in Gas Processing?")
    res = GuardrailManager.process_input(req)
    assert res.blocked is False
    assert res.sanitized_text is not None


@pytest.mark.agent
def test_guardrail_output_sanitization():
    out = GuardrailManager.process_output("Standard response without secrets.")
    assert out == "Standard response without secrets."
