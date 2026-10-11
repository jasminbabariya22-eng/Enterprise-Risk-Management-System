"""
Unit & Integration Tests for Modernized ERM Risk Management Pages:
- riskRegister.html (/risk_register/<function_code>)
- riskDetails.html (/riskDetails, /riskDetailsAdd)
- riskTreatment.html (/riskTreatment)
- riskActionPlan.html (/riskActionPlan)

Verifies:
- Template rendering and response status codes (HTTP 200, redirects when unauthenticated).
- Preservation of all required element IDs, form bindings, and tables.
- Consistent enterprise design tokens and KPI summary components.
- Role-based authorization behavior.
"""
import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parents[2]
WEB_APP_DIR = ROOT_DIR / "ERM_WEB_APP"

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(scope="session")
def flask_app():
    """Create test instance of Flask ERM_WEB_APP in isolated module context."""
    stashed_modules = {k: v for k, v in sys.modules.items() if k == "app" or k.startswith("app.")}
    for k in list(stashed_modules.keys()):
        del sys.modules[k]

    original_sys_path = list(sys.path)
    sys.path.insert(0, str(WEB_APP_DIR))
    try:
        from app import create_app
        test_app = create_app()
        test_app.config["TESTING"] = True
        test_app.config["SECRET_KEY"] = "test-secret-key-12345"
        test_app.config["ONELOGIN_AUTH"] = False
        return test_app
    finally:
        for k in list(sys.modules.keys()):
            if k == "app" or k.startswith("app."):
                del sys.modules[k]
        sys.modules.update(stashed_modules)
        sys.path[:] = original_sys_path


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture
def auth_session(client):
    """Sets up an authenticated session with standard Risk Manager role."""
    with client.session_transaction() as sess:
        sess["token"] = "mock-jwt-token-xyz"
        sess["user"] = "test_user"
        sess["usertype"] = "Risk Manager"
        sess["user_id"] = 101
        sess["user_deptid"] = 1
        sess["login_data"] = {
            "userId": 101,
            "userType": "Risk Manager",
            "fname": "Test",
            "lname": "Manager",
            "dept_id": 1,
            "current_date": "2026-10-11"
        }
    return client


# =========================================================================
# 1. RISK REGISTER PAGE TESTS (riskRegister.html)
# =========================================================================

def test_risk_register_renders_successfully(auth_session):
    """Verify /risk_register/all renders modern risk register workspace."""
    response = auth_session.get("/risk_register/all")
    assert response.status_code == 200
    html = response.data.decode("utf-8")

    # Header and Titles
    assert "Risk Register" in html
    assert "Enterprise risk portfolio overview" in html

    # KPI Summary Cards
    assert "kpiTotalRisks" in html
    assert "kpiHighRisks" in html
    assert "kpiPendingRisks" in html
    assert "kpiApprovedRisks" in html

    # Table and Drawer components
    assert 'id="HrTable"' in html
    assert 'id="riskDrawerPanel"' in html
    assert 'id="customSearchInput"' in html
    assert 'id="statusFilterBtn"' in html

    # Critical JS bindings preserved
    assert "GetAllRiskRegister" in html
    assert "getRiskRegisterbyid" in html
    assert "downloadExcel" in html


# =========================================================================
# 2. RISK DETAILS PAGE TESTS (riskDetails.html)
# =========================================================================

def test_risk_details_renders_successfully(auth_session):
    """Verify /riskDetails renders risk assessment form with all required IDs."""
    response = auth_session.get("/riskDetails")
    assert response.status_code == 200
    html = response.data.decode("utf-8")

    # Risk Details Form IDs
    assert 'id="Risk_Id"' in html
    assert 'id="Department"' in html
    assert 'id="Risk_Owner"' in html
    assert 'id="CoRisk_Owner"' in html
    assert 'id="Financial_Year"' in html
    assert 'id="Approval_Status"' in html
    assert 'id="Risk_Name"' in html

    # Sub-tables
    assert 'id="DescTable"' in html
    assert 'id="TreatmentTable"' in html
    assert 'id="dtApprovalStatus"' in html

    # Action buttons and remark
    assert 'id="Remark"' in html
    assert 'id="btn_Approve"' in html
    assert 'id="btn_Reject"' in html
    assert 'id="btn_save_draft"' in html
    assert 'id="btn_save"' in html

    # Evaluation Modal & Matrix
    assert 'id="staticBackdrop"' in html
    assert 'id="Risk_Desc"' in html
    assert 'id="InherentLikelihoodBtn"' in html
    assert 'id="InherentImpactBtn"' in html
    assert 'id="interactive5x5Grid"' in html


