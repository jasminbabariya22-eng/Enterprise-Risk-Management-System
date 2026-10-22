"""
Enterprise Risk Management (ERM) - Dynamic Bounded Planner for Treatment Management Agent.
Selects next bounded tool or conversational action based on goal, completeness, entity resolution, and validation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ERM_Copilot.agents.treatment.completeness import assess_treatment_completeness
from ERM_Copilot.agents.treatment.merge import apply_documented_treatment_defaults
from ERM_Copilot.agents.treatment.state import (
    TreatmentGoal,
    TreatmentSession,
    TreatmentWorkflowState,
)
from ERM_Copilot.agents.treatment.validation import (
    TreatmentValidationResult,
    validate_treatment_action,
)

logger = logging.getLogger("ERM_Copilot.agents.treatment.planner")


class TreatmentActionType(str, Enum):
    """Next bounded action decided by the planner."""
    REQUEST_MISSING_INPUT = "REQUEST_MISSING_INPUT"
    FETCH_RISK_INFO = "FETCH_RISK_INFO"
    FETCH_TREATMENT_DETAILS = "FETCH_TREATMENT_DETAILS"
    FETCH_ELIGIBLE_OWNERS = "FETCH_ELIGIBLE_OWNERS"
    FETCH_TREATMENTS_LIST = "FETCH_TREATMENTS_LIST"
    VALIDATE_AND_PREVIEW = "VALIDATE_AND_PREVIEW"
    EXECUTE_MUTATION = "EXECUTE_MUTATION"
    RESPOND_AND_COMPLETE = "RESPOND_AND_COMPLETE"
    REPORT_POLICY_BLOCK = "REPORT_POLICY_BLOCK"
    FAIL_SAFELY = "FAIL_SAFELY"
    CANCEL_SESSION = "CANCEL_SESSION"


@dataclass
class TreatmentPlanDecision:
    """Structured decision returned by the treatment planner."""
    action_type: TreatmentActionType
    missing_field: Optional[str] = None
    target_tool: Optional[str] = None
    policy_reason: Optional[str] = None
    validation_result: Optional[TreatmentValidationResult] = None
    reasoning: str = ""


class TreatmentWorkflowPlanner:
    """Bounded, goal-driven planner for Risk Treatment & Action Plan lifecycle."""

    @classmethod
    def plan(
        cls,
        session: TreatmentSession,
        is_confirmation: bool = False,
        is_cancellation: bool = False,
    ) -> TreatmentPlanDecision:
        """Evaluate session state and select the next bounded action."""
        # 1. Step Limits Check
        if session.step_count >= session.max_steps:
            return TreatmentPlanDecision(
                action_type=TreatmentActionType.FAIL_SAFELY,
                policy_reason="Workflow step limit reached. Please re-initiate if you wish to continue.",
                reasoning="Exceeded max workflow steps.",
            )

        # 2. Cancellation Check
        if is_cancellation:
            return TreatmentPlanDecision(
                action_type=TreatmentActionType.CANCEL_SESSION,
                reasoning="User explicitly commanded cancellation.",
            )

        goal = session.goal
        if not goal or goal == TreatmentGoal.UNKNOWN:
            return TreatmentPlanDecision(
                action_type=TreatmentActionType.REQUEST_MISSING_INPUT,
                missing_field="goal",
                reasoning="Goal could not be identified.",
            )

        # -------------------------------------------------------------
        # GOAL: LIST_TREATMENTS
        # -------------------------------------------------------------
        if goal == TreatmentGoal.LIST_TREATMENTS:
            if not session.target_risk_id and not session.dept_id:
                return TreatmentPlanDecision(
                    action_type=TreatmentActionType.REQUEST_MISSING_INPUT,
                    missing_field="target_risk_id",
                    reasoning="Target risk is required to query treatment action plans.",
                )
            if not session.available_treatments:
                return TreatmentPlanDecision(
                    action_type=TreatmentActionType.FETCH_TREATMENTS_LIST,
                    target_tool="get_treatments_for_risk",
                    reasoning=f"Query active treatments for {session.target_risk_id or session.dept_id}.",
                )
            return TreatmentPlanDecision(
                action_type=TreatmentActionType.RESPOND_AND_COMPLETE,
                reasoning="Treatments loaded, ready to format and display.",
            )

        # -------------------------------------------------------------
        # GOAL: SHOW_TREATMENT_DETAILS
        # -------------------------------------------------------------
        if goal == TreatmentGoal.SHOW_TREATMENT_DETAILS:
            if session.treatment_id is None:
                return TreatmentPlanDecision(
                    action_type=TreatmentActionType.REQUEST_MISSING_INPUT,
                    missing_field="treatment_id",
                    reasoning="Treatment ID is required.",
                )
            if not session.action_plan:
                return TreatmentPlanDecision(
                    action_type=TreatmentActionType.FETCH_TREATMENT_DETAILS,
                    target_tool="get_treatment_details",
                    reasoning=f"Fetch record for treatment #{session.treatment_id}.",
                )
            return TreatmentPlanDecision(
                action_type=TreatmentActionType.RESPOND_AND_COMPLETE,
                reasoning="Treatment details loaded, ready to present.",
            )

        # -------------------------------------------------------------
        # GOAL: ADD_TREATMENT
        # -------------------------------------------------------------
        if goal == TreatmentGoal.ADD_TREATMENT:
            # Check target risk
            if not session.target_risk_id and not session.target_risk_register_id:
                return TreatmentPlanDecision(
                    action_type=TreatmentActionType.REQUEST_MISSING_INPUT,
                    missing_field="target_risk_id",
                    reasoning="Target risk is required before an action plan can be attached.",
                )

            # Load risk details if not loaded
            if session.risk_data is None:
                return TreatmentPlanDecision(
                    action_type=TreatmentActionType.FETCH_RISK_INFO,
                    target_tool="get_risk_info",
                    reasoning=f"Load authoritative risk record for {session.target_risk_id}.",
                )

            # Early validation: Authorization & Department Isolation on Target Risk
            risk_val = validate_treatment_action(session=session, risk_data=session.risk_data)
            if not risk_val.is_valid and risk_val.policy_blocked:
                return TreatmentPlanDecision(
                    action_type=TreatmentActionType.REPORT_POLICY_BLOCK,
                    policy_reason=risk_val.policy_block_reason,
                    validation_result=risk_val,
                    reasoning=f"Governance policy blocked: {risk_val.policy_block_reason}",
                )

            # Check action plan description
            if not session.action_plan or len(session.action_plan.strip()) < 5:
                return TreatmentPlanDecision(
                    action_type=TreatmentActionType.REQUEST_MISSING_INPUT,
                    missing_field="action_plan",
                    reasoning="Action plan description is required.",
                )

            # Resolve Action Owner
            if session.action_owner_id is None:
                if not session.available_action_owners:
                    return TreatmentPlanDecision(
                        action_type=TreatmentActionType.FETCH_ELIGIBLE_OWNERS,
                        target_tool="get_department_action_owners",
                        reasoning="Fetch candidate action owners for the risk department.",
                    )
                # If owner name is provided, try resolving
                if session.action_owner_name:
                    resolved_owner = None
                    term = session.action_owner_name.strip().lower()
                    for o in session.available_action_owners:
                        full_name = str(o.get("full_name") or "").lower()
                        log_id = str(o.get("log_id") or "").lower()
                        if term in full_name or term in log_id:
                            resolved_owner = o
                            break
                    if resolved_owner:
                        session.action_owner_id = resolved_owner.get("user_id") or resolved_owner.get("id")
                        session.action_owner_name = resolved_owner.get("full_name") or resolved_owner.get("log_id")
                        session.provenance["action_owner_id"] = "resolved_from_name"
                    else:
                        return TreatmentPlanDecision(
                            action_type=TreatmentActionType.REQUEST_MISSING_INPUT,
                            missing_field="action_owner_id",
                            reasoning=f"Could not find registered action owner matching '{session.action_owner_name}'.",
                        )
                else:
                    return TreatmentPlanDecision(
                        action_type=TreatmentActionType.REQUEST_MISSING_INPUT,
                        missing_field="action_owner_id",
                        reasoning="Action Owner assignment is required.",
                    )

            # Apply documented defaults (target date +30d, progress 0%)
            apply_documented_treatment_defaults(session)

            # Preconditions Validation
            val_res = validate_treatment_action(
                session=session,
                risk_data=session.risk_data,
            )
            if not val_res.is_valid:
                return TreatmentPlanDecision(
                    action_type=TreatmentActionType.REPORT_POLICY_BLOCK,
                    policy_reason=val_res.policy_block_reason,
                    validation_result=val_res,
                    reasoning=f"Validation failed: {val_res.policy_block_reason}",
                )

            # Confirmation handling
            if session.state == TreatmentWorkflowState.AWAITING_CONFIRMATION:
                if is_confirmation:
                    return TreatmentPlanDecision(
                        action_type=TreatmentActionType.EXECUTE_MUTATION,
                        reasoning="User confirmed action plan addition; executing mutation.",
                    )
                else:
                    return TreatmentPlanDecision(
                        action_type=TreatmentActionType.VALIDATE_AND_PREVIEW,
                        validation_result=val_res,
                        reasoning="Awaiting explicit user confirmation.",
                    )

            return TreatmentPlanDecision(
                action_type=TreatmentActionType.VALIDATE_AND_PREVIEW,
                validation_result=val_res,
                reasoning="All requirements validated; prepare preview for user confirmation.",
            )

        # -------------------------------------------------------------
        # GOAL: UPDATE_PROGRESS
        # -------------------------------------------------------------
        if goal == TreatmentGoal.UPDATE_PROGRESS:
            if session.treatment_id is None:
                return TreatmentPlanDecision(
                    action_type=TreatmentActionType.REQUEST_MISSING_INPUT,
                    missing_field="treatment_id",
                    reasoning="Treatment ID is required for progress update.",
                )

            if not session.action_plan:
                return TreatmentPlanDecision(
                    action_type=TreatmentActionType.FETCH_TREATMENT_DETAILS,
                    target_tool="get_treatment_details",
                    reasoning=f"Fetch treatment #{session.treatment_id} to view current progress.",
                )

            # Early validation on target treatment
            if session.api_result:
                trt_val = validate_treatment_action(session=session, treatment_data=session.api_result)
                if not trt_val.is_valid and trt_val.policy_blocked:
                    return TreatmentPlanDecision(
                        action_type=TreatmentActionType.REPORT_POLICY_BLOCK,
                        policy_reason=trt_val.policy_block_reason,
                        validation_result=trt_val,
                        reasoning=f"Governance policy blocked: {trt_val.policy_block_reason}",
                    )

            if "progress" not in session.provenance:
                return TreatmentPlanDecision(
                    action_type=TreatmentActionType.REQUEST_MISSING_INPUT,
                    missing_field="progress",
                    reasoning="Progress percentage is required.",
                )

            val_res = validate_treatment_action(
                session=session,
                treatment_data=session.to_dict(),
            )
            if not val_res.is_valid:
                return TreatmentPlanDecision(
                    action_type=TreatmentActionType.REPORT_POLICY_BLOCK,
                    policy_reason=val_res.policy_block_reason,
                    validation_result=val_res,
                    reasoning=f"Validation failed: {val_res.policy_block_reason}",
                )

            if session.state == TreatmentWorkflowState.AWAITING_CONFIRMATION:
                if is_confirmation:
                    return TreatmentPlanDecision(
                        action_type=TreatmentActionType.EXECUTE_MUTATION,
                        reasoning="User confirmed progress update; executing mutation.",
                    )
                else:
                    return TreatmentPlanDecision(
                        action_type=TreatmentActionType.VALIDATE_AND_PREVIEW,
                        validation_result=val_res,
                        reasoning="Awaiting explicit user confirmation.",
                    )

            return TreatmentPlanDecision(
                action_type=TreatmentActionType.VALIDATE_AND_PREVIEW,
                validation_result=val_res,
                reasoning="Validated progress update; prepare preview for confirmation.",
            )

        # -------------------------------------------------------------
        # GOAL: REASSIGN_OWNER
        # -------------------------------------------------------------
        if goal == TreatmentGoal.REASSIGN_OWNER:
            if session.treatment_id is None:
                return TreatmentPlanDecision(
                    action_type=TreatmentActionType.REQUEST_MISSING_INPUT,
                    missing_field="treatment_id",
                    reasoning="Treatment ID is required for reassignment.",
                )

            if not session.action_plan:
                return TreatmentPlanDecision(
                    action_type=TreatmentActionType.FETCH_TREATMENT_DETAILS,
                    target_tool="get_treatment_details",
                    reasoning=f"Fetch treatment #{session.treatment_id} to view current owner.",
                )

            # Early validation on target treatment
            if session.api_result:
                trt_val = validate_treatment_action(session=session, treatment_data=session.api_result)
                if not trt_val.is_valid and trt_val.policy_blocked:
                    return TreatmentPlanDecision(
                        action_type=TreatmentActionType.REPORT_POLICY_BLOCK,
                        policy_reason=trt_val.policy_block_reason,
                        validation_result=trt_val,
                        reasoning=f"Governance policy blocked: {trt_val.policy_block_reason}",
                    )

            if session.new_action_owner_id is None:
                if not session.available_action_owners:
                    return TreatmentPlanDecision(
                        action_type=TreatmentActionType.FETCH_ELIGIBLE_OWNERS,
                        target_tool="get_department_action_owners",
                        reasoning="Fetch candidate action owners for reassignment.",
                    )
                if session.new_action_owner_name:
                    term = session.new_action_owner_name.strip().lower()
                    resolved = None
                    for o in session.available_action_owners:
                        full_name = str(o.get("full_name") or "").lower()
                        log_id = str(o.get("log_id") or "").lower()
                        if term in full_name or term in log_id:
                            resolved = o
                            break
                    if resolved:
                        session.new_action_owner_id = resolved.get("user_id") or resolved.get("id")
                        session.new_action_owner_name = resolved.get("full_name") or resolved.get("log_id")
                        session.provenance["new_action_owner_id"] = "resolved_from_name"
                    else:
                        return TreatmentPlanDecision(
                            action_type=TreatmentActionType.REQUEST_MISSING_INPUT,
                            missing_field="new_action_owner_id",
                            reasoning=f"Could not find candidate owner matching '{session.new_action_owner_name}'.",
                        )
                else:
                    return TreatmentPlanDecision(
                        action_type=TreatmentActionType.REQUEST_MISSING_INPUT,
                        missing_field="new_action_owner_id",
                        reasoning="Designating a new Action Owner is required.",
                    )

            val_res = validate_treatment_action(
                session=session,
                treatment_data=session.to_dict(),
            )
            if not val_res.is_valid:
                return TreatmentPlanDecision(
                    action_type=TreatmentActionType.REPORT_POLICY_BLOCK,
                    policy_reason=val_res.policy_block_reason,
                    validation_result=val_res,
                    reasoning=f"Validation failed: {val_res.policy_block_reason}",
                )

            if session.state == TreatmentWorkflowState.AWAITING_CONFIRMATION:
                if is_confirmation:
                    return TreatmentPlanDecision(
                        action_type=TreatmentActionType.EXECUTE_MUTATION,
                        reasoning="User confirmed reassignment; executing mutation.",
                    )
                else:
                    return TreatmentPlanDecision(
                        action_type=TreatmentActionType.VALIDATE_AND_PREVIEW,
                        validation_result=val_res,
                        reasoning="Awaiting explicit user confirmation.",
                    )

            return TreatmentPlanDecision(
                action_type=TreatmentActionType.VALIDATE_AND_PREVIEW,
                validation_result=val_res,
                reasoning="Validated reassignment; prepare preview for confirmation.",
            )

        return TreatmentPlanDecision(
            action_type=TreatmentActionType.FAIL_SAFELY,
            policy_reason="Unsupported or unrecognized treatment goal.",
            reasoning="Unrecognized goal.",
        )
