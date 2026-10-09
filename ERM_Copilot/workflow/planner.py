"""
Bounded Autonomous Planner for ERM Copilot Workflows.
Evaluates user intent, workflow state, available tools, missing fields,
and governance policies to select valid, bounded next actions.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.ai_harness.policies import (
    ALL_ROLES,
    APPROVER_ROLES,
    CREATOR_ROLES,
    is_role_authorized_for_tool,
)
from ERM_Copilot.ai_harness.tool_registry import tool_registry
from ERM_Copilot.workflow.contracts import AgentWorkflowState, WorkflowStatus, WorkflowType

logger = logging.getLogger("ERM_Copilot.workflow.planner")


class PlannerDecisionType(str, Enum):
    """Supported bounded actions selectable by the planner."""
    CALL_READ_TOOL = "CALL_READ_TOOL"
    DELEGATE_TO_AGENT = "DELEGATE_TO_AGENT"
    ASK_USER = "ASK_USER"
    WAIT_FOR_CONFIRMATION = "WAIT_FOR_CONFIRMATION"
    WAIT_FOR_APPROVAL = "WAIT_FOR_APPROVAL"
    RESUME_WORKFLOW = "RESUME_WORKFLOW"
    COMPLETE = "COMPLETE"
    FAIL_SAFELY = "FAIL_SAFELY"


class PlannerDecision(BaseModel):
    """Structured decision output from BoundedPlanner."""
    decision_type: PlannerDecisionType
    target_agent: Optional[str] = None
    target_tool: Optional[str] = None
    tool_arguments: Dict[str, Any] = Field(default_factory=dict)
    prompt_for_user: Optional[str] = None
    missing_fields: List[str] = Field(default_factory=list)
    reasoning: str = ""
    is_governed: bool = False
    requires_confirmation: bool = False

    class Config:
        use_enum_values = True


class StepLimitExceededError(Exception):
    """Raised when an autonomous workflow exceeds maximum allowed step count."""
    pass


class CircularHandoffError(Exception):
    """Raised when an endless circular agent handoff loop is detected."""
    pass


class BoundedPlanner:
    """
    Deterministic Planner ensuring bounded multi-step autonomous execution.
    Enforces step limits, circular loop interception, and policy gating.
    """

    KNOWN_AGENTS: Dict[str, str] = {
        "risk_creation": "risk_creation_agent",
        "risk_creation_agent": "risk_creation_agent",
        "treatment": "treatment_management_agent",
        "treatment_management_agent": "treatment_management_agent",
        "approval": "agent_approval_langgraph_v1",
        "approval_agent": "agent_approval_langgraph_v1",
        "agent_approval_langgraph_v1": "agent_approval_langgraph_v1",
        "orchestrator": "erm_copilot_agent",
        "erm_copilot_agent": "erm_copilot_agent",
    }

    @classmethod
    def plan_next_step(
        cls,
        state: AgentWorkflowState,
        user_message: str,
        context: Optional[HarnessContext] = None
    ) -> PlannerDecision:
        """
        Evaluate workflow state and select the next legal, governed action.
        """
        user_role = (context.user_role if context else state.owner_role) or "Risk Owner"

        # 1. Step Limits & Loop Detection
        if state.step_count > state.max_steps:
            return PlannerDecision(
                decision_type=PlannerDecisionType.FAIL_SAFELY,
                reasoning=f"Workflow step limit ({state.max_steps}) exceeded. Stopping execution safely.",
                prompt_for_user="⚠️ **Workflow Limit Reached:** Maximum conversational steps reached for this action. Please re-initiate if you wish to continue."
            )

        if cls._detect_circular_handoff(state.agent_handoff_history):
            return PlannerDecision(
                decision_type=PlannerDecisionType.FAIL_SAFELY,
                reasoning="Circular agent delegation loop detected.",
                prompt_for_user="⚠️ **Execution Intercepted:** A circular delegation cycle was detected and halted safely."
            )

        # 2. Check for active confirmation gate
        if state.workflow_status == WorkflowStatus.WAITING_FOR_CONFIRMATION.value:
            # If user message is confirmation
            lower = (user_message or "").strip().lower()
            if any(lower.startswith(c) for c in ["yes", "confirm", "proceed", "approve", "ok"]):
                if state.pending_action:
                    tool_name = state.pending_action.get("tool_name")
                    return PlannerDecision(
                        decision_type=PlannerDecisionType.DELEGATE_TO_AGENT if state.current_agent != "erm_copilot_agent" else PlannerDecisionType.COMPLETE,
                        target_tool=tool_name,
                        tool_arguments=state.pending_action.get("arguments", {}),
                        reasoning="User confirmed pending action.",
                        is_governed=True
                    )
            elif any(lower.startswith(c) for c in ["no", "cancel", "abort", "discard", "stop"]):
                state.transition_to(WorkflowStatus.CANCELLED, reason="User cancelled action")
                return PlannerDecision(
                    decision_type=PlannerDecisionType.COMPLETE,
                    reasoning="User cancelled pending action.",
                    prompt_for_user="❌ Action cancelled. No changes were made."
                )

        # 3. Check for active subagent wizard
        if state.workflow_type == WorkflowType.RISK_CREATION.value:
            return PlannerDecision(
                decision_type=PlannerDecisionType.DELEGATE_TO_AGENT,
                target_agent="risk_creation_agent",
                reasoning="Continuing multi-step risk creation wizard."
            )

        if state.workflow_type == WorkflowType.TREATMENT_MANAGEMENT.value:
            return PlannerDecision(
                decision_type=PlannerDecisionType.DELEGATE_TO_AGENT,
                target_agent="treatment_management_agent",
                reasoning="Continuing multi-step treatment planning wizard."
            )

        if state.workflow_type == WorkflowType.APPROVAL_GOVERNANCE.value:
            return PlannerDecision(
                decision_type=PlannerDecisionType.DELEGATE_TO_AGENT,
                target_agent="agent_approval_langgraph_v1",
                reasoning="Continuing approval governance workflow."
            )

        # 4. Default: Orchestrator Intent Resolution
        return PlannerDecision(
            decision_type=PlannerDecisionType.COMPLETE,
            target_agent="erm_copilot_agent",
            reasoning="Standard single-turn query completion."
        )

    @classmethod
    def validate_decision(cls, decision: PlannerDecision, user_role: str) -> None:
        """
        Validate decision schema, target tool existence, and RBAC policy compliance.
        """
        # Validate target agent if specified
        if decision.target_agent:
            if decision.target_agent not in cls.KNOWN_AGENTS.values() and decision.target_agent not in cls.KNOWN_AGENTS:
                raise ValueError(f"Unknown or unauthorized target agent '{decision.target_agent}'.")

        # Validate target tool if specified
        if decision.target_tool:
            if not tool_registry.has(decision.target_tool):
                raise ValueError(f"Target tool '{decision.target_tool}' is not registered in ToolRegistry.")
            
            tool = tool_registry.get(decision.target_tool)
            if not is_role_authorized_for_tool(user_role, tool.allowed_roles):
                raise ValueError(
                    f"User role '{user_role}' is not authorized to execute target tool '{decision.target_tool}'."
                )

    @staticmethod
    def _detect_circular_handoff(history: List[str], max_cycle_depth: int = 4) -> bool:
        """Detect recurring agent sequences (e.g. A, B, A, B)."""
        if len(history) < max_cycle_depth:
            return False
        recent = history[-max_cycle_depth:]
        # Check alternating pattern
        if recent[0] == recent[2] and recent[1] == recent[3] and recent[0] != recent[1]:
            return True
        return False
