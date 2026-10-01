from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# Schemas for UserType operations, including creation, update, and response models
class UserTypeCreate(BaseModel):
    name: str
    description: Optional[str] = None


class UserTypeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class UserTypeResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    is_deleted: int
    created_on: Optional[datetime]

    class Config:
        from_attributes = True