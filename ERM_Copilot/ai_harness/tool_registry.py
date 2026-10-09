"""
Centralized Tool Registry for ERM AI Harness.
Declares, documents, schemas, and governs all tools executable by agents.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Type
from pydantic import BaseModel, ValidationError

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
    ToolCategory,
    is_role_authorized_for_tool,
)
from ERM_Copilot.services.db_service import erm_db

logger = logging.getLogger("ERM_Copilot.ai_harness.tool_registry")


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

        # 6. Calculate Risk Assessment
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
                handler=lambda treatment_id, progress, modified_by, **kw: erm_db.update_treatment_progress(
                    treatment_id=int(treatment_id),
                    progress=int(progress),
                    modified_by=int(modified_by)
                ),
                allowed_roles=CREATOR_ROLES,
                requires_confirmation=True,
                is_state_changing=True,
                is_idempotent=False,
                retry_on_transient=False,
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
