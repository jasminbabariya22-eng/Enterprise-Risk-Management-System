"""
Unit & Integration Tests for ERM Help, 401 Unauthorized, and 403 Forbidden pages.
Verifies:
- Template rendering and response status codes (HTTP 200, 401, 403).
- Content integrity (5x5 Matrix tables, Impact/Likelihood criteria, search input, FAQs).
- Error handlers behavior for browser vs JSON API requests.
- RBAC role enforcement and access denial without secret leakage.
"""
import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parents[2]
WEB_APP_DIR = ROOT_DIR / "ERM_WEB_APP"

import pytest
from unittest.mock import patch, MagicMock
from flask import session


@pytest.fixture(scope="session")
def flask_app():
    """Create test instance of Flask ERM_WEB_APP in isolated module context."""
    # Temporarily stash any ERM_API app modules
    stashed_modules = {k: v for k, v in sys.modules.items() if k == "app" or k.startswith("app.")}
    for k in list(stashed_modules.keys()):
        del sys.modules[k]

    original_sys_path = list(sys.path)
    sys.path.insert(0, str(WEB_APP_DIR))
    try:
        import app
        from app import create_app
        test_app = create_app()
        test_app.config["TESTING"] = True
        test_app.config["SECRET_KEY"] = "test-secret-key-12345"
        test_app.config["ONELOGIN_AUTH"] = False
        return test_app
    finally:
        # Clean up web app's app modules from sys.modules
        for k in list(sys.modules.keys()):
            if k == "app" or k.startswith("app."):
                del sys.modules[k]
        # Restore any stashed ERM_API modules
        sys.modules.update(stashed_modules)
        sys.path[:] = original_sys_path


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


# =========================================================================
# 1. HELP CENTER TESTS
# =========================================================================

def test_help_page_renders_successfully(client):
    """Verify /help loads with HTTP 200 and contains core components."""
    response = client.get("/help")
    assert response.status_code == 200
    html = response.data.decode("utf-8")

    # Verify Header and Title
    assert "ERM Knowledge & Help Center" in html or "ERM Knowledge" in html
    assert "helpSearchInput" in html

    # Verify Preserved and Modernized 5x5 Matrix content
    assert "5&times;5 Enterprise Risk Matrix" in html or "5x5 Enterprise Risk Matrix" in html
    assert "Cash Flow at Risk" in html
    assert "Health &amp; Safety" in html or "Health & Safety" in html
    assert "Operational Interruption" in html
    assert "Compliance &amp; Legal" in html or "Compliance & Legal" in html

    # Verify Likelihood criteria
    assert "Likelihood (L) Descriptors" in html
    assert "Expected" in html
    assert "Probable" in html
    assert "Possible" in html
    assert "Unlikely" in html
    assert "Remote" in html

    # Verify Workflow and Governance guides
    assert "3-Stage Governance Approval Workflow" in html
    assert "Functional Head Review" in html
    assert "Risk Manager Verification" in html
    assert "Risk Head Final Approval" in html

    # Verify FAQs
    assert "Frequently Asked Questions" in html
    assert "helpAccordion" in html


def test_help_page_authenticated_layout(client):
    """Verify /help preserves authenticated session data when logged in."""
    with client.session_transaction() as sess:
        sess["token"] = "mock-jwt-token"
        sess["user"] = "Tester"
        sess["usertype"] = "Risk Owner"
        sess["login_data"] = {
            "userId": 10,
            "userType": "Risk Owner",
            "fname": "Test",
            "lname": "User"
        }

    response = client.get("/help")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "helpSearchInput" in html


# =========================================================================
# 2. 401 UNAUTHORIZED TESTS
# =========================================================================

def test_401_unauthorized_page_status_and_content(client):
    """Verify /401 returns HTTP 401 with clear sign-in recovery links."""
    response = client.get("/401")
    assert response.status_code == 401
    html = response.data.decode("utf-8")

    assert "HTTP 401" in html
    assert "Authentication Required" in html
    assert "/login" in html
    assert "/help" in html
    # Ensure no credentials or tokens are leaked
    assert "Bearer" not in html
    assert "token" not in html.lower() or "session" in html.lower()


def test_401_api_request_returns_json(client):
    """Verify that an API request receiving 401 returns JSON rather than HTML."""
    response = client.get("/api/home/workload")
    assert response.status_code == 401
    assert response.is_json
    data = response.get_json()
    assert data.get("success") is False or data.get("status") == "error" or "Unauthorized" in data.get("message", "")


# =========================================================================
# 3. 403 FORBIDDEN TESTS
# =========================================================================

def test_403_forbidden_page_status_and_content(client):
    """Verify /403 returns HTTP 403 with access denial information."""
    response = client.get("/403")
    assert response.status_code == 403
    html = response.data.decode("utf-8")

    assert "HTTP 403" in html
    assert "Access Denied" in html
    assert "/home" in html
    assert "/help" in html


def test_403_displays_current_role_when_authenticated(client):
    """Verify 403 displays the authenticated user role to explain permission denial."""
    with client.session_transaction() as sess:
        sess["token"] = "mock-token"
        sess["usertype"] = "Action Owner"
        sess["login_data"] = {
            "userType": "Action Owner",
            "userId": 5
        }

    response = client.get("/403")
    assert response.status_code == 403
    html = response.data.decode("utf-8")
    assert "Action Owner" in html
    assert "Return to Home" in html


def test_dashboard_rbac_enforcement_triggers_403(client):
    """Verify that an unauthorized role (Action Owner) attempting /dashboard triggers 403."""
    with client.session_transaction() as sess:
        sess["token"] = "mock-token"
        sess["usertype"] = "Action Owner"
        sess["login_data"] = {
            "userType": "Action Owner",
            "userId": 5
        }

    response = client.get("/dashboard")
    assert response.status_code == 403
    html = response.data.decode("utf-8")
    assert "Access Denied" in html
    assert "HTTP 403" in html


def test_403_api_request_returns_json(client):
    """Verify that a JSON API request receiving 403 returns JSON rather than HTML."""
    with client.session_transaction() as sess:
        sess["token"] = "mock-token"
        sess["usertype"] = "Action Owner"
        sess["login_data"] = {"userType": "Action Owner"}

    # Request a role-restricted dashboard API endpoint as Action Owner
    response = client.get("/api/dashboard/summary", headers={"Accept": "application/json"})
    assert response.status_code == 403
    assert response.is_json
    data = response.get_json()
    assert data.get("status") == "error"
    assert "Forbidden" in data.get("message", "")
