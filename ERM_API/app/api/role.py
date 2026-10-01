from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from app.core.database import get_db
from app.models.role import UserRole
from app.schemas.role import (
    RoleCreate,RoleCreateNew,
    RoleUpdate,RoleUpdateNew,
    RoleResponse,RoleResponseNew
)
from app.core.dependencies import get_current_user
from app.core.response import success_response, error_response
from app.models.user_role_map import UserRoleMap

router = APIRouter(prefix="/roles", 
                   tags=["Roles"],
                   dependencies=[Depends(get_current_user)]
                   )


# CREATE
@router.post("/", response_model=RoleResponseNew)
def create_role(data: RoleCreateNew, db: Session = Depends(get_db)):
    
    try:
        roles = db.query(UserRole).filter(UserRole.is_deleted == 0 ,UserRole.name == data.name ).first()
        if roles:
            raise HTTPException(status_code=409, detail="Role Name already exists")
        
        role = UserRole(
            name=data.name,
            description=data.description,
            is_deleted=0,
            created_on=datetime.utcnow()
        )
        db.add(role)
        db.flush()
        #db.commit()
        #db.refresh(role)

        #save data in user_role_map
        role_maps = []
        if data.menuids:
            for menu_id in data.menuids:
                role_map = UserRoleMap(
                    role_id = role.id,
                    menu_id = menu_id
                )
                role_maps.append(role_map)

            db.add_all(role_maps)
        db.commit()
        db.refresh(role)
        
        return success_response({
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "menuids": data.menuids
        })
        
    except Exception as e:
        db.rollback()
        return error_response(str(e), 400)


# GET ALL roles with menuids
@router.get("/", response_model=List[RoleResponseNew])
def get_roles(db: Session = Depends(get_db)):
    
    try:
        roles = db.query(UserRole).filter(UserRole.is_deleted == 0).all()
        response = []
        for role in roles:
            menu_ids = db.query(UserRoleMap.menu_id).filter(
                UserRoleMap.role_id == role.id
                ).all()
            menu_list = [m.menu_id for m in menu_ids]
            response.append({
                "id": role.id,
                "name": role.name,
                "description": role.description,
                "menuids":menu_list
            })
        return success_response(response)
    
    except Exception as e:
        return error_response(str(e), 400)


# GET BY ID
@router.get("/{role_id}", response_model=RoleResponseNew)
def get_role(role_id: int, db: Session = Depends(get_db)):
    
    try:
        dept = db.query(UserRole).filter(
            UserRole.id == role_id,
            UserRole.is_deleted == 0
        ).first()

        if not dept:
            raise HTTPException(status_code=404, detail="Role not found")
        
        menu_ids = db.query(UserRoleMap.menu_id).filter(
                UserRoleMap.role_id == role_id
                ).all()
        menu_list = [m.menu_id for m in menu_ids]

        return success_response({
            "id": dept.id,
            "name": dept.name,
            "description": dept.description,
            "menuids":menu_list
        })
        
    except Exception as e:
        return error_response(str(e), 400)


# UPDATE
@router.put("/{role_id}", response_model=RoleResponseNew)
def update_role(role_id: int, data: RoleUpdateNew, db: Session = Depends(get_db)):
    
    try:
        role = db.query(UserRole).filter(UserRole.id == role_id).first()

        if not role:
            raise HTTPException(status_code=404, detail="Role not found")

        update_data = data.dict(exclude_unset=True)

        for key, value in update_data.items():
            if key != "menuids":
                setattr(role, key, value)
        role.modified_on =  datetime.utcnow()
        role.modified_by = 1

        #delete all existing 
        db.query(UserRoleMap).filter(
                UserRoleMap.role_id == role_id
            ).delete(synchronize_session=False)
        #all records as new
        if "menuids" in update_data:
            new_menu_ids = list(set(update_data["menuids"]))
            role_maps = [
                UserRoleMap(
                    role_id=role_id,
                    menu_id=menu_id
                )
                for menu_id in new_menu_ids
            ]

            db.add_all(role_maps)

        db.commit()
        db.refresh(role)
        return success_response({
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "menuids" :update_data.get("menuids", [])
        })
        
    except Exception as e:
        db.rollback()   
        return error_response(str(e), 400)
    
    

# SOFT DELETE
@router.delete("/{role_id}")
def delete_role(role_id: int, db: Session = Depends(get_db)):
    
    try:
        dept = db.query(UserRole).filter(UserRole.id == role_id).first()

        if not dept:
            raise HTTPException(status_code=404, detail="Role not found")

        dept.is_deleted = 1
        db.commit()

        return success_response(message="Role deleted successfully")
    
    except Exception as e:
        db.rollback()
        return error_response(str(e), 400)