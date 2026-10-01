from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.response import success_response, error_response


from app.schemas.risk_description import (
    RiskDescriptionCreate,
    RiskDescriptionUpdate,
    RiskDescriptionHybridResponse,
)
from app.models.risk_register import RiskRegister
from app.models.risk_description import RiskDescription
from app.models.risk_description_hist import RiskDescriptionHist

router = APIRouter(
    prefix="/risk-description",
    tags=["Risk Description"],
    dependencies=[Depends(get_current_user)]
)

# Helper function to apply eager loading on RiskDescription relationships (avoids N+1 query problem)
def get_risk_description_eager_options():
    return [
        joinedload(RiskDescription.risk_register)
    ]

# for the response of each api
def build_hybrid_response(desc):
    return {
        "risk_description_id": desc.risk_description_id,
        "risk_register_id": desc.risk_register_id,
        "risk_id": desc.risk_id,
        "risk_name": desc.risk_register.risk_name if desc.risk_register else None,

        "risk_description": desc.risk_description,

        "inherent_risk_likelihood_id": desc.inherent_risk_likelihood_id,
        "inherent_risk_impact_id": desc.inherent_risk_impact_id,

        "mitigation": desc.mitigation,

        "current_risk_likelihood_id": desc.current_risk_likelihood_id,
        "current_risk_impact_id": desc.current_risk_impact_id,

        "is_deleted": desc.is_deleted,
        "created_on": desc.created_on
    }

