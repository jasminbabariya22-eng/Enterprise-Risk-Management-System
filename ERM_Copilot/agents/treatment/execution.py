"""
Enterprise Risk Management (ERM) - Governed Execution, Confirmation Verification & State Reconciliation for Treatment Agent.
Enforces anti-tamper confirmation tokens, single-use execution, pre-execution checks, and post-mutation reconciliation.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from ERM_Copilot.agents.treatment.state import (
    TreatmentGoal,
    TreatmentSession,
    TreatmentWorkflowState,
)
from ERM_Copilot.agents.treatment.tools import (
    add_risk_treatment_tool,
    fetch_risk_info,
    fetch_treatment_details,
    reassign_treatment_owner_tool,
    update_treatment_progress_tool,
)

logger = logging.getLogger("ERM_Copilot.agents.treatment.execution")

CONFIRMATION_EXPIRY_SECONDS = 900  # 15 minutes TTL
CONFIRMATION_HMAC_SECRET = os.getenv(
    "CONFIRMATION_HMAC_SECRET",
    os.getenv("SECRET_KEY", "erm-treatment-confirmation-secret-v1")
)


def normalize_action_name(action: str) -> str:
    """Normalize action names between TreatmentGoal enums and tool registry names."""
    act = str(action).strip().lower().replace("-", "_")
    if "update" in act and "progress" in act:
        return "update_progress"
    if "add" in act and "treatment" in act:
        return "add_treatment"
    if "reassign" in act and "owner" in act:
        return "reassign_owner"
    return act


def compute_confirmation_digest(
    actor_id: str,
    actor_role: str,
    action: str,
    target_id: Any,
    arguments: Dict[str, Any],
    secret_key: Optional[str] = None,
) -> str:
    """Generate deterministic HMAC-SHA256 anti-tamper digest bound to trusted server secret."""
    key = (secret_key or CONFIRMATION_HMAC_SECRET).encode("utf-8")
    canon_args = json.dumps(arguments, sort_keys=True, default=str)
    norm_action = normalize_action_name(action)
    raw = f"{actor_id}|{actor_role}|{norm_action}|{target_id}|{canon_args}".encode("utf-8")
    return hmac.new(key, raw, hashlib.sha256).hexdigest()


def bind_pending_confirmation(
    session: TreatmentSession,
    action: str,
    target_id: Any,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate cryptographic confirmation token bound to user, action, target, arguments, and expiry."""
    digest = compute_confirmation_digest(
        actor_id=str(session.user_id),
        actor_role=session.user_role,
        action=action,
        target_id=target_id,
        arguments=arguments,
    )
    now_epoch = time.time()
    conf = {
        "token": str(uuid.uuid4()),
        "actor_id": str(session.user_id),
        "actor_role": session.user_role,
        "action": normalize_action_name(action),
        "target_id": target_id,
        "arguments": arguments,
        "payload_hash": digest,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_epoch": now_epoch,
        "expires_at": now_epoch + CONFIRMATION_EXPIRY_SECONDS,
        "status": "PENDING",
    }
    session.pending_confirmation = conf
    session.state = TreatmentWorkflowState.AWAITING_CONFIRMATION
    return conf


