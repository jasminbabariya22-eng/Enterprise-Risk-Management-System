from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List,Dict
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.response import success_response, error_response

from app.models.risk_register import RiskRegister
from app.schemas.risk_register import (
    RiskRegisterCreate,
    RiskRegisterUpdate,
    RiskRegisterHybridResponse
)

from app.models.department import Department
from app.models.risk_register_hist import RiskRegisterHist

router = APIRouter(
    prefix="/risk-register",
    tags=["Risk Register"],
    dependencies=[Depends(get_current_user)]
)

# Helper function to apply eager loading on RiskRegister relationships (avoids N+1 query problem)
def get_risk_register_eager_options():
    return [
        joinedload(RiskRegister.department),
        joinedload(RiskRegister.risk_owner),
        joinedload(RiskRegister.risk_co_owner),
        joinedload(RiskRegister.status),
        joinedload(RiskRegister.function_head_status),
        joinedload(RiskRegister.risk_function_head_approval_by_name),
        joinedload(RiskRegister.risk_head_status),
        joinedload(RiskRegister.risk_head_approval_by_name),
        joinedload(RiskRegister.risk_manager_status),
        joinedload(RiskRegister.risk_manager_approval_by_name),
        joinedload(RiskRegister.created_name)
    ]

# for the response of each api
def build_hybrid_response(risk):
    return {
        "risk_register_id": risk.risk_register_id,
        "risk_id": risk.risk_id,
        "risk_name": risk.risk_name,

        "dept_id": risk.dept_id,
        "department_name": risk.department.dept_name if risk.department else None,

        "risk_owner_id": risk.risk_owner_id,
        "risk_owner_name": risk.risk_owner.log_id if risk.risk_owner else None,

        # "risk_created_by_name": risk.created_user.log_id if risk.created_user else None,

        "risk_co_owner_id": risk.risk_co_owner_id,
        "risk_co_owner_name": risk.risk_co_owner.log_id if risk.risk_co_owner else None,

        "financial_year": risk.financial_year,

        "risk_status": risk.risk_status,
        "risk_status_name": risk.status.status_name if risk.status else None,

        "risk_progress": risk.risk_progress,

        # ---------------- Function Head ----------------
        "risk_function_head_approval_status": risk.risk_function_head_approval_status,
        "risk_function_head_approval_status_name": (
            risk.function_head_status.status_name if risk.function_head_status else None
        ),
        "risk_function_head_approval_remark": risk.risk_function_head_approval_remark,
        "risk_function_head_approval_on": risk.risk_function_head_approval_on,
        "risk_function_head_approval_by": risk.risk_function_head_approval_by,
        "risk_function_head_approval_by_name": risk.risk_function_head_approval_by_name.log_id if risk.risk_function_head_approval_by_name else None,

        # ---------------- Risk Head ----------------
        "risk_head_approval_status": risk.risk_head_approval_status,
        "risk_head_approval_status_name": (
            risk.risk_head_status.status_name if risk.risk_head_status else None
        ),
        "risk_head_approval_remark": risk.risk_head_approval_remark,
        "risk_head_approved_on": risk.risk_head_approved_on,
        "risk_head_approval_by": risk.risk_head_approval_by,
        "risk_head_approval_by_name": risk.risk_head_approval_by_name.log_id if risk.risk_head_approval_by_name else None,

        # ---------------- Risk Manager ----------------
        "risk_manager_approval_status": risk.risk_manager_approval_status,
        "risk_manager_approval_status_name": (
            risk.risk_manager_status.status_name if risk.risk_manager_status else None
        ),
        "risk_manager_approval_remark": risk.risk_manager_approval_remark,
        "risk_manager_approved_on": risk.risk_manager_approved_on,
        "risk_manager_approval_by": risk.risk_manager_approval_by,
        "risk_manager_approval_by_name": risk.risk_manager_approval_by_name.log_id if risk.risk_manager_approval_by_name else None,

        "is_active": risk.is_active,
        "is_deleted": risk.is_deleted,

        "created_on": risk.created_on,
        "created_by": risk.created_by,
        "created_by_name" : risk.created_name.log_id if risk.created_name else None
    }
    
    

# Generate unique risk_id based on department sequence
def generate_risk_id(db: Session, dept_id: int):

    dept = db.query(Department).filter(
        Department.id == dept_id
    ).with_for_update().first()

    if not dept:
        raise Exception("Department not found")

    dept.last_risk_number += 1

    number = dept.last_risk_number

    risk_id = f"{dept.dept_short_name}-{str(number).zfill(4)}"

    return risk_id