# CREATE
@router.post("/")
def create_risk_description(
    payload: RiskDescriptionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        # Fetch risk_register
        risk_register = db.query(RiskRegister).filter(
            RiskRegister.risk_register_id == payload.risk_register_id,
            RiskRegister.is_deleted == 0
        ).first()

        if not risk_register:
            raise HTTPException(status_code=404, detail="Risk Register not found")

        # Fetch risk_id from risk_register
        risk_id = risk_register.risk_id

        # Insert into risk_description
        new_risk_desc = RiskDescription(
            risk_register_id=payload.risk_register_id,
            risk_id=risk_id,
            risk_description=payload.risk_description,

            inherent_risk_likelihood_id=payload.inherent_risk_likelihood_id,
            inherent_risk_impact_id=payload.inherent_risk_impact_id,

            mitigation=payload.mitigation,

            current_risk_likelihood_id=payload.current_risk_likelihood_id,
            current_risk_impact_id=payload.current_risk_impact_id,

            created_by=current_user["id"],
            created_on = datetime.now(timezone.utc),
            is_deleted=0
        )

        db.add(new_risk_desc)
        db.commit()
        db.refresh(new_risk_desc)

        # Insert into history table
        hist = RiskDescriptionHist(
            risk_description_id=new_risk_desc.risk_description_id,
            risk_register_id=new_risk_desc.risk_register_id,
            risk_id=new_risk_desc.risk_id,
            risk_description=new_risk_desc.risk_description,

            inherent_risk_likelihood_id=new_risk_desc.inherent_risk_likelihood_id,
            inherent_risk_impact_id=new_risk_desc.inherent_risk_impact_id,

            mitigation=new_risk_desc.mitigation,

            current_risk_likelihood_id=new_risk_desc.current_risk_likelihood_id,
            current_risk_impact_id=new_risk_desc.current_risk_impact_id,

            created_by=new_risk_desc.created_by,
            created_on=new_risk_desc.created_on,
            is_deleted=new_risk_desc.is_deleted
        )

        db.add(hist)

        db.commit()

        # Reload with relationships for response
        new_risk_desc = (
            db.query(RiskDescription)
            .options(*get_risk_description_eager_options())
            .filter(RiskDescription.risk_description_id == new_risk_desc.risk_description_id)
            .first()
        )

        return success_response(build_hybrid_response(new_risk_desc))

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# Get ALL Risk Description
@router.get("/")
def get_All_Risk_Descriptions(db: Session = Depends(get_db)):
    try:
        # --- PREVIOUS UNOPTIMIZED CODE (Commented out) ---
        # descriptions = db.query(RiskDescription).filter(
        #     RiskDescription.is_deleted == 0
        # ).all()

        # --- OPTIMIZED CODE (Eager loading relationships to prevent N+1) ---
        descriptions = (
            db.query(RiskDescription)
            .options(*get_risk_description_eager_options())
            .filter(
                RiskDescription.is_deleted == 0
            )
            .all()
        )

        response_list = [build_hybrid_response(d) for d in descriptions]
        return success_response(response_list)

    except Exception as e:
        return error_response(str(e), 400)
    

# Get by risk_id
@router.get("/{risk_id}")
def get_Risk_Description_by_risk_id(risk_id: str, db: Session = Depends(get_db)):
    try:
        if any(char.isdigit() for char in risk_id):            # if user fill complete risk_id with prefix and number

            # --- PREVIOUS UNOPTIMIZED CODE (Commented out) ---
            # risk = db.query(RiskDescription).filter(
            #     RiskDescription.risk_id == risk_id,
            #     RiskDescription.is_deleted == 0
            # ).first()

            # --- OPTIMIZED CODE (Eager loading relationships) ---
            risk = (
                db.query(RiskDescription)
                .options(*get_risk_description_eager_options())
                .filter(
                    RiskDescription.risk_id == risk_id,
                    RiskDescription.is_deleted == 0
                )
                .first()
            )

            if not risk:
                raise HTTPException(status_code=404, detail="Risk Description not found")

            response_list = [build_hybrid_response(risk)]
            return success_response(response_list)

        
        else:                                         # if user fill prfix only
            # --- PREVIOUS UNOPTIMIZED CODE (Commented out) ---
            # risks = db.query(RiskDescription).filter(
            #     RiskDescription.risk_id.like(f"{risk_id}%"),
            #     RiskDescription.is_deleted == 0
            # ).all()

            # --- OPTIMIZED CODE (Eager loading relationships) ---
            risks = (
                db.query(RiskDescription)
                .options(*get_risk_description_eager_options())
                .filter(
                    RiskDescription.risk_id.like(f"{risk_id}%"),
                    RiskDescription.is_deleted == 0
                )
                .all()
            )

            if not risks:
                raise HTTPException(status_code=404, detail="No Risk Descriptions found")

            return success_response([build_hybrid_response(r) for r in risks])

    except Exception as e:
        return error_response(str(e), 400)


# Get BY Risk_Description_id
@router.get("/risk_description_id/{risk_description_id}", response_model=RiskDescriptionHybridResponse)
def Get_Risk_Description_by_risk_description_id(risk_description_id: int, db: Session = Depends(get_db)):
    try:
        # --- PREVIOUS UNOPTIMIZED CODE (Commented out) ---
        # desc = db.query(RiskDescription).filter(
        #     RiskDescription.risk_description_id == risk_description_id,
        #     RiskDescription.is_deleted == 0
        # ).first()

        # --- OPTIMIZED CODE (Eager loading relationships) ---
        desc = (
            db.query(RiskDescription)
            .options(*get_risk_description_eager_options())
            .filter(
                RiskDescription.risk_description_id == risk_description_id,
                RiskDescription.is_deleted == 0
            )
            .first()
        )

        if not desc:
            raise HTTPException(status_code=404, detail="Risk Description not found")

        response_list = [build_hybrid_response(desc)]
        return success_response(response_list)

    except Exception as e:
        return error_response(str(e), 400)



# UPDATE
@router.put("/{risk_description_id}", response_model=RiskDescriptionHybridResponse)
def update_Risk_Description(
    risk_description_id: int,
    payload: RiskDescriptionUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    try:
        risk_desc = db.query(RiskDescription).filter(
            RiskDescription.risk_description_id == risk_description_id,
            RiskDescription.is_deleted == 0
        ).first()
        
        risk_id = risk_desc.risk_id

        if not risk_desc:
            return error_response("Risk Description not found", 404)

        update_data = payload.dict(exclude_unset=True)      # update fields

        for key, value in update_data.items():
            setattr(risk_desc, key, value)

        risk_desc.modified_by = current_user["id"]
        risk_desc.modified_on = datetime.now(timezone.utc)

        db.flush()                                       # apply update before history insert

        # insert updated record into history table
        hist = RiskDescriptionHist(
            risk_description_id=risk_desc.risk_description_id,
            risk_register_id=risk_desc.risk_register_id,
            risk_id=risk_id,
            risk_description=risk_desc.risk_description,
            
            inherent_risk_likelihood_id=risk_desc.inherent_risk_likelihood_id,
            inherent_risk_impact_id=risk_desc.inherent_risk_impact_id,
            
            mitigation=risk_desc.mitigation,
            current_risk_likelihood_id=risk_desc.current_risk_likelihood_id,
            current_risk_impact_id=risk_desc.current_risk_impact_id,
            created_on=datetime.now(timezone.utc),
            created_by=current_user["id"],
            
            modified_by=current_user["id"],
            modified_on=datetime.now(timezone.utc),
            is_deleted=risk_desc.is_deleted
        )

        db.add(hist)

        db.commit()

        return success_response(
            {"risk_description_id": risk_desc.risk_description_id,
            "message": "Risk Description updated successfully"}
        )

    except Exception as e:
        db.rollback()
        return error_response(str(e), 400)
    

# SOFT DELETE
@router.delete("/{risk_description_id}")
def Delete_Risk_Description(risk_description_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    try:
        risk_desc = db.query(RiskDescription).filter(
            RiskDescription.risk_description_id == risk_description_id
        ).first()

        if not risk_desc:
            raise HTTPException(status_code=404, detail="Risk Description not found")

        # Soft delete main table
        risk_desc.is_deleted = 1

        # Insert into history table
        hist = RiskDescriptionHist(
            risk_description_id=risk_desc.risk_description_id,
            risk_register_id=risk_desc.risk_register_id,
            risk_id=risk_desc.risk_id,
            risk_description=risk_desc.risk_description,
            inherent_risk_likelihood_id=risk_desc.inherent_risk_likelihood_id,
            inherent_risk_impact_id=risk_desc.inherent_risk_impact_id,
            mitigation=risk_desc.mitigation,
            current_risk_likelihood_id=risk_desc.current_risk_likelihood_id,
            current_risk_impact_id=risk_desc.current_risk_impact_id,
            
            created_by=current_user["id"],
            created_on=datetime.now(timezone.utc),
            
            modified_by=current_user["id"],
            modified_on=datetime.now(timezone.utc),
            
            is_deleted=risk_desc.is_deleted
        )

        db.add(hist)
        db.commit()
        db.refresh(risk_desc)

        return success_response({
            "risk_description_id": risk_desc.risk_description_id,
            "message": "Risk Description deleted successfully"
        })

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))