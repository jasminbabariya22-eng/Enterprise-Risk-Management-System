from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# Schemas for Risk Register operations, including creation, update, and response models
class RiskRegisterCreate(BaseModel):
    risk_name: str
    dept_id: int
    risk_owner_id: int
    risk_co_owner_id: Optional[int] = None

    financial_year: Optional[str] = None
    risk_status: Optional[int] = None
    risk_progress: Optional[str] = None

    is_active: Optional[int] = 0
    
class RiskRegisterUpdate(BaseModel):

    risk_name: Optional[str] = None
    dept_id: Optional[int] = None
    risk_owner_id: Optional[int] = None
    risk_co_owner_id: Optional[int] = None

    financial_year: Optional[str] = None
    risk_status: Optional[int] = None
    risk_progress: Optional[str] = None

    is_active: Optional[int] = None
    
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class RiskRegisterHybridResponse(BaseModel):

    risk_register_id: int
    risk_id: str
    risk_name: str

    dept_id: int
    risk_owner_id: int
    risk_co_owner_id: Optional[int] = None

    financial_year: Optional[str] = None
    risk_status: Optional[int] = None
    risk_progress: Optional[str] = None

    risk_function_head_approval_status: Optional[int] = None
    risk_function_head_approval_remark: Optional[str] = None
    risk_function_head_approval_on: Optional[datetime] = None

    risk_head_approval_status: Optional[int] = None
    risk_head_approval_remark: Optional[str] = None
    risk_head_approved_on: Optional[datetime] = None

    risk_manager_approval_status: Optional[int] = None
    risk_manager_approval_remark: Optional[str] = None
    risk_manager_approved_on: Optional[datetime] = None

    class Config:
        from_attributes = True
