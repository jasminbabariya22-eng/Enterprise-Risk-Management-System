from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# Schemas for Risk Description operations, including creation, update, and response models
class RiskDescriptionCreate(BaseModel):
    risk_description_id: Optional[str] = "0"
    risk_description: Optional[str] = ""

    inherent_risk_likelihood_id: Optional[str] = "0"
    inherent_risk_impact_id: Optional[str] = "0"

    mitigation: Optional[str] = ""

    current_risk_likelihood_id: Optional[str] = "0"
    current_risk_impact_id: Optional[str] = "0"
    
    
class RiskDescriptionUpdate(BaseModel):

    risk_description: Optional[str] = ""
    mitigation: Optional[str] = ""

    inherent_risk_likelihood_id: Optional[str] = "0"
    inherent_risk_impact_id: Optional[str] = "0"

    current_risk_likelihood_id: Optional[str] = "0"
    current_risk_impact_id: Optional[str] = "0"
    

class RiskDescriptionHybridResponse(BaseModel):
    risk_description_id: int
    risk_register_id: int
    risk_id: Optional[str]

    risk_name: Optional[str]

    risk_description: Optional[str]

    inherent_risk_likelihood_id: Optional[int]
    inherent_risk_impact_id: Optional[int]

    mitigation: Optional[str]

    current_risk_likelihood_id: Optional[int]
    current_risk_impact_id: Optional[int]

    is_deleted: int
    created_on: Optional[datetime]

    class Config:
        from_attributes = True