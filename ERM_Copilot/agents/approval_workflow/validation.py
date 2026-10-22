"""
Validation and Precondition Enforcement for Approval Workflows.
Implements strict server-side business rules, stage sequence checks,
department isolation, and role authorization.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from ERM_Copilot.ai_harness.policies import (
    APPROVER_ROLES,
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_RISK_MANAGER,
    ROLE_RISK_HEADER,
    is_role_authorized_for_tool,
    normalize_role,
)

logger = logging.getLogger("ERM_Copilot.agents.approval_workflow.validation")


@dataclass
class ApprovalValidationResult:
    """Outcome of validating an approval/rejection request against authoritative state."""
    is_valid: bool
    policy_block_reason: Optional[str] = None
    approval_level: Optional[int] = None
    stage_name: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


def resolve_role_tier(role_name: str) -> Optional[int]:
    """
    Map user role to approval governance level:
    1: Functional Head (FH)
    2: Risk Manager (RM)
    3: Risk Head (RH) / Executive
    4: Admin / Super Admin (can act at any active stage)
    None: Unauthorized
    """
    norm = normalize_role(role_name).lower()
    if any(k in norm for k in ["function", "dept head", "fh"]):
        return 1
    elif any(k in norm for k in ["manager", "rm"]):
        return 2
    elif any(k in norm for k in ["head", "rh", "cro", "chief risk", "executive", "ceo"]):
        return 3
    elif any(k in norm for k in ["admin", "super admin"]):
        return 4
    return None


def validate_approval_preconditions(
    user_role: str,
    user_dept_id: Optional[int],
    risk_data: Dict[str, Any],
    action: str,
    remark: Optional[str] = None,
) -> ApprovalValidationResult:
    """
    Validate whether the authenticated user is authorized to approve or reject
    the specified risk at its current stage.
    """
    # 1. Role Authorization
    if not is_role_authorized_for_tool(user_role, APPROVER_ROLES):
        return ApprovalValidationResult(
            is_valid=False,
            policy_block_reason=(
                f"User role '{user_role}' is not authorized to approve or reject risks. "
                f"Governance sign-offs are restricted to Functional Head, Risk Manager, and Risk Head."
            )
        )

    tier = resolve_role_tier(user_role)
    if tier is None:
        return ApprovalValidationResult(
            is_valid=False,
            policy_block_reason=f"Role '{user_role}' cannot be mapped to an authorized governance approval tier."
        )

    # 2. Extract risk lifecycle state
    raw_status = risk_data.get("risk_status") or 0
    try:
        numeric_status = int(raw_status)
    except (ValueError, TypeError):
        numeric_status = 0

    curr_status_name = str(risk_data.get("current_status_name") or risk_data.get("status") or "").lower()

    fh_status = risk_data.get("risk_function_head_approval_status") or risk_data.get("fh_status")
    rm_status = risk_data.get("risk_manager_approval_status") or risk_data.get("rm_status")
    rh_status = risk_data.get("risk_head_approval_status") or risk_data.get("rh_status")

    fh_done = (fh_status == 1) or (numeric_status >= 3)
    rm_done = (rm_status == 1) or (numeric_status >= 4)
    rh_done = (rh_status == 1) or (numeric_status >= 5)

    risk_code = risk_data.get("risk_id") or "Risk"

    # 3. Check Draft & Rejection states
    if "draft" in curr_status_name or numeric_status == 1:
        return ApprovalValidationResult(
            is_valid=False,
            policy_block_reason=f"Risk '{risk_code}' is currently in Draft status and has not been submitted for review."
        )

    if (fh_status == -1 or rm_status == -1 or rh_status == -1 or
            numeric_status == 6 or "pending for action" in curr_status_name or "rejected" in curr_status_name):
        return ApprovalValidationResult(
            is_valid=False,
            policy_block_reason=(
                f"Risk '{risk_code}' has already been rejected/returned and must be modified "
                f"and resubmitted by the Risk Owner before review can continue."
            )
        )

    # 4. Check already fully approved
    if numeric_status == 5 or (fh_done and rm_done and rh_done):
        return ApprovalValidationResult(
            is_valid=False,
            policy_block_reason=f"Risk '{risk_code}' has already been fully approved at all governance stages."
        )

    # 5. Department Isolation for Functional Head (Fail Closed)
    risk_dept_id = risk_data.get("dept_id") or risk_data.get("department_id")
    is_enterprise_role = tier in (2, 3, 4)
    if tier == 1:
        if user_dept_id is None:
            return ApprovalValidationResult(
                is_valid=False,
                policy_block_reason=(
                    f"Department access restriction: Authenticated Functional Head user context is missing assigned department ID. "
                    f"Functional Head review must fail closed when department information is unavailable."
                )
            )
        if risk_dept_id is None:
            return ApprovalValidationResult(
                is_valid=False,
                policy_block_reason=(
                    f"Department access restriction: Risk '{risk_code}' is missing department association. "
                    f"Functional Head review requires verified department alignment."
                )
            )
        try:
            if int(user_dept_id) != int(risk_dept_id):
                return ApprovalValidationResult(
                    is_valid=False,
                    policy_block_reason=(
                        f"Department access restriction: Risk '{risk_code}' belongs to department ID {risk_dept_id}, "
                        f"which does not match your assigned department (ID {user_dept_id}). "
                        f"Functional Head review is restricted to risks within your own department."
                    )
                )
        except (ValueError, TypeError):
            return ApprovalValidationResult(
                is_valid=False,
                policy_block_reason="Department access restriction: Department identifier cannot be verified (invalid numeric format)."
            )

    # 6. Admin active stage determination
    effective_tier = tier
    if tier == 4:
        if not fh_done:
            effective_tier = 1
        elif not rm_done:
            effective_tier = 2
        elif not rh_done:
            effective_tier = 3
        else:
            return ApprovalValidationResult(
                is_valid=False,
                policy_block_reason=f"Risk '{risk_code}' has already been fully approved at all governance stages."
            )

    # 7. Strict Sequence Enforcement (FH -> RM -> RH)
    if effective_tier == 1:
        if fh_done:
            return ApprovalValidationResult(
                is_valid=False,
                policy_block_reason=f"Risk '{risk_code}' has already been approved by Functional Head."
            )
        stage_title = "Stage 1: Functional Head Approval"
    elif effective_tier == 2:
        if not fh_done:
            return ApprovalValidationResult(
                is_valid=False,
                policy_block_reason="This risk is not yet available for Risk Manager approval. Functional Head approval is still pending."
            )
        if rm_done:
            return ApprovalValidationResult(
                is_valid=False,
                policy_block_reason=f"Risk '{risk_code}' has already been approved by Risk Manager."
            )
        stage_title = "Stage 2: Risk Manager Validation"
    elif effective_tier == 3:
        if not fh_done:
            return ApprovalValidationResult(
                is_valid=False,
                policy_block_reason="This risk is not yet available for Risk Head approval. Functional Head approval is still pending."
            )
        if not rm_done:
            return ApprovalValidationResult(
                is_valid=False,
                policy_block_reason="This risk is not yet available for Risk Head approval. Risk Manager approval is still pending."
            )
        if rh_done:
            return ApprovalValidationResult(
                is_valid=False,
                policy_block_reason=f"Risk '{risk_code}' has already been approved by Risk Head (Final Approval complete)."
            )
        stage_title = "Stage 3: Risk Head Final Sign-Off"
    else:
        return ApprovalValidationResult(
            is_valid=False,
            policy_block_reason="Unable to determine valid approval stage."
        )

    # 8. Rejection remark validation
    if str(action).lower() == "reject":
        if not remark or not str(remark).strip():
            return ApprovalValidationResult(
                is_valid=False,
                policy_block_reason="A rejection reason/remark is mandatory when rejecting a risk."
            )

    return ApprovalValidationResult(
        is_valid=True,
        approval_level=effective_tier,
        stage_name=stage_title,
        details={
            "risk_id": risk_code,
            "stage_level": effective_tier,
            "stage_name": stage_title,
            "fh_done": fh_done,
            "rm_done": rm_done,
            "rh_done": rh_done,
        }
    )
