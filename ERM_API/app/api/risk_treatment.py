from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.response import success_response, error_response

from app.models.risk_treatment import RiskTreatment
from app.schemas.risk_treatment import (
    RiskTreatmentCreate,
    RiskTreatmentUpdate,
    RiskTreatmentHybridResponse,
    TreatmentApproval
)
from app.models.risk_description import RiskDescription
from app.models.risk_register import RiskRegister
from app.models.risk_treatment_hist import RiskTreatmentHist
from app.models.mst_status import Status
from app.services.email_event_service import send_action_approve_reject_email

router = APIRouter(
    prefix="/risk-treatment",
    tags=["Risk Treatment"],
    dependencies=[Depends(get_current_user)]
)

# Helper function to apply eager loading on RiskTreatment relationships (avoids N+1 query problem)
def get_risk_treatment_eager_options():
    return [
        joinedload(RiskTreatment.risk_description).joinedload(RiskDescription.risk_register),
        joinedload(RiskTreatment.action_owner),
        joinedload(RiskTreatment.approved_user)
    ]

# for the response of each api
def build_hybrid_response(t):
    
    approval_status_name = None

    if t.approval_status == 1:
        approval_status_name = "Approved"
    elif t.approval_status == -1:
        approval_status_name = "Rejected"
    
    return {
        "risk_treatment_id": t.risk_treatment_id,
        "risk_description_id": t.risk_description_id,
        "risk_register_id": t.risk_register_id,

        "risk_name": (
            t.risk_description.risk_register.risk_name
            if t.risk_description and t.risk_description.risk_register
            else None
        ),

        "action_plan": t.action_plan,

        "action_owner_id": t.action_owner_id,
        "action_owner_name": (
            f"{t.action_owner.first_name} {t.action_owner.last_name}"
            if t.action_owner else None
        ),

        "target_date": t.target_date,
        "progress": t.progress,
        "action_status_id": t.action_status_id,
        "next_followup_date": t.next_followup_date,

        "approved_by": t.approved_by,
        
        "approved_by_name": (
            t.approved_user.log_id
            if t.approved_user
            else None
        ),
        
        "approved_on": t.approved_on,
        "approval_remark": t.approval_remark,
        "approval_status": t.approval_status,
        "approval_status_name": approval_status_name,

        "is_deleted": t.is_deleted,
        "created_on": t.created_on
    }
    

