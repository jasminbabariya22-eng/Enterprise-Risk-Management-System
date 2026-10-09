"""
Integration Tests: Complete Flow from Request -> AI Harness -> Orchestrator -> Tool -> Database.
"""
import pytest
from unittest.mock import patch
from ERM_Copilot.ai_harness.harness import ERMAIHarness
from ERM_Copilot.models.contracts import AgentRequest


@pytest.mark.integration
def test_full_copilot_risk_query_flow(ro_context, in_memory_db):
    resp = ERMAIHarness.run(
        context=ro_context,
        message="Show high severity open risks"
    )
    assert resp.success is True
    assert resp.request_id == ro_context.request_id
    assert resp.metadata.get("harness_governed") is True
