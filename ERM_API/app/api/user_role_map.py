from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.response import success_response, error_response

from app.models.user_role_map import UserRoleMap
from app.schemas.user_role_map import RoleMenuCreate


router = APIRouter(prefix="/role_map", 
                   tags=["Role_Map"],
                   dependencies=[Depends(get_current_user)]
                   )

# Create
@router.post("/create")
def create_role_menu(data: RoleMenuCreate, db: Session = Depends(get_db)):

    try:
        db.query(UserRoleMap).filter(
            UserRoleMap.role_id == data.role_id
        ).delete()

        new_records = []

        for menu_id in data.menu_ids:
            new_records.append(
                UserRoleMap(
                    role_id=data.role_id,
                    menu_id=menu_id
                )
            )

        db.add_all(new_records)
        db.commit()

        result = [
            {
                "role_id": record.role_id,
                "menu_id": record.menu_id
            }
            for record in new_records
        ]

        return success_response(result)

    except Exception as e:
        return error_response(str(e), 400)
        
    
    
# Get by role_id 
@router.get("/{role_id}")
def get_role_menu(role_id: int, db: Session = Depends(get_db)):

    try:
        data = db.query(UserRoleMap).filter(
            UserRoleMap.role_id == role_id
        ).all()

        return success_response(data)
    
    except Exception as e:
        return error_response(str(e), 400)