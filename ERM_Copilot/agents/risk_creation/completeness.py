"""
Deterministic Risk Completeness Assessment Module.
Evaluates the current risk draft against authoritative backend creation requirements,
categorizing present, missing, invalid, and system-derived attributes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ERM_Copilot.agents.risk_creation.requirements import RiskCreationRequirements, get_risk_creation_requirements
from ERM_Copilot.agents.risk_creation.state import RiskCreationSession


class RiskCompletenessAssessment(BaseModel):
    """
    Structured outcome of the completeness and validity evaluation.
    Enforces deterministic compliance with backend database rules.
    """
    is_ready_for_review: bool = False
    present_valid_fields: List[str] = Field(default_factory=list)
    missing_required_fields: List[str] = Field(default_factory=list)
    missing_optional_fields: List[str] = Field(default_factory=list)
    invalid_fields: Dict[str, str] = Field(default_factory=dict)
    ambiguous_fields: List[str] = Field(default_factory=list)
    system_derived_fields: List[str] = Field(default_factory=list)
    summary_message: str = ""

    @property
    def has_errors(self) -> bool:
        return len(self.invalid_fields) > 0

    @property
    def is_complete(self) -> bool:
        return len(self.missing_required_fields) == 0 and not self.has_errors


def assess_risk_completeness(
    draft: RiskCreationSession,
    requirements: Optional[RiskCreationRequirements] = None
) -> RiskCompletenessAssessment:
    """
    Deterministically assess whether a risk creation draft has satisfied all backend
    creation requirements and constraints.
    """
    if requirements is None:
        requirements = get_risk_creation_requirements(dept_id=draft.dept_id)

    assessment = RiskCompletenessAssessment()

    # 1. System Derived Fields Check
    if draft.inherent_score is not None:
        assessment.system_derived_fields.append("inherent_score")
    if draft.inherent_level is not None:
        assessment.system_derived_fields.append("inherent_level")
    if draft.current_score is not None:
        assessment.system_derived_fields.append("current_score")
    if draft.current_level is not None:
        assessment.system_derived_fields.append("current_level")

    # 2. Server Context Fields Check
    if not draft.user_id:
        assessment.missing_required_fields.append("user_id")
        assessment.invalid_fields["user_id"] = "Authenticated user identity is required."
    else:
        assessment.present_valid_fields.append("user_id")

    if not draft.dept_id:
        assessment.missing_required_fields.append("dept_id")
        assessment.invalid_fields["dept_id"] = "Department identity could not be resolved from user context."
    else:
        assessment.present_valid_fields.append("dept_id")

    # 3. Required User Fields Check
    field_values: Dict[str, Any] = {
        "risk_name": draft.risk_name,
        "risk_description": draft.risk_description,
        "inherent_likelihood": draft.inherent_likelihood,
        "inherent_impact": draft.inherent_impact,
        "mitigation": draft.mitigation,
        "current_likelihood": draft.current_likelihood,
        "current_impact": draft.current_impact,
        "action_plan": draft.action_plan,
    }

    for fname in requirements.required_user_fields:
        val = field_values.get(fname)
        if val is None or (isinstance(val, str) and not val.strip()):
            assessment.missing_required_fields.append(fname)
        else:
            is_valid, err_msg = requirements.validate_field(fname, val)
            if is_valid:
                assessment.present_valid_fields.append(fname)
            else:
                assessment.invalid_fields[fname] = err_msg or f"Invalid value for {fname}"

    # 4. Optional Fields Check
    optional_values: Dict[str, Any] = {
        "risk_co_owner_id": draft.risk_co_owner_id,
        "action_owner_id": draft.action_owner_id,
        "target_date": draft.target_date,
        "status_id": draft.status_id,
        "progress": draft.progress,
        "financial_year": draft.financial_year,
    }

    for opt_name in requirements.optional_fields:
        opt_val = optional_values.get(opt_name)
        if opt_val is None or (isinstance(opt_val, str) and not opt_val.strip()):
            assessment.missing_optional_fields.append(opt_name)
        else:
            is_valid, err_msg = requirements.validate_field(opt_name, opt_val)
            if is_valid:
                assessment.present_valid_fields.append(opt_name)
            else:
                assessment.invalid_fields[opt_name] = err_msg or f"Invalid optional value for {opt_name}"

    # 5. Assessment readiness
    assessment.is_ready_for_review = (
        len(assessment.missing_required_fields) == 0
        and len(assessment.invalid_fields) == 0
    )

    if assessment.is_ready_for_review:
        assessment.summary_message = "All required fields are present and valid. Ready for confirmation review."
    elif len(assessment.invalid_fields) > 0:
        err_keys = list(assessment.invalid_fields.keys())
        assessment.summary_message = f"Validation errors found in: {', '.join(err_keys)}."
    else:
        missing_keys = [f.replace('_', ' ').title() for f in assessment.missing_required_fields]
        assessment.summary_message = f"Missing required fields: {', '.join(missing_keys)}."

    return assessment
