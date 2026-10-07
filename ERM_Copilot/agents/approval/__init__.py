"""
LangGraph Conversational Approval Workflow Package for ERM Copilot.
"""
from ERM_Copilot.agents.approval.state import ApprovalState
from ERM_Copilot.agents.approval.tools import approve_or_reject_risk
from ERM_Copilot.agents.approval.graph import (
    ApprovalWorkflowGraph,
    ApprovalWorkflowAgent,
    approval_agent,
)

__all__ = [
    "ApprovalState",
    "approve_or_reject_risk",
    "ApprovalWorkflowGraph",
    "ApprovalWorkflowAgent",
    "approval_agent",
]
