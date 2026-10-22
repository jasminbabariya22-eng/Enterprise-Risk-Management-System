"""
Goal Requirements and Precondition Analysis for Approval Workflows.
Determines what inputs and preconditions are mandatory for a given user goal.
"""
from __future__ import annotations

import logging
from typing import List, Tuple
from ERM_Copilot.agents.approval_workflow.state import ApprovalGoal, ApprovalWorkflowSession

logger = logging.getLogger("ERM_Copilot.agents.approval_workflow.requirements")


def get_goal_requirements(goal: ApprovalGoal) -> List[str]:
    """Return list of mandatory input fields for a given approval domain goal."""
    if goal == ApprovalGoal.SHOW_PENDING_APPROVALS:
        return []
    elif goal in (ApprovalGoal.SHOW_RISK_DETAILS, ApprovalGoal.SHOW_AUDIT_TRAIL, ApprovalGoal.CHECK_STATUS):
        return ["risk_id"]
    elif goal == ApprovalGoal.APPROVE_RISK:
        return ["risk_id"]
    elif goal == ApprovalGoal.REJECT_RISK:
        return ["risk_id", "remark"]
    return []


def check_missing_requirements(session: ApprovalWorkflowSession) -> List[str]:
    """Evaluate session state and identify missing requirements for the active goal."""
    missing: List[str] = []
    goal = session.goal

    if not goal:
        return ["goal"]

    if goal == ApprovalGoal.SHOW_PENDING_APPROVALS:
        return []

    if goal in (ApprovalGoal.SHOW_RISK_DETAILS, ApprovalGoal.SHOW_AUDIT_TRAIL, ApprovalGoal.CHECK_STATUS):
        if not session.risk_id or not str(session.risk_id).strip():
            missing.append("risk_id")
        return missing

    if goal == ApprovalGoal.APPROVE_RISK:
        if not session.risk_id or not str(session.risk_id).strip():
            missing.append("risk_id")
        if not session.remark or not str(session.remark).strip():
            missing.append("remark")
        return missing

    if goal == ApprovalGoal.REJECT_RISK:
        if not session.risk_id or not str(session.risk_id).strip():
            missing.append("risk_id")
        if not session.remark or not str(session.remark).strip():
            missing.append("remark")
        return missing

    return missing
