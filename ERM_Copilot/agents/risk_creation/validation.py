"""
Authoritative Deterministic Risk Validation Module for ERM Copilot.
Validates risk creation drafts against backend schemas, enterprise governance constraints,
server-side security contexts, and authoritative 5x5 ERM risk matrix rules.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from ERM_Copilot.agents.risk_creation.requirements import (
    RiskCreationRequirements,
    get_risk_creation_requirements,
)
from ERM_Copilot.agents.risk_creation.scoring import RiskMatrixCalculator
from ERM_Copilot.agents.risk_creation.state import RiskCreationSession

logger = logging.getLogger("ERM_Copilot.agents.risk_creation.validation")


class RiskValidationResult(BaseModel):
    """
    Deterministic validation result for an Enterprise Risk draft.
    Explicitly distinguishes missing fields from invalid fields,
    contains authoritative scores, and enforces review eligibility.
    """
    is_valid: bool = False
    is_ready_for_review: bool = False
    errors: Dict[str, str] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    missing_required_fields: List[str] = Field(default_factory=list)
    missing_optional_fields: List[str] = Field(default_factory=list)
    present_valid_fields: List[str] = Field(default_factory=list)
    normalized_values: Dict[str, Any] = Field(default_factory=dict)
    calculated_scores: Dict[str, Any] = Field(default_factory=dict)
    summary_message: str = ""

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_missing(self) -> bool:
        return len(self.missing_required_fields) > 0


def validate_risk_draft(
    draft: RiskCreationSession,
    server_context: Optional[Dict[str, Any]] = None,
    requirements: Optional[RiskCreationRequirements] = None,
) -> RiskValidationResult:
    """
    Deterministically validate a risk creation draft using authoritative rules and server context.
    
    Invariants:
    1. Authenticated user_id and dept_id from server_context are authoritative and cannot be overridden by conversational input.
    2. Missing fields are strictly distinguished from invalid fields.
    3. Ratings (1-5) must be valid integers; out-of-range values produce explicit validation errors and are never clamped.
    4. Authoritative risk scores and levels are computed exclusively through RiskMatrixCalculator.
    5. Pure function: zero database writes.
    """
    server_ctx = server_context or {}
    reqs = requirements or get_risk_creation_requirements(dept_id=draft.dept_id)

    res = RiskValidationResult()

    # 1. Enforce Trusted Server-Side Context
    auth_user_id = server_ctx.get("user_id") or draft.user_id
    auth_dept_id = server_ctx.get("dept_id") or draft.dept_id
    auth_dept_name = server_ctx.get("dept_name") or draft.dept_name

    if not auth_user_id:
        res.missing_required_fields.append("user_id")
        res.errors["user_id"] = "Authenticated User ID is required from server context."
    else:
        # Support both numeric user ID and log_id/string identity
        res.normalized_values["user_id"] = auth_user_id
        res.present_valid_fields.append("user_id")

    if not auth_dept_id:
        res.missing_required_fields.append("dept_id")
        res.errors["dept_id"] = "Department ID could not be resolved from authenticated user context."
    else:
        try:
            dept_int = int(auth_dept_id)
            if dept_int < 1:
                res.errors["dept_id"] = f"Invalid Department ID: {auth_dept_id}."
            else:
                res.normalized_values["dept_id"] = dept_int
                res.normalized_values["dept_name"] = str(auth_dept_name or "General").strip()
                res.present_valid_fields.append("dept_id")
        except (ValueError, TypeError):
            res.errors["dept_id"] = f"Department ID must be a valid integer (got '{auth_dept_id}')."

    # 2. Validate Required Text Fields
    # 2a. Risk Name / Title
    if draft.risk_name is None:
        res.missing_required_fields.append("risk_name")
    else:
        cleaned_name = str(draft.risk_name).strip()
        if not cleaned_name:
            res.errors["risk_name"] = "Risk Name / Title cannot be empty or whitespace only."
        elif len(cleaned_name) < 3:
            res.errors["risk_name"] = f"Risk Name / Title must be at least 3 characters (got {len(cleaned_name)})."
        elif len(cleaned_name) > 250:
            res.errors["risk_name"] = f"Risk Name / Title cannot exceed 250 characters (got {len(cleaned_name)})."
        else:
            res.normalized_values["risk_name"] = cleaned_name
            res.present_valid_fields.append("risk_name")

    # 2b. Risk Description
    if draft.risk_description is None:
        res.missing_required_fields.append("risk_description")
    else:
        cleaned_desc = str(draft.risk_description).strip()
        if not cleaned_desc:
            res.errors["risk_description"] = "Risk Description cannot be empty or whitespace only."
        elif len(cleaned_desc) < 5:
            res.errors["risk_description"] = f"Risk Description must be at least 5 characters (got {len(cleaned_desc)})."
        else:
            res.normalized_values["risk_description"] = cleaned_desc
            res.present_valid_fields.append("risk_description")

    # 2c. Mitigation Strategy
    if draft.mitigation is None:
        res.missing_required_fields.append("mitigation")
    else:
        cleaned_mit = str(draft.mitigation).strip()
        if not cleaned_mit:
            res.errors["mitigation"] = "Mitigation Strategy cannot be empty or whitespace only."
        elif len(cleaned_mit) < 5:
            res.errors["mitigation"] = f"Mitigation Strategy must be at least 5 characters (got {len(cleaned_mit)})."
        else:
            res.normalized_values["mitigation"] = cleaned_mit
            res.present_valid_fields.append("mitigation")

    # 2d. Action Plan
    if draft.action_plan is None:
        res.missing_required_fields.append("action_plan")
    else:
        cleaned_act = str(draft.action_plan).strip()
        if not cleaned_act:
            res.errors["action_plan"] = "Action Plan cannot be empty or whitespace only."
        elif len(cleaned_act) < 5:
            res.errors["action_plan"] = f"Action Plan must be at least 5 characters (got {len(cleaned_act)})."
        else:
            res.normalized_values["action_plan"] = cleaned_act
            res.present_valid_fields.append("action_plan")

    # 3. Validate Rating Values (1-5) and Recalculate Authoritative Scores
    # 3a. Inherent Likelihood & Impact
    inh_l_valid = False
    inh_i_valid = False

    if draft.inherent_likelihood is None:
        res.missing_required_fields.append("inherent_likelihood")
    else:
        ok, err = RiskMatrixCalculator.validate_rating(draft.inherent_likelihood, "Inherent Likelihood")
        if ok:
            inh_l_valid = True
            res.normalized_values["inherent_likelihood"] = int(draft.inherent_likelihood)
            res.present_valid_fields.append("inherent_likelihood")
        else:
            res.errors["inherent_likelihood"] = err

    if draft.inherent_impact is None:
        res.missing_required_fields.append("inherent_impact")
    else:
        ok, err = RiskMatrixCalculator.validate_rating(draft.inherent_impact, "Inherent Impact")
        if ok:
            inh_i_valid = True
            res.normalized_values["inherent_impact"] = int(draft.inherent_impact)
            res.present_valid_fields.append("inherent_impact")
        else:
            res.errors["inherent_impact"] = err

    if inh_l_valid and inh_i_valid:
        score, level, badge = RiskMatrixCalculator.calculate_score(
            res.normalized_values["inherent_likelihood"],
            res.normalized_values["inherent_impact"],
            strict=True
        )
        res.calculated_scores["inherent_score"] = score
        res.calculated_scores["inherent_level"] = level
        res.calculated_scores["inherent_badge"] = badge
        draft.inherent_score = score
        draft.inherent_level = level
        draft.inherent_badge = badge
    else:
        res.calculated_scores["inherent_score"] = None
        res.calculated_scores["inherent_level"] = None
        res.calculated_scores["inherent_badge"] = None
        draft.inherent_score = None
        draft.inherent_level = None
        draft.inherent_badge = None

    # 3b. Current Likelihood & Impact
    cur_l_valid = False
    cur_i_valid = False

    if draft.current_likelihood is None:
        res.missing_required_fields.append("current_likelihood")
    else:
        ok, err = RiskMatrixCalculator.validate_rating(draft.current_likelihood, "Current Likelihood")
        if ok:
            cur_l_valid = True
            res.normalized_values["current_likelihood"] = int(draft.current_likelihood)
            res.present_valid_fields.append("current_likelihood")
        else:
            res.errors["current_likelihood"] = err

    if draft.current_impact is None:
        res.missing_required_fields.append("current_impact")
    else:
        ok, err = RiskMatrixCalculator.validate_rating(draft.current_impact, "Current Impact")
        if ok:
            cur_i_valid = True
            res.normalized_values["current_impact"] = int(draft.current_impact)
            res.present_valid_fields.append("current_impact")
        else:
            res.errors["current_impact"] = err

    if cur_l_valid and cur_i_valid:
        score, level, badge = RiskMatrixCalculator.calculate_score(
            res.normalized_values["current_likelihood"],
            res.normalized_values["current_impact"],
            strict=True
        )
        res.calculated_scores["current_score"] = score
        res.calculated_scores["current_level"] = level
        res.calculated_scores["current_badge"] = badge
        draft.current_score = score
        draft.current_level = level
        draft.current_badge = badge
    else:
        res.calculated_scores["current_score"] = None
        res.calculated_scores["current_level"] = None
        res.calculated_scores["current_badge"] = None
        draft.current_score = None
        draft.current_level = None
        draft.current_badge = None

    # 4. Validate Optional Fields & Defaults
    # 4a. Action Owner
    if draft.action_owner_id:
        try:
            ao_id = int(draft.action_owner_id)
            if ao_id < 1:
                res.errors["action_owner_id"] = f"Invalid Action Owner ID: {draft.action_owner_id}."
            else:
                res.normalized_values["action_owner_id"] = ao_id
                res.present_valid_fields.append("action_owner_id")
        except (ValueError, TypeError):
            res.errors["action_owner_id"] = f"Action Owner ID must be an integer (got '{draft.action_owner_id}')."
    else:
        res.missing_optional_fields.append("action_owner_id")
        default_ao = res.normalized_values.get("user_id")
        res.normalized_values["action_owner_id"] = default_ao
        res.warnings.append("Action Owner was not assigned; default set to Risk Owner.")

    # 4b. Co-Owner
    if draft.risk_co_owner_id:
        try:
            co_id = int(draft.risk_co_owner_id)
            if co_id < 1:
                res.errors["risk_co_owner_id"] = f"Invalid Co-Owner ID: {draft.risk_co_owner_id}."
            else:
                res.normalized_values["risk_co_owner_id"] = co_id
                res.present_valid_fields.append("risk_co_owner_id")
        except (ValueError, TypeError):
            res.errors["risk_co_owner_id"] = f"Co-Owner ID must be an integer (got '{draft.risk_co_owner_id}')."
    else:
        res.missing_optional_fields.append("risk_co_owner_id")
        res.normalized_values["risk_co_owner_id"] = None

    # 4c. Target Date
    if draft.target_date:
        cleaned_td = str(draft.target_date).strip()
        try:
            dt = datetime.strptime(cleaned_td, "%Y-%m-%d")
            res.normalized_values["target_date"] = dt.strftime("%Y-%m-%d")
            res.present_valid_fields.append("target_date")
        except ValueError:
            res.errors["target_date"] = f"Target date must be a valid ISO date in YYYY-MM-DD format (got '{draft.target_date}')."
    else:
        res.missing_optional_fields.append("target_date")
        res.warnings.append("Target Date was not explicitly set; defaulting to +30 days.")

    # 4d. Progress
    if draft.progress is not None:
        try:
            prog_val = int(draft.progress)
            if not (0 <= prog_val <= 100):
                res.errors["progress"] = f"Progress percentage must be between 0 and 100 (got {prog_val})."
            else:
                res.normalized_values["progress"] = prog_val
                res.present_valid_fields.append("progress")
        except (ValueError, TypeError):
            res.errors["progress"] = f"Progress must be a whole integer percentage (got '{draft.progress}')."
    else:
        res.normalized_values["progress"] = 0

    # 4e. Status & Financial Year
    res.normalized_values["status_id"] = int(draft.status_id or 1)
    res.normalized_values["status_name"] = str(draft.status_name or "Draft").strip()
    res.normalized_values["financial_year"] = str(draft.financial_year or "2026-2027").strip()

    # 5. Review and Persistence Eligibility
    res.is_valid = len(res.errors) == 0
    res.is_ready_for_review = (
        res.is_valid
        and len(res.missing_required_fields) == 0
        and inh_l_valid
        and inh_i_valid
        and cur_l_valid
        and cur_i_valid
    )

    if res.is_ready_for_review:
        res.summary_message = "All required fields and ratings are valid. Draft is ready for user preview and confirmation."
    elif res.has_errors:
        err_list = [f"{k}: {v}" for k, v in res.errors.items()]
        res.summary_message = f"Validation failed with {len(res.errors)} error(s): {'; '.join(err_list)}"
    else:
        missing_titles = [m.replace('_', ' ').title() for m in res.missing_required_fields]
        res.summary_message = f"Draft is incomplete. Missing required field(s): {', '.join(missing_titles)}"

    return res
