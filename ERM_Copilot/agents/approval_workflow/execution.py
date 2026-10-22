"""
Execution Coordination for Approval Workflow Mutations and Checks.
Manages confirmation tokens, replay protection, authoritative verification,
and safe outcome reconciliation.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from ERM_Copilot.ai_harness.confirmation import confirmation_manager
from ERM_Copilot.ai_harness.exceptions import (
    ConfirmationMismatchError,
    ConfirmationRequiredError,
    ToolValidationError,
    AuthorizationError,
)
from ERM_Copilot.agents.approval_workflow.state import (
    ApprovalWorkflowSession,
    ApprovalWorkflowState,
)
from ERM_Copilot.agents.approval_workflow.tools import (
    execute_governed_approval_decision,
    fetch_risk_details,
)

logger = logging.getLogger("ERM_Copilot.agents.approval_workflow.execution")


def bind_pending_confirmation(
    session: ApprovalWorkflowSession,
    action: str,
    risk_id: str,
    remark: str
) -> Dict[str, Any]:
    """
    Create a cryptographically verifiable confirmation token for the proposed mutation.
    Binds exact action arguments to prevent argument tampering between preview and confirmation.
    """
    token_data = confirmation_manager.create_pending_confirmation(
        action_name="approve_or_reject_risk",
        user_id=str(session.user_id),
        user_role=str(session.user_role),
        risk_id=risk_id,
        parameters={
            "risk_id": risk_id,
            "action": action,
            "remark": remark,
            "approver_id": int(session.user_id),
        },
        summary_text=f"Confirm {action.upper()} for risk {risk_id}",
    )
    session.pending_confirmation = token_data
    session.state = ApprovalWorkflowState.AWAITING_CONFIRMATION
    return token_data


def execute_confirmed_decision(
    session: ApprovalWorkflowSession
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """
    Execute the confirmed approval/rejection mutation with confirmation token validation,
    replay protection, and state-reconciliation safety.
    
    Returns:
        (success, result_dict, error_message)
    """
    if not session.pending_confirmation:
        return False, {}, "No pending confirmation found. Action requires explicit user confirmation."

    risk_id = session.risk_id
    action = session.action

    if not risk_id or not action:
        return False, {}, "Missing risk identifier or decision action."

    # Consistent remark policy: mandatory for rejection, default fallback for approval
    if action == "reject":
        if not session.remark or not session.remark.strip():
            return False, {}, "A rejection reason/remark is mandatory when rejecting a risk."
        remark = session.remark.strip()
    else:
        remark = session.remark.strip() if session.remark and session.remark.strip() else f"Approved by {session.user_role} via ERM Copilot"

    # 1. Verify confirmation token against registered manager
    try:
        confirmation_manager.validate_confirmation(
            pending_state=session.pending_confirmation,
            executing_user_id=str(session.user_id),
            executing_action="approve_or_reject_risk",
            executing_params={
                "risk_id": risk_id,
                "action": action,
                "remark": session.remark or remark,
                "approver_id": int(session.user_id),
            },
            executing_risk_id=risk_id,
        )
    except ConfirmationMismatchError as cme:
        return False, {}, f"Confirmation arguments mismatched: {cme}"

    # 2. Revalidate authorization and current approval stage immediately before executing
    fresh_risk = fetch_risk_details(session, risk_id)
    if not fresh_risk:
        return False, {}, f"Risk record '{risk_id}' could not be verified from the database prior to execution."

    from ERM_Copilot.agents.approval_workflow.validation import validate_approval_preconditions
    val_res = validate_approval_preconditions(
        user_role=session.user_role,
        user_dept_id=session.dept_id,
        risk_data=fresh_risk,
        action=action,
        remark=remark,
    )
    if not val_res.is_valid:
        logger.warning(f"Pre-execution revalidation failed for {risk_id}: {val_res.policy_block_reason}")
        return False, fresh_risk, f"Precondition revalidation failed immediately before execution: {val_res.policy_block_reason}"

    # 3. Mark token as EXECUTED to prevent replay
    session.pending_confirmation["status"] = "EXECUTED"

    # 4. Execute through Governed Tool Adapter
    try:
        result = execute_governed_approval_decision(
            session=session,
            risk_id=risk_id,
            action=action,
            remark=remark,
            bypass_confirmation=True,  # Verified above
        )
        
        # If wrapped result
        actual = result.get("result", result) if isinstance(result, dict) else result
        success = actual.get("success", True) if isinstance(actual, dict) else True
        if not success:
            err = actual.get("message", "Approval operation failed in database.")
            return False, actual, err

        if isinstance(actual, dict) and actual.get("notification_status") == "FAILED_OR_PENDING":
            actual["notification_warning"] = "Risk mutation committed in database, but notification dispatch encountered an issue or remains pending."

        return True, actual, None

    except Exception as exc:
        logger.warning(f"Error during approval mutation execution: {exc}. Reconciling with authoritative state...")
        # 5. Safe recovery: Inspect authoritative DB state before declaring complete failure
        # Never allow a previous stage flag to count as proof of current stage success!
        try:
            rechecked = fetch_risk_details(session, risk_id)
            if rechecked:
                user_role_lower = str(session.user_role or "").lower()
                intended_level = None
                if "function" in user_role_lower or "fh" in user_role_lower:
                    intended_level = 1
                elif "manager" in user_role_lower or "rm" in user_role_lower:
                    intended_level = 2
                elif "head" in user_role_lower or "rh" in user_role_lower or "cro" in user_role_lower:
                    intended_level = 3
                elif "admin" in user_role_lower:
                    fh_pre = (fresh_risk.get("risk_function_head_approval_status") or fresh_risk.get("fh_status")) == 1
                    rm_pre = (fresh_risk.get("risk_manager_approval_status") or fresh_risk.get("rm_status")) == 1
                    if not fh_pre:
                        intended_level = 1
                    elif not rm_pre:
                        intended_level = 2
                    else:
                        intended_level = 3

                target_status_val = 1 if action == "approve" else -1

                if intended_level == 1:
                    curr_fh = rechecked.get("risk_function_head_approval_status") or rechecked.get("fh_status")
                    prev_fh = fresh_risk.get("risk_function_head_approval_status") or fresh_risk.get("fh_status")
                    by_fh = str(rechecked.get("risk_function_head_approval_by") or "")
                    if curr_fh == target_status_val and (curr_fh != prev_fh or by_fh == str(session.user_id)):
                        logger.info("Authoritative state reconciliation: Stage 1 (FH) mutation was successfully committed.")
                        return True, rechecked, None

                elif intended_level == 2:
                    curr_rm = rechecked.get("risk_manager_approval_status") or rechecked.get("rm_status")
                    prev_rm = fresh_risk.get("risk_manager_approval_status") or fresh_risk.get("rm_status")
                    by_rm = str(rechecked.get("risk_manager_approval_by") or "")
                    if curr_rm == target_status_val and (curr_rm != prev_rm or by_rm == str(session.user_id)):
                        logger.info("Authoritative state reconciliation: Stage 2 (RM) mutation was successfully committed.")
                        return True, rechecked, None

                elif intended_level == 3:
                    curr_rh = rechecked.get("risk_head_approval_status") or rechecked.get("rh_status")
                    prev_rh = fresh_risk.get("risk_head_approval_status") or fresh_risk.get("rh_status")
                    by_rh = str(rechecked.get("risk_head_approval_by") or "")
                    if curr_rh == target_status_val and (curr_rh != prev_rh or by_rh == str(session.user_id)):
                        logger.info("Authoritative state reconciliation: Stage 3 (RH) mutation was successfully committed.")
                        return True, rechecked, None

        except Exception as rec_err:
            logger.debug(f"State reconciliation failed: {rec_err}")

        return False, {}, str(exc)
