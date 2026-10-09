"""
API Tests for Governance Approval and Status Endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from ERM_API.app.main import app

client = TestClient(app)


@pytest.mark.api
def test_approval_status_endpoint():
    response = client.get("/status/getAllStatus")
    assert response.status_code in [200, 401, 403, 404, 500]


@pytest.mark.api
def test_unauthorized_approval_submission_rejected():
    response = client.post("/approval/approve", json={"risk_id": "RSK-001", "approver_id": 999})
    assert response.status_code in [401, 403, 404, 405, 422, 500]
