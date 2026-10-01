from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.response import success_response, error_response

from app.schemas.risk_approval import *

from app.services.risk_approval import *

from datetime import date

from app.models.user import User
from app.models.risk_register_hist import RiskRegisterHist


router = APIRouter(
    prefix="/approval",
    tags=["Approval"],
    dependencies=[Depends(get_current_user)]
)


# ---------------- HISTORY RESPONSE ----------------

def build_history_response(row):

    status_map = {
        1: "Approved",
        -1: "Rejected"
    }

    return {

        "risk_register_id": row.risk_register_id,
        "risk_id": row.risk_id,
        "risk_name": row.risk_name,

        "risk_status": row.risk_status,

        "risk_status_name": (
            row.status.status_name
            if row.status else None
        ),

        "risk_progress": row.risk_progress,

        # ---------------- FUNCTION HEAD ----------------

        "risk_function_head_approval_status":
            row.risk_function_head_approval_status,

        "risk_function_head_approval_status_name":
            status_map.get(
                row.risk_function_head_approval_status
            ),

        "risk_function_head_approval_remark":
            row.risk_function_head_approval_remark,

        "risk_function_head_approval_on":
            row.risk_function_head_approval_on,

        "risk_function_head_approval_by":
            row.risk_function_head_approval_by,

        "risk_function_head_approval_by_name": (
            row.function_head_user.log_id
            if row.function_head_user else None
        ),

        # ---------------- RISK HEAD ----------------

        "risk_head_approval_status":
            row.risk_head_approval_status,

        "risk_head_approval_status_name":
            status_map.get(
                row.risk_head_approval_status
            ),

        "risk_head_approval_remark":
            row.risk_head_approval_remark,

        "risk_head_approved_on":
            row.risk_head_approved_on,

        "risk_head_approval_by":
            row.risk_head_approval_by,

        "risk_head_approval_by_name": (
            row.risk_head_user.log_id
            if row.risk_head_user else None
        ),

        # ---------------- RISK MANAGER ----------------

        "risk_manager_approval_status":
            row.risk_manager_approval_status,

        "risk_manager_approval_status_name":
            status_map.get(
                row.risk_manager_approval_status
            ),

        "risk_manager_approval_remark":
            row.risk_manager_approval_remark,

        "risk_manager_approved_on":
            row.risk_manager_approved_on,

        "risk_manager_approval_by":
            row.risk_manager_approval_by,

        "risk_manager_approval_by_name": (
            row.risk_manager_user.log_id
            if row.risk_manager_user else None
        ),

        # ---------------- AUDIT ----------------

        "created_by": row.created_by,
        "created_on": row.created_on,

        "created_by_name": (
            row.created_user.log_id
            if row.created_user else None
        ),

        "modified_by": row.modified_by,
        "modified_on": row.modified_on
    }


# ---------------- APPROVE API ----------------

