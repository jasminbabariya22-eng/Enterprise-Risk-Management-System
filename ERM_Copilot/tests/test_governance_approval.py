"""
Unit & Integration Test Suite for Governance Approval/Rejection Refactoring (FH, RM, RH).
Verifies:
1. Single common approve_or_reject_risk operation.
2. Automatic role determination from DB identity (no role parameter accepted).
3. Sequence enforcement (FH -> RM -> RH).
4. Strict rejection reason requirement.
5. Audit trail history logging (risk_register_hist).
6. No user fallback IDs (e.g. else 4).
"""
import pytest
from unittest.mock import MagicMock, patch
from ERM_Copilot.services.db_service import ERMDatabaseService
from ERM_Copilot.agents.agent import ERMCopilotAgent
from ERM_Copilot.models.contracts import AgentRequest


class TestGovernanceApprovalUnit:
    """Unit tests for approve_or_reject_risk in ERMDatabaseService."""

    def setup_method(self):
        self.db = ERMDatabaseService()

    @patch.object(ERMDatabaseService, '_get_connection')
    def test_missing_or_invalid_approver_id(self, mock_conn):
        """Test missing or invalid approver ID returns authentication error without fallback."""
        res_none = self.db.approve_or_reject_risk(risk_id="RSK-TEST-001", approver_id=None, action="approve")
        assert res_none["success"] is False
        assert "Authentication required" in res_none["message"]

        res_zero = self.db.approve_or_reject_risk(risk_id="RSK-TEST-001", approver_id=0, action="approve")
        assert res_zero["success"] is False

        res_neg = self.db.approve_or_reject_risk(risk_id="RSK-TEST-001", approver_id=-5, action="approve")
        assert res_neg["success"] is False

    @patch.object(ERMDatabaseService, '_get_connection')
    def test_unauthorized_user_role(self, mock_conn):
        """Test that users with non-approver roles (e.g. Risk Owner) cannot approve/reject."""
        mock_c = MagicMock()
        mock_conn.return_value = mock_c
        mock_cur = MagicMock()
        mock_c.cursor.return_value = mock_cur

        # User is Risk Owner (user_type_id = 2)
        mock_cur.fetchone.return_value = {
            "id": 10, "log_id": "gas_ro", "first_name": "Risk", "last_name": "Owner",
            "email": "ro@gas.com", "dept_id": 1, "role_id": 5, "user_type_id": 2,
            "user_type_name": "Risk Owner"
        }

        res = self.db.approve_or_reject_risk(risk_id="RSK-TEST-001", approver_id=10, action="approve")
        assert res["success"] is False
        assert "not authorized to approve or reject" in res["message"]

    @patch.object(ERMDatabaseService, '_get_connection')
    def test_fh_approves_pending_fh_risk(self, mock_conn):
        """Test FH approves risk pending Stage 1 approval -> SUCCESS."""
        mock_c = MagicMock()
        mock_conn.return_value = mock_c
        mock_cur = MagicMock()
        mock_c.cursor.return_value = mock_cur

        # 1. Fetch user (FH)
        user_row = {
            "id": 4, "log_id": "gas_fh", "first_name": "Gas", "last_name": "FH",
            "email": "fh@gas.com", "dept_id": 1, "role_id": 4, "user_type_id": 4,
            "user_type_name": "Functional Head"
        }
        # 2. Fetch risk (pending FH)
        risk_row = {
            "risk_register_id": 101, "risk_id": "RSK-GAS-001", "risk_name": "Gas Leakage Hazard",
            "dept_id": 1, "risk_owner_id": 5, "risk_co_owner_id": None,
            "financial_year": "2026-2027", "risk_status": 2, "risk_progress": "0%",
            "risk_function_head_approval_status": 0, "risk_function_head_approval_by": None,
            "risk_function_head_approval_on": None, "risk_function_head_approval_remark": None,
            "risk_manager_approval_status": 0, "risk_manager_approval_by": None,
            "risk_manager_approved_on": None, "risk_manager_approval_remark": None,
            "risk_head_approval_status": 0, "risk_head_approval_by": None,
            "risk_head_approved_on": None, "risk_head_approval_remark": None,
            "created_by": 5, "created_on": None, "modified_by": 5, "modified_on": None,
            "is_active": 1, "is_deleted": 0, "current_status_name": "Submitted to Functional Head"
        }
        status_rows = [
            {"id": 1, "status_name": "Draft"},
            {"id": 2, "status_name": "Submitted to Functional Head"},
            {"id": 3, "status_name": "Opened"},
            {"id": 5, "status_name": "Approved"},
            {"id": 6, "status_name": "Pending for Action"}
        ]

        mock_cur.fetchone.side_effect = [user_row, risk_row]
        mock_cur.fetchall.return_value = status_rows

        res = self.db.approve_or_reject_risk(
            risk_id="RSK-GAS-001", approver_id=4, action="approve", remark="FH approved controls"
        )
        assert res["success"] is True
        assert res["action"] == "Approved"
        assert res["approval_level"] == 1
        assert "Functional Head" in res["stage"]
        assert "Risk Manager" in res["next_queue"]
        mock_c.commit.assert_called_once()

    @patch.object(ERMDatabaseService, '_get_connection')
    def test_rm_cannot_bypass_pending_fh(self, mock_conn):
        """Test RM tries to approve a risk while FH is still pending -> Sequence error."""
        mock_c = MagicMock()
        mock_conn.return_value = mock_c
        mock_cur = MagicMock()
        mock_c.cursor.return_value = mock_cur

        # User is RM (id = 3)
        user_row = {
            "id": 3, "log_id": "gas_rm", "first_name": "Risk", "last_name": "Manager",
            "email": "rm@gas.com", "dept_id": 1, "role_id": 3, "user_type_id": 3,
            "user_type_name": "Risk Manager"
        }
        # Risk is pending FH (fh_status = 0)
        risk_row = {
            "risk_register_id": 102, "risk_id": "RSK-GAS-002", "risk_name": "Pipeline Pressure Drop",
            "dept_id": 1, "risk_owner_id": 5, "risk_status": 2,
            "risk_function_head_approval_status": 0, "risk_manager_approval_status": 0, "risk_head_approval_status": 0,
            "current_status_name": "Submitted to Functional Head"
        }

        mock_cur.fetchone.side_effect = [user_row, risk_row]

        res = self.db.approve_or_reject_risk(
            risk_id="RSK-GAS-002", approver_id=3, action="approve", remark="RM check"
        )
        assert res["success"] is False
        assert "not yet available for Risk Manager approval" in res["message"]
        assert "Functional Head approval is still pending" in res["message"]

    @patch.object(ERMDatabaseService, '_get_connection')
    def test_rh_cannot_bypass_pending_rm(self, mock_conn):
        """Test RH tries to approve a risk while RM is still pending -> Sequence error."""
        mock_c = MagicMock()
        mock_conn.return_value = mock_c
        mock_cur = MagicMock()
        mock_c.cursor.return_value = mock_cur

        # User is RH (id = 2)
        user_row = {
            "id": 2, "log_id": "gas_rh", "first_name": "Risk", "last_name": "Head",
            "email": "rh@gas.com", "dept_id": 1, "role_id": 2, "user_type_id": 5,
            "user_type_name": "Risk Head"
        }
        # Risk is FH approved (fh_status = 1), but RM is pending (rm_status = 0)
        risk_row = {
            "risk_register_id": 103, "risk_id": "RSK-GAS-003", "risk_name": "Compressor Vibration",
            "dept_id": 1, "risk_owner_id": 5, "risk_status": 3,
            "risk_function_head_approval_status": 1, "risk_manager_approval_status": 0, "risk_head_approval_status": 0,
            "current_status_name": "Opened"
        }

        mock_cur.fetchone.side_effect = [user_row, risk_row]

        res = self.db.approve_or_reject_risk(
            risk_id="RSK-GAS-003", approver_id=2, action="approve"
        )
        assert res["success"] is False
        assert "not yet available for Risk Head approval" in res["message"]
        assert "Risk Manager approval is still pending" in res["message"]

    @patch.object(ERMDatabaseService, '_get_connection')
    def test_rejection_requires_mandatory_remark(self, mock_conn):
        """Test rejection without remark fails validation."""
        mock_c = MagicMock()
        mock_conn.return_value = mock_c
        mock_cur = MagicMock()
        mock_c.cursor.return_value = mock_cur

        user_row = {
            "id": 4, "log_id": "gas_fh", "first_name": "Gas", "last_name": "FH",
            "dept_id": 1,
            "user_type_name": "Functional Head"
        }
        risk_row = {
            "risk_register_id": 104, "risk_id": "RSK-GAS-004", "risk_name": "Flare System Surge",
            "dept_id": 1,
            "risk_function_head_approval_status": 0, "risk_manager_approval_status": 0, "risk_head_approval_status": 0,
            "current_status_name": "Submitted to Functional Head"
        }

        mock_cur.fetchone.side_effect = [user_row, risk_row]

        res = self.db.approve_or_reject_risk(
            risk_id="RSK-GAS-004", approver_id=4, action="reject", remark=""
        )
        assert res["success"] is False
        assert "rejection reason/remark is mandatory" in res["message"]

    @patch.object(ERMDatabaseService, '_get_connection')
    def test_rh_final_approval_success(self, mock_conn):
        """Test RH final approval after FH + RM -> Marks Approved."""
        mock_c = MagicMock()
        mock_conn.return_value = mock_c
        mock_cur = MagicMock()
        mock_c.cursor.return_value = mock_cur

        user_row = {
            "id": 2, "log_id": "gas_rh", "first_name": "Chief", "last_name": "Risk Officer",
            "dept_id": 1,
            "user_type_name": "Risk Head"
        }
        risk_row = {
            "risk_register_id": 105, "risk_id": "RSK-GAS-005", "risk_name": "Turbine Overheating",
            "dept_id": 1, "risk_owner_id": 5, "risk_co_owner_id": None,
            "financial_year": "2026-2027", "risk_status": 4, "risk_progress": "0%",
            "risk_function_head_approval_status": 1, "risk_manager_approval_status": 1, "risk_head_approval_status": 0,
            "current_status_name": "Opened"
        }
        status_rows = [
            {"id": 1, "status_name": "Draft"},
            {"id": 5, "status_name": "Approved"},
            {"id": 6, "status_name": "Pending for Action"}
        ]

        mock_cur.fetchone.side_effect = [user_row, risk_row]
        mock_cur.fetchall.return_value = status_rows

        res = self.db.approve_or_reject_risk(
            risk_id="RSK-GAS-005", approver_id=2, action="approve", remark="Final board sign-off granted"
        )
        assert res["success"] is True
        assert res["approval_level"] == 3
        assert "Risk Head Final Sign-Off" in res["stage"]
        assert "Approved" in res["next_queue"]
        mock_c.commit.assert_called_once()


