"""
Authoritative Final Risk Payload Builder for ERM Copilot.
Constructs deterministic, schema-compatible persistence payloads from validated drafts
and trusted server-side context, binding them to cryptographic confirmation fingerprints.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ERM_Copilot.agents.risk_creation.scoring import RiskMatrixCalculator
from ERM_Copilot.agents.risk_creation.state import RiskCreationSession
from ERM_Copilot.agents.risk_creation.validation import validate_risk_draft

logger = logging.getLogger("ERM_Copilot.agents.risk_creation.payload")


class RiskPayloadError(ValueError):
    """Raised when a risk draft cannot produce a valid persistence payload."""
    pass


class FinalRiskPayload(BaseModel):
    """
    Schema-compatible, immutable representation of a validated risk payload.
    Excludes internal prompts, raw tool outputs, and LLM reasoning.
    """
    risk_name: str
    risk_description: str
    dept_id: int
    dept_name: str
    risk_owner_id: int | str
    risk_co_owner_id: Optional[Any] = None
    inherent_likelihood: int
    inherent_impact: int
    inherent_score: int
    inherent_level: str
    inherent_badge: str
    current_likelihood: int
    current_impact: int
    current_score: int
    current_level: str
    current_badge: str
    mitigation: str
    action_plan: str
    action_owner_id: Optional[Any] = None
    target_date: str
    status: int
    status_name: str
    progress: int = 0
    financial_year: str = "2026-2027"
    treatments: List[Dict[str, Any]] = Field(default_factory=list)

    def to_db_kwargs(self) -> Dict[str, Any]:
        """
        Produce keyword arguments accepted by ERMDatabaseService.create_risk.
        Guarantees zero unknown arguments and strict schema compliance.
        """
        return {
            "risk_name": self.risk_name,
            "risk_description": self.risk_description,
            "dept_id": self.dept_id,
            "dept_name": self.dept_name,
            "risk_owner_id": self.risk_owner_id,
            "risk_co_owner_id": self.risk_co_owner_id,
            "inherent_likelihood": self.inherent_likelihood,
            "inherent_impact": self.inherent_impact,
            "current_likelihood": self.current_likelihood,
            "current_impact": self.current_impact,
            "mitigation": self.mitigation,
            "status": self.status,
            "financial_year": self.financial_year,
            "treatments": self.treatments,
        }

    def to_canonical_dict(self) -> Dict[str, Any]:
        """
        Produce a deterministic dictionary representation for cryptographic confirmation hashing.
        Excludes transient tokens and timestamps.
        """
        return {
            "action_owner_id": self.action_owner_id,
            "action_plan": self.action_plan,
            "current_impact": self.current_impact,
            "current_likelihood": self.current_likelihood,
            "current_score": self.current_score,
            "dept_id": self.dept_id,
            "dept_name": self.dept_name,
            "financial_year": self.financial_year,
            "inherent_impact": self.inherent_impact,
            "inherent_likelihood": self.inherent_likelihood,
            "inherent_score": self.inherent_score,
            "mitigation": self.mitigation,
            "progress": self.progress,
            "risk_co_owner_id": self.risk_co_owner_id,
            "risk_description": self.risk_description,
            "risk_name": self.risk_name,
            "risk_owner_id": str(self.risk_owner_id),
            "status": self.status,
            "status_name": self.status_name,
            "target_date": self.target_date,
        }


def build_final_risk_payload(
    draft: RiskCreationSession,
    server_context: Dict[str, Any]
) -> FinalRiskPayload:
    """
    Construct a deterministic FinalRiskPayload from a validated draft and trusted server context.
    
    Invariants:
    1. Validates the draft deterministically before building. Rejects invalid or incomplete drafts.
    2. Overrides any conversational identity or department values with trusted server_context.
    3. Re-computes inherent and current risk scores authoritatively via RiskMatrixCalculator.
    4. Applies only approved defaults (target_date +30 days UTC, action_owner=risk_owner, progress=0).
    5. Pure function: performs zero database writes.
    """
    if not server_context or not server_context.get("user_id"):
        raise RiskPayloadError("Missing authoritative user identity in server context.")
    if not server_context.get("dept_id"):
        raise RiskPayloadError("Missing authoritative department in server context.")

    # 1. Authoritative Validation Check
    val_res = validate_risk_draft(draft, server_context=server_context)
    if not val_res.is_ready_for_review:
        err_msg = val_res.summary_message or "Draft is not eligible for final review."
        raise RiskPayloadError(f"Cannot build final risk payload: {err_msg}")

    norm = val_res.normalized_values
    scores = val_res.calculated_scores

    # 2. Extract Trusted Server Context
    raw_uid = server_context["user_id"]
    auth_owner_id = int(raw_uid) if str(raw_uid).isdigit() else raw_uid
    auth_dept_id = int(server_context["dept_id"])
    auth_dept_name = str(server_context.get("dept_name") or "General").strip()

    # 3. Approved Defaults
    target_dt = norm.get("target_date")
    if not target_dt:
        target_dt = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")

    action_owner_id = norm.get("action_owner_id") or auth_owner_id
    co_owner_id = norm.get("risk_co_owner_id")
    prog = norm.get("progress", 0)

    # 4. Construct Treatments Structure
    treatments = [{
        "action_plan": norm["action_plan"],
        "action_owner_id": action_owner_id,
        "target_date": target_dt,
        "progress": prog,
    }]

    return FinalRiskPayload(
        risk_name=norm["risk_name"][:250],
        risk_description=norm["risk_description"],
        dept_id=auth_dept_id,
        dept_name=auth_dept_name,
        risk_owner_id=auth_owner_id,
        risk_co_owner_id=co_owner_id,
        inherent_likelihood=norm["inherent_likelihood"],
        inherent_impact=norm["inherent_impact"],
        inherent_score=scores["inherent_score"],
        inherent_level=scores["inherent_level"],
        inherent_badge=scores["inherent_badge"],
        current_likelihood=norm["current_likelihood"],
        current_impact=norm["current_impact"],
        current_score=scores["current_score"],
        current_level=scores["current_level"],
        current_badge=scores["current_badge"],
        mitigation=norm["mitigation"],
        action_plan=norm["action_plan"],
        action_owner_id=action_owner_id,
        target_date=target_dt,
        status=norm.get("status_id", 1),
        status_name=norm.get("status_name", "Draft"),
        progress=prog,
        financial_year=norm.get("financial_year", "2026-2027"),
        treatments=treatments,
    )
