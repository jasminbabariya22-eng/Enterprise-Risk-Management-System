"""
Production Workflow State Contracts & Legal Transitions for ERM Copilot.
Declares typed state schemas, lifecycle statuses, transition validators,
and identity-bound recovery metadata.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field, field_validator


class WorkflowStatus(str, Enum):
    """Lifecycle statuses for agentic workflows."""
    RUNNING = "RUNNING"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    WAITING_FOR_CONFIRMATION = "WAITING_FOR_CONFIRMATION"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class WorkflowType(str, Enum):
    """Categorization of agentic workflows."""
    RISK_CREATION = "RISK_CREATION"
    TREATMENT_MANAGEMENT = "TREATMENT_MANAGEMENT"
    APPROVAL_GOVERNANCE = "APPROVAL_GOVERNANCE"
    AUTONOMOUS_PLANNING = "AUTONOMOUS_PLANNING"
    GENERAL_QUERY = "GENERAL_QUERY"


class WorkflowTransitionError(Exception):
    """Raised when an illegal workflow state transition is attempted."""
    def __init__(self, from_status: str, to_status: str, reason: str = ""):
        self.from_status = from_status
        self.to_status = to_status
        self.reason = reason
        super().__init__(f"Illegal state transition from '{from_status}' to '{to_status}': {reason}")


# Defined legal transition graph
LEGAL_TRANSITIONS: Dict[WorkflowStatus, Set[WorkflowStatus]] = {
    WorkflowStatus.RUNNING: {
        WorkflowStatus.RUNNING,
        WorkflowStatus.WAITING_FOR_INPUT,
        WorkflowStatus.WAITING_FOR_CONFIRMATION,
        WorkflowStatus.WAITING_FOR_APPROVAL,
        WorkflowStatus.PAUSED,
        WorkflowStatus.COMPLETED,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
        WorkflowStatus.EXPIRED,
    },
    WorkflowStatus.WAITING_FOR_INPUT: {
        WorkflowStatus.RUNNING,
        WorkflowStatus.PAUSED,
        WorkflowStatus.CANCELLED,
        WorkflowStatus.FAILED,
        WorkflowStatus.EXPIRED,
    },
    WorkflowStatus.WAITING_FOR_CONFIRMATION: {
        WorkflowStatus.RUNNING,
        WorkflowStatus.PAUSED,
        WorkflowStatus.CANCELLED,
        WorkflowStatus.FAILED,
        WorkflowStatus.EXPIRED,
    },
    WorkflowStatus.WAITING_FOR_APPROVAL: {
        WorkflowStatus.RUNNING,
        WorkflowStatus.PAUSED,
        WorkflowStatus.CANCELLED,
        WorkflowStatus.FAILED,
        WorkflowStatus.EXPIRED,
    },
    WorkflowStatus.PAUSED: {
        WorkflowStatus.RUNNING,
        WorkflowStatus.WAITING_FOR_INPUT,
        WorkflowStatus.WAITING_FOR_CONFIRMATION,
        WorkflowStatus.CANCELLED,
        WorkflowStatus.FAILED,
        WorkflowStatus.EXPIRED,
    },
    # Terminal states have no valid onward transitions
    WorkflowStatus.COMPLETED: set(),
    WorkflowStatus.FAILED: set(),
    WorkflowStatus.CANCELLED: set(),
    WorkflowStatus.EXPIRED: set(),
}


class AgentWorkflowState(BaseModel):
    """
    Typed, persistent workflow state contract.
    Shared across the Master Orchestrator and specialized ERM subagents.
    """
    workflow_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = Field(..., description="Unique user::session key for session isolation")
    workflow_type: WorkflowType = Field(default=WorkflowType.GENERAL_QUERY)
    workflow_status: WorkflowStatus = Field(default=WorkflowStatus.RUNNING)
    
    # Ownership & Tenancy (Immutable authenticated context reference)
    owner_user_id: str = Field(..., description="Authenticated user ID who initiated workflow")
    owner_role: str = Field(..., description="Canonical ERM role of initiator")
    dept_id: Optional[int] = None
    dept_name: Optional[str] = None
    
    # Execution Tracking
    current_agent: str = Field(default="erm_copilot_agent")
    current_step: str = Field(default="INITIATION")
    step_count: int = Field(default=1)
    max_steps: int = Field(default=15)
    agent_handoff_history: List[str] = Field(default_factory=list)
    
    # Target Entity & Field Collection
    risk_id: Optional[str] = None
    collected_fields: Dict[str, Any] = Field(default_factory=dict)
    missing_fields: List[str] = Field(default_factory=list)
    
    # Governance & Confirmation
    pending_action: Optional[Dict[str, Any]] = None
    confirmation_token: Optional[str] = None
    action_fingerprint: Optional[str] = None
    
    # History & Recovery
    last_completed_step: Optional[str] = None
    last_error_code: Optional[str] = None
    last_error_message: Optional[str] = None
    recovery_attempts: int = 0
    idempotency_key: Optional[str] = None
    
    # Versioning & Lifecycle
    state_version: int = Field(default=1, description="Optimistic locking version")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=30))

    class Config:
        use_enum_values = True

    @property
    def is_terminal(self) -> bool:
        """Returns True if the workflow is in a terminal state."""
        return self.workflow_status in (
            WorkflowStatus.COMPLETED.value,
            WorkflowStatus.FAILED.value,
            WorkflowStatus.CANCELLED.value,
            WorkflowStatus.EXPIRED.value,
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.EXPIRED,
        )

    @property
    def is_expired(self) -> bool:
        """Check if workflow TTL has elapsed."""
        now = datetime.now(timezone.utc)
        exp = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
        return now > exp

    def transition_to(
        self,
        new_status: WorkflowStatus,
        step: Optional[str] = None,
        reason: str = ""
    ) -> AgentWorkflowState:
        """
        Validate and execute a deterministic state transition.
        Increments state_version and updates timestamp.
        """
        cur_enum = WorkflowStatus(self.workflow_status)
        new_enum = WorkflowStatus(new_status)

        allowed = LEGAL_TRANSITIONS.get(cur_enum, set())
        if new_enum not in allowed:
            raise WorkflowTransitionError(
                from_status=cur_enum.value,
                to_status=new_enum.value,
                reason=reason or f"Transition from {cur_enum.value} to {new_enum.value} is prohibited by policy."
            )

        self.workflow_status = new_enum
        if step:
            if self.current_step and self.current_step != step:
                self.last_completed_step = self.current_step
            self.current_step = step
            
        self.state_version += 1
        self.updated_at = datetime.now(timezone.utc)
        return self

    def record_agent_handoff(self, target_agent: str) -> None:
        """Track agent handoff sequence to guard against circular delegation."""
        self.agent_handoff_history.append(target_agent)
        self.current_agent = target_agent
        self.updated_at = datetime.now(timezone.utc)

    def to_checkpoint_dict(self) -> Dict[str, Any]:
        """Convert state to safe, sanitized dictionary for checkpoint persistence."""
        data = self.model_dump() if hasattr(self, "model_dump") else self.dict()
        # Convert datetime objects to ISO strings
        for k in ["created_at", "updated_at", "expires_at"]:
            if isinstance(data.get(k), datetime):
                data[k] = data[k].isoformat()
        return data

    @classmethod
    def from_checkpoint_dict(cls, data: Dict[str, Any]) -> AgentWorkflowState:
        """Reconstitute state model from checkpoint payload."""
        payload = dict(data)
        for k in ["created_at", "updated_at", "expires_at"]:
            val = payload.get(k)
            if isinstance(val, str):
                try:
                    payload[k] = datetime.fromisoformat(val)
                except Exception:
                    payload[k] = datetime.now(timezone.utc)
        return cls(**payload)
