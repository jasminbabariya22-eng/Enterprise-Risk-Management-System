"""
Enterprise Risk Management (ERM) - Deterministic Validation & RBAC Policy Enforcement for Treatment Agent.
Enforces actor authorization, department isolation, resource existence, and field constraints.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from ERM_Copilot.agents.treatment.state import TreatmentGoal, TreatmentSession

# Roles permitted to create treatments and action plans
CREATOR_ROLES = {
    "risk owner", "ro", "functional head", "fh", "risk manager", "rm",
    "risk head", "rh", "cro", "admin", "super admin", "action owner", "ao"
}

# Enterprise-wide governance roles exempt from single-department restrictions
ENTERPRISE_ROLES = {
    "risk manager", "rm", "risk head", "rh", "cro", "admin", "super admin"
}

# Read-only audit roles strictly prohibited from mutating treatment data
READ_ONLY_ROLES = {"auditor", "viewer", "guest"}


@dataclass
class TreatmentValidationResult:
    """Structured validation and authorization verdict."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    policy_blocked: bool = False
    policy_block_reason: Optional[str] = None


def validate_treatment_action(
    session: TreatmentSession,
    risk_data: Optional[Dict[str, Any]] = None,
    treatment_data: Optional[Dict[str, Any]] = None,
    action_owner_data: Optional[Dict[str, Any]] = None,
) -> TreatmentValidationResult:
    """
    Validate caller authorization, department isolation, target existence, and business rules.
    """
    role = (session.user_role or "").strip().lower()
    user_id = str(session.user_id or "").strip()
    goal = session.goal
    errors: List[str] = []

    # 1. Authentication Check - Fail Closed
    if not user_id:
        return TreatmentValidationResult(
            is_valid=False,
            policy_blocked=True,
            policy_block_reason="Authentication Failure: No verified user ID detected.",
            errors=["User identity is required for treatment actions."],
        )

    if not role:
        return TreatmentValidationResult(
            is_valid=False,
            policy_blocked=True,
            policy_block_reason="Authorization Failure: No assigned user role detected.",
            errors=["A valid role is required for treatment management."],
        )

    # 2. State-Changing Authorization Checks
    if goal in (TreatmentGoal.ADD_TREATMENT, TreatmentGoal.UPDATE_PROGRESS, TreatmentGoal.REASSIGN_OWNER):
        # Disallow read-only roles
        if role in READ_ONLY_ROLES:
            return TreatmentValidationResult(
                is_valid=False,
                policy_blocked=True,
                policy_block_reason=f"Role '{session.user_role}' is not authorized to create or modify risk treatments.",
                errors=["Read-only audit roles cannot execute treatment mutations."],
            )

        if role not in CREATOR_ROLES:
            return TreatmentValidationResult(
                is_valid=False,
                policy_blocked=True,
                policy_block_reason=f"Role '{session.user_role}' lacks permission to perform treatment action '{goal.value}'.",
                errors=["Caller role is not permitted to mutate treatment records."],
            )

    # 3. Target Risk & Department Isolation Validation (for ADD_TREATMENT & LIST_TREATMENTS)
    if goal == TreatmentGoal.ADD_TREATMENT:
        if risk_data:
            risk_dept = risk_data.get("dept_id")
            # If not an enterprise role, caller department must match risk department
            if role not in ENTERPRISE_ROLES:
                if session.dept_id is None or risk_dept is None or int(session.dept_id) != int(risk_dept):
                    return TreatmentValidationResult(
                        is_valid=False,
                        policy_blocked=True,
                        policy_block_reason=(
                            f"Department Isolation: Risk '{risk_data.get('risk_id')}' belongs to department #{risk_dept}. "
                            f"Users in department #{session.dept_id} cannot attach treatment plans to external risks."
                        ),
                        errors=["Cross-department treatment attachment is blocked."],
                    )

        # Action Plan Text Validation
        if session.action_plan is not None:
            if len(session.action_plan.strip()) < 5:
                errors.append("Action plan description must contain at least 5 characters.")

        # Action Owner Validation
        if action_owner_data:
            owner_dept = action_owner_data.get("dept_id")
            risk_dept = risk_data.get("dept_id") if risk_data else session.dept_id
            if role not in ENTERPRISE_ROLES and risk_dept and owner_dept:
                if int(owner_dept) != int(risk_dept):
                    return TreatmentValidationResult(
                        is_valid=False,
                        policy_blocked=True,
                        policy_block_reason=(
                            f"Action Owner '{action_owner_data.get('full_name')}' belongs to department #{owner_dept}, "
                            f"which does not match the risk department #{risk_dept}."
                        ),
                        errors=["Action owners must belong to the department of the risk being treated."],
                    )

        # Target Date Validation
        if session.target_date:
            try:
                dt = datetime.strptime(session.target_date, "%Y-%m-%d").date()
                today = datetime.now(timezone.utc).date()
                if dt < today:
                    errors.append(f"Target date '{session.target_date}' cannot be in the past.")
            except ValueError:
                errors.append(f"Invalid target date format '{session.target_date}'. Expected YYYY-MM-DD.")

        # Progress Percentage Validation
        if session.progress is not None:
            if not (0 <= session.progress <= 100):
                errors.append(f"Progress percentage must be between 0 and 100. Received: {session.progress}%.")

    # 4. Target Treatment Validation (for UPDATE_PROGRESS & REASSIGN_OWNER)
    if goal in (TreatmentGoal.UPDATE_PROGRESS, TreatmentGoal.REASSIGN_OWNER):
        if treatment_data:
            treatment_dept = treatment_data.get("dept_id")
            if role not in ENTERPRISE_ROLES:
                if session.dept_id is not None and treatment_dept is not None and int(session.dept_id) != int(treatment_dept):
                    return TreatmentValidationResult(
                        is_valid=False,
                        policy_blocked=True,
                        policy_block_reason=(
                            f"Department Isolation: Treatment #{treatment_data.get('risk_treatment_id')} belongs to department #{treatment_dept}. "
                            f"You are authenticated in department #{session.dept_id}."
                        ),
                        errors=["Cross-department treatment modification is prohibited."],
                    )

        if goal == TreatmentGoal.UPDATE_PROGRESS:
            if session.progress is not None:
                if not (0 <= session.progress <= 100):
                    errors.append(f"Progress percentage must be between 0 and 100. Received: {session.progress}%.")

    is_valid = len(errors) == 0
    return TreatmentValidationResult(
        is_valid=is_valid,
        errors=errors,
        policy_blocked=not is_valid and len(errors) > 0 and any("blocked" in e.lower() or "prohibited" in e.lower() for e in errors),
        policy_block_reason=errors[0] if errors else None,
    )
