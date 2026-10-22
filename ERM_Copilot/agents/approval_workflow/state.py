"""
Typed State and Session Definitions for the Goal-Driven Approval Workflow Agent.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger("ERM_Copilot.agents.approval_workflow.state")


class ApprovalGoal(str, Enum):
    """Recognized user goals for the approval workflow domain."""
    SHOW_PENDING_APPROVALS = "SHOW_PENDING_APPROVALS"
    SHOW_RISK_DETAILS = "SHOW_RISK_DETAILS"
    SHOW_AUDIT_TRAIL = "SHOW_AUDIT_TRAIL"
    CHECK_STATUS = "CHECK_STATUS"
    APPROVE_RISK = "APPROVE_RISK"
    REJECT_RISK = "REJECT_RISK"
    UNKNOWN = "UNKNOWN"


class ApprovalWorkflowState(str, Enum):
    """Lifecycle states for the Approval Workflow Agent interaction."""
    INITIATION = "INITIATION"
    COLLECTING_INPUTS = "COLLECTING_INPUTS"
    AWAITING_RISK_ID = "AWAITING_RISK_ID"
    AWAITING_ACTION = "AWAITING_ACTION"
    AWAITING_REMARK = "AWAITING_REMARK"
    EVALUATING_PRECONDITIONS = "EVALUATING_PRECONDITIONS"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    EXECUTING_MUTATION = "EXECUTING_MUTATION"
    COMPLETED = "COMPLETED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass
class ApprovalWorkflowSession:
    """
    Persistent multi-turn session tracking goal, collected parameters,
    loaded authoritative state, pending confirmation, and execution audit history.
    """
    session_id: str
    user_id: str
    user_role: str
    dept_id: Optional[int] = None
    dept_name: Optional[str] = None
    goal: Optional[ApprovalGoal] = None
    state: ApprovalWorkflowState = ApprovalWorkflowState.INITIATION
    risk_id: Optional[str] = None
    risk_register_id: Optional[int] = None
    action: Optional[Literal["approve", "reject"]] = None
    remark: Optional[str] = None
    risk_data: Optional[Dict[str, Any]] = None
    audit_trail_data: Optional[Dict[str, Any]] = None
    pending_queue_data: Optional[List[Dict[str, Any]]] = None
    policy_block_reason: Optional[str] = None
    missing_requirements: List[str] = field(default_factory=list)
    pending_confirmation: Optional[Dict[str, Any]] = None
    tool_call_history: List[Dict[str, Any]] = field(default_factory=list)
    api_result: Optional[Dict[str, Any]] = None
    last_user_message: str = ""
    step_count: int = 0
    max_steps: int = 10
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_terminal(self) -> bool:
        """Return True if session has reached a final state."""
        return self.state in (
            ApprovalWorkflowState.COMPLETED,
            ApprovalWorkflowState.CANCELLED,
            ApprovalWorkflowState.FAILED,
            ApprovalWorkflowState.POLICY_BLOCKED,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize session state for PostgreSQL checkpointing or JSON transport."""
        return {
            "session_id": self.session_id,
            "user_id": str(self.user_id),
            "user_role": self.user_role,
            "dept_id": self.dept_id,
            "dept_name": self.dept_name,
            "goal": self.goal.value if hasattr(self.goal, "value") else str(self.goal) if self.goal else None,
            "state": self.state.value if hasattr(self.state, "value") else str(self.state),
            "risk_id": self.risk_id,
            "risk_register_id": self.risk_register_id,
            "action": self.action,
            "remark": self.remark,
            "risk_data": self.risk_data,
            "audit_trail_data": self.audit_trail_data,
            "pending_queue_data": self.pending_queue_data,
            "policy_block_reason": self.policy_block_reason,
            "missing_requirements": list(self.missing_requirements),
            "pending_confirmation": self.pending_confirmation,
            "tool_call_history": self.tool_call_history,
            "api_result": self.api_result,
            "last_user_message": self.last_user_message,
            "step_count": self.step_count,
            "max_steps": self.max_steps,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ApprovalWorkflowSession:
        """Reconstruct session state from checkpoint dictionary."""
        goal_val = data.get("goal")
        goal_enum = None
        if goal_val:
            try:
                goal_enum = ApprovalGoal(goal_val)
            except ValueError:
                goal_enum = ApprovalGoal.UNKNOWN

        state_val = data.get("state", ApprovalWorkflowState.INITIATION.value)
        try:
            state_enum = ApprovalWorkflowState(state_val)
        except ValueError:
            state_enum = ApprovalWorkflowState.INITIATION

        return cls(
            session_id=str(data.get("session_id", "")),
            user_id=str(data.get("user_id", "")),
            user_role=str(data.get("user_role", "")),
            dept_id=data.get("dept_id"),
            dept_name=data.get("dept_name"),
            goal=goal_enum,
            state=state_enum,
            risk_id=data.get("risk_id"),
            risk_register_id=data.get("risk_register_id"),
            action=data.get("action"),
            remark=data.get("remark"),
            risk_data=data.get("risk_data"),
            audit_trail_data=data.get("audit_trail_data"),
            pending_queue_data=data.get("pending_queue_data"),
            policy_block_reason=data.get("policy_block_reason"),
            missing_requirements=list(data.get("missing_requirements") or []),
            pending_confirmation=data.get("pending_confirmation"),
            tool_call_history=list(data.get("tool_call_history") or []),
            api_result=data.get("api_result"),
            last_user_message=str(data.get("last_user_message", "")),
            step_count=int(data.get("step_count", 0)),
            max_steps=int(data.get("max_steps", 10)),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        )
