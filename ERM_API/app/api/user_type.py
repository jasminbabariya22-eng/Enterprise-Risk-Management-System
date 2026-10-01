from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from app.core.database import get_db
from app.models.user_type import UserType
from app.schemas.user_type import (
    UserTypeCreate,
    UserTypeUpdate,
    UserTypeResponse
)
from app.core.dependencies import get_current_user
from app.core.response import success_response, error_response

router = APIRouter(prefix="/user_types", 
                   tags=["User Types"],
                   dependencies=[Depends(get_current_user)]
                   )


# CREATE
@router.post("/", response_model=UserTypeResponse)
def create_user_type(data: UserTypeCreate, db: Session = Depends(get_db)):
    
    try:
        dept = UserType(
            name=data.name,
            description=data.description,
            is_deleted=0,
            created_on=datetime.utcnow()
        )
        db.add(dept)
        db.commit()
        db.refresh(dept)
        return success_response({
            "id": dept.id,
            "name": dept.name,
            "description": dept.description,
            "created_on": dept.created_on,
            "modified_on": dept.modified_on
        })
        
    except Exception as e:
        db.rollback()
        return error_response(str(e), 400)


# GET ALL
@router.get("/", response_model=List[UserTypeResponse])
def get_user_types(db: Session = Depends(get_db)):
    
    try:
        user_types = db.query(UserType).filter(UserType.is_deleted == 0).all()
        response = []
        
        for user_type in user_types:
            response.append({
                "id": user_type.id,
                "name": user_type.name,
                "description": user_type.description,
                "created_on": user_type.created_on,
                "modified_on": user_type.modified_on
            })
        return success_response(response)
    
    except Exception as e:
        return error_response(str(e), 400)


# GET BY ID
@router.get("/{user_type_id}", response_model=UserTypeResponse)
def get_user_type(user_type_id: int, db: Session = Depends(get_db)):
    
    try:
        dept = db.query(UserType).filter(
            UserType.id == user_type_id,
            UserType.is_deleted == 0
        ).first()

        if not dept:
            raise HTTPException(status_code=404, detail="User Type not found")

        return success_response({
            "id": dept.id,
            "name": dept.name,
            "description": dept.description,
            "created_on": dept.created_on,
            "modified_on": dept.modified_on
        })
        
    except Exception as e:
        return error_response(str(e), 400)

# UPDATE User Type
@router.put("/{user_type_id}", response_model=UserTypeResponse)
def update_user_type(user_type_id: int, data: UserTypeUpdate, db: Session = Depends(get_db)):
    
    try:
        dept = db.query(UserType).filter(UserType.id == user_type_id).first()

        if not dept:
            raise HTTPException(status_code=404, detail="User Type not found")

        update_data = data.dict(exclude_unset=True)

        for key, value in update_data.items():
            setattr(dept, key, value)

        db.commit()
        db.refresh(dept)
        return success_response({
            "id": dept.id,
            "name": dept.name,
            "description": dept.description,
            "created_on": dept.created_on,
            "modified_on": dept.modified_on
        })

    except Exception as e:
        db.rollback()
        return error_response(str(e), 400)

# SOFT DELETE
@router.delete("/{user_type_id}")
def delete_user_type(user_type_id: int, db: Session = Depends(get_db)):
    
    try:
        dept = db.query(UserType).filter(UserType.id == user_type_id).first()

        if not dept:
            raise HTTPException(status_code=404, detail="User Type not found")

        dept.is_deleted = 1
        db.commit()

        return success_response(message="User Type deleted successfully")
    
    except Exception as e:
        db.rollback()
        return error_response(str(e), 400)