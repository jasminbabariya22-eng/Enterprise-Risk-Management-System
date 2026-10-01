from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# Schemas for Status operations, including creation, update, and response models
class StatusCreate(BaseModel):
    status_name: str
    type: Optional[str] = None


class StatusUpdate(BaseModel):
    status_name: Optional[str] = None
    type: Optional[str] = None


class StatusResponse(BaseModel):
    id: int
    status_name: str
    type: Optional[str]
    created_by: Optional[int]
    created_on: Optional[datetime]
    modified_by: Optional[int]
    modified_on: Optional[datetime]
    is_deleted: int

    class Config:
        from_attributes = True