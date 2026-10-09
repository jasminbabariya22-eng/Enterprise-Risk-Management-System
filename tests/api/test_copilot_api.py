"""
API Tests for ERM Copilot Chat Endpoint (/api/erm/chat).
"""
import pytest
from unittest.mock import patch, MagicMock
from ERM_Copilot.ai_harness.harness import ERMAIHarness
from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.models.contracts import AgentResponse


@pytest.mark.api
def test_copilot_chat_harness_integration(ro_context):
    mock_response = AgentResponse(
        request_id=ro_context.request_id,
        agent_id="erm_copilot_agent",
        status="success",
        response="Here is the risk assessment for Gas Processing Facilities.",
        metadata={"count": 5}
    )

    with patch("ERM_Copilot.erm_copilot_agent.process", return_value=mock_response):
        resp = ERMAIHarness.run(
            context=ro_context,
            message="Show high severity risks"
        )
        assert resp.success is True
        assert resp.request_id == ro_context.request_id
        assert "Gas Processing Facilities" in resp.response
        assert resp.metadata.get("harness_governed") is True


@pytest.mark.api
def test_copilot_chat_missing_auth_rejected():
    with pytest.raises(Exception):
        ERMAIHarness.run(context=None, message="Show risks")