def verify_confirmation_integrity(
    session: TreatmentSession,
    action: str,
    target_id: Any,
    current_args: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """
    Verify single-use token validity, actor binding, expiry, and payload HMAC-SHA256 digest.
    """
    conf = session.pending_confirmation
    if not conf:
        return False, "No active confirmation token found for this session."

    status = conf.get("status")
    if status == "EXECUTED":
        return False, "This confirmation token has already been executed and cannot be reused (replay rejected)."

    if status == "EXECUTING":
        return False, "This confirmation token is currently being processed by another worker/request (concurrent execution blocked)."

    if status == "CANCELLED":
        return False, "This confirmation token was cancelled by the user."

    # Expiry verification (15 minutes window)
    expires_at = conf.get("expires_at")
    if expires_at and time.time() > float(expires_at):
        return False, "This confirmation token has expired (exceeded 15-minute window). Please request a fresh preview."

    # Actor identity verification
    if str(conf.get("actor_id")) != str(session.user_id):
        return False, f"Confirmation actor mismatch: Token belongs to user '{conf.get('actor_id')}', but acting user is '{session.user_id}'."

    # Actor role verification
    if conf.get("actor_role") and str(conf.get("actor_role")) != str(session.user_role):
        return False, f"Confirmation role mismatch: Token was bound to role '{conf.get('actor_role')}', but current role is '{session.user_role}'."

    # Action verification
    conf_action = normalize_action_name(conf.get("action", ""))
    curr_action = normalize_action_name(action)
    if conf_action != curr_action:
        return False, f"Action mismatch: Token is bound to '{conf.get('action')}', but current action is '{action}'."

    # Target resource verification
    if conf.get("target_id") and str(conf.get("target_id")) != str(target_id):
        return False, f"Target mismatch: Token is bound to target '{conf.get('target_id')}', but current target is '{target_id}'."

    # Cryptographic anti-tamper verification using HMAC-SHA256
    expected_hash = compute_confirmation_digest(
        actor_id=str(session.user_id),
        actor_role=session.user_role,
        action=action,
        target_id=target_id,
        arguments=current_args,
    )
    if not hmac.compare_digest(str(conf.get("payload_hash", "")), expected_hash):
        return False, "Confirmation payload tampered or mismatched: Action arguments have changed since preview generation."

    return True, None


def execute_confirmed_treatment_decision(
    session: TreatmentSession,
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Safely execute a confirmed treatment mutation through authoritative backend services.
    Includes pre-execution state revalidation, execution, and state reconciliation.
    """
    goal = session.goal
    target_id = session.target_risk_id if goal == TreatmentGoal.ADD_TREATMENT else session.treatment_id
    action_name = goal.value if isinstance(goal, TreatmentGoal) else str(goal)

    current_args = {}
    if goal == TreatmentGoal.ADD_TREATMENT:
        current_args = {
            "risk_register_id": session.target_risk_register_id,
            "action_plan": session.action_plan,
            "action_owner_id": session.action_owner_id,
            "target_date": session.target_date,
            "progress": session.progress,
            "action_status_id": session.action_status_id,
        }
    elif goal == TreatmentGoal.UPDATE_PROGRESS:
        current_args = {
            "treatment_id": session.treatment_id,
            "progress": session.progress,
            "remarks": session.remarks,
        }
    elif goal == TreatmentGoal.REASSIGN_OWNER:
        current_args = {
            "treatment_id": session.treatment_id,
            "new_action_owner_id": session.new_action_owner_id,
        }

    # 1. Anti-Tamper & Replay Verification
    is_valid_token, token_err = verify_confirmation_integrity(
        session=session,
        action=action_name,
        target_id=target_id,
        current_args=current_args,
    )
    if not is_valid_token:
        logger.warning(f"Confirmation rejected for session {session.session_id}: {token_err}")
        return False, None, token_err

    # Atomic lock: Transition status to EXECUTING to block race conditions & concurrent requests
    session.pending_confirmation["status"] = "EXECUTING"
    session.pending_confirmation["executing_at"] = datetime.now(timezone.utc).isoformat()

    # 2. Pre-Execution Fresh State Revalidation
    if goal == TreatmentGoal.ADD_TREATMENT:
        fresh_risk = fetch_risk_info(session, session.target_risk_id or str(session.target_risk_register_id))
        if not fresh_risk:
            session.pending_confirmation["status"] = "FAILED"
            return False, None, f"Pre-execution revalidation failed: Target risk '{session.target_risk_id}' was not found in the Enterprise Risk Register."
        if fresh_risk.get("is_deleted") == 1:
            session.pending_confirmation["status"] = "FAILED"
            return False, None, f"Pre-execution revalidation failed: Risk '{session.target_risk_id}' has been deleted."

    elif goal in (TreatmentGoal.UPDATE_PROGRESS, TreatmentGoal.REASSIGN_OWNER):
        fresh_treatment = fetch_treatment_details(session, int(session.treatment_id))
        if not fresh_treatment:
            session.pending_confirmation["status"] = "FAILED"
            return False, None, f"Pre-execution revalidation failed: Treatment #{session.treatment_id} was not found."

    # 3. Governed Mutation Execution with Error Catching & State Reconciliation
    result_dict: Optional[Dict[str, Any]] = None
    try:
        created_by_int = int(session.user_id) if str(session.user_id).isdigit() else 1

        if goal == TreatmentGoal.ADD_TREATMENT:
            result_dict = add_risk_treatment_tool(
                risk_register_id=int(session.target_risk_register_id),
                action_plan=session.action_plan,
                action_owner_id=int(session.action_owner_id),
                target_date=session.target_date,
                progress=int(session.progress),
                action_status_id=int(session.action_status_id),
                created_by=created_by_int,
            )

        elif goal == TreatmentGoal.UPDATE_PROGRESS:
            result_dict = update_treatment_progress_tool(
                treatment_id=int(session.treatment_id),
                progress=int(session.progress),
                modified_by=created_by_int,
                remarks=session.remarks,
            )

        elif goal == TreatmentGoal.REASSIGN_OWNER:
            result_dict = reassign_treatment_owner_tool(
                treatment_id=int(session.treatment_id),
                new_action_owner_id=int(session.new_action_owner_id),
                modified_by=created_by_int,
            )

    except Exception as exec_err:
        logger.error(f"Error during treatment mutation execution: {exec_err}. Reconciling with authoritative state...")

        # Authoritative State Reconciliation after uncertain outcome/timeout
        if goal == TreatmentGoal.UPDATE_PROGRESS and session.treatment_id:
            recheck = fetch_treatment_details(session, int(session.treatment_id))
            if recheck and int(recheck.get("progress", -1)) == int(session.progress):
                logger.info(f"State reconciliation confirmed treatment #{session.treatment_id} progress updated to {session.progress}% despite error.")
                result_dict = {
                    "status": "success",
                    "risk_treatment_id": session.treatment_id,
                    "progress": session.progress,
                    "reconciled": True,
                }
            else:
                return False, None, f"Mutation failed or timed out uncommitted: {exec_err}"

        elif goal == TreatmentGoal.REASSIGN_OWNER and session.treatment_id:
            recheck = fetch_treatment_details(session, int(session.treatment_id))
            if recheck and int(recheck.get("action_owner_id", -1)) == int(session.new_action_owner_id):
                logger.info(f"State reconciliation confirmed treatment #{session.treatment_id} reassigned to {session.new_action_owner_id} despite error.")
                result_dict = {
                    "status": "success",
                    "risk_treatment_id": session.treatment_id,
                    "action_owner_id": session.new_action_owner_id,
                    "reconciled": True,
                }
            else:
                return False, None, f"Reassignment failed or timed out uncommitted: {exec_err}"
        else:
            return False, None, f"Execution failed: {exec_err}"

    if not result_dict or result_dict.get("status") == "error":
        err_msg = (result_dict or {}).get("message", "Database service returned an error status.")
        return False, None, err_msg

    # 4. Mark Confirmation Token Executed
    session.pending_confirmation["status"] = "EXECUTED"
    session.pending_confirmation["executed_at"] = datetime.now(timezone.utc).isoformat()

    return True, result_dict, None


# Aliases for compatibility
generate_confirmation_token = bind_pending_confirmation
verify_confirmation_token = verify_confirmation_integrity

