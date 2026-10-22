"""
Authoritative Risk Creation Requirements and Constraints.
Exposes real creation requirements derived from backend schemas, database constraints,
and business governance rules for Enterprise Risk Management.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field


class FieldConstraint(BaseModel):
    """Validation bounds and rules for a single risk field."""
    field_name: str
    expected_type: str
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    allowed_values: Optional[List[Any]] = None
    description: str = ""


class FieldRequirement(BaseModel):
    """Specification of a field's role in the risk creation workflow."""
    name: str
    is_required: bool
    is_server_context: bool = False
    is_server_derived: bool = False
    has_server_default: bool = False
    default_value: Optional[Any] = None
    description: str = ""
    constraint: Optional[FieldConstraint] = None


class RiskCreationRequirements(BaseModel):
    """
    Authoritative single source of truth for risk creation requirements.
    Directly reflects backend schema, ISO-31000 governance, and database constraints.
    """
    required_user_fields: List[str] = Field(
        default_factory=lambda: [
            "risk_name",
            "risk_description",
            "inherent_likelihood",
            "inherent_impact",
            "mitigation",
            "current_likelihood",
            "current_impact",
            "action_plan",
        ]
    )
    server_context_fields: List[str] = Field(
        default_factory=lambda: [
            "user_id",
            "dept_id",
        ]
    )
    optional_fields: List[str] = Field(
        default_factory=lambda: [
            "risk_co_owner_id",
            "action_owner_id",
            "target_date",
            "status_id",
            "progress",
            "financial_year",
        ]
    )
    derived_fields: List[str] = Field(
        default_factory=lambda: [
            "inherent_score",
            "inherent_level",
            "inherent_badge",
            "current_score",
            "current_level",
            "current_badge",
        ]
    )
    field_definitions: Dict[str, FieldRequirement] = Field(default_factory=dict)

    def is_required(self, field_name: str) -> bool:
        """Check if a field is strictly required to formulate a valid risk."""
        return field_name in self.required_user_fields or field_name in self.server_context_fields

    def validate_field(self, field_name: str, value: Any) -> Tuple[bool, Optional[str]]:
        """Deterministically validate a field value against backend constraints."""
        req = self.field_definitions.get(field_name)
        if not req or not req.constraint:
            return True, None

        c = req.constraint
        if value is None or value == "":
            if req.is_required:
                return False, f"Field '{field_name}' is required and cannot be empty."
            return True, None

        # String length checks
        if c.expected_type == "str":
            s_val = str(value).strip()
            if c.min_length is not None and len(s_val) < c.min_length:
                return False, f"'{field_name}' must be at least {c.min_length} characters (got {len(s_val)})."
            if c.max_length is not None and len(s_val) > c.max_length:
                return False, f"'{field_name}' cannot exceed {c.max_length} characters."

        # Numeric bounds checks
        elif c.expected_type == "int":
            if isinstance(value, bool):
                return False, f"'{field_name}' must be an integer, not a boolean."
            try:
                i_val = int(value)
                if float(value) != i_val:
                    return False, f"'{field_name}' must be a whole integer."
                if c.min_value is not None and i_val < c.min_value:
                    return False, f"'{field_name}' must be at least {c.min_value} (got {i_val})."
                if c.max_value is not None and i_val > c.max_value:
                    return False, f"'{field_name}' cannot exceed {c.max_value} (got {i_val})."
            except (ValueError, TypeError):
                return False, f"'{field_name}' must be a valid integer."

        if c.allowed_values is not None and value not in c.allowed_values:
            return False, f"'{field_name}' must be one of {c.allowed_values} (got {value})."

        return True, None


