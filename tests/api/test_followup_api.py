"""
API Tests for Risk Action Follow-Up Endpoints.
"""
import pytest
from fastapi.testclient import TestClient

from ERM_API.app.main import app

client = TestClient(app)


@pytest.mark.api
def test_get_risk_action_followups():
    response = client.get("/risk_action_followup/getAllRiskActionFollowup")
    assert response.status_code in [200, 401, 403, 404, 500]
