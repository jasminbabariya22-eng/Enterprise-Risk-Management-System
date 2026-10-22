"""
Targeted Verification Suite for Hardened Approval Workflow Agent.
Tests all 8 requirements:
 1. Orchestrator routing to new approval_workflow_agent vs legacy session preservation.
 2. Strict stage-specific state reconciliation (previous stage flags cannot prove current stage success).
 3. Trusted server context & fail-closed behavior on missing user ID or role.
 4. Unified remark policy enforcement (mandatory for rejection, optional with standard default for approval).
 5. Fail-closed department isolation for Functional Head in validation and mutation paths.
 6. Immediate pre-execution revalidation of authorization and approval stage.
"""
import unittest
from unittest.mock import patch, MagicMock

from ERM_Copilot.models.contracts import AgentRequest, AgentResponse
from ERM_Copilot.agents.approval_workflow import (
    ApprovalWorkflowAgent,
    approval_workflow_agent,
    ApprovalGoal,
    ApprovalWorkflowState,
    validate_approval_preconditions,
    extract_goal_and_inputs,
)
from ERM_Copilot.agents.approval_workflow.state import ApprovalWorkflowSession
from ERM_Copilot.agents.approval_workflow.requirements import check_missing_requirements
from ERM_Copilot.agents.approval_workflow.planner import ApprovalWorkflowPlanner, ApprovalActionType
from ERM_Copilot.agents.approval_workflow.execution import (
    bind_pending_confirmation,
    execute_confirmed_decision,
)
from ERM_Copilot.agents.orchestrator.agent import ERMCopilotAgent


