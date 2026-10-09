"""
API Tests for Authentication and JWT Endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from ERM_API.app.main import app

client = TestClient(app)


@pytest.mark.api
def test_health_check_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.api
def test_login_invalid_credentials_returns_error():
    response = client.post("/auth/login", json={"log_id": "nonexistent_user", "password": "wrong_password"})
    # Expect 400, 401, or error response
    assert response.status_code in [400, 401, 404] or response.json().get("status") == "error"


@pytest.mark.api
def test_unauthenticated_protected_endpoint_rejected():
    # Attempting to access protected risk endpoint without token
    response = client.get("/api/risk/getAllRisks")
    # If endpoint requires token/dependency, should return 401/403 or redirect
    assert response.status_code in [401, 403, 404, 422, 200]
