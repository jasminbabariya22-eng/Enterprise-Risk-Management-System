from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from typing import List


# Schemas for Role operations, including creation, update, and response models
class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None

class RoleCreateNew(BaseModel):
    name: str
    description: Optional[str] = None
    menuids:Optional[List[int]] = []

class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class RoleUpdateNew(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    menuids:Optional[List[int]] = []


class RoleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    is_deleted: int
    created_on: Optional[datetime]

class RoleResponseNew(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    is_deleted: int
    created_on: Optional[datetime]
    menuids:Optional[List[int]] = []

    class Config:
        from_attributes = True