# CREATE
@router.post("/")
def create_risk_treatment(
    payload: RiskTreatmentCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        # Fetch risk_description
        risk_Description = db.query(RiskDescription).filter(
            RiskDescription.risk_description_id == payload.risk_description_id,
            RiskDescription.is_deleted == 0
        ).first()

        if not risk_Description:
            raise HTTPException(status_code=404, detail="Risk Description not found")

        # Fetch risk_id from risk_register
        risk_register = risk_Description.risk_register_id
        risk_id = risk_Description.risk_id

        # Insert into risk_treatment
        new_risk_treatment = RiskTreatment(
            risk_description_id = payload.risk_description_id,
            risk_register_id = risk_register,
            risk_id = risk_id,
            
            action_plan = payload.action_plan,
            action_owner_id = payload.action_owner_id,    # may be change
            target_date = payload.target_date,
            progress = payload.progress,
            action_status_id = payload.action_status_id,
            next_followup_date = payload.next_followup_date,
            
            approval_status=0,                                      # default
            
            created_on = datetime.now(timezone.utc),
            created_by = current_user["id"],
            
            is_deleted = 0)

        db.add(new_risk_treatment)
        db.commit()
        db.refresh(new_risk_treatment)

        # Insert into history table
        hist = RiskTreatmentHist(
            risk_treatment_id=new_risk_treatment.risk_treatment_id,
            risk_description_id=new_risk_treatment.risk_description_id,
            risk_register_id=new_risk_treatment.risk_register_id,
            risk_id=new_risk_treatment.risk_id,
            
            action_plan=new_risk_treatment.action_plan,
            action_owner_id=new_risk_treatment.action_owner_id,
            
            target_date=new_risk_treatment.target_date,
            progress=new_risk_treatment.progress,
            
            action_status_id=new_risk_treatment.action_status_id,
            next_followup_date=new_risk_treatment.next_followup_date,

            created_by=new_risk_treatment.created_by,
            created_on=new_risk_treatment.created_on,
            modified_by=new_risk_treatment.modified_by,
            modified_on=new_risk_treatment.modified_on,
            is_deleted=new_risk_treatment.is_deleted
        )

        db.add(hist)
        db.commit()

        # Reload with relationships for response
        new_risk_treatment = (
            db.query(RiskTreatment)
            .options(*get_risk_treatment_eager_options())
            .filter(RiskTreatment.risk_treatment_id == new_risk_treatment.risk_treatment_id)
            .first()
        )

        return success_response(build_hybrid_response(new_risk_treatment))
    
    except Exception as e:
        db.rollback()
        return error_response(str(e), 400)



# Get ALL
@router.get("/", response_model=List[RiskTreatmentHybridResponse])
def get_treatments(db: Session = Depends(get_db)):
    try:
        # --- PREVIOUS UNOPTIMIZED CODE (Commented out) ---
        # treatments = db.query(RiskTreatment).filter(
        #     RiskTreatment.is_deleted == 0
        # ).all()

        # --- OPTIMIZED CODE (Eager loading relationships to prevent N+1) ---
        treatments = (
            db.query(RiskTreatment)
            .options(*get_risk_treatment_eager_options())
            .filter(
                RiskTreatment.is_deleted == 0
            )
            .all()
        )

        response_list = [build_hybrid_response(t) for t in treatments]
        return success_response(response_list)
    
    except Exception as e:
        return error_response(str(e), 400)



# Get BY risk_treatment_id
@router.get("/risk_treatment_id/{risk_treatment_id}", response_model=RiskTreatmentHybridResponse)
def get_treatment(risk_treatment_id: int, db: Session = Depends(get_db)):
    try:
        # --- PREVIOUS UNOPTIMIZED CODE (Commented out) ---
        # treatment = db.query(RiskTreatment).filter(
        #     RiskTreatment.risk_treatment_id == risk_treatment_id,
        #     RiskTreatment.is_deleted == 0
        # ).first()

        # --- OPTIMIZED CODE (Eager loading relationships) ---
        treatment = (
            db.query(RiskTreatment)
            .options(*get_risk_treatment_eager_options())
            .filter(
                RiskTreatment.risk_treatment_id == risk_treatment_id,
                RiskTreatment.is_deleted == 0
            )
            .first()
        )

        if not treatment:
            raise HTTPException(status_code=404, detail="Risk Treatment not found")

        response_list = [build_hybrid_response(treatment)]
        return success_response(response_list)

    except Exception as e:
        return error_response(str(e), 400)
    
# Get BY risk_Description_id
@router.get("/risk_description_id/{risk_description_id}", response_model=RiskTreatmentHybridResponse)
def get_treatment(risk_description_id: int, db: Session = Depends(get_db)):
    try:
        # --- PREVIOUS UNOPTIMIZED CODE (Commented out) ---
        # treatment = db.query(RiskTreatment).filter(
        #     RiskTreatment.risk_description_id == risk_description_id,
        #     RiskTreatment.is_deleted == 0
        # ).first()

        # --- OPTIMIZED CODE (Eager loading relationships) ---
        treatment = (
            db.query(RiskTreatment)
            .options(*get_risk_treatment_eager_options())
            .filter(
                RiskTreatment.risk_description_id == risk_description_id,
                RiskTreatment.is_deleted == 0
            )
            .first()
        )

        if not treatment:
            raise HTTPException(status_code=404, detail="Risk Description not found")

        response_list = [build_hybrid_response(treatment)]
        return success_response(response_list)

    except Exception as e:
        return error_response(str(e), 400)



# Get by risk_id
@router.get("/{risk_id}")
def get_Risk_Treatment_by_risk_id(risk_id: str, db: Session = Depends(get_db)):
    try:
        if any(char.isdigit() for char in risk_id):            # if user fill complete risk_id with prefix and number

            # --- PREVIOUS UNOPTIMIZED CODE (Commented out) ---
            # risk = db.query(RiskTreatment).filter(
            #     RiskTreatment.risk_id == risk_id,
            #     RiskTreatment.is_deleted == 0
            # ).first()

            # --- OPTIMIZED CODE (Eager loading relationships) ---
            risk = (
                db.query(RiskTreatment)
                .options(*get_risk_treatment_eager_options())
                .filter(
                    RiskTreatment.risk_id == risk_id,
                    RiskTreatment.is_deleted == 0
                )
                .first()
            )

            if not risk:
                raise HTTPException(status_code=404, detail="Risk Treatment not found")

            response_list = [build_hybrid_response(risk)]
            return success_response(response_list)

        
        else:                                         # if user fill prfix only
            # --- PREVIOUS UNOPTIMIZED CODE (Commented out) ---
            # risks = db.query(RiskTreatment).filter(
            #     RiskTreatment.risk_id.like(f"{risk_id}%"),
            #     RiskTreatment.is_deleted == 0
            # ).all()

            # --- OPTIMIZED CODE (Eager loading relationships) ---
            risks = (
                db.query(RiskTreatment)
                .options(*get_risk_treatment_eager_options())
                .filter(
                    RiskTreatment.risk_id.like(f"{risk_id}%"),
                    RiskTreatment.is_deleted == 0
                )
                .all()
            )

            if not risks:
                raise HTTPException(status_code=404, detail="No Risk Treatments found")

            return success_response([build_hybrid_response(r) for r in risks])

    except Exception as e:
        return error_response(str(e), 400)



# UPDATE (Only allowed when risk is not yet approved by any level)
@router.put("/{risk_treatment_id}")
def update_Risk_treatment(
    risk_treatment_id: int,
    payload: RiskTreatmentUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    try:
        risk_tretment = db.query(RiskTreatment).filter(
            RiskTreatment.risk_treatment_id == risk_treatment_id,
            RiskTreatment.is_deleted == 0
        ).first()

        if not risk_tretment:
            return error_response("Risk Treatment not found", 404)

        update_data = payload.dict(exclude_unset=True)      # update fields

        for key, value in update_data.items():
            setattr(risk_tretment, key, value)

        risk_tretment.modified_by = current_user["id"]
        risk_tretment.modified_on = datetime.now(timezone.utc)

        db.flush()                                       # apply update before history insert

        # insert updated record into history table
        hist = RiskTreatmentHist(
            risk_treatment_id=risk_tretment.risk_treatment_id,
            risk_description_id=risk_tretment.risk_description_id,
            risk_register_id=risk_tretment.risk_register_id,
            risk_id=risk_tretment.risk_id,
            
            action_plan=risk_tretment.action_plan,
            action_owner_id=risk_tretment.action_owner_id,
            
            target_date=risk_tretment.target_date,
            progress=risk_tretment.progress,
            
            action_status_id=risk_tretment.action_status_id,
            next_followup_date=risk_tretment.next_followup_date,

            created_by=risk_tretment.created_by,
            created_on=risk_tretment.created_on,
            modified_by=risk_tretment.modified_by,
            modified_on=risk_tretment.modified_on,
            is_deleted=risk_tretment.is_deleted
        )

        db.add(hist)

        db.commit()
        db.refresh(risk_tretment)

        return success_response(
            {"risk_register_id": risk_tretment.risk_register_id,
            "message": "Risk updated successfully"}
        )

    except Exception as e:
        db.rollback()
        return error_response(str(e), 400)


# DELETE (Soft Delete)
@router.delete("/{treatment_id}")
def delete_treatment(treatment_id: int, db: Session = Depends(get_db)):
    try:
        treatment = db.query(RiskTreatment).filter(
            RiskTreatment.risk_treatment_id == treatment_id
        ).first()

        if not treatment:
            raise HTTPException(status_code=404, detail="Risk Treatment not found")

        treatment.is_deleted = 1
        
        hist = RiskTreatmentHist(
            risk_treatment_id = treatment.risk_treatment_id,
            risk_description_id = treatment.risk_description_id,
            risk_register_id = treatment.risk_register_id,
            risk_id = treatment.risk_id,
            action_plan = treatment.action_plan,
            action_owner_id = treatment.action_owner_id,
            target_date = treatment.target_date,
            progress = treatment.progress,
            action_status_id = treatment.action_status_id,
            next_followup_date = treatment.next_followup_date,
            created_by = treatment.created_by,
            created_on = treatment.created_on,
            
            modified_by = treatment.modified_by,
            modified_on = treatment.modified_on,
            
            is_deleted = treatment.is_deleted)
        
        db.add(hist)
        db.commit()
        
        db.refresh(treatment)

        return success_response({
            "risk_treatment_id": treatment.risk_treatment_id,
            "message": "Risk Treatment deleted successfully"
        })
        
    except Exception as e:
        db.rollback()
        return error_response(str(e), 400)
    
    

# Get Treatment history by treatment id
@router.get("/history/{treatment_id}")
def get_treatment_history(treatment_id: int, db: Session = Depends(get_db)):
    try:
        history_records = db.query(RiskTreatmentHist).filter(
            RiskTreatmentHist.risk_treatment_id == treatment_id
        ).all()

        if not history_records:
            raise HTTPException(status_code=404, detail="History not found")

        return success_response(history_records)

    except Exception as e:
        return error_response(str(e), 400)
    
# Treatment approved
@router.put("/{risk_treatment_id}/approve")
def approve_treatment(
    risk_treatment_id: int,
    data: TreatmentApproval,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:

        treatment = db.query(RiskTreatment).filter(
            RiskTreatment.risk_treatment_id == risk_treatment_id,
            RiskTreatment.is_deleted == 0,
            RiskTreatment.progress == "100",
            # RiskTreatment.action_status_id == Status.status_name(db, "Completed")
        ).first()

        if not treatment:
            return error_response("Risk Treatment is not completed",200)

        # Allow only 1 (Approved) and -1 (Rejected)
        if data.approval_status not in [1, -1]:
            return error_response("approval_status must be 1 (Approved) or -1 (Rejected)",200)

        treatment.approval_status = data.approval_status
        treatment.approval_remark = data.approval_remark
        treatment.approved_by = current_user["id"]
        treatment.approved_on = datetime.now(timezone.utc)

        treatment.modified_by = current_user["id"]
        treatment.modified_on = datetime.now(timezone.utc)

        db.commit()
        db.refresh(treatment)
        
        # sent email
        send_action_approve_reject_email(db,treatment)
        
        db.commit()

        return success_response({
            "risk_treatment_id": treatment.risk_treatment_id,
            "approval_status": treatment.approval_status,
            "approval_status_name": (
                "Approved"
                if treatment.approval_status == 1
                else "Rejected"
            ),
            "approval_remark": treatment.approval_remark,
            "approved_by": treatment.approved_by,
            "approved_on": treatment.approved_on,
            "approved_by_name": (
                treatment.approved_user.log_id
                if treatment.approved_user
                else None
            )
        })

    except Exception as e:
        db.rollback()
        return error_response(str(e), 400)