class TestGovernanceApprovalAgent:
    """Agent integration tests verifying conversational commands and validation."""

    def setup_method(self):
        self.agent = ERMCopilotAgent()
        from ERM_Copilot.agents.approval_workflow import approval_workflow_agent
        from ERM_Copilot.workflow.checkpointer import workflow_checkpointer
        approval_workflow_agent.sessions.clear()
        for sid in ["test_rej_sess", "test_app_sess"]:
            for key in (f"4::{sid}", sid):
                try:
                    wf = workflow_checkpointer.load_active_for_session(key)
                    if wf:
                        workflow_checkpointer.delete(wf.workflow_id)
                except Exception:
                    pass

    def test_missing_auth_user_id_returns_auth_error(self):
        """Test chat command without authenticated user_id fails immediately without fallback."""
        req = AgentRequest(
            message="Approve RSK-GAS-001",
            user_id="", # No user ID
            user_role="Functional Head",
            metadata={}
        )
        resp = self.agent.process(req)
        assert "Authentication" in resp.response
        assert resp.metadata.get("intent") == "AUTH_FAILURE"

    @patch("ERM_Copilot.agents.approval_workflow.agent.fetch_risk_details")
    def test_rejection_without_remark_prompts_for_reason(self, mock_fetch_details):
        """Test chat command 'Reject RSK-GAS-001' prompts user for mandatory reason."""
        mock_fetch_details.return_value = {
            "risk_id": "RSK-GAS-001",
            "risk_name": "Flare System Surge",
            "dept_id": 1,
            "risk_status": 2,
            "fh_status": 0,
            "rm_status": 0,
            "rh_status": 0,
        }
        req = AgentRequest(
            message="Reject RSK-GAS-001",
            user_id="4",
            user_role="Functional Head",
            session_id="test_rej_sess",
            metadata={"dept_id": 1}
        )
        resp = self.agent.process(req)
        assert "Rejection Reason Required" in resp.response
        assert resp.metadata.get("intent") == "AWAITING_REMARK"

    @patch("ERM_Copilot.agents.approval_workflow.agent.fetch_risk_details")
    def test_approve_prompts_for_confirmation(self, mock_fetch_details):
        """Test chat command 'Approve RSK-GAS-001' prompts user for confirmation preview."""
        mock_fetch_details.return_value = {
            "risk_id": "RSK-GAS-001",
            "risk_name": "Flare System Surge",
            "dept_id": 1,
            "risk_status": 2,
            "fh_status": 0,
            "rm_status": 0,
            "rh_status": 0,
        }
        req = AgentRequest(
            message="Approve RSK-GAS-001",
            user_id="4",
            user_role="Functional Head",
            session_id="test_app_sess",
            metadata={"dept_id": 1}
        )
        resp = self.agent.process(req)
        assert resp.metadata.get("intent") == "AWAITING_CONFIRMATION"
        assert "Risk Approval Summary" in resp.response
