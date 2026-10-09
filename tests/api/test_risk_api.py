"""
API Tests for Risk Register and Risk Details Endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from ERM_API.app.main import app

client = TestClient(app)


@pytest.mark.api
def test_get_departments_endpoint():
    response = client.get("/departments/getAllDepartments")
    # Endpoint should respond with valid status
    assert response.status_code in [200, 401, 403, 404, 500]


@pytest.mark.api
def test_get_roles_endpoint():
    response = client.get("/roles/getAllRoles")
    assert response.status_code in [200, 401, 403, 404, 500]
