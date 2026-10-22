"""
Enterprise Risk Management (ERM) - Treatment Management Agent State.
Typed, serializable session state, goals, workflow stages, and deterministic parsers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class TreatmentGoal(str, Enum):
    """Supported treatment lifecycle goals."""
    ADD_TREATMENT = "ADD_TREATMENT"
    UPDATE_PROGRESS = "UPDATE_PROGRESS"
    REASSIGN_OWNER = "REASSIGN_OWNER"
    LIST_TREATMENTS = "LIST_TREATMENTS"
    SHOW_TREATMENT_DETAILS = "SHOW_TREATMENT_DETAILS"
    UNKNOWN = "UNKNOWN"


class TreatmentWorkflowState(str, Enum):
    """Goal-driven workflow states for treatment interactions."""
    IDLE = "IDLE"
    INITIATION = "INITIATION"
    COLLECTING_INFO = "COLLECTING_INFO"
    RESOLVING_ENTITIES = "RESOLVING_ENTITIES"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    POLICY_BLOCKED = "POLICY_BLOCKED"


class TreatmentState:
    """Legacy state machine constants for backward compatibility."""
    IDLE = "IDLE"
    AWAITING_RISK_SELECTION = "AWAITING_RISK_SELECTION"
    AWAITING_ACTION_PLAN = "AWAITING_ACTION_PLAN"
    AWAITING_ACTION_OWNER = "AWAITING_ACTION_OWNER"
    AWAITING_TARGET_DATE = "AWAITING_TARGET_DATE"
    AWAITING_PROGRESS = "AWAITING_PROGRESS"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    AWAITING_PROGRESS_UPDATE_SELECTION = "AWAITING_PROGRESS_UPDATE_SELECTION"
    AWAITING_NEW_PROGRESS_VALUE = "AWAITING_NEW_PROGRESS_VALUE"
    AWAITING_REASSIGN_OWNER_SELECTION = "AWAITING_REASSIGN_OWNER_SELECTION"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    POLICY_BLOCKED = "POLICY_BLOCKED"


@dataclass
class TreatmentSession:
    """
    Serializable session state for the goal-driven Treatment Management Agent.
    Maintains user identity, parameters, field provenance, and confirmation tokens.
    """
    session_id: str
    user_id: str
    user_role: str
    dept_id: Optional[int] = None
    dept_name: Optional[str] = None
    goal: TreatmentGoal = TreatmentGoal.UNKNOWN
    state: TreatmentWorkflowState = TreatmentWorkflowState.INITIATION
    mode: str = "ADD"  # Backward compatibility: "ADD", "UPDATE_PROGRESS", "REASSIGN"

    # Target Risk info
    target_risk_register_id: Optional[int] = None
    target_risk_id: Optional[str] = None
    target_risk_name: Optional[str] = None
    risk_data: Optional[Dict[str, Any]] = None

    # Target Treatment parameters
    treatment_id: Optional[int] = None
    action_plan: Optional[str] = None
    action_owner_id: Optional[int] = None
    action_owner_name: Optional[str] = None
    target_date: Optional[str] = None
    progress: int = 0
    action_status_id: int = 1
    remarks: Optional[str] = None

    # Reassignment specific fields
    new_action_owner_id: Optional[int] = None
    new_action_owner_name: Optional[str] = None

    # Provenance tracking (field_name -> source tag, e.g. "user_extracted", "user_corrected", "default", "db_resolved")
    provenance: Dict[str, str] = field(default_factory=dict)

    # Confirmation security artifacts
    pending_confirmation: Optional[Dict[str, Any]] = None

    # Candidate lists / options
    available_risks: List[Dict[str, Any]] = field(default_factory=list)
    available_action_owners: List[Dict[str, Any]] = field(default_factory=list)
    available_treatments: List[Dict[str, Any]] = field(default_factory=list)

    # Execution control & safety bounds
    step_count: int = 0
    max_steps: int = 15
    last_user_message: str = ""
    api_result: Optional[Dict[str, Any]] = None
    policy_block_reason: Optional[str] = None

    @property
    def is_terminal(self) -> bool:
        """True if the workflow reached a terminal state."""
        return self.state in (
            TreatmentWorkflowState.COMPLETED,
            TreatmentWorkflowState.CANCELLED,
            TreatmentWorkflowState.FAILED,
            TreatmentWorkflowState.POLICY_BLOCKED,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize session state to dictionary for checkpoint persistence."""
        return {
            "session_id": self.session_id,
            "user_id": str(self.user_id),
            "user_role": self.user_role,
            "dept_id": self.dept_id,
            "dept_name": self.dept_name,
            "goal": self.goal.value if isinstance(self.goal, TreatmentGoal) else str(self.goal),
            "state": self.state.value if isinstance(self.state, TreatmentWorkflowState) else str(self.state),
            "mode": self.mode,
            "target_risk_register_id": self.target_risk_register_id,
            "target_risk_id": self.target_risk_id,
            "target_risk_name": self.target_risk_name,
            "risk_data": self.risk_data,
            "treatment_id": self.treatment_id,
            "action_plan": self.action_plan,
            "action_owner_id": self.action_owner_id,
            "action_owner_name": self.action_owner_name,
            "target_date": self.target_date,
            "progress": self.progress,
            "action_status_id": self.action_status_id,
            "remarks": self.remarks,
            "new_action_owner_id": self.new_action_owner_id,
            "new_action_owner_name": self.new_action_owner_name,
            "provenance": self.provenance,
            "pending_confirmation": self.pending_confirmation,
            "step_count": self.step_count,
            "max_steps": self.max_steps,
            "policy_block_reason": self.policy_block_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TreatmentSession:
        """Instantiate TreatmentSession from serialized dictionary."""
        goal_val = data.get("goal")
        try:
            goal = TreatmentGoal(goal_val) if goal_val else TreatmentGoal.UNKNOWN
        except ValueError:
            goal = TreatmentGoal.UNKNOWN

        state_val = data.get("state")
        try:
            state = TreatmentWorkflowState(state_val) if state_val else TreatmentWorkflowState.INITIATION
        except ValueError:
            state = TreatmentWorkflowState.INITIATION

        return cls(
            session_id=str(data.get("session_id", "")),
            user_id=str(data.get("user_id", "")),
            user_role=str(data.get("user_role", "")),
            dept_id=data.get("dept_id"),
            dept_name=data.get("dept_name"),
            goal=goal,
            state=state,
            mode=str(data.get("mode", "ADD")),
            target_risk_register_id=data.get("target_risk_register_id"),
            target_risk_id=data.get("target_risk_id"),
            target_risk_name=data.get("target_risk_name"),
            risk_data=data.get("risk_data"),
            treatment_id=data.get("treatment_id"),
            action_plan=data.get("action_plan"),
            action_owner_id=data.get("action_owner_id"),
            action_owner_name=data.get("action_owner_name"),
            target_date=data.get("target_date"),
            progress=int(data.get("progress", 0)),
            action_status_id=int(data.get("action_status_id", 1)),
            remarks=data.get("remarks"),
            new_action_owner_id=data.get("new_action_owner_id"),
            new_action_owner_name=data.get("new_action_owner_name"),
            provenance=data.get("provenance", {}) or {},
            pending_confirmation=data.get("pending_confirmation"),
            step_count=int(data.get("step_count", 0)),
            max_steps=int(data.get("max_steps", 15)),
            policy_block_reason=data.get("policy_block_reason"),
        )


# ---------------------------------------------------------------------
# Deterministic Parsers & Normalizers
# ---------------------------------------------------------------------

def parse_date_string(text: str) -> Optional[str]:
    """Parse explicit date or relative day offset into YYYY-MM-DD string."""
    if not text:
        return None
    cleaned = text.strip()

    # Relative offset: "+30 days", "in 60 days", "+90d"
    match = re.search(r'(?:\+|in\s+)?(\d{1,3})\s*(?:days?|d)\b', cleaned, re.IGNORECASE)
    if match:
        days = int(match.group(1))
        return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")

    patterns = [
        ("%Y-%m-%d", r'\b(\d{4}-\d{1,2}-\d{1,2})\b'),
        ("%d-%m-%Y", r'\b(\d{1,2}-\d{1,2}-\d{4})\b'),
        ("%d/%m/%Y", r'\b(\d{1,2}/\d{1,2}/\d{4})\b'),
        ("%d %B %Y", r'\b(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b'),
        ("%d %b %Y", r'\b(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\b'),
        ("%B %d, %Y", r'\b([A-Za-z]+\s+\d{1,2},\s*\d{4})\b'),
    ]
    for fmt, regex in patterns:
        m = re.search(regex, cleaned, re.IGNORECASE)
        if m:
            try:
                dt = datetime.strptime(m.group(1), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
    return None


def parse_progress_percentage(text: str) -> Optional[int]:
    """Extract progress integer percentage between 0 and 100."""
    if not text:
        return None
    cleaned = text.strip().lower()

    pct_match = re.search(r'\b(\d{1,3})\s*%', cleaned)
    if pct_match:
        val = int(pct_match.group(1))
        return val if 0 <= val <= 100 else None

    # Contextual keywords
    if "not started" in cleaned:
        return 0
    if "completed" in cleaned or "done" in cleaned or "finished" in cleaned:
        return 100

    digits = [int(s) for s in re.findall(r'\b\d{1,3}\b', cleaned)]
    for d in digits:
        if 0 <= d <= 100:
            return d
    return None


def extract_risk_identifier(text: str) -> Optional[str]:
    """Extract canonical risk code (e.g. RSK-GAS-049) or register number."""
    if not text:
        return None
    code_match = re.search(
        r'\b((?:RSK|GAS|REF|HSSE|MAINT|IT|FIN|HR|OPS|SEC|ENV)-[A-Z0-9_-]+-\d{1,5}|[A-Z]{2,5}-\d{2,5}|RSK-\d{1,5})\b',
        text,
        re.IGNORECASE,
    )
    if code_match:
        return code_match.group(1).upper()

    num_match = re.search(r'(?:risk|register)?\s*#?\s*(\d{1,5})\b', text, re.IGNORECASE)
    if num_match and any(w in text.lower() for w in ["risk", "register", "rsk", "for risk", "to risk", "on risk", "#"]):
        return num_match.group(1)

    return None


def extract_treatment_id(text: str) -> Optional[int]:
    """Extract treatment primary key ID (e.g. Treatment #14 or Action #14), avoiding Risk ID numbers."""
    if not text:
        return None
    # Strip any canonical Risk IDs first so their digits are not mistaken for a treatment PK
    sanitized = re.sub(
        r'\b(?:RSK-[A-Z0-9_-]+-\d{1,5}|[A-Z]{2,5}-\d{2,5}|RSK-\d{1,5})\b',
        '',
        text,
        flags=re.IGNORECASE,
    )

    t_match = re.search(r'(?:treatment|action\s*plan|action|trt)\s*[-#]?\s*(\d{1,5})\b', sanitized, re.IGNORECASE)
    if t_match:
        return int(t_match.group(1))

    hash_match = re.search(r'#(\d{1,5})\b', sanitized)
    if hash_match:
        return int(hash_match.group(1))

    return None
