from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.mst_status import Status
from app.core.dependencies import get_current_user
from app.core.response import success_response, error_response
from typing import List
from app.schemas.Status import *

router = APIRouter(
    prefix="/approval",
    tags=["Approval"]
)

# Get all Status 
@router.get("/", response_model=List[StatusResponse])
def get_all_status(db: Session = Depends(get_db)):
    try:
        statuses = db.query(Status).filter(Status.is_deleted == 0).all()
        return success_response(statuses)
    except Exception as e:
        return error_response(str(e), 400)


# Create Status
@router.post("/", response_model=StatusResponse)
def create_status(
    payload: StatusCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        new_status = Status(
            status_name=payload.status_name,
            type=payload.type,
            created_by=current_user["id"],
            created_on=datetime.utcnow(),
            is_deleted=0
        )

        db.add(new_status)
        db.commit()
        db.refresh(new_status)

        return success_response(new_status)
    except Exception as e:
        db.rollback()
        return error_response(str(e), 400)

# Update Status
@router.put("/{status_id}", response_model=StatusResponse)
def update_status(
    status_id: int,
    payload: StatusUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        status = db.query(Status).filter(Status.id == status_id, Status.is_deleted == 0).first()

        if not status:
            return error_response("Status not found", 404)

        if payload.status_name is not None:
            status.status_name = payload.status_name

        if payload.type is not None:
            status.type = payload.type

        status.modified_by = current_user["id"]
        status.modified_on = datetime.utcnow()

        db.commit()
        db.refresh(status)

        return success_response(status)
    
    except Exception as e:
        db.rollback()
        return error_response(str(e), 400)


# GET STATUS BY TYPE
@router.get("/type/{status_type}")
def get_status_by_type(status_type: str, db: Session = Depends(get_db)):
    try:
        statuses = db.query(Status).filter(
            Status.type.ilike(f"%{status_type}%"),
            Status.is_deleted == 0
        ).order_by(Status.id.asc()).all()

        if not statuses:
            statuses = db.query(Status).filter(Status.is_deleted == 0).order_by(Status.id.asc()).all()

        return success_response([
            {
                "id": s.id,
                "status_name": s.status_name,
                "type": s.type
            }
            for s in statuses
        ])

    except Exception as e:
        return error_response(str(e))


# GET STATUS BY ID
@router.get("/id/{status_id}")
def get_status_by_id(status_id: int, db: Session = Depends(get_db)):
    try:
        status = db.query(Status).filter(
            Status.id == status_id,
            Status.is_deleted == 0
        ).first()

        if not status:
            return error_response("Status not found")

        return success_response({
            "id": status.id,
            "status_name": status.status_name,
            "type": status.type
        })

    except Exception as e:
        return error_response(str(e))


# GET STATUS BY NAME
@router.get("/name/{status_name}")
def get_status_by_status_name(status_name: str, db: Session = Depends(get_db)):
    try:
        status = db.query(Status).filter(
            Status.status_name == status_name,
            Status.is_deleted == 0
        ).first()

        if not status:
            return error_response("Status not found")

        return success_response({
            "id": status.id,
            "status_name": status.status_name,
            "type": status.type
        })

    except Exception as e:
        return error_response(str(e))
    


# Delete Status
@router.delete("/{status_id}")
def delete_status(
    status_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    
    try:
        status = db.query(Status).filter(Status.id == status_id, Status.is_deleted == 0).first()

        if not status:
            return error_response("Status not found", 404)

        status.is_deleted = 1
        status.modified_by = current_user["id"]
        status.modified_on = datetime.utcnow()

        db.commit()

        return success_response({"message": "Status deleted successfully"})
    
    except Exception as e:
        db.rollback()
        return error_response(str(e), 400)