class TestApprovalWorkflowHardening(unittest.TestCase):
    """Deep verification of hardened security, routing, and state reconciliation rules."""

    def setUp(self):
        self.workflow_agent = ApprovalWorkflowAgent()
        self.workflow_agent.sessions.clear()
        approval_workflow_agent.sessions.clear()
        self.orchestrator = ERMCopilotAgent()

        from ERM_Copilot.workflow.checkpointer import workflow_checkpointer
        for sid in ["sess_orch_route_01", "sess_legacy_01", "sess_rm_reconcile", "sess_rm_success",
                    "sess_no_role", "sess_no_uid", "sess_rem_rej", "sess_rem_app", "sess_pre_reval"]:
            for key in (f"10::{sid}", f"20::{sid}", sid):
                wf = workflow_checkpointer.load_active_for_session(key)
                if wf:
                    workflow_checkpointer.delete(wf.workflow_id)

    # -----------------------------------------------------------------
    # Requirement 1: Orchestrator Routing
    # -----------------------------------------------------------------

    @patch("ERM_Copilot.agents.approval_workflow.agent.fetch_risk_details")
    def test_01_orchestrator_routes_new_approval_requests_to_workflow_agent(self, mock_fetch):
        """Orchestrator delegates new approval prompts to approval_workflow_agent, not legacy approval_agent."""
        mock_fetch.return_value = {
            "risk_id": "RSK-ORCH-01",
            "risk_name": "Pipeline Overpressure",
            "dept_id": 1,
            "risk_status": 2,
            "fh_status": 0,
        }
        req = AgentRequest(
            message="Approve RSK-ORCH-01 with remark verified",
            user_id="10",
            user_role="Functional Head",
            session_id="sess_orch_route_01",
            metadata={"dept_id": 1}
        )
        resp = self.orchestrator.process(req)
        # Should be processed by approval_workflow_agent, producing confirmation prompt
        self.assertEqual(resp.metadata.get("intent"), "AWAITING_CONFIRMATION")
        self.assertIn("Confirm Risk Governance Sign-Off", resp.response)
        self.assertIn("RSK-ORCH-01", resp.response)

    def test_02_orchestrator_preserves_active_legacy_approval_session(self):
        """If legacy approval_agent has an active session, orchestrator preserves it for backward compatibility."""
        from ERM_Copilot.agents.approval import approval_agent

        req = AgentRequest(
            message="confirm",
            user_id="10",
            user_role="Functional Head",
            session_id="sess_legacy_01",
            metadata={"dept_id": 1}
        )
        with patch.object(approval_agent, "is_session_active", return_value=True), \
             patch.object(approval_agent, "process", return_value=AgentResponse(
                 request_id="req-leg",
                 agent_id="approval_agent",
                 status="success",
                 success=True,
                 response="Legacy approval executed",
                 metadata={"intent": "APPROVAL_EXECUTED"}
             )) as mock_proc:
            resp = self.orchestrator.process(req)
            mock_proc.assert_called_once()
            self.assertEqual(resp.response, "Legacy approval executed")

    # -----------------------------------------------------------------
    # Requirement 2: Exact Intended Stage State Reconciliation
    # -----------------------------------------------------------------

    @patch("ERM_Copilot.agents.approval_workflow.execution.execute_governed_approval_decision")
    @patch("ERM_Copilot.agents.approval_workflow.execution.fetch_risk_details")
    def test_03_reconciliation_rejects_previous_fh_flag_as_proof_of_rm_mutation(self, mock_fetch, mock_exec):
        """When RM approves, an existing fh_status=1 flag MUST NOT be accepted as proof of RM approval."""
        sess = ApprovalWorkflowSession(
            session_id="sess_rm_reconcile",
            user_id="20",
            user_role="Risk Manager",
            dept_id=1,
            risk_id="RSK-RM-01",
            action="approve",
            remark="RM verified"
        )
        bind_pending_confirmation(sess, "approve", "RSK-RM-01", "RM verified")

        mock_exec.side_effect = TimeoutError("Database connection dropped during email notification dispatch.")

        # Pre-state before execution: FH was approved earlier (fh_status=1), RM is pending (rm_status=0)
        pre_state = {
            "risk_id": "RSK-RM-01",
            "dept_id": 1,
            "risk_status": 3,
            "fh_status": 1,
            "rm_status": 0,
            "risk_function_head_approval_by": 10,
        }
        # Post-state in DB: rm_status is still 0 (mutation failed to commit)
        post_state = {
            "risk_id": "RSK-RM-01",
            "dept_id": 1,
            "risk_status": 3,
            "fh_status": 1,
            "rm_status": 0,
            "risk_function_head_approval_by": 10,
        }
        mock_fetch.side_effect = [pre_state, post_state]

        success, res, err = execute_confirmed_decision(sess)
        # Must FAIL closed because RM stage was not actually committed
        self.assertFalse(success)
        self.assertIn("Database connection dropped", str(err))

    @patch("ERM_Copilot.agents.approval_workflow.execution.execute_governed_approval_decision")
    @patch("ERM_Copilot.agents.approval_workflow.execution.fetch_risk_details")
    def test_04_reconciliation_accepts_rm_mutation_when_rm_flag_committed(self, mock_fetch, mock_exec):
        """When RM approves and network times out, but rm_status=1 committed in DB, reconciliation confirms success."""
        sess = ApprovalWorkflowSession(
            session_id="sess_rm_success",
            user_id="20",
            user_role="Risk Manager",
            dept_id=1,
            risk_id="RSK-RM-02",
            action="approve",
            remark="RM verified"
        )
        bind_pending_confirmation(sess, "approve", "RSK-RM-02", "RM verified")

        mock_exec.side_effect = TimeoutError("Network timeout during notification.")

        pre_state = {
            "risk_id": "RSK-RM-02",
            "dept_id": 1,
            "risk_status": 3,
            "fh_status": 1,
            "rm_status": 0,
        }
        post_state = {
            "risk_id": "RSK-RM-02",
            "dept_id": 1,
            "risk_status": 4,
            "fh_status": 1,
            "rm_status": 1,
            "risk_manager_approval_by": "20",
        }
        mock_fetch.side_effect = [pre_state, post_state]

        success, res, err = execute_confirmed_decision(sess)
        self.assertTrue(success)
        self.assertIsNone(err)

    # -----------------------------------------------------------------
    # Requirement 3: Trusted Server Context & Fail-Closed
    # -----------------------------------------------------------------

    def test_05_missing_user_role_fails_closed(self):
        """Missing user_role must fail closed with ROLE_MISSING rather than defaulting to Functional Head."""
        req = AgentRequest(
            message="Approve RSK-101",
            user_id="10",
            user_role=None,
            session_id="sess_no_role"
        )
        resp = self.workflow_agent.process(req)
        self.assertFalse(resp.success)
        self.assertEqual(resp.metadata.get("intent"), "ROLE_MISSING")
        self.assertIn("Authorization Failure", resp.response)

    def test_06_missing_user_id_fails_closed(self):
        """Missing user_id must fail closed with AUTH_FAILURE."""
        req = AgentRequest(
            message="Approve RSK-101",
            user_id=None,
            user_role="Functional Head",
            session_id="sess_no_uid"
        )
        resp = self.workflow_agent.process(req)
        self.assertFalse(resp.success)
        self.assertEqual(resp.metadata.get("intent"), "AUTH_FAILURE")
        self.assertIn("Authentication Failure", resp.response)

    # -----------------------------------------------------------------
    # Requirement 4: Unified Remark Policy
    # -----------------------------------------------------------------

    def test_07_rejection_remark_is_mandatory_across_requirements_and_planner(self):
        """Rejection requires a non-empty remark; approval does not require a remark."""
        # Session for rejection without remark (with risk_data loaded)
        sess_rej = ApprovalWorkflowSession(
            session_id="sess_rem_rej",
            user_id="10",
            user_role="Functional Head",
            dept_id=1,
            goal=ApprovalGoal.REJECT_RISK,
            risk_id="RSK-101",
            risk_data={"risk_id": "RSK-101", "dept_id": 1, "risk_status": 2, "fh_status": 0},
            action="reject",
            remark=None
        )
        missing_rej = check_missing_requirements(sess_rej)
        self.assertIn("remark", missing_rej)

        plan_rej = ApprovalWorkflowPlanner.plan_next_action(sess_rej)
        self.assertEqual(plan_rej.action_type, ApprovalActionType.REQUEST_MISSING_INPUT)
        self.assertEqual(plan_rej.missing_field, "remark")

        # Session for approval without remark
        sess_app = ApprovalWorkflowSession(
            session_id="sess_rem_app",
            user_id="10",
            user_role="Functional Head",
            goal=ApprovalGoal.APPROVE_RISK,
            risk_id="RSK-101",
            action="approve",
            remark=None
        )
        missing_app = check_missing_requirements(sess_app)
        self.assertNotIn("remark", missing_app)

    # -----------------------------------------------------------------
    # Requirement 5: Fail-Closed Department Isolation
    # -----------------------------------------------------------------

    def test_08_fh_department_isolation_fails_closed_when_dept_missing(self):
        """Functional Head review must fail closed if either user dept or risk dept is None."""
        risk_data = {"risk_id": "RSK-DEPT-01", "dept_id": 1, "risk_status": 2, "fh_status": 0}

        # 1. User dept is None
        res_no_user_dept = validate_approval_preconditions(
            user_role="Functional Head",
            user_dept_id=None,
            risk_data=risk_data,
            action="approve"
        )
        self.assertFalse(res_no_user_dept.is_valid)
        self.assertIn("Department access restriction", res_no_user_dept.policy_block_reason)

        # 2. Risk dept is None
        res_no_risk_dept = validate_approval_preconditions(
            user_role="Functional Head",
            user_dept_id=1,
            risk_data={"risk_id": "RSK-DEPT-02", "dept_id": None, "risk_status": 2, "fh_status": 0},
            action="approve"
        )
        self.assertFalse(res_no_risk_dept.is_valid)
        self.assertIn("Department access restriction", res_no_risk_dept.policy_block_reason)

        # 3. Dept mismatch
        res_mismatch = validate_approval_preconditions(
            user_role="Functional Head",
            user_dept_id=1,
            risk_data={"risk_id": "RSK-DEPT-03", "dept_id": 2, "risk_status": 2, "fh_status": 0},
            action="approve"
        )
        self.assertFalse(res_mismatch.is_valid)
        self.assertIn("does not match your assigned department", res_mismatch.policy_block_reason)

    # -----------------------------------------------------------------
    # Requirement 6: Immediate Pre-Execution Revalidation
    # -----------------------------------------------------------------

    @patch("ERM_Copilot.agents.approval_workflow.execution.execute_governed_approval_decision")
    @patch("ERM_Copilot.agents.approval_workflow.execution.fetch_risk_details")
    def test_09_pre_execution_revalidation_blocks_if_state_changed_to_already_approved(self, mock_fetch, mock_exec):
        """If risk was approved by another approver before confirmation was confirmed, revalidation blocks mutation."""
        sess = ApprovalWorkflowSession(
            session_id="sess_pre_reval",
            user_id="10",
            user_role="Functional Head",
            dept_id=1,
            risk_id="RSK-CONCUR-01",
            action="approve",
            remark="approved"
        )
        bind_pending_confirmation(sess, "approve", "RSK-CONCUR-01", "approved")

        # Database state fetched immediately before execution shows risk was already approved (fh_status=1)
        mock_fetch.return_value = {
            "risk_id": "RSK-CONCUR-01",
            "dept_id": 1,
            "risk_status": 3,
            "fh_status": 1,
        }

        success, res, err = execute_confirmed_decision(sess)
        self.assertFalse(success)
        self.assertIn("Precondition revalidation failed", str(err))
        self.assertIn("already been approved by Functional Head", str(err))
        mock_exec.assert_not_called()

    # -----------------------------------------------------------------
    # Section 1 Extended: Identity Spoofing & Checkpoint Role Mutation
    # -----------------------------------------------------------------

    @patch("ERM_Copilot.agents.approval_workflow.agent.fetch_risk_details")
    def test_10_client_metadata_role_spoofing_prevented(self, mock_fetch):
        """Client supplying metadata={'role': 'Super Admin'} while request.user_role='Risk Owner' must NOT be granted admin rights."""
        mock_fetch.return_value = {
            "risk_id": "RSK-SPOOF-01",
            "dept_id": 1,
            "risk_status": 2,
            "fh_status": 0,
        }
        req = AgentRequest(
            message="Approve RSK-SPOOF-01",
            user_id="101",
            user_role="Risk Owner",  # Trusted authenticated role
            session_id="sess_spoof_01",
            metadata={"role": "Super Admin", "dept_id": 1}  # Malicious metadata injection
        )
        resp = self.orchestrator.process(req)
        # Must be rejected because trusted role is Risk Owner
        self.assertFalse(resp.success)
        self.assertIn("Risk Owner", resp.response)
        self.assertIn("not authorized", resp.response.lower())

    @patch("ERM_Copilot.agents.approval_workflow.agent.fetch_risk_details")
    @patch("ERM_Copilot.agents.approval_workflow.execution.execute_governed_approval_decision")
    def test_11_checkpoint_resume_blocks_if_user_role_changed_upon_resume(self, mock_exec, mock_fetch):
        """User started approval session as FH, but upon resume their role is revoked to Risk Owner -> execution blocked."""
        # Session was saved in checkpoint when user was Functional Head
        sess = ApprovalWorkflowSession(
            session_id="sess_revoked_role",
            user_id="10",
            user_role="Functional Head",
            dept_id=1,
            goal=ApprovalGoal.APPROVE_RISK,
            state=ApprovalWorkflowState.AWAITING_CONFIRMATION,
            risk_id="RSK-REVOKED-01",
            risk_data={"risk_id": "RSK-REVOKED-01", "dept_id": 1, "risk_status": 2, "fh_status": 0},
            action="approve",
            remark="ok"
        )
        bind_pending_confirmation(sess, "approve", "RSK-REVOKED-01", "ok")

        # Now simulate resuming with request context where user_role has been revoked
        req_resume = AgentRequest(
            message="confirm",
            user_id="10",
            user_role="Risk Owner",  # Revoked role
            session_id="sess_revoked_role",
            metadata={"dept_id": 1}
        )
        self.workflow_agent.sessions["10::sess_revoked_role"] = sess

        resp = self.workflow_agent.process(req_resume)
        self.assertFalse(resp.success)
        self.assertEqual(resp.metadata.get("intent"), "APPROVAL_POLICY_BLOCKED")
        self.assertIn("Risk Owner", resp.response)
        mock_exec.assert_not_called()

    # -----------------------------------------------------------------
    # Section 2 Extended: Independent Stage Recovery (FH, RM, RH)
    # -----------------------------------------------------------------

    # --- STAGE 1: Functional Head ---
    @patch("ERM_Copilot.agents.approval_workflow.execution.execute_governed_approval_decision")
    @patch("ERM_Copilot.agents.approval_workflow.execution.fetch_risk_details")
    def test_12_fh_timeout_before_db_commit_fails_closed(self, mock_fetch, mock_exec):
        """FH approval timeout before DB commit: DB still shows fh_status=0 -> state reconciliation fails closed."""
        sess = ApprovalWorkflowSession(session_id="sess_fh_timeout_pre", user_id="10", user_role="Functional Head", dept_id=1, risk_id="RSK-FH-T1", action="approve", remark="verified")
        bind_pending_confirmation(sess, "approve", "RSK-FH-T1", "verified")
        mock_exec.side_effect = TimeoutError("Connection reset before commit")
        # Pre-state and post-state both show fh_status=0 (did not commit)
        state_uncommitted = {"risk_id": "RSK-FH-T1", "dept_id": 1, "risk_status": 2, "fh_status": 0}
        mock_fetch.side_effect = [state_uncommitted, state_uncommitted]

        success, res, err = execute_confirmed_decision(sess)
        self.assertFalse(success)
        self.assertIn("Connection reset before commit", str(err))

    @patch("ERM_Copilot.agents.approval_workflow.agent.fetch_risk_details")
    def test_13_fh_earlier_approval_flag_already_set_blocks(self, mock_fetch):
        """FH attempting to approve when fh_status is already 1 is blocked before execution."""
        mock_fetch.return_value = {"risk_id": "RSK-FH-1301", "dept_id": 1, "risk_status": 3, "fh_status": 1}
        req = AgentRequest(message="Approve RSK-FH-1301 with remark ok", user_id="10", user_role="Functional Head", session_id="sess_fh_early", metadata={"dept_id": 1})
        resp = self.workflow_agent.process(req)
        self.assertFalse(resp.success)
        self.assertEqual(resp.metadata.get("intent"), "APPROVAL_POLICY_BLOCKED")
        self.assertIn("already been approved by Functional Head", resp.response)

    # --- STAGE 2: Risk Manager ---
    @patch("ERM_Copilot.agents.approval_workflow.execution.execute_governed_approval_decision")
    @patch("ERM_Copilot.agents.approval_workflow.execution.fetch_risk_details")
    def test_14_rm_successful_mutation(self, mock_fetch, mock_exec):
        """RM confirms approval on pending Stage 2 risk -> successfully executes RM mutation."""
        mock_fetch.return_value = {"risk_id": "RSK-RM-SUCC", "dept_id": 1, "risk_status": 3, "fh_status": 1, "rm_status": 0}
        mock_exec.return_value = {"success": True, "risk_id": "RSK-RM-SUCC", "action": "Approved", "stage": "Stage 2: Risk Manager Validation", "approver_role": "Risk Manager"}
        sess = ApprovalWorkflowSession(session_id="sess_rm_succ", user_id="20", user_role="Risk Manager", dept_id=1, risk_id="RSK-RM-SUCC", action="approve", remark="RM check")
        bind_pending_confirmation(sess, "approve", "RSK-RM-SUCC", "RM check")
        success, res, err = execute_confirmed_decision(sess)
        self.assertTrue(success)
        self.assertIsNone(err)

    @patch("ERM_Copilot.agents.approval_workflow.agent.fetch_risk_details")
    def test_15_rm_mutation_rejected_when_fh_pending(self, mock_fetch):
        """RM attempting to approve when FH is still pending (fh_status=0) is rejected by policy."""
        mock_fetch.return_value = {"risk_id": "RSK-RM-1501", "dept_id": 1, "risk_status": 2, "fh_status": 0, "rm_status": 0}
        req = AgentRequest(message="Approve RSK-RM-1501 with remark ok", user_id="20", user_role="Risk Manager", session_id="sess_rm_ood", metadata={"dept_id": 1})
        resp = self.workflow_agent.process(req)
        self.assertFalse(resp.success)
        self.assertEqual(resp.metadata.get("intent"), "APPROVAL_POLICY_BLOCKED")
        self.assertIn("Functional Head approval is still pending", resp.response)

    @patch("ERM_Copilot.agents.approval_workflow.agent.fetch_risk_details")
    def test_16_rm_earlier_approval_flag_already_set_blocks(self, mock_fetch):
        """RM attempting to approve when rm_status is already 1 is blocked."""
        mock_fetch.return_value = {"risk_id": "RSK-RM-1601", "dept_id": 1, "risk_status": 4, "fh_status": 1, "rm_status": 1}
        req = AgentRequest(message="Approve RSK-RM-1601 with remark ok", user_id="20", user_role="Risk Manager", session_id="sess_rm_early", metadata={"dept_id": 1})
        resp = self.workflow_agent.process(req)
        self.assertFalse(resp.success)
        self.assertEqual(resp.metadata.get("intent"), "APPROVAL_POLICY_BLOCKED")
        self.assertIn("already been approved by Risk Manager", resp.response)

    # --- STAGE 3: Risk Head ---
    @patch("ERM_Copilot.agents.approval_workflow.execution.execute_governed_approval_decision")
    @patch("ERM_Copilot.agents.approval_workflow.execution.fetch_risk_details")
    def test_17_rh_successful_mutation(self, mock_fetch, mock_exec):
        """RH confirms final approval on Stage 3 risk -> successfully executes RH mutation."""
        mock_fetch.return_value = {"risk_id": "RSK-RH-SUCC", "dept_id": 1, "risk_status": 4, "fh_status": 1, "rm_status": 1, "rh_status": 0}
        mock_exec.return_value = {"success": True, "risk_id": "RSK-RH-SUCC", "action": "Approved", "stage": "Stage 3: Risk Head Final Sign-Off", "approver_role": "Risk Head"}
        sess = ApprovalWorkflowSession(session_id="sess_rh_succ", user_id="30", user_role="Risk Head", dept_id=1, risk_id="RSK-RH-SUCC", action="approve", remark="Final RH sign-off")
        bind_pending_confirmation(sess, "approve", "RSK-RH-SUCC", "Final RH sign-off")
        success, res, err = execute_confirmed_decision(sess)
        self.assertTrue(success)
        self.assertIsNone(err)

    @patch("ERM_Copilot.agents.approval_workflow.agent.fetch_risk_details")
    def test_18_rh_mutation_rejected_when_rm_pending(self, mock_fetch):
        """RH attempting to approve when RM is still pending (rm_status=0) is rejected by policy."""
        mock_fetch.return_value = {"risk_id": "RSK-RH-1801", "dept_id": 1, "risk_status": 3, "fh_status": 1, "rm_status": 0, "rh_status": 0}
        req = AgentRequest(message="Approve RSK-RH-1801 with remark ok", user_id="30", user_role="Risk Head", session_id="sess_rh_ood", metadata={"dept_id": 1})
        resp = self.workflow_agent.process(req)
        self.assertFalse(resp.success)
        self.assertEqual(resp.metadata.get("intent"), "APPROVAL_POLICY_BLOCKED")
        self.assertIn("Risk Manager approval is still pending", resp.response)

    @patch("ERM_Copilot.agents.approval_workflow.execution.execute_governed_approval_decision")
    @patch("ERM_Copilot.agents.approval_workflow.execution.fetch_risk_details")
    def test_19_rh_timeout_reconciliation_verifies_rh_status(self, mock_fetch, mock_exec):
        """RH approval timeout: state reconciliation confirms rh_status=1, ignoring prior fh_status and rm_status."""
        sess = ApprovalWorkflowSession(session_id="sess_rh_timeout", user_id="30", user_role="Risk Head", dept_id=1, risk_id="RSK-RH-T1", action="approve", remark="RH ok")
        bind_pending_confirmation(sess, "approve", "RSK-RH-T1", "RH ok")
        mock_exec.side_effect = TimeoutError("SMTP timeout on treatment notification")

        pre_state = {"risk_id": "RSK-RH-T1", "dept_id": 1, "risk_status": 4, "fh_status": 1, "rm_status": 1, "rh_status": 0}
        post_state = {"risk_id": "RSK-RH-T1", "dept_id": 1, "risk_status": 5, "fh_status": 1, "rm_status": 1, "rh_status": 1, "risk_head_approval_by": "30"}
        mock_fetch.side_effect = [pre_state, post_state]

        success, res, err = execute_confirmed_decision(sess)
        self.assertTrue(success)
        self.assertIsNone(err)

    @patch("ERM_Copilot.agents.approval_workflow.agent.fetch_risk_details")
    def test_20_rh_earlier_approval_flag_already_set_blocks(self, mock_fetch):
        """RH attempting to approve when risk is already fully approved (numeric_status=5) is blocked."""
        mock_fetch.return_value = {"risk_id": "RSK-RH-2001", "dept_id": 1, "risk_status": 5, "fh_status": 1, "rm_status": 1, "rh_status": 1}
        req = AgentRequest(message="Approve RSK-RH-2001 with remark ok", user_id="30", user_role="Risk Head", session_id="sess_rh_early", metadata={"dept_id": 1})
        resp = self.workflow_agent.process(req)
        self.assertFalse(resp.success)
        self.assertEqual(resp.metadata.get("intent"), "APPROVAL_POLICY_BLOCKED")
        self.assertIn("already been fully approved", resp.response)

    # -----------------------------------------------------------------
    # Section 4: Transaction & Notification Differentiation
    # -----------------------------------------------------------------

    @patch("ERM_Copilot.agents.approval_workflow.execution.execute_governed_approval_decision")
    @patch("ERM_Copilot.agents.approval_workflow.execution.fetch_risk_details")
    def test_21_notification_failure_tracked_without_rolling_back_committed_mutation(self, mock_fetch, mock_exec):
        """When DB mutation commits but email notification dispatch fails, system marks mutation as committed with notification warning."""
        mock_fetch.return_value = {"risk_id": "RSK-NOTIF-01", "dept_id": 1, "risk_status": 2, "fh_status": 0}
        mock_exec.return_value = {
            "success": True,
            "risk_id": "RSK-NOTIF-01",
            "action": "Approved",
            "notification_status": "FAILED_OR_PENDING",
            "notification_error": "SMTP gateway timeout",
        }

        sess = ApprovalWorkflowSession(session_id="sess_notif_warn", user_id="10", user_role="Functional Head", dept_id=1, risk_id="RSK-NOTIF-01", action="approve", remark="ok")
        bind_pending_confirmation(sess, "approve", "RSK-NOTIF-01", "ok")

        success, res, err = execute_confirmed_decision(sess)
        self.assertTrue(success)
        self.assertIn("notification_warning", res)
        self.assertIn("committed in database", res["notification_warning"])


if __name__ == "__main__":
    unittest.main()
