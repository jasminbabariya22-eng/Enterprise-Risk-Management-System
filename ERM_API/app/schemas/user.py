from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


# Schemas for User operations, including creation, update, and response models
# -------- CREATE --------
class UserCreate(BaseModel):
    log_id: str
    password: str
    first_name: str
    last_name: str
    email: EmailStr

    # photo: Optional[str] = None
    contact_no: Optional[str] = None    # optinal because some users may not have contact number
    # country_code: Optional[int] = None
    # std_code: Optional[int] = None

    # country: Optional[str] = None
    address: Optional[str] = None       # optional because some users may not have address
    # user_city: Optional[str] = None

    dept_id: int
    role_id: int
    user_type_id: Optional[int] = 0

    status: str
    
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
    email: Optional[EmailStr] = None

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


# -------- RESPONSE --------
class UserResponse(BaseModel):
    id: int
    log_id: str
    password: str
    first_name: str
    last_name: str
    email: str
    country: Optional[str]
    status: str
    role_id: Optional[int]
    dept_id: Optional[int]
    user_type_id: Optional[int]
    is_deleted: int
    created_on: Optional[datetime]
    
class UserHybridResponse(BaseModel):
    id: int
    log_id: str
    password: str
    first_name: str
    last_name: str
    email: str
    country: str
    status: str

    department_id: Optional[int]
    department_name: Optional[str]

    role_id: Optional[int]
    role_name: Optional[str]

    user_type_id: Optional[int]
    user_type_name: Optional[str]

    is_deleted: int
    created_on: Optional[datetime]


    class Config:
        from_attributes = True