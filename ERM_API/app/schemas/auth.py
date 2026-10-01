from pydantic import BaseModel
from typing import Optional


class LoginRequest(BaseModel):
    log_id: str
    password: str

# This schema is used for the response of the login API, it includes user details and access token
class LoginResponse(BaseModel):
    id: int
    password: str
    first_name: str
    last_name: str
    logid: str
    department_id: Optional[int]
    role_id: Optional[int]
    user_type_id: Optional[int]
    user_type: str
    access_token: str
    token_type: str = "Bearer"
    
    
class ResetPasswordRequest(BaseModel):
    log_id: str
    
    
class changepasswordRequest(BaseModel):
    code: str
    new_password: str
