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
    remark = session.remark or ("Approved via ERM Copilot" if action == "approve" else "")

    if not risk_id or not action:
        return False, {}, "Missing risk identifier or decision action."

    # 1. Verify confirmation token against registered manager
    try:
        confirmation_manager.validate_confirmation(
            pending_state=session.pending_confirmation,
            executing_user_id=str(session.user_id),
            executing_action="approve_or_reject_risk",
            executing_params={
                "risk_id": risk_id,
                "action": action,
                "remark": remark,
                "approver_id": int(session.user_id),
            },
            executing_risk_id=risk_id,
        )
    except ConfirmationMismatchError as cme:
        return False, {}, f"Confirmation arguments mismatched: {cme}"

    # 2. Mark token as EXECUTED to prevent replay
    session.pending_confirmation["status"] = "EXECUTED"

    # 3. Execute through Governed Tool Adapter
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

        return True, actual, None

    except Exception as exc:
        logger.warning(f"Error during approval mutation execution: {exc}. Reconciling with authoritative state...")
        # 4. Safe recovery: Inspect authoritative DB state before declaring complete failure
        try:
            rechecked = fetch_risk_details(session, risk_id)
            if rechecked:
                # Check if the mutation actually committed despite the exception (e.g. email timeout)
                fh_st = rechecked.get("risk_function_head_approval_status") or rechecked.get("fh_status")
                rm_st = rechecked.get("risk_manager_approval_status") or rechecked.get("rm_status")
                rh_st = rechecked.get("risk_head_approval_status") or rechecked.get("rh_status")
                
                # If any of the status flags reflect the action, reconcile as success
                if action == "approve" and (fh_st == 1 or rm_st == 1 or rh_st == 1):
                    logger.info("Authoritative state reconciliation: risk was approved successfully.")
                    return True, rechecked, None
                elif action == "reject" and (fh_st == -1 or rm_st == -1 or rh_st == -1):
                    logger.info("Authoritative state reconciliation: risk was rejected successfully.")
                    return True, rechecked, None
        except Exception as rec_err:
            logger.debug(f"State reconciliation failed: {rec_err}")

        return False, {}, str(exc)
