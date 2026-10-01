from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# Schemas for Risk Description operations, including creation, update, and response models
class RiskDescriptionCreate(BaseModel):
    risk_register_id: int
    risk_description: Optional[str] = None

    inherent_risk_likelihood_id: Optional[int] = None
    inherent_risk_impact_id: Optional[int] = None

    mitigation: Optional[str] = None

    current_risk_likelihood_id: Optional[int] = None
    current_risk_impact_id: Optional[int] = None
    
    
class RiskDescriptionUpdate(BaseModel):
    risk_description: Optional[str] = None
    mitigation: Optional[str] = None

    inherent_risk_likelihood_id: Optional[int] = None
    inherent_risk_impact_id: Optional[int] = None

    current_risk_likelihood_id: Optional[int] = None
    current_risk_impact_id: Optional[int] = None
    

class RiskDescriptionHybridResponse(BaseModel):

    risk_description_id: int
    risk_description: str
    mitigation: Optional[str]

    risk_register_id: Optional[int]
    risk_id: Optional[str]

    inherent_risk_likelihood_id: Optional[int]
    inherent_risk_impact_id: Optional[int]

    current_risk_likelihood_id: Optional[int]
    current_risk_impact_id: Optional[int]

    created_on: Optional[datetime]
    created_by: Optional[int]
    
    modified_by: Optional[int]
    modified_on: Optional[datetime]
    
    is_deleted: int

    class Config:
        from_attributes = True
        
