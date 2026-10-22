"""
State Definitions and Session Container for Risk Creation Agent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ERM_Copilot.agents.risk_creation.scoring import RiskMatrixCalculator


class RiskCreationState:
    """State Machine States for Conversational Risk Creation."""
    START = "START"
    COLLECTING = "COLLECTING"
    AWAITING_RISK_NAME = "AWAITING_RISK_NAME"
    AWAITING_CO_OWNER = "AWAITING_CO_OWNER"
    AWAITING_DESCRIPTION = "AWAITING_DESCRIPTION"
    AWAITING_INHERENT_ASSESSMENT = "AWAITING_INHERENT_ASSESSMENT"
    AWAITING_MITIGATION = "AWAITING_MITIGATION"
    AWAITING_CURRENT_ASSESSMENT = "AWAITING_CURRENT_ASSESSMENT"
    AWAITING_ACTION_PLAN = "AWAITING_ACTION_PLAN"
    AWAITING_ACTION_OWNER = "AWAITING_ACTION_OWNER"
    AWAITING_TARGET_DATE = "AWAITING_TARGET_DATE"
    AWAITING_STATUS = "AWAITING_STATUS"
    VALIDATING = "VALIDATING"
    READY_FOR_PREVIEW = "READY_FOR_PREVIEW"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    SAVING = "SAVING"
    SAVED = "SAVED"
    SUBMITTED = "SUBMITTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass
class RiskCreationSession:
    """Stateful Session for Multi-Turn Conversational Risk Creation."""
    session_id: str
    user_id: int | str
    user_role: str
    dept_id: Optional[int] = None
    dept_name: Optional[str] = None

    # Workflow State
    state: str = RiskCreationState.START

    # 1. Risk Name / Title
    risk_name: Optional[str] = None

    # 2. Risk Co-Owner
    risk_co_owner_id: Optional[int] = None
    risk_co_owner_name: Optional[str] = None
    risk_co_owner_role: Optional[str] = None
    pending_co_owner: Optional[str] = None

    # 3. Risk Description
    risk_description: Optional[str] = None

    # 4. Inherent Risk Assessment
    inherent_likelihood: Optional[int] = None
    inherent_impact: Optional[int] = None
    inherent_score: Optional[int] = None
    inherent_level: Optional[str] = None
    inherent_badge: Optional[str] = None

    # 5. Mitigation
    mitigation: Optional[str] = None

    # 6. Current / Residual Risk Assessment (Independent)
    current_likelihood: Optional[int] = None
    current_impact: Optional[int] = None
    current_score: Optional[int] = None
    current_level: Optional[str] = None
    current_badge: Optional[str] = None

    # 7. Action Plan (Distinct from Mitigation)
    action_plan: Optional[str] = None

    # 8. Action Owner
    action_owner_id: Optional[int] = None
    action_owner_name: Optional[str] = None
    action_owner_role: Optional[str] = None
    pending_action_owner: Optional[str] = None

    # 9. Target Date
    target_date: Optional[str] = None

    # 10. Status
    status_id: int = 1
    status_name: str = "Draft"

    # Progress (Default 0%)
    progress: int = 0

    # Submission Mode & Confirmation
    submission_mode: str = "draft"
    validation_result: Optional[Dict[str, Any]] = None
    awaiting_confirmation: bool = False
    pending_confirmation: Optional[Dict[str, Any]] = None

    # Financial Year
    financial_year: str = "2026-2027"

    # Cached Options for Turn-by-Turn Prompting
    desc_options: List[str] = field(default_factory=list)
    mitigation_options: List[str] = field(default_factory=list)
    action_plan_options: List[str] = field(default_factory=list)
    available_action_owners: List[Dict[str, Any]] = field(default_factory=list)
    available_co_owners: List[Dict[str, Any]] = field(default_factory=list)
    available_statuses: List[Dict[str, Any]] = field(default_factory=list)

    # Duplicate Risk Detection
    duplicate_check_status: str = "not_checked"
    duplicate_candidates: List[Dict[str, Any]] = field(default_factory=list)
    duplicate_check_input_hash: Optional[str] = None
    duplicate_acknowledged: bool = False

    # Provenance tracking: mapping of field_name -> source ('user_stated', 'user_corrected', 'suggested', 'system_default', 'calculated')
    field_provenance: Dict[str, str] = field(default_factory=dict)

    # Durable tool call tracking
    tool_call_history: List[Dict[str, Any]] = field(default_factory=list)

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def update_inherent_assessment(self, likelihood: Optional[int], impact: Optional[int]) -> bool:
        """Update inherent likelihood, impact, score, and level using authoritative math. Invalidate if invalid."""
        self.pending_confirmation = None
        self.awaiting_confirmation = False
        self.duplicate_check_input_hash = None
        self.duplicate_acknowledged = False

        if likelihood is None or impact is None or not (RiskMatrixCalculator.is_valid_rating(likelihood) and RiskMatrixCalculator.is_valid_rating(impact)):
            self.inherent_likelihood = int(likelihood) if RiskMatrixCalculator.is_valid_rating(likelihood) else None
            self.inherent_impact = int(impact) if RiskMatrixCalculator.is_valid_rating(impact) else None
            self.inherent_score = None
            self.inherent_level = None
            self.inherent_badge = None
            self.updated_at = datetime.now(timezone.utc)
            return False

        score, level, badge = RiskMatrixCalculator.calculate_score(int(likelihood), int(impact), strict=True)
        self.inherent_likelihood = int(likelihood)
        self.inherent_impact = int(impact)
        self.inherent_score = score
        self.inherent_level = level
        self.inherent_badge = badge
        self.updated_at = datetime.now(timezone.utc)
        return True

    def update_current_assessment(self, likelihood: Optional[int], impact: Optional[int]) -> bool:
        """Update current / residual likelihood, impact, score, and level independently. Invalidate if invalid."""
        self.pending_confirmation = None
        self.awaiting_confirmation = False
        self.duplicate_check_input_hash = None
        self.duplicate_acknowledged = False

        if likelihood is None or impact is None or not (RiskMatrixCalculator.is_valid_rating(likelihood) and RiskMatrixCalculator.is_valid_rating(impact)):
            self.current_likelihood = int(likelihood) if RiskMatrixCalculator.is_valid_rating(likelihood) else None
            self.current_impact = int(impact) if RiskMatrixCalculator.is_valid_rating(impact) else None
            self.current_score = None
            self.current_level = None
            self.current_badge = None
            self.updated_at = datetime.now(timezone.utc)
            return False

        score, level, badge = RiskMatrixCalculator.calculate_score(int(likelihood), int(impact), strict=True)
        self.current_likelihood = int(likelihood)
        self.current_impact = int(impact)
        self.current_score = score
        self.current_level = level
        self.current_badge = badge
        self.updated_at = datetime.now(timezone.utc)
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize session to dictionary for persistent checkpointing."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "user_role": self.user_role,
            "dept_id": self.dept_id,
            "dept_name": self.dept_name,
            "state": self.state,
            "risk_name": self.risk_name,
            "risk_co_owner_id": self.risk_co_owner_id,
            "risk_co_owner_name": self.risk_co_owner_name,
            "risk_co_owner_role": self.risk_co_owner_role,
            "risk_description": self.risk_description,
            "inherent_likelihood": self.inherent_likelihood,
            "inherent_impact": self.inherent_impact,
            "inherent_score": self.inherent_score,
            "inherent_level": self.inherent_level,
            "inherent_badge": self.inherent_badge,
            "mitigation": self.mitigation,
            "current_likelihood": self.current_likelihood,
            "current_impact": self.current_impact,
            "current_score": self.current_score,
            "current_level": self.current_level,
            "current_badge": self.current_badge,
            "action_plan": self.action_plan,
            "action_owner_id": self.action_owner_id,
            "action_owner_name": self.action_owner_name,
            "action_owner_role": self.action_owner_role,
            "target_date": self.target_date,
            "status_id": self.status_id,
            "status_name": self.status_name,
            "progress": self.progress,
            "submission_mode": self.submission_mode,
            "pending_confirmation": self.pending_confirmation,
            "financial_year": self.financial_year,
            "field_provenance": self.field_provenance,
            "desc_options": self.desc_options,
            "mitigation_options": self.mitigation_options,
            "action_plan_options": self.action_plan_options,
            "available_action_owners": self.available_action_owners,
            "available_co_owners": self.available_co_owners,
            "duplicate_check_status": self.duplicate_check_status,
            "duplicate_candidates": self.duplicate_candidates,
            "duplicate_check_input_hash": self.duplicate_check_input_hash,
            "duplicate_acknowledged": self.duplicate_acknowledged,
            "tool_call_history": self.tool_call_history,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RiskCreationSession:
        """Instantiate RiskCreationSession from dictionary."""
        sess = cls(
            session_id=str(data.get("session_id", "")),
            user_id=data.get("user_id", "5"),
            user_role=str(data.get("user_role", "Risk Owner")),
            dept_id=data.get("dept_id"),
            dept_name=data.get("dept_name"),
            state=data.get("state", RiskCreationState.START),
            risk_name=data.get("risk_name"),
            risk_co_owner_id=data.get("risk_co_owner_id"),
            risk_co_owner_name=data.get("risk_co_owner_name"),
            risk_co_owner_role=data.get("risk_co_owner_role"),
            risk_description=data.get("risk_description"),
            inherent_likelihood=data.get("inherent_likelihood"),
            inherent_impact=data.get("inherent_impact"),
            inherent_score=data.get("inherent_score"),
            inherent_level=data.get("inherent_level"),
            inherent_badge=data.get("inherent_badge"),
            mitigation=data.get("mitigation"),
            current_likelihood=data.get("current_likelihood"),
            current_impact=data.get("current_impact"),
            current_score=data.get("current_score"),
            current_level=data.get("current_level"),
            current_badge=data.get("current_badge"),
            action_plan=data.get("action_plan"),
            action_owner_id=data.get("action_owner_id"),
            action_owner_name=data.get("action_owner_name"),
            action_owner_role=data.get("action_owner_role"),
            target_date=data.get("target_date"),
            status_id=data.get("status_id", 1),
            status_name=data.get("status_name", "Draft"),
            progress=data.get("progress", 0),
            submission_mode=data.get("submission_mode", "draft"),
            financial_year=data.get("financial_year", "2026-2027"),
            field_provenance=data.get("field_provenance", {}),
        )
        sess.pending_confirmation = data.get("pending_confirmation")
        sess.desc_options = data.get("desc_options", [])
        sess.mitigation_options = data.get("mitigation_options", [])
        sess.action_plan_options = data.get("action_plan_options", [])
        sess.available_action_owners = data.get("available_action_owners", [])
        sess.available_co_owners = data.get("available_co_owners", [])
        sess.duplicate_check_status = data.get("duplicate_check_status", "not_checked")
        sess.duplicate_candidates = data.get("duplicate_candidates", [])
        sess.duplicate_check_input_hash = data.get("duplicate_check_input_hash")
        sess.duplicate_acknowledged = bool(data.get("duplicate_acknowledged", False))
        sess.tool_call_history = data.get("tool_call_history", [])
        return sess

