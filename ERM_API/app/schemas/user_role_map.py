from pydantic import BaseModel
from typing import List


# Schemas for User Role Mapping operations, including creation model for assigning roles to users
class RoleMenuCreate(BaseModel):
    role_id: int
    menu_ids: List[int]