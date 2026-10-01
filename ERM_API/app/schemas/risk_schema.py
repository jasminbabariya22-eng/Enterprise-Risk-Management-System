from pydantic import BaseModel
from typing import List, Optional

from app.schemas.risk_register_full import RiskRegisterCreate
from app.schemas.risk_description_full import RiskDescriptionCreate
from app.schemas.risk_treatment_full import RiskTreatmentCreate

from .risk_register_full import RiskRegisterHybridResponse
from .risk_description_full import RiskDescriptionHybridResponse
from .risk_treatment_full import RiskTreatmentHybridResponse


# Schemas for Risk operations, including request models for saving and updating risks, and response model for detailed risk information
class RiskSaveRequest(BaseModel):
    risk_register: RiskRegisterCreate = None
    risk_description: RiskDescriptionCreate = None
    risk_treatments: Optional[List[RiskTreatmentCreate]] = []


class RiskUpdateRequest(BaseModel):
    risk_register_id: str
    risk_register: RiskRegisterCreate
    risk_description: RiskDescriptionCreate
    risk_treatments: Optional[List[RiskTreatmentCreate]] = []
    
class RiskDetailResponse(BaseModel):
    risk_register: RiskRegisterHybridResponse
    risk_description: Optional[RiskDescriptionHybridResponse]
    risk_treatments: List[RiskTreatmentHybridResponse]

    class Config:
        from_attributes = True