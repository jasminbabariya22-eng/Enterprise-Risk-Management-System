from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


# Schemas for User operations, including creation, update, and response models
# -------- CREATE --------
class UserCreate(BaseModel):
    log_id: str
    password: str
    first_name: str
    last_name: str
    email: Optional[str] = None

    photo: Optional[str] = None
    contact_no: Optional[str] = None
    country_code: Optional[int] = None
    std_code: Optional[int] = None

    country: Optional[str] = "India"
    address: Optional[str] = None
    user_city: Optional[str] = None

    dept_id: Optional[int] = None
    role_id: Optional[int] = None
    user_type_id: Optional[int] = None

    status: Optional[str] = "Active"

    class Config:
        extra = "ignore"
    
class ChangePasswordRequest(BaseModel):
    id: int
    old_password: str
    new_password: str


# -------- UPDATE --------
class UserUpdate(BaseModel):
    log_id: Optional[str] = None
    password: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None

    photo: Optional[str] = None
    contact_no: Optional[str] = None
    country_code: Optional[int] = None
    std_code: Optional[int] = None

    country: Optional[str] = None
    address: Optional[str] = None
    user_city: Optional[str] = None

    dept_id: Optional[int] = None
    role_id: Optional[int] = None
    user_type_id: Optional[int] = None

    status: Optional[str] = None

    class Config:
        extra = "ignore"


# -------- RESPONSE --------
class UserResponse(BaseModel):
    id: Optional[int] = None
    log_id: Optional[str] = None
    password: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    country: Optional[str] = None
    status: Optional[str] = "Active"
    role_id: Optional[int] = None
    dept_id: Optional[int] = None
    user_type_id: Optional[int] = None
    is_deleted: Optional[int] = 0
    created_on: Optional[datetime] = None
    photo: Optional[str] = None
    contact_no: Optional[str] = None
    country_code: Optional[int] = None
    std_code: Optional[int] = None
    user_city: Optional[str] = None
    address: Optional[str] = None

    class Config:
        extra = "ignore"
        from_attributes = True
    
class UserHybridResponse(BaseModel):
    id: Optional[int] = None
    log_id: Optional[str] = None
    password: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    country: Optional[str] = None
    status: Optional[str] = "Active"
    address: Optional[str] = None

    department_id: Optional[int] = None
    department_name: Optional[str] = None

    role_id: Optional[int] = None
    role_name: Optional[str] = None

    user_type_id: Optional[int] = None
    user_type_name: Optional[str] = None

    is_deleted: Optional[int] = 0
    created_on: Optional[datetime] = None

    photo: Optional[str] = None
    contact_no: Optional[str] = None
    country_code: Optional[int] = None
    std_code: Optional[int] = None
    user_city: Optional[str] = None

    class Config:
        extra = "ignore"
        from_attributes = True