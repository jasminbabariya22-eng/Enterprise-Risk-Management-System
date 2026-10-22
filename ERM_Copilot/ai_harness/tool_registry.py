"""
Centralized Tool Registry for ERM AI Harness.
Declares, documents, schemas, and governs all tools executable by agents.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Type
from pydantic import BaseModel, Field, ValidationError, field_validator

from ERM_Copilot.ai_harness.exceptions import (
    AuthorizationError,
    ToolNotFoundError,
    ToolValidationError,
)
from ERM_Copilot.ai_harness.policies import (
    ALL_ROLES,
    APPROVER_ROLES,
    CREATOR_ROLES,
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_RISK_MANAGER,
    ROLE_RISK_HEADER,
    ToolCategory,
    is_role_authorized_for_tool,
    normalize_role,
)
from ERM_Copilot.services.db_service import erm_db

logger = logging.getLogger("ERM_Copilot.ai_harness.tool_registry")


class ReferenceDataInput(BaseModel):
    dataset: str = Field(default="all", description="Reference dataset: 'status', 'departments', 'assessment_criteria', or 'all'")
    dept_id: Optional[int] = Field(default=None, description="Optional department ID")

    @field_validator("dataset")
    @classmethod
    def validate_dataset(cls, v: str) -> str:
        cleaned = str(v).strip().lower()
        allowed = {"status", "departments", "assessment_criteria", "all"}
        if cleaned not in allowed:
            raise ValueError(f"Invalid dataset '{v}'. Allowed datasets: {sorted(list(allowed))}")
        return cleaned


class EligibleOwnersInput(BaseModel):
    owner_type: str = Field(..., description="Type of owner to lookup: 'action_owner' or 'co_owner'")
    search_term: Optional[str] = Field(default=None, description="Optional search term to filter candidates by name or role")
    dept_id: Optional[int] = Field(default=None, description="Optional department ID")

    @field_validator("owner_type")
    @classmethod
    def validate_owner_type(cls, v: str) -> str:
        cleaned = str(v).strip().lower()
        if cleaned not in ("action_owner", "co_owner"):
            raise ValueError(f"Invalid owner_type '{v}'. Must be either 'action_owner' or 'co_owner'")
        return cleaned


def _handle_resolve_reference_data(dataset: str = "all", dept_id: Optional[int] = None, **kw) -> Dict[str, Any]:
    dataset_normalized = str(dataset).strip().lower()
    dropdown_data = erm_db.get_dropdown_options(dept_id=dept_id)

    matrix_bands = [
        {"min_score": 15, "max_score": 25, "level": "CRITICAL", "badge": "[CRITICAL]"},
        {"min_score": 10, "max_score": 14, "level": "HIGH", "badge": "[HIGH]"},
        {"min_score": 5, "max_score": 9, "level": "MEDIUM", "badge": "[MEDIUM]"},
        {"min_score": 1, "max_score": 4, "level": "LOW", "badge": "[LOW]"}
    ]

    if dataset_normalized == "status":
        return {
            "status": "success",
            "dataset": "status",
            "data": dropdown_data.get("statuses", [])
        }
    elif dataset_normalized == "departments":
        return {
            "status": "success",
            "dataset": "departments",
            "data": dropdown_data.get("departments", [])
        }
    elif dataset_normalized == "assessment_criteria":
        return {
            "status": "success",
            "dataset": "assessment_criteria",
            "likelihood_scales": dropdown_data.get("likelihood_scales", []),
            "impact_scales": dropdown_data.get("impact_scales", []),
            "matrix_bands": matrix_bands,
        }
    else:  # "all"
        return {
            "status": "success",
            "dataset": "all",
            "departments": dropdown_data.get("departments", []),
            "statuses": dropdown_data.get("statuses", []),
            "likelihood_scales": dropdown_data.get("likelihood_scales", []),
            "impact_scales": dropdown_data.get("impact_scales", []),
            "matrix_bands": matrix_bands,
        }


def _handle_lookup_eligible_owners(
    owner_type: str,
    search_term: Optional[str] = None,
    dept_id: Optional[int] = None,
    caller_role: Optional[str] = None,
    caller_dept_id: Optional[int] = None,
    **kw
) -> Dict[str, Any]:
    normalized_type = str(owner_type).strip().lower()

    # Determine effective department ID:
    # Enterprise roles (Admin, Super Admin, Risk Manager, Risk Head) may query any department; standard users are strictly bound to caller_dept_id.
    is_cross_dept_permitted = normalize_role(caller_role or "") in (
        ROLE_ADMIN, ROLE_SUPER_ADMIN, ROLE_RISK_MANAGER, ROLE_RISK_HEADER
    )
    if is_cross_dept_permitted:
        effective_dept_id = dept_id if dept_id is not None else caller_dept_id
    else:
        # Prevent user-supplied dept_id manipulation for standard users; fail closed if missing
        if caller_dept_id is None and normalized_type == "action_owner":
            return {
                "status": "error",
                "owner_type": normalized_type,
                "dept_id": None,
                "count": 0,
                "owners": [],
                "guidance": "Cannot look up action owners without an authenticated department context.",
            }
        effective_dept_id = caller_dept_id

    if normalized_type == "action_owner":
        raw_candidates = erm_db.get_department_action_owners(dept_id=effective_dept_id)
    elif normalized_type == "co_owner":
        # Cross-department co-owner lookup permitted under governance
        raw_candidates = erm_db.get_all_users_for_co_owner(limit=50)
    else:
        raw_candidates = []

    # Optional search filtering across name or role
    filtered = raw_candidates
    if search_term and str(search_term).strip():
        term = str(search_term).strip().lower()
        filtered = [
            c for c in raw_candidates
            if term in str(c.get("full_name") or "").lower()
            or term in str(c.get("log_id") or "").lower()
            or term in str(c.get("role_name") or "").lower()
        ]

    # Sanitize and omit sensitive personal data (email)
    sanitized_owners = [
        {
            "user_id": c.get("user_id"),
            "log_id": c.get("log_id"),
            "full_name": c.get("full_name"),
            "dept_id": c.get("dept_id"),
            "dept_name": c.get("dept_name"),
            "role_name": c.get("role_name"),
        }
        for c in filtered
    ]

    guidance = (
        f"Found {len(sanitized_owners)} eligible {normalized_type}(s). Select one to assign."
        if sanitized_owners else
        f"No eligible {normalized_type} found matching search criteria. Verify spelling or department assignment."
    )

    return {
        "status": "success",
        "owner_type": normalized_type,
        "dept_id": effective_dept_id if normalized_type == "action_owner" else None,
        "count": len(sanitized_owners),
        "owners": sanitized_owners,
        "guidance": guidance,
    }


class MitigationSuggestionsInput(BaseModel):
    risk_title: str = Field(..., min_length=3, description="Risk title or hazard description, min 3 characters")
    risk_description: Optional[str] = Field(default=None, description="Optional risk description for added context")
    hazard_category: Optional[str] = Field(default=None, description="Optional hazard category")
    include_historical: bool = Field(default=True, description="Whether to retrieve authorized historical department treatments")
    dept_id: Optional[int] = Field(default=None, description="Department ID constraint")

    @field_validator("risk_title")
    @classmethod
    def validate_risk_title(cls, v: str) -> str:
        cleaned = str(v).strip()
        if len(cleaned) < 3:
            raise ValueError("Argument 'risk_title' must be at least 3 characters long.")
        return cleaned


class ActionPlanSuggestionsInput(BaseModel):
    risk_title: str = Field(..., min_length=3, description="Risk title or hazard description, min 3 characters")
    mitigation_strategy: Optional[str] = Field(default=None, description="Accepted mitigation strategy context")
    risk_description: Optional[str] = Field(default=None, description="Optional risk description")
    dept_id: Optional[int] = Field(default=None, description="Department ID constraint")

    @field_validator("risk_title")
    @classmethod
    def validate_risk_title(cls, v: str) -> str:
        cleaned = str(v).strip()
        if len(cleaned) < 3:
            raise ValueError("Argument 'risk_title' must be at least 3 characters long.")
        return cleaned


def _handle_get_mitigation_suggestions(
    risk_title: str,
    risk_description: Optional[str] = None,
    hazard_category: Optional[str] = None,
    include_historical: bool = True,
    caller_role: Optional[str] = None,
    caller_dept_id: Optional[int] = None,
    dept_id: Optional[int] = None,
    **kw
) -> Dict[str, Any]:
    from ERM_Copilot.agents.risk_creation.suggestions import static_suggestion_provider

    try:
        curated = static_suggestion_provider.get_mitigation_suggestions(
            title=risk_title,
            category=hazard_category
        )
    except Exception as e:
        logger.error(f"Error generating curated mitigation suggestions: {e}", exc_info=True)
        return {
            "status": "error",
            "risk_title": risk_title,
            "suggestions": [],
            "source": "none",
            "message": f"Failed to retrieve mitigation suggestions: {str(e)}",
            "warnings": ["Suggestion provider unavailable. Please enter custom mitigation manually."]
        }

    historical_evidence: List[Dict[str, Any]] = []
    if include_historical:
        try:
            is_admin = caller_role in (ROLE_ADMIN, ROLE_SUPER_ADMIN, "Admin", "Super Admin")
            if not is_admin and caller_dept_id is None:
                effective_dept = None
            else:
                effective_dept = dept_id if (is_admin and dept_id is not None) else caller_dept_id
            
            if is_admin or effective_dept is not None:
                raw_hist = erm_db.get_historical_treatments(
                    keyword=risk_title,
                    dept_id=effective_dept,
                    limit=3
                )
                for h in raw_hist:
                    plan = h.get("action_plan")
                    if plan and str(plan).strip():
                        historical_evidence.append({
                            "risk_name": h.get("risk_name") or "Historical Risk",
                            "historical_action": plan.strip(),
                            "status": h.get("status", "Completed")
                        })
        except Exception as e:
            logger.warning(f"Historical treatment lookup failed (continuing with curated): {e}")

    source = "hybrid" if historical_evidence else "curated"
    msg = (
        f"Generated {len(curated)} curated mitigation recommendation(s)"
        + (f" with {len(historical_evidence)} historical treatment record(s)." if historical_evidence else ".")
    )

    return {
        "status": "success",
        "risk_title": risk_title,
        "suggestions": curated,
        "source": source,
        "historical_evidence": historical_evidence,
        "message": msg,
        "warnings": [] if curated else ["No curated suggestions available for this category."]
    }


def _handle_get_action_plan_suggestions(
    risk_title: str,
    mitigation_strategy: Optional[str] = None,
    risk_description: Optional[str] = None,
    caller_role: Optional[str] = None,
    caller_dept_id: Optional[int] = None,
    dept_id: Optional[int] = None,
    **kw
) -> Dict[str, Any]:
    from ERM_Copilot.agents.risk_creation.suggestions import static_suggestion_provider

    try:
        curated_plans = static_suggestion_provider.get_action_plan_suggestions(
            title=risk_title,
            mitigation=mitigation_strategy
        )
    except Exception as e:
        logger.error(f"Error generating action plan suggestions: {e}", exc_info=True)
        return {
            "status": "error",
            "risk_title": risk_title,
            "suggestions": [],
            "source": "none",
            "message": f"Failed to retrieve action plan suggestions: {str(e)}",
            "warnings": ["Suggestion provider unavailable. Please enter action plan manually."]
        }

    return {
        "status": "success",
        "risk_title": risk_title,
        "mitigation_context": mitigation_strategy,
        "suggestions": curated_plans,
        "source": "curated",
        "message": f"Generated {len(curated_plans)} actionable implementation steps corresponding to proposed mitigation.",
        "warnings": [] if curated_plans else ["No action plan suggestions available."]
    }


class DuplicateRiskCheckInput(BaseModel):
    risk_title: str = Field(..., min_length=3, description="Risk title or hazard description to check, min 3 characters")
    risk_description: Optional[str] = Field(default=None, description="Optional draft description for context")
    dept_id: Optional[int] = Field(default=None, description="Department ID constraint")
    limit: int = Field(default=5, ge=1, le=10, description="Max duplicate candidates to return (1-10)")

    @field_validator("risk_title")
    @classmethod
    def validate_risk_title(cls, v: str) -> str:
        cleaned = str(v).strip()
        if len(cleaned) < 3:
            raise ValueError("Argument 'risk_title' must be at least 3 characters long.")
        return cleaned


def _handle_detect_duplicate_risks(
    risk_title: str,
    risk_description: Optional[str] = None,
    caller_role: Optional[str] = None,
    caller_dept_id: Optional[int] = None,
    dept_id: Optional[int] = None,
    limit: int = 5,
    **kw
) -> Dict[str, Any]:
    cross_dept_roles = (
        ROLE_ADMIN, ROLE_SUPER_ADMIN, ROLE_RISK_MANAGER, ROLE_RISK_HEADER,
        "Admin", "Super Admin", "Risk Manager", "Risk Header", "Risk Head"
    )
    is_cross_dept_permitted = caller_role in cross_dept_roles

    if is_cross_dept_permitted:
        effective_dept = dept_id if dept_id is not None else caller_dept_id
    else:
        if caller_dept_id is None:
            return {
                "status": "error",
                "checked_risk_title": risk_title,
                "candidate_count": 0,
                "candidates": [],
                "is_duplicate_suspected": False,
                "message": "Duplicate check requires an authenticated department context for standard users.",
                "warnings": ["Duplicate detection skipped due to missing department context."]
            }
        effective_dept = caller_dept_id

    try:
        candidates = erm_db.find_potential_duplicate_risks(
            risk_name=risk_title,
            risk_description=risk_description,
            dept_id=effective_dept,
            limit=min(limit, 10)
        )
    except Exception as e:
        logger.error(f"Error in detect_duplicate_risks handler: {e}", exc_info=True)
        return {
            "status": "error",
            "checked_risk_title": risk_title,
            "candidate_count": 0,
            "candidates": [],
            "is_duplicate_suspected": False,
            "message": f"Duplicate risk check could not be completed: {str(e)}",
            "warnings": ["Duplicate detection service unavailable. Verification will be required at governance review."]
        }

    is_duplicate_suspected = len(candidates) > 0
    guidance = (
        f"Found {len(candidates)} potentially similar existing risk(s) in the register. Please review before proceeding."
        if is_duplicate_suspected
        else "No similar existing risks found in the department register."
    )

    return {
        "status": "success",
        "checked_risk_title": risk_title,
        "dept_id": effective_dept,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "is_duplicate_suspected": is_duplicate_suspected,
        "guidance": guidance,
    }


class RiskCreationRequirementsInput(BaseModel):
    dept_id: Optional[int] = Field(default=None, description="Department ID context for requirement lookup")


def _handle_get_risk_creation_requirements(
    dept_id: Optional[int] = None,
    caller_dept_id: Optional[int] = None,
    **kw
) -> Dict[str, Any]:
    from ERM_Copilot.agents.risk_creation.requirements import get_risk_creation_requirements
    effective_dept_id = dept_id if dept_id is not None else caller_dept_id
    reqs = get_risk_creation_requirements(dept_id=effective_dept_id)
    constraints_summary = {}
    for fname, req in reqs.field_definitions.items():
        if req.constraint:
            c = req.constraint
            constraints_summary[fname] = {
                "expected_type": c.expected_type,
                "min_length": c.min_length,
                "max_length": c.max_length,
                "min_value": c.min_value,
                "max_value": c.max_value,
                "allowed_values": c.allowed_values,
                "description": c.description,
            }
    return {
        "status": "success",
        "dept_id": effective_dept_id,
        "required_user_fields": reqs.required_user_fields,
        "server_context_fields": reqs.server_context_fields,
        "optional_fields": reqs.optional_fields,
        "derived_fields": reqs.derived_fields,
        "constraints": constraints_summary,
    }


class AssessRiskCompletenessInput(BaseModel):
    draft: Dict[str, Any] = Field(..., description="Draft risk attributes to evaluate")
    dept_id: Optional[int] = Field(default=None, description="Optional department ID")


def _handle_assess_risk_completeness(
    draft: Dict[str, Any],
    dept_id: Optional[int] = None,
    caller_dept_id: Optional[int] = None,
    caller_user_id: Optional[Any] = None,
    caller_role: Optional[str] = None,
    **kw
) -> Dict[str, Any]:
    from ERM_Copilot.agents.risk_creation.state import RiskCreationSession
    from ERM_Copilot.agents.risk_creation.completeness import assess_risk_completeness
    effective_dept = caller_dept_id if caller_dept_id is not None else (dept_id or draft.get("dept_id"))
    sess = RiskCreationSession.from_dict({
        **draft,
        "user_id": caller_user_id or draft.get("user_id", "5"),
        "dept_id": effective_dept,
        "user_role": caller_role or draft.get("user_role", "Risk Owner"),
    })
    assessment = assess_risk_completeness(sess)
    return {
        "status": "success",
        "is_ready_for_review": assessment.is_ready_for_review,
        "is_complete": assessment.is_complete,
        "present_valid_fields": assessment.present_valid_fields,
        "missing_required_fields": assessment.missing_required_fields,
        "missing_optional_fields": assessment.missing_optional_fields,
        "invalid_fields": assessment.invalid_fields,
        "ambiguous_fields": assessment.ambiguous_fields,
        "system_derived_fields": assessment.system_derived_fields,
        "guidance": (
            "All required risk fields are valid. Ready for review and preview generation."
            if assessment.is_ready_for_review
            else f"Draft is incomplete. Missing required fields: {', '.join(assessment.missing_required_fields)}."
        ),
    }


class RiskDescriptionSuggestionsInput(BaseModel):
    risk_title: str = Field(..., min_length=3, description="Risk title or hazard description, min 3 characters")
    hazard_category: Optional[str] = Field(default=None, description="Optional hazard category")

    @field_validator("risk_title")
    @classmethod
    def validate_risk_title(cls, v: str) -> str:
        cleaned = str(v).strip()
        if len(cleaned) < 3:
            raise ValueError("Argument 'risk_title' must be at least 3 characters long.")
        return cleaned


def _handle_get_description_suggestions(
    risk_title: str,
    hazard_category: Optional[str] = None,
    **kw
) -> Dict[str, Any]:
    from ERM_Copilot.agents.risk_creation.suggestions import static_suggestion_provider
    try:
        suggs = static_suggestion_provider.get_description_suggestions(title=risk_title, category=hazard_category)
        return {
            "status": "success",
            "risk_title": risk_title,
            "suggestions": suggs,
            "source": "curated",
            "message": f"Generated {len(suggs)} curated risk description recommendation(s).",
        }
    except Exception as e:
        logger.error(f"Error in get_description_suggestions handler: {e}", exc_info=True)
        return {
            "status": "error",
            "risk_title": risk_title,
            "suggestions": [],
            "source": "none",
            "message": f"Failed to retrieve description suggestions: {str(e)}",
        }


class CalculateRiskScoresInput(BaseModel):
    likelihood: int = Field(..., ge=1, le=5, description="Likelihood rating (1-5)")
    impact: int = Field(..., ge=1, le=5, description="Impact rating (1-5)")


def _handle_calculate_risk_scores(likelihood: int, impact: int, **kw) -> Dict[str, Any]:
    from ERM_Copilot.agents.risk_creation.scoring import RiskMatrixCalculator
    try:
        score, level, badge = RiskMatrixCalculator.calculate_score(int(likelihood), int(impact), strict=True)
        return {
            "status": "success",
            "likelihood": int(likelihood),
            "impact": int(impact),
            "score": score,
            "level": level,
            "badge": badge,
        }
    except Exception as e:
        logger.error(f"Error calculating risk scores: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
        }


class ValidateRiskPayloadInput(BaseModel):
    draft: Dict[str, Any] = Field(..., description="Draft risk attributes to validate")
    dept_id: Optional[int] = Field(default=None, description="Department ID")


def _handle_validate_risk_payload(
    draft: Dict[str, Any],
    dept_id: Optional[int] = None,
    caller_role: Optional[str] = None,
    caller_dept_id: Optional[int] = None,
    caller_user_id: Optional[Any] = None,
    **kw
) -> Dict[str, Any]:
    from ERM_Copilot.agents.risk_creation.state import RiskCreationSession
    from ERM_Copilot.agents.risk_creation.validation import validate_risk_draft
    effective_dept = caller_dept_id if caller_dept_id is not None else (dept_id or draft.get("dept_id"))
    effective_user = caller_user_id or draft.get("user_id", "5")
    effective_role = caller_role or draft.get("user_role", "Risk Owner")

    sess = RiskCreationSession.from_dict({
        **draft,
        "user_id": effective_user,
        "dept_id": effective_dept,
        "user_role": effective_role,
    })
    server_ctx = {
        "user_id": effective_user,
        "dept_id": effective_dept,
        "role": effective_role,
        "user_role": effective_role,
    }
    res = validate_risk_draft(sess, server_context=server_ctx)
    return {
        "status": "success" if res.is_valid else "invalid",
        "is_valid": res.is_valid,
        "is_ready_for_review": res.is_ready_for_review,
        "errors": res.errors,
        "warnings": res.warnings,
        "missing_required_fields": res.missing_required_fields,
        "calculated_scores": res.calculated_scores,
        "normalized_values": res.normalized_values,
        "summary_message": res.summary_message,
    }


class CreateRiskInput(BaseModel):
    risk_name: str = Field(..., min_length=3, max_length=250, description="Risk title/name")
    risk_description: str = Field(..., min_length=5, description="Risk description")
    dept_id: Optional[int] = Field(default=None, description="Department ID")
    dept_name: Optional[str] = Field(default=None, description="Department name")
    risk_owner_id: Optional[Any] = Field(default=None, description="Risk owner ID")
    risk_co_owner_id: Optional[Any] = Field(default=None, description="Risk co-owner ID")
    inherent_likelihood: int = Field(default=4, ge=1, le=5, description="Inherent likelihood rating 1-5")
    inherent_impact: int = Field(default=4, ge=1, le=5, description="Inherent impact rating 1-5")
    current_likelihood: int = Field(default=2, ge=1, le=5, description="Current likelihood rating 1-5")
    current_impact: int = Field(default=2, ge=1, le=5, description="Current impact rating 1-5")
    mitigation: str = Field(default="", description="Mitigation strategy")
    status: int = Field(default=1, description="Status ID")
    financial_year: str = Field(default="2026-2027", description="Financial year")
    treatments: Optional[List[Dict[str, Any]]] = Field(default=None, description="Action plan treatments")


class AddRiskTreatmentInput(BaseModel):
    risk_register_id: int = Field(..., description="Risk register numeric ID")
    action_plan: str = Field(..., min_length=3, description="Mitigation action plan description")
    action_owner_id: int = Field(..., description="Action owner user ID")
    target_date: Optional[str] = Field(default=None, description="Target completion date YYYY-MM-DD")
    progress: int = Field(default=0, ge=0, le=100, description="Initial progress percentage")
    action_status_id: int = Field(default=1, description="Status ID (default 1 for Draft / In Progress)")
    created_by: int = Field(default=1, description="Creator user ID")


class UpdateTreatmentProgressInput(BaseModel):
    treatment_id: int = Field(..., description="Unique treatment/action plan ID")
    progress: int = Field(..., ge=0, le=100, description="New progress percentage (0-100)")
    modified_by: int = Field(default=1, description="Authenticated user ID modifying progress")
    remarks: Optional[str] = Field(default=None, description="Optional progress remark")


class ReassignTreatmentOwnerInput(BaseModel):
    treatment_id: int = Field(..., description="Unique treatment/action plan ID")
    new_action_owner_id: int = Field(..., description="New action owner user ID")
    modified_by: int = Field(default=1, description="Authenticated user ID modifying the assignment")


class GetRiskTreatmentsInput(BaseModel):
    risk_ident: str = Field(..., description="Risk identifier code or numeric register ID")
    dept_id: Optional[int] = Field(default=None, description="Optional department ID filter")


class GetTreatmentDetailsInput(BaseModel):
    treatment_id: int = Field(..., description="Unique treatment/action plan ID")


@dataclass
class ToolDefinition:
    """Complete governance definition for an AI tool."""
    name: str
    description: str
    category: ToolCategory
    handler: Callable[..., Any]
    input_schema: Dict[str, Any] = field(default_factory=dict)
    schema_model: Optional[Type[BaseModel]] = None
    allowed_roles: Optional[List[str]] = None
    requires_confirmation: bool = False
    is_state_changing: bool = False
    is_idempotent: bool = True
    timeout_seconds: float = 30.0
    max_retries: int = 2
    retry_on_transient: bool = True
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value if hasattr(self.category, "value") else str(self.category),
            "allowed_roles": self.allowed_roles,
            "requires_confirmation": self.requires_confirmation,
            "is_state_changing": self.is_state_changing,
            "is_idempotent": self.is_idempotent,
            "timeout_seconds": self.timeout_seconds,
            "enabled": self.enabled,
        }


class ToolRegistry:
    """
    Centralized registry enforcing validation, RBAC, and policy constraints on tools.
    """

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_default_tools()

    def register(self, tool: ToolDefinition) -> None:
        """Register a new governed tool."""
        self._tools[tool.name] = tool
        logger.debug(f"[TOOL_REGISTERED] name='{tool.name}' category='{tool.category}' confirmation={tool.requires_confirmation}")

    def get(self, name: str) -> ToolDefinition:
        """Retrieve a tool definition or raise ToolNotFoundError."""
        tool = self._tools.get(name)
        if not tool or not tool.enabled:
            raise ToolNotFoundError(name)
        return tool

    def has(self, name: str) -> bool:
        return name in self._tools and self._tools[name].enabled

    def list_tools(self, user_role: Optional[str] = None) -> List[ToolDefinition]:
        """List all active tools, optionally filtered by the user's role authorization."""
        tools = [t for t in self._tools.values() if t.enabled]
        if user_role:
            tools = [t for t in tools if is_role_authorized_for_tool(user_role, t.allowed_roles)]
        return tools

    def validate_arguments(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Validate tool invocation arguments against registered schema or model."""
        tool = self.get(tool_name)
        
        # If a Pydantic schema model is registered, use it for rigorous validation
        if tool.schema_model:
            try:
                validated_model = tool.schema_model(**arguments)
                return validated_model.model_dump() if hasattr(validated_model, "model_dump") else validated_model.dict()
            except ValidationError as ve:
                errors = ve.errors()
                error_msgs = [f"{e.get('loc', ['field'])[0]}: {e.get('msg', 'invalid')}" for e in errors]
                raise ToolValidationError(
                    f"Argument validation failed for tool '{tool_name}': {', '.join(error_msgs)}",
                    details={"validation_errors": errors}
                )

        # Custom validation checks for critical governance tools
        if tool_name == "approve_or_reject_risk":
            risk_id = arguments.get("risk_id")
            action = arguments.get("action")
            remark = arguments.get("remark")
            
            if not risk_id or not str(risk_id).strip():
                raise ToolValidationError("Argument 'risk_id' is mandatory and must not be empty.")
            if not action or str(action).lower() not in ["approve", "reject"]:
                raise ToolValidationError("Argument 'action' must be either 'approve' or 'reject'.")
            if not remark or not str(remark).strip():
                raise ToolValidationError("Argument 'remark' is mandatory for risk approval/rejection decisions.")

        elif tool_name in ("save_risk", "create_risk_full"):
            title = arguments.get("risk_name") or arguments.get("title")
            dept_id = arguments.get("department_id") or arguments.get("dept_id")
            if not title or not str(title).strip():
                raise ToolValidationError("Argument 'risk_name' is mandatory for creating a risk.")
            if not dept_id:
                raise ToolValidationError("Argument 'department_id' is mandatory for creating a risk.")

        return arguments

    def _register_default_tools(self) -> None:
        """Register the standard enterprise risk management tools."""
        
        # 1. Search Risks
        self.register(
            ToolDefinition(
                name="search_risks",
                description="Search active risks in the enterprise risk register by keyword, department, or status.",
                category=ToolCategory.SEARCH,
                handler=lambda query="", dept_id=None, limit=20, **kw: erm_db.search_risks(keyword=query, dept_id=dept_id, limit=limit),
                allowed_roles=ALL_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )

        # 2. Get Pending Approvals
        self.register(
            ToolDefinition(
                name="get_pending_approvals",
                description="Fetch the list of risks pending approval at the user's authorized governance stage.",
                category=ToolCategory.READ_ONLY,
                handler=lambda approver_role, dept_id=None, limit=50, **kw: erm_db.get_approval_queues(approver_role, dept_id=dept_id, limit=limit),
                allowed_roles=APPROVER_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )

        # 3. Get Risk Details
        self.register(
            ToolDefinition(
                name="get_risk_details",
                description="Retrieve full details for a specific risk by identifier.",
                category=ToolCategory.READ_ONLY,
                handler=lambda risk_id, dept_id=None, **kw: (
                    erm_db.get_risk_by_code(risk_id) if hasattr(erm_db, "get_risk_by_code")
                    else erm_db.search_risks(keyword=risk_id, dept_id=dept_id, limit=1)
                ),
                allowed_roles=ALL_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )

        # 4. Get Risk Audit Trail
        self.register(
            ToolDefinition(
                name="get_risk_audit_trail",
                description="Query the complete history and audit trail of stage transitions and approvals for a risk.",
                category=ToolCategory.READ_ONLY,
                handler=lambda risk_identifier, **kw: erm_db.get_risk_audit_trail(risk_identifier),
                allowed_roles=ALL_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )

        # 5. Get Dropdown Options
        self.register(
            ToolDefinition(
                name="get_dropdown_options",
                description="Fetch dropdown metadata options for categories, likelihood, impact, and action owners.",
                category=ToolCategory.READ_ONLY,
                handler=lambda dept_id=None, **kw: erm_db.get_dropdown_options(dept_id=dept_id),
                allowed_roles=ALL_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )

        # 5a. Resolve Reference Data
        self.register(
            ToolDefinition(
                name="resolve_reference_data",
                description="Authoritatively resolve reference data for risk statuses, departments, and assessment criteria.",
                category=ToolCategory.READ_ONLY,
                handler=_handle_resolve_reference_data,
                schema_model=ReferenceDataInput,
                allowed_roles=ALL_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )
        self.register(
            ToolDefinition(
                name="get_risk_reference_options",
                description="Authoritatively resolve reference data for risk statuses, departments, and assessment criteria.",
                category=ToolCategory.READ_ONLY,
                handler=_handle_resolve_reference_data,
                schema_model=ReferenceDataInput,
                allowed_roles=ALL_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )

        # 5b. Lookup Eligible Owners
        self.register(
            ToolDefinition(
                name="lookup_eligible_owners",
                description="Look up eligible and active Action Owners (department-scoped) or Co-Risk Owners (enterprise-wide).",
                category=ToolCategory.READ_ONLY,
                handler=_handle_lookup_eligible_owners,
                schema_model=EligibleOwnersInput,
                allowed_roles=ALL_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )
        self.register(
            ToolDefinition(
                name="get_eligible_risk_owners",
                description="Look up eligible and active Action Owners (department-scoped) or Co-Risk Owners (enterprise-wide).",
                category=ToolCategory.READ_ONLY,
                handler=_handle_lookup_eligible_owners,
                schema_model=EligibleOwnersInput,
                allowed_roles=ALL_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )

        # 5c. Get Mitigation Suggestions
        self.register(
            ToolDefinition(
                name="get_mitigation_suggestions",
                description="Provide relevant, curated and historical mitigation strategy recommendations for a risk.",
                category=ToolCategory.READ_ONLY,
                handler=_handle_get_mitigation_suggestions,
                schema_model=MitigationSuggestionsInput,
                allowed_roles=CREATOR_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )
        self.register(
            ToolDefinition(
                name="generate_mitigation_suggestions",
                description="Provide relevant, curated and historical mitigation strategy recommendations for a risk.",
                category=ToolCategory.READ_ONLY,
                handler=_handle_get_mitigation_suggestions,
                schema_model=MitigationSuggestionsInput,
                allowed_roles=CREATOR_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )

        # 5d. Get Action Plan Suggestions
        self.register(
            ToolDefinition(
                name="get_action_plan_suggestions",
                description="Provide actionable, phased implementation action-plan recommendations corresponding to a risk and mitigation.",
                category=ToolCategory.READ_ONLY,
                handler=_handle_get_action_plan_suggestions,
                schema_model=ActionPlanSuggestionsInput,
                allowed_roles=CREATOR_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )
        self.register(
            ToolDefinition(
                name="generate_action_plan_suggestions",
                description="Provide actionable, phased implementation action-plan recommendations corresponding to a risk and mitigation.",
                category=ToolCategory.READ_ONLY,
                handler=_handle_get_action_plan_suggestions,
                schema_model=ActionPlanSuggestionsInput,
                allowed_roles=CREATOR_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )

        # 5e. Detect Duplicate Risks
        self.register(
            ToolDefinition(
                name="detect_duplicate_risks",
                description="Check for potential duplicate or similar existing risks in the enterprise risk register.",
                category=ToolCategory.READ_ONLY,
                handler=_handle_detect_duplicate_risks,
                schema_model=DuplicateRiskCheckInput,
                allowed_roles=CREATOR_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )
        self.register(
            ToolDefinition(
                name="check_risk_duplicates",
                description="Check for potential duplicate or similar existing risks in the enterprise risk register.",
                category=ToolCategory.READ_ONLY,
                handler=_handle_detect_duplicate_risks,
                schema_model=DuplicateRiskCheckInput,
                allowed_roles=CREATOR_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )

        # 5f. Generate Risk Description Suggestions
        self.register(
            ToolDefinition(
                name="generate_risk_description_suggestions",
                description="Generate curated description recommendations based on risk title or hazard category.",
                category=ToolCategory.READ_ONLY,
                handler=_handle_get_description_suggestions,
                schema_model=RiskDescriptionSuggestionsInput,
                allowed_roles=CREATOR_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )
        self.register(
            ToolDefinition(
                name="get_description_suggestions",
                description="Generate curated description recommendations based on risk title or hazard category.",
                category=ToolCategory.READ_ONLY,
                handler=_handle_get_description_suggestions,
                schema_model=RiskDescriptionSuggestionsInput,
                allowed_roles=CREATOR_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )

        # 5g. Risk Creation Requirements
        self.register(
            ToolDefinition(
                name="get_risk_creation_requirements",
                description="Retrieve authoritative risk creation required fields, optional fields, defaults, and constraints.",
                category=ToolCategory.READ_ONLY,
                handler=_handle_get_risk_creation_requirements,
                schema_model=RiskCreationRequirementsInput,
                allowed_roles=ALL_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )

        # 5h. Assess Risk Completeness
        self.register(
            ToolDefinition(
                name="assess_risk_completeness",
                description="Deterministically assess whether a risk creation draft has satisfied all backend requirements.",
                category=ToolCategory.READ_ONLY,
                handler=_handle_assess_risk_completeness,
                schema_model=AssessRiskCompletenessInput,
                allowed_roles=CREATOR_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )

        # 5i. Validate Risk Payload
        self.register(
            ToolDefinition(
                name="validate_risk_payload",
                description="Deterministically validate risk draft data and server context, returning validation results.",
                category=ToolCategory.READ_ONLY,
                handler=_handle_validate_risk_payload,
                schema_model=ValidateRiskPayloadInput,
                allowed_roles=CREATOR_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )

        # 6. Calculate Risk Assessment / Scores
        from ERM_Copilot.agents.risk_creation.scoring import RiskMatrixCalculator
        self.register(
            ToolDefinition(
                name="calculate_risk_assessment",
                description="Calculate authoritative risk rating and score using backend matrix tables.",
                category=ToolCategory.READ_ONLY,
                handler=lambda likelihood_id, impact_id, **kw: RiskMatrixCalculator.calculate_score(likelihood_id, impact_id),
                allowed_roles=ALL_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )
        self.register(
            ToolDefinition(
                name="calculate_risk_scores",
                description="Calculate authoritative risk rating and score using backend matrix tables.",
                category=ToolCategory.READ_ONLY,
                handler=_handle_calculate_risk_scores,
                schema_model=CalculateRiskScoresInput,
                allowed_roles=ALL_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )

        # 7. Approve or Reject Risk
        self.register(
            ToolDefinition(
                name="approve_or_reject_risk",
                description="Execute an official approval or rejection signoff for a risk at the current stage.",
                category=ToolCategory.APPROVAL,
                handler=lambda risk_id, action, remark, approver_id, **kw: erm_db.approve_or_reject_risk(
                    risk_id=risk_id, approver_id=int(approver_id), action=action, remark=remark
                ),
                allowed_roles=APPROVER_ROLES,
                requires_confirmation=True,
                is_state_changing=True,
                is_idempotent=False,
                retry_on_transient=False,
            )
        )

        # 8. Save Risk (Create Risk)
        self.register(
            ToolDefinition(
                name="save_risk",
                description="Persist a newly drafted risk into the database after explicit confirmation.",
                category=ToolCategory.STATE_CHANGING,
                handler=lambda risk_name, dept_id, **kw: erm_db.create_risk(risk_name=risk_name, dept_id=dept_id, **kw),
                allowed_roles=CREATOR_ROLES,
                requires_confirmation=True,
                is_state_changing=True,
                is_idempotent=False,
                retry_on_transient=False,
            )
        )
        self.register(
            ToolDefinition(
                name="create_risk",
                description="Persist a newly drafted risk into the database after explicit confirmation.",
                category=ToolCategory.STATE_CHANGING,
                handler=lambda **kw: erm_db.create_risk(**kw),
                schema_model=CreateRiskInput,
                allowed_roles=CREATOR_ROLES,
                requires_confirmation=True,
                is_state_changing=True,
                is_idempotent=False,
                retry_on_transient=False,
            )
        )

        # 9. Add Risk Treatment
        self.register(
            ToolDefinition(
                name="add_risk_treatment",
                description="Add an action plan / mitigation treatment to an existing risk register record.",
                category=ToolCategory.STATE_CHANGING,
                handler=lambda risk_register_id, action_plan, action_owner_id, target_date, progress, action_status_id, created_by, **kw: (
                    erm_db.add_risk_treatment(
                        risk_register_id=int(risk_register_id),
                        action_plan=action_plan,
                        action_owner_id=int(action_owner_id),
                        target_date=target_date,
                        progress=int(progress),
                        action_status_id=int(action_status_id),
                        created_by=int(created_by)
                    )
                ),
                schema_model=AddRiskTreatmentInput,
                allowed_roles=CREATOR_ROLES,
                requires_confirmation=True,
                is_state_changing=True,
                is_idempotent=False,
                retry_on_transient=False,
            )
        )

        # 10. Update Treatment Progress
        self.register(
            ToolDefinition(
                name="update_treatment_progress",
                description="Update progress percentage on an existing treatment action plan.",
                category=ToolCategory.STATE_CHANGING,
                handler=lambda treatment_id, progress, modified_by, remarks=None, **kw: erm_db.update_treatment_progress(
                    treatment_id=int(treatment_id),
                    progress=int(progress),
                    modified_by=int(modified_by),
                    remarks=remarks
                ),
                schema_model=UpdateTreatmentProgressInput,
                allowed_roles=CREATOR_ROLES,
                requires_confirmation=True,
                is_state_changing=True,
                is_idempotent=False,
                retry_on_transient=False,
            )
        )

        # 10b. Reassign Treatment Owner
        self.register(
            ToolDefinition(
                name="reassign_treatment_owner",
                description="Reassign designated Action Owner for a specific risk treatment.",
                category=ToolCategory.STATE_CHANGING,
                handler=lambda treatment_id, new_action_owner_id, modified_by, **kw: (
                    erm_db.reassign_treatment_owner(
                        treatment_id=int(treatment_id),
                        new_action_owner_id=int(new_action_owner_id),
                        modified_by=int(modified_by)
                    )
                ),
                schema_model=ReassignTreatmentOwnerInput,
                allowed_roles=CREATOR_ROLES,
                requires_confirmation=True,
                is_state_changing=True,
                is_idempotent=False,
                retry_on_transient=False,
            )
        )

        # 10c. Get Treatments for Risk
        self.register(
            ToolDefinition(
                name="get_risk_treatments",
                description="Fetch all treatment action plans associated with a risk register record.",
                category=ToolCategory.READ_ONLY,
                handler=lambda risk_ident, dept_id=None, **kw: (
                    erm_db.get_treatments_for_risk(
                        risk_ident=str(risk_ident),
                        dept_id=dept_id
                    )
                ),
                schema_model=GetRiskTreatmentsInput,
                allowed_roles=ALL_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )

        # 10d. Get Treatment Details
        self.register(
            ToolDefinition(
                name="get_treatment_details",
                description="Fetch complete details of a specific risk treatment action plan by ID.",
                category=ToolCategory.READ_ONLY,
                handler=lambda treatment_id, **kw: (
                    erm_db.get_treatment_by_id(
                        treatment_id=int(treatment_id)
                    )
                ),
                schema_model=GetTreatmentDetailsInput,
                allowed_roles=ALL_ROLES,
                requires_confirmation=False,
                is_state_changing=False,
                is_idempotent=True,
                retry_on_transient=True,
            )
        )

        # 11. Resubmit Risk
        self.register(
            ToolDefinition(
                name="resubmit_risk",
                description="Resubmit a returned or rejected risk back to Stage 2 Functional Head.",
                category=ToolCategory.STATE_CHANGING,
                handler=lambda risk_id, user_id, **kw: erm_db.resubmit_risk(
                    risk_id=risk_id, user_id=int(user_id)
                ),
                allowed_roles=CREATOR_ROLES,
                requires_confirmation=True,
                is_state_changing=True,
                is_idempotent=False,
                retry_on_transient=False,
            )
        )


tool_registry = ToolRegistry()
