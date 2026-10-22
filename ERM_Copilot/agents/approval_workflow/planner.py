"""
Dynamic Goal-Driven Planner for the Approval Workflow Agent.
Evaluates user intent, workflow state, missing fields, tool history,
and governance policies to select the next legal, bounded action.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from ERM_Copilot.agents.approval_workflow.state import (
    ApprovalGoal,
    ApprovalWorkflowSession,
    ApprovalWorkflowState,
)
from ERM_Copilot.agents.approval_workflow.requirements import check_missing_requirements
from ERM_Copilot.agents.approval_workflow.validation import (
    validate_approval_preconditions,
    ApprovalValidationResult,
)

logger = logging.getLogger("ERM_Copilot.agents.approval_workflow.planner")


class ApprovalActionType(str, Enum):
    """Actions selected by the ApprovalWorkflowPlanner."""
    FETCH_PENDING_APPROVALS = "FETCH_PENDING_APPROVALS"
    FETCH_RISK_DETAILS = "FETCH_RISK_DETAILS"
    FETCH_AUDIT_TRAIL = "FETCH_AUDIT_TRAIL"
    REQUEST_MISSING_INPUT = "REQUEST_MISSING_INPUT"
    VALIDATE_AND_PREVIEW = "VALIDATE_AND_PREVIEW"
    EXECUTE_MUTATION = "EXECUTE_MUTATION"
    REPORT_POLICY_BLOCK = "REPORT_POLICY_BLOCK"
    RESPOND_AND_COMPLETE = "RESPOND_AND_COMPLETE"
    CANCEL_SESSION = "CANCEL_SESSION"
    FAIL_SAFELY = "FAIL_SAFELY"


@dataclass
class ApprovalPlanDecision:
    """Action plan decided by the planner."""
    action_type: ApprovalActionType
    target_tool: Optional[str] = None
    tool_arguments: Dict[str, Any] = None
    missing_field: Optional[str] = None
    policy_reason: Optional[str] = None
    validation_result: Optional[ApprovalValidationResult] = None
    reasoning: str = ""


class ApprovalWorkflowPlanner:
    """
    Goal-driven planner deciding the next step dynamically based on
    user goal, authoritative data loaded, and policy requirements.
    """

    @classmethod
    def plan_next_action(
        cls,
        session: ApprovalWorkflowSession,
        is_confirmation: bool = False,
        is_cancellation: bool = False,
    ) -> ApprovalPlanDecision:
        """Evaluate session state and select the next bounded action."""
        # 1. Step Limits check
        if session.step_count >= session.max_steps:
            return ApprovalPlanDecision(
                action_type=ApprovalActionType.FAIL_SAFELY,
                policy_reason="Workflow step limit reached. Please re-initiate if you wish to continue.",
                reasoning="Exceeded max workflow steps."
            )

        # 2. Cancellation check
        if is_cancellation:
            return ApprovalPlanDecision(
                action_type=ApprovalActionType.CANCEL_SESSION,
                reasoning="User explicitly commanded cancellation."
            )

        goal = session.goal

        # If goal is not identified
        if not goal or goal == ApprovalGoal.UNKNOWN:
            return ApprovalPlanDecision(
                action_type=ApprovalActionType.REQUEST_MISSING_INPUT,
                missing_field="goal",
                reasoning="User goal could not be mapped to an approval workflow intent."
            )

        # 3. Handle GOAL: SHOW_PENDING_APPROVALS
        if goal == ApprovalGoal.SHOW_PENDING_APPROVALS:
            if session.pending_queue_data is None:
                return ApprovalPlanDecision(
                    action_type=ApprovalActionType.FETCH_PENDING_APPROVALS,
                    target_tool="get_pending_approvals",
                    reasoning="Fetch pending approval queue for caller."
                )
            return ApprovalPlanDecision(
                action_type=ApprovalActionType.RESPOND_AND_COMPLETE,
                reasoning="Queue loaded, ready to format and present."
            )

        # 4. Check for missing required inputs (risk_id, remark)
        missing = check_missing_requirements(session)
        if "risk_id" in missing:
            return ApprovalPlanDecision(
                action_type=ApprovalActionType.REQUEST_MISSING_INPUT,
                missing_field="risk_id",
                reasoning="Risk identifier is required."
            )

        # 5. Handle GOAL: SHOW_AUDIT_TRAIL
        if goal == ApprovalGoal.SHOW_AUDIT_TRAIL:
            if session.audit_trail_data is None:
                return ApprovalPlanDecision(
                    action_type=ApprovalActionType.FETCH_AUDIT_TRAIL,
                    target_tool="get_risk_audit_trail",
                    reasoning=f"Fetch audit trail for risk {session.risk_id}."
                )
            return ApprovalPlanDecision(
                action_type=ApprovalActionType.RESPOND_AND_COMPLETE,
                reasoning="Audit trail loaded, ready to format."
            )

        # 6. Ensure risk_data is loaded for risk-specific goals
        if session.risk_data is None:
            return ApprovalPlanDecision(
                action_type=ApprovalActionType.FETCH_RISK_DETAILS,
                target_tool="get_risk_details",
                reasoning=f"Load authoritative risk record for {session.risk_id}."
            )

        # 7. Handle GOAL: SHOW_RISK_DETAILS
        if goal == ApprovalGoal.SHOW_RISK_DETAILS:
            return ApprovalPlanDecision(
                action_type=ApprovalActionType.RESPOND_AND_COMPLETE,
                reasoning="Risk details loaded, ready to format."
            )

        # 8. Handle GOAL: CHECK_STATUS
        if goal == ApprovalGoal.CHECK_STATUS:
            val_res = validate_approval_preconditions(
                user_role=session.user_role,
                user_dept_id=session.dept_id,
                risk_data=session.risk_data,
                action="approve",
                remark=session.remark,
            )
            return ApprovalPlanDecision(
                action_type=ApprovalActionType.RESPOND_AND_COMPLETE,
                validation_result=val_res,
                reasoning="Status and approval eligibility evaluated."
            )

        # 9. Handle missing remark check
        if goal in (ApprovalGoal.APPROVE_RISK, ApprovalGoal.REJECT_RISK):
            if "remark" in missing:
                return ApprovalPlanDecision(
                    action_type=ApprovalActionType.REQUEST_MISSING_INPUT,
                    missing_field="remark",
                    reasoning=f"Remark is required for {goal.value}."
                )

        # 10. Handle GOAL: APPROVE_RISK or REJECT_RISK
        if goal in (ApprovalGoal.APPROVE_RISK, ApprovalGoal.REJECT_RISK):
            action_name = "approve" if goal == ApprovalGoal.APPROVE_RISK else "reject"
            val_res = validate_approval_preconditions(
                user_role=session.user_role,
                user_dept_id=session.dept_id,
                risk_data=session.risk_data,
                action=action_name,
                remark=session.remark,
            )

            # Policy block if preconditions fail
            if not val_res.is_valid:
                return ApprovalPlanDecision(
                    action_type=ApprovalActionType.REPORT_POLICY_BLOCK,
                    policy_reason=val_res.policy_block_reason,
                    validation_result=val_res,
                    reasoning=f"Preconditions failed for {action_name}: {val_res.policy_block_reason}"
                )

            # If currently in AWAITING_CONFIRMATION state
            if session.state == ApprovalWorkflowState.AWAITING_CONFIRMATION:
                if is_confirmation:
                    return ApprovalPlanDecision(
                        action_type=ApprovalActionType.EXECUTE_MUTATION,
                        target_tool="approve_or_reject_risk",
                        validation_result=val_res,
                        reasoning=f"User confirmed {action_name}. Ready to execute mutation."
                    )
                else:
                    # Ambiguous or non-confirm message: re-render preview
                    return ApprovalPlanDecision(
                        action_type=ApprovalActionType.VALIDATE_AND_PREVIEW,
                        validation_result=val_res,
                        reasoning="User provided input during confirmation; re-showing confirmation preview."
                    )

            # Not yet awaiting confirmation: present preview and wait for confirmation
            return ApprovalPlanDecision(
                action_type=ApprovalActionType.VALIDATE_AND_PREVIEW,
                validation_result=val_res,
                reasoning=f"Preconditions passed. Request confirmation before executing {action_name}."
            )

        # Default fallback
        return ApprovalPlanDecision(
            action_type=ApprovalActionType.RESPOND_AND_COMPLETE,
            reasoning="Default completion."
        )
