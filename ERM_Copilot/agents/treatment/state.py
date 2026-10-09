"""
State Definitions and Session Container for Treatment Management Agent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


class TreatmentState:
    """State machine states for Treatment / Action Plan workflows."""
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


@dataclass
class TreatmentSession:
    """Session state for multi-turn Treatment / Action Plan interactions."""
    session_id: str
    user_id: int | str
    user_role: str = "Risk Owner"
    dept_id: Optional[int] = None
    dept_name: Optional[str] = None
    state: str = TreatmentState.IDLE
    mode: str = "ADD"  # "ADD", "UPDATE_PROGRESS", "REASSIGN"

    # Target Risk Info
    target_risk_register_id: Optional[int] = None
    target_risk_id: Optional[str] = None
    target_risk_name: Optional[str] = None

    # Treatment Parameters
    treatment_id: Optional[int] = None
    action_plan: Optional[str] = None
    action_owner_id: Optional[int] = None
    action_owner_name: Optional[str] = None
    target_date: Optional[str] = None
    progress: int = 0
    action_status_id: int = 1

    # Suggestions / Options
    action_plan_suggestions: List[str] = field(default_factory=list)
    available_action_owners: List[Dict[str, Any]] = field(default_factory=list)
    available_risks: List[Dict[str, Any]] = field(default_factory=list)
    available_treatments: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize treatment session to dictionary."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "user_role": self.user_role,
            "dept_id": self.dept_id,
            "dept_name": self.dept_name,
            "state": self.state,
            "mode": self.mode,
            "target_risk_register_id": self.target_risk_register_id,
            "target_risk_id": self.target_risk_id,
            "target_risk_name": self.target_risk_name,
            "treatment_id": self.treatment_id,
            "action_plan": self.action_plan,
            "action_owner_id": self.action_owner_id,
            "action_owner_name": self.action_owner_name,
            "target_date": self.target_date,
            "progress": self.progress,
            "action_status_id": self.action_status_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TreatmentSession:
        """Instantiate TreatmentSession from dictionary."""
        return cls(
            session_id=str(data.get("session_id", "")),
            user_id=data.get("user_id", "5"),
            user_role=str(data.get("user_role", "Risk Owner")),
            dept_id=data.get("dept_id"),
            dept_name=data.get("dept_name"),
            state=data.get("state", TreatmentState.IDLE),
            mode=data.get("mode", "ADD"),
            target_risk_register_id=data.get("target_risk_register_id"),
            target_risk_id=data.get("target_risk_id"),
            target_risk_name=data.get("target_risk_name"),
            treatment_id=data.get("treatment_id"),
            action_plan=data.get("action_plan"),
            action_owner_id=data.get("action_owner_id"),
            action_owner_name=data.get("action_owner_name"),
            target_date=data.get("target_date"),
            progress=data.get("progress", 0),
            action_status_id=data.get("action_status_id", 1),
        )



def parse_date_string(text: str) -> Optional[str]:
    """Parse explicit date or relative day offset."""
    cleaned = text.strip()
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
    """Extract progress integer percentage 0-100."""
    cleaned = text.strip().lower()
    pct_match = re.search(r'\b(\d{1,3})\s*%', cleaned)
    if pct_match:
        val = int(pct_match.group(1))
        return val if 0 <= val <= 100 else None

    digits = [int(s) for s in re.findall(r'\b\d{1,3}\b', cleaned)]
    for d in digits:
        if 0 <= d <= 100:
            return d
    return None


def extract_risk_identifier(text: str) -> Optional[str]:
    """Extract risk code (e.g. RSK-GAS-049) or register number from text."""
    code_match = re.search(r'\b(RSK-[A-Z0-9]+-\d{1,4}|GAS-\d{1,4}|REF-\d{1,4}|HSSE-\d{1,4}|MAINT-\d{1,4}|IT-\d{1,4}|FIN-\d{1,4}|RSK-\d{1,4})\b', text, re.IGNORECASE)
    if code_match:
        return code_match.group(1).upper()
    
    num_match = re.search(r'(?:risk|register)?\s*#?\s*(\d{1,4})\b', text, re.IGNORECASE)
    if num_match and any(w in text.lower() for w in ["risk", "register", "rsk", "for risk", "to risk", "on risk"]):
        return num_match.group(1)
    
    return None


def extract_treatment_id(text: str) -> Optional[int]:
    """Extract treatment primary key ID (e.g. Treatment #14 or Action #14), avoiding Risk ID numbers."""
    # Strip any Risk IDs first (e.g. RSK-GAS-056) so their digits aren't mistaken for a treatment PK
    sanitized = re.sub(r'\b(?:RSK-[A-Z0-9]+-\d{1,4}|[A-Z]{2,5}-\d{1,4})\b', '', text, flags=re.IGNORECASE)
    
    t_match = re.search(r'(?:treatment|action\s*plan|action)\s*#?\s*(\d{1,5})\b', sanitized, re.IGNORECASE)
    if t_match:
        return int(t_match.group(1))
    
    hash_match = re.search(r'#(\d{1,5})\b', sanitized)
    if hash_match:
        return int(hash_match.group(1))
        
    return None