# CREATE
@router.post("/")
def create_risk_register(payload: RiskRegisterCreate, db: Session = Depends(get_db)):

    try:

        dept = db.query(Department).filter(
            Department.id == payload.dept_id
        ).first()

        if not dept:
            raise HTTPException(status_code=404, detail="Department not found")

        # Generate department-wise risk id
        risk_id = generate_risk_id(db, dept.id)

        risk = RiskRegister(
            risk_id=risk_id,
            risk_name=payload.risk_name,
            dept_id=payload.dept_id,
            risk_owner_id=payload.risk_owner_id,
            risk_co_owner_id=payload.risk_co_owner_id,
            financial_year=payload.financial_year,
            risk_status=payload.risk_status,
            risk_progress=payload.risk_progress,
            created_by=1,
            created_on=datetime.now(timezone.utc),
            is_active=0,
            is_deleted=0
        )

        db.add(risk)
        db.flush()

        hist = RiskRegisterHist(                              # HISTORY TABLE INSERT
            risk_register_id=risk.risk_register_id,
            risk_id=risk.risk_id,
            risk_name=risk.risk_name,
            dept_id=risk.dept_id,
            risk_owner_id=risk.risk_owner_id,
            risk_co_owner_id=risk.risk_co_owner_id,
            financial_year=risk.financial_year,
            risk_status=risk.risk_status,
            risk_progress=risk.risk_progress,
            created_by=risk.created_by,
            created_on=datetime.now(timezone.utc),
            is_active=risk.is_active,
            is_deleted=risk.is_deleted
        )

        db.add(hist)

        db.commit()

        # Reload with relationships for response
        risk = (
            db.query(RiskRegister)
            .options(*get_risk_register_eager_options())
            .filter(RiskRegister.risk_register_id == risk.risk_register_id)
            .first()
        )

        return success_response(build_hybrid_response(risk))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# Get all financial years
@router.get("/get-financial-years")
def get_financial_years(db: Session = Depends(get_db)):
    try:
        years = (
            db.query(RiskRegister.financial_year)
            .filter(
                RiskRegister.financial_year.isnot(None),
                RiskRegister.financial_year != "",
                RiskRegister.is_deleted == 0,
                RiskRegister.is_active == 0
            )
            .distinct()
            .order_by(RiskRegister.financial_year.desc())
            .all()
        )

        result = [row[0] for row in years]

        return success_response(result)

    except Exception as e:
        return error_response(str(e), 400)

# Get ALL 
@router.get("/")
def get_All_Risks(db: Session = Depends(get_db)):
    try:
        # --- PREVIOUS UNOPTIMIZED CODE (Commented out) ---
        # risks = db.query(RiskRegister).filter(
        #     RiskRegister.is_deleted == 0 and RiskRegister.is_active == 0
        # ).all()

        # --- OPTIMIZED CODE (Eager loading relationships + proper AND condition) ---
        risks = (
            db.query(RiskRegister)
            .options(*get_risk_register_eager_options())
            .filter(
                RiskRegister.is_deleted == 0,
                RiskRegister.is_active == 0
            )
            .all()
        )

        response_list = [build_hybrid_response(r) for r in risks]
        return success_response(response_list)
    except Exception as e:
        return error_response(str(e), 400)

# Get by risk_id
@router.get("/{risk_id}")
def get_Risk_by_risk__id(risk_id: str, db: Session = Depends(get_db)):
    try:
        if any(char.isdigit() for char in risk_id):            # if user fill complete risk_id with prefix and number

            # --- PREVIOUS UNOPTIMIZED CODE (Commented out) ---
            # risk = db.query(RiskRegister).filter(
            #     RiskRegister.risk_id == risk_id,
            #     RiskRegister.is_deleted == 0,
            #     RiskRegister.is_active == 0
            # ).first()

            # --- OPTIMIZED CODE (Eager loading relationships) ---
            risk = (
                db.query(RiskRegister)
                .options(*get_risk_register_eager_options())
                .filter(
                    RiskRegister.risk_id == risk_id,
                    RiskRegister.is_deleted == 0,
                    RiskRegister.is_active == 0
                )
                .first()
            )

            if not risk:
                raise HTTPException(status_code=404, detail="Risk not found")

            response_list = [build_hybrid_response(risk)]
            return success_response(response_list)

        
        else:                                         # if user fill prfix only
            # --- PREVIOUS UNOPTIMIZED CODE (Commented out) ---
            # risks = db.query(RiskRegister).filter(
            #     RiskRegister.risk_id.like(f"{risk_id}%"),
            #     RiskRegister.is_deleted == 0,
            #     RiskRegister.is_active == 0
            # ).all()

            # --- OPTIMIZED CODE (Eager loading relationships) ---
            risks = (
                db.query(RiskRegister)
                .options(*get_risk_register_eager_options())
                .filter(
                    RiskRegister.risk_id.like(f"{risk_id}%"),
                    RiskRegister.is_deleted == 0,
                    RiskRegister.is_active == 0
                )
                .all()
            )

            if not risks:
                raise HTTPException(status_code=404, detail="No risks found")
            
            response_list = [build_hybrid_response(r) for r in risks]
            return success_response(response_list)

    except Exception as e:
        return error_response(str(e), 400)


