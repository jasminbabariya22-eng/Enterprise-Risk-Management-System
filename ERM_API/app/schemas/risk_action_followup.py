from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from fastapi import UploadFile, File


# Schemas for Risk Action Follow-up operations, including creation, update, and response models
class RiskActionFollowupCreate(BaseModel):

    reference_id: int
    module_name: Optional[str]
    remark: str
    progress: Optional[str]
    status: Optional[int]
    next_followup_date: Optional[datetime]



class RiskActionFollowupUpdate(BaseModel):

    remark: Optional[str]
    progress: Optional[str]
    status: Optional[int]
    next_followup_date: Optional[datetime]


class RiskActionFollowupResponse(BaseModel):

    followup_id: int
    reference_id: int
    module_name: Optional[str]
    remark: str
    progress: Optional[str]
    status: Optional[int]
    next_followup_date: Optional[datetime]
    created_on: datetime
    created_by: int

    class Config:
        from_attributes = True