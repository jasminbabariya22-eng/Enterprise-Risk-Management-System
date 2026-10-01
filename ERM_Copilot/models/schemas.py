"""
ERM Risk Data Models and Domain Schemas.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class RiskItem(BaseModel):
    risk_id: str
    risk_code: Optional[str] = None
    department: Optional[str] = None
    title: str
    description: Optional[str] = None
    severity: Optional[str] = None
    likelihood: Optional[str] = None
    impact: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None


class RiskTreatmentPlan(BaseModel):
    treatment_id: Optional[str] = None
    risk_id: str
    treatment_strategy: str
    treatment_action: str
    action_owner: Optional[str] = None
    target_completion_date: Optional[str] = None
    residual_risk_level: Optional[str] = None
    status: Optional[str] = "OPEN"


class RiskActionFollowup(BaseModel):
    action_id: str
    risk_id: str
    action_title: str
    assigned_to: str
    due_date: Optional[str] = None
    is_overdue: bool = False
    followup_notes: Optional[str] = None


class ERMQueryResult(BaseModel):
    query: str
    intent: str
    total_found: int = 0
    data: List[Dict[str, Any]] = Field(default_factory=list)
    summary: str
    recommended_actions: List[str] = Field(default_factory=list)
