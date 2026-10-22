"""
Goal-Driven Governance Approval Workflow Agent Package.
"""
from ERM_Copilot.agents.approval_workflow.agent import (
    ApprovalWorkflowAgent,
    approval_workflow_agent,
)
from ERM_Copilot.agents.approval_workflow.state import (
    ApprovalGoal,
    ApprovalWorkflowSession,
    ApprovalWorkflowState,
)
from ERM_Copilot.agents.approval_workflow.planner import (
    ApprovalActionType,
    ApprovalWorkflowPlanner,
    ApprovalPlanDecision,
)
from ERM_Copilot.agents.approval_workflow.validation import (
    ApprovalValidationResult,
    validate_approval_preconditions,
    resolve_role_tier,
)
from ERM_Copilot.agents.approval_workflow.extraction import (
    ExtractedApprovalInputs,
    extract_goal_and_inputs,
    extract_risk_id,
    extract_remark,
    is_user_confirming,
    is_user_cancelling,
)
from ERM_Copilot.agents.approval_workflow.tools import (
    fetch_pending_approvals,
    fetch_risk_details,
    fetch_risk_audit_trail,
    execute_governed_approval_decision,
)

__all__ = [
    "ApprovalWorkflowAgent",
    "approval_workflow_agent",
    "ApprovalGoal",
    "ApprovalWorkflowSession",
    "ApprovalWorkflowState",
    "ApprovalActionType",
    "ApprovalWorkflowPlanner",
    "ApprovalPlanDecision",
    "ApprovalValidationResult",
    "validate_approval_preconditions",
    "resolve_role_tier",
    "ExtractedApprovalInputs",
    "extract_goal_and_inputs",
    "extract_risk_id",
    "extract_remark",
    "is_user_confirming",
    "is_user_cancelling",
    "fetch_pending_approvals",
    "fetch_risk_details",
    "fetch_risk_audit_trail",
    "execute_governed_approval_decision",
]
