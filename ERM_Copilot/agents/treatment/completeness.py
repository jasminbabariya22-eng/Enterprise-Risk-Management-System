"""
Enterprise Risk Management (ERM) - Deterministic Completeness Assessment for Treatment Agent.
Evaluates whether a session has satisfied all requirements and identifies next inputs or entity resolutions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
from ERM_Copilot.agents.treatment.requirements import check_missing_requirements
from ERM_Copilot.agents.treatment.state import TreatmentGoal, TreatmentSession


@dataclass
class TreatmentCompletenessAssessment:
    """Deterministic assessment of session completeness and entity resolution status."""
    is_complete: bool
    missing_fields: List[str] = field(default_factory=list)
    unresolved_entities: List[str] = field(default_factory=list)
    next_step: Optional[str] = None


def assess_treatment_completeness(session: TreatmentSession) -> TreatmentCompletenessAssessment:
    """
    Evaluate if all mandatory parameters and entity resolutions are satisfied for the current goal.
    """
    goal = session.goal
    if not goal or goal == TreatmentGoal.UNKNOWN:
        return TreatmentCompletenessAssessment(
            is_complete=False,
            missing_fields=["goal"],
            next_step="request_goal",
        )

    missing = check_missing_requirements(session)
    unresolved: List[str] = []

    # Check entity resolution for target risk
    if goal in (TreatmentGoal.ADD_TREATMENT, TreatmentGoal.LIST_TREATMENTS):
        if session.target_risk_id and not session.target_risk_register_id:
            unresolved.append("target_risk")

    # Check entity resolution for action owner in ADD_TREATMENT
    if goal == TreatmentGoal.ADD_TREATMENT:
        if session.action_owner_name and session.action_owner_id is None:
            unresolved.append("action_owner")

    # Check entity resolution for new action owner in REASSIGN_OWNER
    if goal == TreatmentGoal.REASSIGN_OWNER:
        if session.new_action_owner_name and session.new_action_owner_id is None:
            unresolved.append("new_action_owner")

    # Check treatment record resolution for UPDATE_PROGRESS / REASSIGN_OWNER
    if goal in (TreatmentGoal.UPDATE_PROGRESS, TreatmentGoal.REASSIGN_OWNER, TreatmentGoal.SHOW_TREATMENT_DETAILS):
        if session.treatment_id is not None and not session.action_plan:
            unresolved.append("treatment_details")

    is_complete = (len(missing) == 0 and len(unresolved) == 0)

    # Determine recommended next step
    next_step: Optional[str] = None
    if missing:
        next_step = f"request_{missing[0]}"
    elif unresolved:
        next_step = f"resolve_{unresolved[0]}"
    else:
        next_step = "ready_for_validation"

    return TreatmentCompletenessAssessment(
        is_complete=is_complete,
        missing_fields=missing,
        unresolved_entities=unresolved,
        next_step=next_step,
    )