def test_risk_details_unauthenticated_redirect(client):
    """Verify /riskDetails redirects to login if token is missing."""
    response = client.get("/riskDetails")
    assert response.status_code == 302


# =========================================================================
# 3. RISK TREATMENT PAGE TESTS (riskTreatment.html)
# =========================================================================

def test_risk_treatment_renders_successfully(auth_session):
    """Verify /riskTreatment renders modern treatment interface with all bindings."""
    response = auth_session.get("/riskTreatment")
    assert response.status_code == 200
    html = response.data.decode("utf-8")

    # Title & Subtitle
    assert "Risk Treatment &amp; Mitigation" in html or "Risk Treatment & Mitigation" in html
    assert "Mitigation Portfolio" in html

    # KPI summary cards
    assert "kpiTotalTreatments" in html
    assert "kpiUniqueRisks" in html
    assert "kpiHighResidual" in html
    assert "kpiActionOwners" in html

    # DataTable & Script preservation
    assert 'id="HrTable"' in html
    assert "GetAllRiskRegister" in html
    assert "getTreatmentbyid" in html
    assert "mergeRows" in html
    assert "downloadExcel" in html
    assert "dept_code" in html


def test_risk_treatment_unauthenticated_redirect(client):
    """Verify /riskTreatment redirects to login if unauthenticated."""
    response = client.get("/riskTreatment")
    assert response.status_code == 302


def test_export_excel_route_handling(flask_app, auth_session):
    """Verify /exportExcel handles requests with or without dept_code safely."""
    api_client_cls = flask_app.view_functions["auth.exportExcel"].__globals__["APIClient"]
    with patch.object(api_client_cls, "getdata") as mock_getdata:
        mock_resp = MagicMock()
        mock_resp.content = b"fake-excel-content"
        mock_getdata.return_value = mock_resp

        # With department code
        resp = auth_session.get("/exportExcel?dept_code=2")
        assert resp.status_code == 200
        assert resp.headers["Content-Disposition"].startswith("attachment")
        mock_getdata.assert_called_with("risk/export-data?dept_id=2")

        # Without department code
        resp = auth_session.get("/exportExcel")
        assert resp.status_code == 200
        mock_getdata.assert_called_with("risk/export-data")


# =========================================================================
# 4. RISK ACTION PLAN PAGE TESTS (riskActionPlan.html)
# =========================================================================

def test_risk_action_plan_renders_successfully(auth_session):
    """Verify /riskActionPlan renders modern action plan workspace with all IDs."""
    response = auth_session.get("/riskActionPlan")
    assert response.status_code == 200
    html = response.data.decode("utf-8")

    # Header
    assert "Risk Action Plan &amp; Follow-up" in html or "Risk Action Plan & Follow-up" in html

    # Parent Risk Context Inputs
    assert 'id="RfId"' in html
    assert 'id="Risk_Id"' in html
    assert 'id="RiskName"' in html
    assert 'id="value"' in html
    assert 'id="financial_year"' in html
    assert 'id="Risk_Description"' in html
    assert 'id="InherentRiskLevel"' in html
    assert 'id="CurrentRiskLevel"' in html
    assert 'id="Risk_Mitigation"' in html
    assert 'id="Action_plan"' in html
    assert 'id="Risk_Status"' in html
    assert 'id="Risk_Progress"' in html

    # Approval table and Risk Manager review box
    assert 'id="ActionPlanTable--1"' in html
    assert 'id="apr_rejc"' in html
    assert 'id="ApprRemark"' in html
    assert 'id="btn_Approve"' in html
    assert 'id="btn_Reject"' in html

    # Timeline container and update form
    assert 'id="FollowupContainer"' in html
    assert 'id="divDetail"' in html
    assert 'id="Add_New_Remark"' in html
    assert 'id="Progress"' in html
    assert 'id="Status_followup"' in html
    assert 'id="Target_Date_Next"' in html
    assert 'id="fileUpload"' in html
    assert 'id="btnsubmit"' in html

    # Workflow JS functions
    assert "riskfollowup" in html
    assert "AddNewRiskDes" in html
    assert "intitiateApproval" in html
    assert "downloadReffile" in html