# Get by risk_register_id
@router.get("/Risk_Register_id/{risk_register_id}")
def get_Risk_by_register_id(risk_register_id: int, db: Session = Depends(get_db)):
    try:
        # --- PREVIOUS UNOPTIMIZED CODE (Commented out) ---
        # risk = db.query(RiskRegister).filter(
        #     RiskRegister.risk_register_id == risk_register_id,
        #     RiskRegister.is_deleted == 0,
        #     RiskRegister.is_active == 0
        # ).first()

        # --- OPTIMIZED CODE (Eager loading relationships) ---
        risk = (
            db.query(RiskRegister)
            .options(*get_risk_register_eager_options())
            .filter(
                RiskRegister.risk_register_id == risk_register_id,
                RiskRegister.is_deleted == 0,
                RiskRegister.is_active == 0
            )
            .first()
        )

        if not risk:
            return error_response("Risk Register not found", 404)

        return success_response(build_hybrid_response(risk))

    except Exception as e:
        return error_response(str(e), 400)


# UPDATE Risk Register (Only allowed when risk is not yet approved by any level)
@router.put("/{risk_register_id}")
def update_Risk(
    risk_register_id: int,
    payload: RiskRegisterUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    try:
        # --- PREVIOUS UNOPTIMIZED CODE (Commented out) ---
        # risk = db.query(RiskRegister).filter(
        #     RiskRegister.risk_register_id == risk_register_id,
        #     RiskRegister.is_deleted == 0 and RiskRegister.is_active == 0
        # ).first()

        # --- OPTIMIZED CODE (Fixed Python 'and' clause in filter) ---
        risk = db.query(RiskRegister).filter(
            RiskRegister.risk_register_id == risk_register_id,
            RiskRegister.is_deleted == 0,
            RiskRegister.is_active == 0
        ).first()

        if not risk:
            return error_response("Risk not found", 404)

        update_data = payload.dict(exclude_unset=True)      # update fields

        for key, value in update_data.items():
            setattr(risk, key, value)

        risk.modified_by = current_user["id"]
        risk.modified_on = datetime.now(timezone.utc)

        db.flush()                                       # apply update before history insert

        # insert updated record into history table
        hist = RiskRegisterHist(
            risk_register_id=risk.risk_register_id,
            risk_id=risk.risk_id,
            risk_name=risk.risk_name,
            dept_id=risk.dept_id,
            risk_owner_id=risk.risk_owner_id,
            risk_co_owner_id=risk.risk_co_owner_id,
            financial_year=risk.financial_year,
            risk_status=risk.risk_status,
            risk_progress=risk.risk_progress,
            created_by=current_user["id"],
            created_on=datetime.now(timezone.utc),
            is_active=risk.is_active,
            is_deleted=0
        )

        db.add(hist)

        db.commit()

        return success_response(
            {"risk_register_id": risk.risk_register_id,
            "message": "Risk updated successfully"}
        )

    except Exception as e:
        db.rollback()
        return error_response(str(e), 400)
    
    

# DELETE (Soft Delete)
@router.delete("/{risk_register_id}")
def delete_risk(risk_register_id: int, db: Session = Depends(get_db)):
    try:
        risk = db.query(RiskRegister).filter(
            RiskRegister.risk_register_id == risk_register_id
        ).first()

        if not risk:
            raise HTTPException(status_code=404, detail="Risk not found")

        # Soft delete main table
        risk.is_deleted = 1
        risk.is_active = 1

        # Insert into history table
        hist = RiskRegisterHist(
            risk_register_id=risk.risk_register_id,
            risk_id=risk.risk_id,
            risk_name=risk.risk_name,
            dept_id=risk.dept_id,
            risk_owner_id=risk.risk_owner_id,
            risk_co_owner_id=risk.risk_co_owner_id,
            financial_year=risk.financial_year,
            risk_status=risk.risk_status,
            risk_progress=risk.risk_progress,

            created_by=risk.created_by,             
            created_on=risk.created_on,              
            modified_by=risk.modified_by,
            modified_on=datetime.now(timezone.utc),

            is_active=risk.is_active,
            is_deleted=risk.is_deleted
        )

        db.add(hist)
        db.commit()
        db.refresh(risk)

        return success_response({
            "risk_register_id": risk.risk_register_id,
            "message": "Risk deleted successfully"
        })

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))    
    
    
# Get Financial Year
# @router.get("/get-financial-years")
# def get_financial_years(db: Session = Depends(get_db)):
#     try:
#         years = (
#             db.query(RiskRegister.financial_year)
#             .filter(RiskRegister.financial_year.isnot(None))
#             .distinct()
#             .order_by(RiskRegister.financial_year.desc())
#             .all()
#         )

#         result = [row[0] for row in years]

#         return success_response(result)

#     except Exception as e:
#         return error_response(str(e), 400)


