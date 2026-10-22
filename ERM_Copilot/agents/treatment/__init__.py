"""
ERM Risk Treatment & Action Plan Management Package.
Goal-driven, adaptive agent coordinating ISO-31000 risk treatments,
mitigation action plans, progress updates, owner reassignments, and audit inspections.
"""
from ERM_Copilot.agents.treatment.agent import (
    TreatmentManagementAgent,
    treatment_management_agent,
)
from ERM_Copilot.agents.treatment.state import (
    TreatmentGoal,
    TreatmentWorkflowState,
    TreatmentState,
    TreatmentSession,
    parse_date_string,
    parse_progress_percentage,
    extract_risk_identifier,
    extract_treatment_id,
)
from ERM_Copilot.agents.treatment.requirements import (
    check_missing_requirements,
    get_required_fields_for_goal,
)
from ERM_Copilot.agents.treatment.extraction import (
    ExtractedTreatmentInputs,
    extract_treatment_inputs,
    is_add_treatment_trigger,
    is_update_progress_trigger,
    is_reassign_owner_trigger,
    is_list_treatments_trigger,
    is_show_details_trigger,
    is_user_confirming,
    is_user_cancelling,
)
from ERM_Copilot.agents.treatment.merge import (
    merge_treatment_inputs,
    apply_documented_treatment_defaults,
)
from ERM_Copilot.agents.treatment.completeness import (
    TreatmentCompletenessAssessment,
    assess_treatment_completeness,
)
from ERM_Copilot.agents.treatment.planner import (
    TreatmentActionType,
    TreatmentPlanDecision,
    TreatmentWorkflowPlanner,
)
from ERM_Copilot.agents.treatment.validation import (
    TreatmentValidationResult,
    validate_treatment_action,
)
from ERM_Copilot.agents.treatment.execution import (
    bind_pending_confirmation,
    execute_confirmed_treatment_decision,
    generate_confirmation_token,
    verify_confirmation_token,
    verify_confirmation_integrity,
    compute_confirmation_digest,
)
from ERM_Copilot.agents.treatment.prompts import (
    build_treatment_preview,
    format_add_treatment_preview,
    format_update_progress_preview,
    format_reassign_owner_preview,
    format_add_treatment_success,
    format_update_progress_success,
    format_reassign_owner_success,
    format_list_treatments_response,
    format_treatment_details_response,
    format_cancellation_response,
    format_policy_block_response,
    prompt_risk_selection,
    prompt_action_plan_step,
    prompt_action_owner_step,
    prompt_target_date_step,
    prompt_progress_step,
)
from ERM_Copilot.agents.treatment.tools import (
    fetch_risk_info,
    fetch_treatment_details,
    fetch_treatments_for_risk,
    fetch_eligible_action_owners,
    add_risk_treatment_tool,
    update_treatment_progress_tool,
    reassign_treatment_owner_tool,
    get_treatments_for_risk_tool,
)

__all__ = [
    # Agent
    "TreatmentManagementAgent",
    "treatment_management_agent",
    # State
    "TreatmentGoal",
    "TreatmentWorkflowState",
    "TreatmentState",
    "TreatmentSession",
    "parse_date_string",
    "parse_progress_percentage",
    "extract_risk_identifier",
    "extract_treatment_id",
    # Requirements
    "check_missing_requirements",
    "get_required_fields_for_goal",
    # Extraction
    "ExtractedTreatmentInputs",
    "extract_treatment_inputs",
    "is_add_treatment_trigger",
    "is_update_progress_trigger",
    "is_reassign_owner_trigger",
    "is_list_treatments_trigger",
    "is_show_details_trigger",
    "is_user_confirming",
    "is_user_cancelling",
    # Merge
    "merge_treatment_inputs",
    "apply_documented_treatment_defaults",
    # Completeness
    "TreatmentCompletenessAssessment",
    "assess_treatment_completeness",
    # Planner
    "TreatmentActionType",
    "TreatmentPlanDecision",
    "TreatmentWorkflowPlanner",
    # Validation
    "TreatmentValidationResult",
    "validate_treatment_action",
    # Execution
    "bind_pending_confirmation",
    "execute_confirmed_treatment_decision",
    "generate_confirmation_token",
    "verify_confirmation_token",
    "verify_confirmation_integrity",
    "compute_confirmation_digest",
    # Prompts
    "build_treatment_preview",
    "format_add_treatment_preview",
    "format_update_progress_preview",
    "format_reassign_owner_preview",
    "format_add_treatment_success",
    "format_update_progress_success",
    "format_reassign_owner_success",
    "format_list_treatments_response",
    "format_treatment_details_response",
    "format_cancellation_response",
    "format_policy_block_response",
    "prompt_risk_selection",
    "prompt_action_plan_step",
    "prompt_action_owner_step",
    "prompt_target_date_step",
    "prompt_progress_step",
    # Tools
    "fetch_risk_info",
    "fetch_treatment_details",
    "fetch_treatments_for_risk",
    "fetch_eligible_action_owners",
    "add_risk_treatment_tool",
    "update_treatment_progress_tool",
    "reassign_treatment_owner_tool",
    "get_treatments_for_risk_tool",
]