def get_risk_creation_requirements(dept_id: Optional[int] = None) -> RiskCreationRequirements:
    """
    Expose the authoritative creation requirements derived from backend schemas and business rules.
    """
    defs: Dict[str, FieldRequirement] = {
        # 1. Identity / Server Context
        "user_id": FieldRequirement(
            name="user_id",
            is_required=True,
            is_server_context=True,
            description="Authenticated User ID acting as Risk Owner (ers.risk_register.risk_owner_id)",
            constraint=FieldConstraint(field_name="user_id", expected_type="int", min_value=1)
        ),
        "dept_id": FieldRequirement(
            name="dept_id",
            is_required=True,
            is_server_context=True,
            description="Department identifier resolving to mst_department",
            constraint=FieldConstraint(field_name="dept_id", expected_type="int", min_value=1)
        ),

        # 2. Required Core Risk Fields
        "risk_name": FieldRequirement(
            name="risk_name",
            is_required=True,
            description="Hazard or Risk Title (minimum 3 characters)",
            constraint=FieldConstraint(field_name="risk_name", expected_type="str", min_length=3, max_length=250)
        ),
        "risk_description": FieldRequirement(
            name="risk_description",
            is_required=True,
            description="Detailed operational threat / failure mode description (minimum 5 characters)",
            constraint=FieldConstraint(field_name="risk_description", expected_type="str", min_length=5)
        ),

        # 3. Assessment Matrix Ratings (1-5 Scale)
        "inherent_likelihood": FieldRequirement(
            name="inherent_likelihood",
            is_required=True,
            description="Inherent Likelihood rating from 1 to 5",
            constraint=FieldConstraint(field_name="inherent_likelihood", expected_type="int", min_value=1, max_value=5)
        ),
        "inherent_impact": FieldRequirement(
            name="inherent_impact",
            is_required=True,
            description="Inherent Impact/consequence rating from 1 to 5",
            constraint=FieldConstraint(field_name="inherent_impact", expected_type="int", min_value=1, max_value=5)
        ),
        "mitigation": FieldRequirement(
            name="mitigation",
            is_required=True,
            description="Preventive engineering, safety, or operational controls (minimum 5 characters)",
            constraint=FieldConstraint(field_name="mitigation", expected_type="str", min_length=5)
        ),
        "current_likelihood": FieldRequirement(
            name="current_likelihood",
            is_required=True,
            description="Residual / Current Likelihood rating post-mitigation from 1 to 5",
            constraint=FieldConstraint(field_name="current_likelihood", expected_type="int", min_value=1, max_value=5)
        ),
        "current_impact": FieldRequirement(
            name="current_impact",
            is_required=True,
            description="Residual / Current Impact post-mitigation from 1 to 5",
            constraint=FieldConstraint(field_name="current_impact", expected_type="int", min_value=1, max_value=5)
        ),
        "action_plan": FieldRequirement(
            name="action_plan",
            is_required=True,
            description="Specific tactical mitigation action plan (minimum 5 characters)",
            constraint=FieldConstraint(field_name="action_plan", expected_type="str", min_length=5)
        ),

        # 4. Optional Fields with Safe Defaults
        "risk_co_owner_id": FieldRequirement(
            name="risk_co_owner_id",
            is_required=False,
            has_server_default=True,
            default_value=None,
            description="Optional Enterprise Co-Owner User ID",
            constraint=FieldConstraint(field_name="risk_co_owner_id", expected_type="int", min_value=1)
        ),
        "action_owner_id": FieldRequirement(
            name="action_owner_id",
            is_required=False,
            has_server_default=True,
            default_value=None,
            description="Assigned Action Owner ID (defaults to Risk Owner user_id if omitted)",
            constraint=FieldConstraint(field_name="action_owner_id", expected_type="int", min_value=1)
        ),
        "target_date": FieldRequirement(
            name="target_date",
            is_required=False,
            has_server_default=True,
            default_value="+30 days",
            description="Target completion date in YYYY-MM-DD format (defaults to +30 days)",
            constraint=FieldConstraint(field_name="target_date", expected_type="str", min_length=8)
        ),
        "status_id": FieldRequirement(
            name="status_id",
            is_required=False,
            has_server_default=True,
            default_value=1,
            description="Lifecycle status: 1=Draft, 2=Submitted to Functional Head",
            constraint=FieldConstraint(field_name="status_id", expected_type="int", allowed_values=[1, 2])
        ),
        "progress": FieldRequirement(
            name="progress",
            is_required=False,
            has_server_default=True,
            default_value=0,
            description="Action execution progress percentage from 0 to 100",
            constraint=FieldConstraint(field_name="progress", expected_type="int", min_value=0, max_value=100)
        ),
        "financial_year": FieldRequirement(
            name="financial_year",
            is_required=False,
            has_server_default=True,
            default_value="2026-2027",
            description="Fiscal year association",
            constraint=FieldConstraint(field_name="financial_year", expected_type="str", min_length=4)
        ),
    }

    return RiskCreationRequirements(field_definitions=defs)
