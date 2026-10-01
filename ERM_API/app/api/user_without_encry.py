from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from typing import List
from datetime import datetime
from app.schemas.user import UserHybridResponse
from app.core.dependencies import get_current_user
from app.core.response import success_response, error_response
from app.models.user_type import UserType


from app.core.security import (get_password_hash,verify_password)


router = APIRouter(
    prefix="/users",
    tags=["Users"],
    dependencies=[Depends(get_current_user)]         #router-level protection
)

# --------------------------------
# CREATE USER
# --------------------------------
@router.post("/", response_model=UserResponse)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        user_data = user.dict()
        
        user_data["password"] = get_password_hash(user_data["password"])

        # convert empty string to null
        if user_data.get("contact_no") == "string" or user_data.get("contact_no") == "":
            user_data["contact_no"] = None

        if user_data.get("address") == "string" or user_data.get("address") == "":
            user_data["address"] = None

        db_user = User(
            **user_data,
            created_by=current_user["id"],
            created_on=datetime.utcnow(),
            is_deleted=0
        )

        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        return success_response({
            "id": db_user.id,
            "log_id": db_user.log_id,
            "password": db_user.password,
            "first_name": db_user.first_name,
            "last_name": db_user.last_name,
            "email": db_user.email,
            "country": db_user.country,
            "address": db_user.address,
            "status": db_user.status,
            "dept_id": db_user.dept_id,
            "role_id": db_user.role_id,
            "user_type_id": db_user.user_type_id,
            "is_deleted": db_user.is_deleted,
            "created_on": db_user.created_on,
            "photo": db_user.photo,
            "contact_no": db_user.contact_no,
            "country_code": db_user.country_code,
            "std_code": db_user.std_code,
            "user_city": db_user.user_city,
        })
        
    except Exception as e:
        db.rollback()
        return error_response(str(e), 400)


# --------------------------------
# GET USER BY ID
# --------------------------------
@router.get("/{user_id}", response_model=UserHybridResponse)
def get_user_by_id(user_id: int, db: Session = Depends(get_db)):
    
    try:
        user = db.query(User).filter(
            User.id == user_id,
            User.is_deleted == 0
        ).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return success_response({
            "id": user.id,
            "log_id": user.log_id,
            "password": user.password,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "country": user.country,
            "status": user.status,
            "address": user.address,

            "department_id": user.dept_id,
            "department_name": user.department.dept_name if user.department else None,

            "role_id": user.role_id,
            "role_name": user.role.name if user.role else None,

            "user_type_id": user.user_type_id,
            "user_type_name": user.user_type.name if user.user_type else None,

            "is_deleted": user.is_deleted,
            "created_on": user.created_on,
            
            "photo": user.photo,
            "contact_no": user.contact_no,
            "country_code": user.country_code,
            "std_code": user.std_code,
            "user_city": user.user_city,
        })
        
    except Exception as e:
        return error_response(str(e), 400)

# --------------------------------
# SOFT DELETE USER
# --------------------------------
@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    
    try:
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.is_deleted = 1
        db.commit()

        return success_response(message="User deleted successfully")
    
    except Exception as e:
        db.rollback()
        return error_response(str(e), 400)


# --------------------------------
# UPDATE USER
# --------------------------------
@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    
    try:
        user = db.query(User).filter(
            User.id == user_id,
            User.is_deleted == 0
        ).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        update_data = user_update.dict(exclude_unset=True)
        
        if "password" in update_data and update_data["password"]:
            update_data["password"] = get_password_hash(update_data["password"])

        for key, value in update_data.items():
            setattr(user, key, value)

        user.modified_by = current_user["id"]
        user.modified_on = datetime.utcnow()

        db.commit()
        db.refresh(user)

        return success_response({
            "id": user.id,
            "log_id": user.log_id,
            "password": user.password,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "country": user.country,
            "status": user.status,
            "address": user.address,
            "dept_id": user.dept_id,
            "role_id": user.role_id,
            "user_type_id": user.user_type_id,
            "is_deleted": user.is_deleted,
            "created_on": user.created_on,
            "photo": user.photo,
            "contact_no": user.contact_no,
            "country_code": user.country_code,
            "std_code": user.std_code,
            "user_city": user.user_city,
        })
        
    except Exception as e:
        db.rollback()
        return error_response(str(e), 400)

# --------------------------------
#  GET ALL USERS 
#---------------------------------  
@router.get("/", response_model=List[UserHybridResponse])
def get_users(db: Session = Depends(get_db)):
    
    try:
        users = (db.query(User)
                 .join(UserType, User.user_type_id == UserType.id)
                 .filter(User.is_deleted == 0,User.log_id != 'admin')
                 .order_by(User.first_name)
                 ).all()

        response = []

        for user in users:
            response.append({
                "id": user.id,
                "log_id": user.log_id,
                "password": user.password,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "country": user.country,
                "status": user.status,
                "address": user.address,

                "department_id": user.dept_id,
                "department_name": user.department.dept_name if user.department else None,

                "role_id": user.role_id,
                "role_name": user.role.name if user.role else None,

                "user_type_id": user.user_type_id,
                "user_type_name": user.user_type.name if user.user_type else None,

                "is_deleted": user.is_deleted,
                "created_on": user.created_on,
                
                "photo": user.photo,
                "contact_no": user.contact_no,
                "country_code": user.country_code,
                "std_code": user.std_code,
                "user_city": user.user_city,
            })

        return success_response(response)
    
    except Exception as e:
        return error_response(str(e), 400)
    
    

#-------------------------------------------------------------
#           Get User Department Wise except function head
#-------------------------------------------------------------
@router.get("/department/{dept_id}", response_model=UserHybridResponse)
def get_user_by_deptid( dept_id: int, db: Session = Depends(get_db)):
    
    try:
        users = ( db.query(User)
            .join(UserType, User.user_type_id == UserType.id)
            .filter(
                User.dept_id == dept_id,
                #UserType.name != 'Functional Head',
                UserType.name != 'Admin',
                User.is_deleted == 0)
            ).all()

        if not users:
            raise HTTPException(status_code=404, detail="User not found")
        response = []

        for user in users:
            response.append({
                "id": user.id,
                "log_id": user.log_id,
                "password": user.password,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "country": user.country,
                "status": user.status,
                "address": user.address,

                "department_id": user.dept_id,
                "department_name": user.department.dept_name if user.department else None,

                "role_id": user.role_id,
                "role_name": user.role.name if user.role else None,

                "user_type_id": user.user_type_id,
                "user_type_name": user.user_type.name if user.user_type else None,

                "is_deleted": user.is_deleted,
                "created_on": user.created_on,
                
                "photo": user.photo,
                "contact_no": user.contact_no,
                "country_code": user.country_code,
                "std_code": user.std_code,
                "user_city": user.user_city,
            })

        return success_response(response)        
    except Exception as e:
        return error_response(str(e), 400)