@router.post("/approve")
def approve_risk_api(
    data: RiskApprovalRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    try:

        (
            risk,

            approval_status_id,
            approval_status_name,

            risk_status_id,
            risk_status_name

        ) = approve_risk(
            db=db,
            data=data,
            user_id=current_user["id"]
        )

        # ---------------- USER INFO ----------------

        user_obj = db.query(User).filter(
            User.id == current_user["id"]
        ).first()

        approval_by_name = (
            user_obj.log_id if user_obj else None
        )

        # ---------------- RESPONSE ----------------

        return success_response(
            data={

                "risk_register_id":
                    data.risk_register_id,

                "approval_level":
                    data.approval_level,

                "approval_status_id":
                    approval_status_id,

                "approval_status_name":
                    approval_status_name,

                "risk_status_id":
                    risk_status_id,

                "risk_status_name":
                    risk_status_name,

                "approval_by_name":
                    approval_by_name,

                "risk_approval_on":
                    date.today(),

                "remark":
                    data.remark
            }
        )

    except Exception as e:

        return error_response(str(e), 400)


# ---------------- HISTORY API ----------------

@router.get("/history/{risk_register_id}")
def get_risk_history(
    risk_register_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    try:

        # --- PREVIOUS UNOPTIMIZED CODE (Commented out) ---
        # data = db.query(RiskRegisterHist).filter(
        #     RiskRegisterHist.risk_register_id
        #     == risk_register_id,
        #     or_(
        #         RiskRegisterHist
        #         .risk_function_head_approval_status != None,
        #         RiskRegisterHist
        #         .risk_head_approval_status != None,
        #         RiskRegisterHist
        #         .risk_manager_approval_status != None
        #     )
        # ).order_by(
        #     RiskRegisterHist.modified_on.desc(),
        #     RiskRegisterHist.created_on.desc()
        # ).all()

        # --- OPTIMIZED CODE (Eager loading relationships to eliminate N+1 queries) ---
        data = (
            db.query(RiskRegisterHist)
            .options(
                joinedload(RiskRegisterHist.status),
                joinedload(RiskRegisterHist.function_head_user),
                joinedload(RiskRegisterHist.risk_head_user),
                joinedload(RiskRegisterHist.risk_manager_user),
                joinedload(RiskRegisterHist.created_user)
            )
            .filter(
                RiskRegisterHist.risk_register_id == risk_register_id,
                or_(
                    RiskRegisterHist.risk_function_head_approval_status.isnot(None),
                    RiskRegisterHist.risk_head_approval_status.isnot(None),
                    RiskRegisterHist.risk_manager_approval_status.isnot(None)
                )
            )
            .order_by(
                RiskRegisterHist.modified_on.desc(),
                RiskRegisterHist.created_on.desc()
            )
            .all()
        )

        if not data:

            raise HTTPException(
                status_code=404,
                detail="No history found"
            )

        return success_response(
            [build_history_response(r) for r in data]
        )

    except Exception as e:

        return error_response(str(e), 400)



#----------------force Approval------------------


@router.post("/force-approve")
def force_approve_api(
    data: ForceApproveRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    try:
        (risk, approved_levels, risk_status_id, risk_status_name) = force_approve_risk(
            db=db,
            data=data,
            user_id=current_user["id"],
            user_type=current_user["user_type_name"]
        )

        user_obj = db.query(User).filter(
            User.id == current_user["id"]
        ).first()

        approval_by_name = (
            user_obj.log_id
            if user_obj
            else None
        )

        # ---------------- LEVEL NAMES ----------------

        level_map = {
            1: "Functional Head",
            2: "Risk Manager",
            3: "Risk Head"
        }

        approved_level_names = [
            level_map[level]
            for level in approved_levels
        ]

        return success_response(
            data={

                "risk_register_id":
                    risk.risk_register_id,

                "approved_levels":
                    approved_levels,

                "approved_level_names":
                    approved_level_names,

                "approval_by":
                    approval_by_name,

                "approval_by_user_type":
                    current_user["user_type_name"],

                "risk_status_id":
                    risk_status_id,

                "risk_status_name":
                    risk_status_name,

                "remark":
                    data.remark,

                "approved_on":
                    date.today()

            }
        )

    except Exception as e:

        return error_response(
            str(e),
            400
        )















# from fastapi import APIRouter, Depends, HTTPException
# from sqlalchemy.orm import Session
# from sqlalchemy import or_
# from app.core.database import get_db
# from app.core.dependencies import get_current_user
# from app.core.response import success_response, error_response

# from app.schemas.risk_approval import RiskApprovalRequest
# from app.services.risk_approval import approve_risk

# from datetime import date
# from app.models.user import User
# from app.models.risk_register_hist import RiskRegisterHist


# # for the return each data
# def build_history_response(row):
    
#     if row.risk_function_head_approval_status == 1:          # for the risk register table
#         function_head_status_name = "Approved"
#     elif row.risk_function_head_approval_status == -1:
#         function_head_status_name = "Rejected"
#     else:
#         function_head_status_name = None
        
#     if row.risk_head_approval_status == 1:
#         risk_head_status_name = "Approved"
#     elif row.risk_head_approval_status == -1:
#         risk_head_status_name = "Rejected"
#     else:
#         risk_head_status_name = None

#     if row.risk_manager_approval_status == 1:
#         risk_manager_status_name = "Approved"
#     elif row.risk_manager_approval_status == -1:
#         risk_manager_status_name = "Rejected"
#     else:
#         risk_manager_status_name = None

#     return {
#         "risk_register_id": row.risk_register_id,
#         "risk_id": row.risk_id,
#         "risk_status": row.risk_status,
#         "risk_status_name": row.status.status_name if row.status else None,
#         "risk_progress": row.risk_progress,

#         # ---------------- Function Head ----------------
#         "risk_function_head_approval_status": row.risk_function_head_approval_status,
#         "risk_function_head_approval_status_name":function_head_status_name,
#         "risk_function_head_approval_remark": row.risk_function_head_approval_remark,
#         "risk_function_head_approval_on": row.risk_function_head_approval_on,
#         "risk_function_head_approval_by": row.risk_function_head_approval_by,
#         "risk_function_head_approval_by_name": (
#             row.function_head_user.log_id if row.function_head_user else None
#         ),

#         # ---------------- Risk Head ----------------
#         "risk_head_approval_status": row.risk_head_approval_status,
#         "risk_head_approval_status_name":risk_head_status_name,
#         "risk_head_approval_remark": row.risk_head_approval_remark,
#         "risk_head_approved_on": row.risk_head_approved_on,
#         "risk_head_approval_by": row.risk_head_approval_by,
#         "risk_head_approval_by_name": (
#             row.risk_head_user.log_id if row.risk_head_user else None
#         ),

#         # ---------------- Risk Manager ----------------
#         "risk_manager_approval_status": row.risk_manager_approval_status,
#         "risk_manager_approval_status_name": risk_manager_status_name,
#         "risk_manager_approval_remark": row.risk_manager_approval_remark,
#         "risk_manager_approved_on": row.risk_manager_approved_on,
#         "risk_manager_approval_by": row.risk_manager_approval_by,
#         "risk_manager_approval_by_name": (
#             row.risk_manager_user.log_id if row.risk_manager_user else None
#         ),

#         # ---------------- Audit ----------------
#         "created_by": row.created_by,
#         "created_on": row.created_on,
#         "created_by_name": (
#             row.created_user.log_id if row.created_user else None
#         ),

#         "modified_by": row.modified_by,
#         "modified_on": row.modified_on
#     }


# router = APIRouter(prefix="/approval", tags=["Approval"], dependencies=[Depends(get_current_user)])


# # Get Approval for existing Risk
# # @router.post("/approve")
# # def approve_risk_api(
# #     data: RiskApprovalRequest,
# #     db: Session = Depends(get_db),
# #     current_user = Depends(get_current_user)
# # ):

# #     try:
# #         risk = approve_risk(db, data, current_user["id"])

# #         return success_response(
# #             data=data
# #         )
        
# #     except Exception as e:
# #         return error_response(str(e), 400)

# @router.post("/approve")                        # for the Approve any riks using risk_register_id            
# def approve_risk_api(
#     data: RiskApprovalRequest,
#     db: Session = Depends(get_db),
#     current_user = Depends(get_current_user)
# ):
#     try:
#         risk, status_id, status_name = approve_risk(db, data, current_user["id"])

#         user_obj = db.query(User).filter(
#             User.id == current_user["id"]
#         ).first()

#         approval_by_name = user_obj.log_id if user_obj else None

#         return success_response(
#             data={
#                 "risk_register_id": data.risk_register_id,
#                 "approval_level": data.approval_level,
#                 "approval_status_id": data.approval_status_id,
#                 "risk_status_id": status_id,     # actual ID from mst_status table
#                 "risk_status_name": status_name,
#                 "approval_by_name": approval_by_name,
#                 "risk_approval_on": date.today(),
#                 "remark": data.remark
#             }
#         )

#     except Exception as e:
#         return error_response(str(e), 400)
    
    
# # get by risk_register_id in History table

# @router.get("/history/{risk_register_id}")
# def get_risk_history(
#     risk_register_id: int,
#     db: Session = Depends(get_db),
#     current_user = Depends(get_current_user)
# ):
#     try:
#         data = db.query(RiskRegisterHist).filter(
#             RiskRegisterHist.risk_register_id == risk_register_id,
#             or_(
#                 RiskRegisterHist.risk_function_head_approval_status != None,
#                 RiskRegisterHist.risk_head_approval_status != None,
#                 RiskRegisterHist.risk_manager_approval_status != None
#             )
#         ).order_by(
#             RiskRegisterHist.modified_on.desc(),
#             RiskRegisterHist.created_on.desc()
#         ).all()

#         if not data:
#             raise HTTPException(status_code=404, detail="No history found")

#         return success_response([build_history_response(r) for r in data])

#     except Exception as e:
#         return error_response(str(e), 400)