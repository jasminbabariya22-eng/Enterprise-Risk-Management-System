"""
Enterprise Risk Management (ERM) - Treatment Management Goal Requirements.
Defines required vs optional fields and defaults per treatment goal.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from ERM_Copilot.agents.treatment.state import TreatmentGoal, TreatmentSession


REQUIRED_FIELDS_BY_GOAL: Dict[TreatmentGoal, List[str]] = {
    TreatmentGoal.ADD_TREATMENT: [
        "target_risk_id",
        "action_plan",
        "action_owner_id",
    ],
    TreatmentGoal.UPDATE_PROGRESS: [
        "treatment_id",
        "progress",
    ],
    TreatmentGoal.REASSIGN_OWNER: [
        "treatment_id",
        "new_action_owner_id",
    ],
    TreatmentGoal.LIST_TREATMENTS: [
        "target_risk_id",
    ],
    TreatmentGoal.SHOW_TREATMENT_DETAILS: [
        "treatment_id",
    ],
}

OPTIONAL_FIELDS_BY_GOAL: Dict[TreatmentGoal, List[str]] = {
    TreatmentGoal.ADD_TREATMENT: [
        "target_date",
        "progress",
        "action_status_id",
    ],
    TreatmentGoal.UPDATE_PROGRESS: [
        "remarks",
    ],
    TreatmentGoal.REASSIGN_OWNER: [
        "remarks",
    ],
    TreatmentGoal.LIST_TREATMENTS: [
        "dept_id",
    ],
    TreatmentGoal.SHOW_TREATMENT_DETAILS: [],
}


def get_required_fields_for_goal(goal: TreatmentGoal) -> List[str]:
    """Return list of mandatory field names for given goal."""
    return REQUIRED_FIELDS_BY_GOAL.get(goal, [])


def get_optional_fields_for_goal(goal: TreatmentGoal) -> List[str]:
    """Return list of optional field names for given goal."""
    return OPTIONAL_FIELDS_BY_GOAL.get(goal, [])


def check_missing_requirements(session: TreatmentSession) -> List[str]:
    """
    Deterministically assess which mandatory fields are still missing for the session's goal.
    """
    goal = session.goal
    if not goal or goal == TreatmentGoal.UNKNOWN:
        return ["goal"]

    missing: List[str] = []

    if goal == TreatmentGoal.ADD_TREATMENT:
        if not session.target_risk_id and not session.target_risk_register_id:
            missing.append("target_risk_id")
        if not session.action_plan or len(session.action_plan.strip()) < 5:
            missing.append("action_plan")
        if session.action_owner_id is None:
            missing.append("action_owner_id")

    elif goal == TreatmentGoal.UPDATE_PROGRESS:
        if session.treatment_id is None:
            missing.append("treatment_id")
        if session.progress is None:
            missing.append("progress")

    elif goal == TreatmentGoal.REASSIGN_OWNER:
        if session.treatment_id is None:
            missing.append("treatment_id")
        if session.new_action_owner_id is None:
            missing.append("new_action_owner_id")

    elif goal == TreatmentGoal.LIST_TREATMENTS:
        if not session.target_risk_id and not session.target_risk_register_id and not session.dept_id:
            missing.append("target_risk_id")

    elif goal == TreatmentGoal.SHOW_TREATMENT_DETAILS:
        if session.treatment_id is None:
            missing.append("treatment_id")

    return missing
