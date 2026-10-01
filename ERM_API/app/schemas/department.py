from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# Schemas for Department operations, including creation, update, and response models
class DepartmentCreate(BaseModel):
    dept_name: str
    dept_short_name: str
    description: Optional[str] = None


class DepartmentUpdate(BaseModel):
    dept_name: Optional[str] = None
    dept_short_name: Optional[str] = None
    description: Optional[str] = None


class DepartmentResponse(BaseModel):
    id: int
    dept_name: str
    dept_short_name: Optional[str] = None
    description: Optional[str] = None
    is_deleted: int
    created_on: Optional[datetime]

    class Config:
        from_attributes = True