from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# Schemas for Risk Treatment operations, including creation, update, and response models
class RiskTreatmentCreate(BaseModel):
    risk_treatment_id: Optional[str] = "0"
    action_plan: str
    action_owner_id: Optional[str] = "0"

    target_date: Optional[str] = ""
    progress: Optional[str] = "0"
    action_status_id: Optional[str] = "0"
    next_followup_date: Optional[str] = ""
    
    
class RiskTreatmentUpdate(BaseModel):
    action_plan: Optional[str] = ""
    progress: Optional[str] = "0"
    action_status_id: Optional[str] = "0"
    target_date: Optional[str] = ""
    next_followup_date: Optional[str] = ""
    
class RiskTreatmentHybridResponse(BaseModel):
    risk_treatment_id: int
    risk_description_id: int
    risk_register_id: Optional[int]

    risk_name: Optional[str]
    action_plan: str

    action_owner_id: int
    action_owner_name: Optional[str]

    target_date: Optional[datetime]
    progress: Optional[str]
    action_status_id: Optional[int]
    next_followup_date: Optional[datetime]

    is_deleted: int
    created_on: Optional[datetime]

    class Config:
        from_attributes = True