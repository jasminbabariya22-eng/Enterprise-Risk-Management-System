from datetime import datetime, timezone

from app.models.risk_register import RiskRegister
from app.models.mst_status import Status
from app.models.risk_register_hist import RiskRegisterHist
from app.services.risk_service import reset_risk_approvals

from app.services.email_event_service import *

def approve_risk(db, data, user_id):

    # ---------------- GET RISK ----------------

    risk = db.query(RiskRegister).filter(
        RiskRegister.risk_register_id == data.risk_register_id,
        RiskRegister.is_deleted == 0
    ).first()

    if not risk:
        raise Exception("Risk not found")

    # ---------------- APPROVAL STATUS MAP ----------------

    approval_map = {
        7: {
            "name": "Approved",
            "db_value": 1
        },
        8: {
            "name": "Rejected",
            "db_value": -1
        }
    }

    if data.approval_status_id not in approval_map:
        raise Exception(
            "Invalid approval status. "
            "Use 7 for Approved and 8 for Rejected"
        )

    approval_status_name = approval_map[
        data.approval_status_id
    ]["name"]

    status_req_id = approval_map[
        data.approval_status_id
    ]["db_value"]

    current_time = datetime.now(timezone.utc)

    # ---------------- APPROVAL LEVEL ----------------

    if data.approval_level == 1:

        risk.risk_function_head_approval_status = status_req_id
        risk.risk_function_head_approval_remark = data.remark
        risk.risk_function_head_approval_by = user_id
        risk.risk_function_head_approval_on = current_time

    elif data.approval_level == 2:

        risk.risk_manager_approval_status = status_req_id
        risk.risk_manager_approval_remark = data.remark
        risk.risk_manager_approval_by = user_id
        risk.risk_manager_approved_on = current_time

    elif data.approval_level == 3:

        risk.risk_head_approval_status = status_req_id
        risk.risk_head_approval_remark = data.remark
        risk.risk_head_approval_by = user_id
        risk.risk_head_approved_on = current_time

    else:
        raise Exception("Invalid approval level")

    # ---------------- STATUS QUERY ----------------

    statuses = db.query(Status).filter(
        Status.status_name.in_([
            "Pending for Action"
            # "New"
        ]),
        Status.is_deleted == 0
    ).all()

    status_map = {
        s.status_name: s.id for s in statuses
    }

    pending_id = status_map.get("Pending for Action")
    new_id = status_map.get("New")

    # ---------------- FINAL RISK STATUS ----------------

    approvals = [
        risk.risk_function_head_approval_status,
        risk.risk_head_approval_status,
        risk.risk_manager_approval_status
    ]

    # keep current status by default
    risk_status_name = None

    if -1 in approvals:
        risk.risk_status = pending_id
        risk_status_name = "Pending for Action"
    else:

        current_status = db.query(Status).filter(
            Status.id == risk.risk_status
        ).first()

        risk_status_name = (
            current_status.status_name
            if current_status else None
        )
        

    # ---------------- HISTORY INSERT ----------------

    hist = RiskRegisterHist(

        risk_register_id=risk.risk_register_id,

        risk_id=risk.risk_id,
        risk_name=risk.risk_name,

        dept_id=risk.dept_id,
        risk_owner_id=risk.risk_owner_id,
        risk_co_owner_id=risk.risk_co_owner_id,

        # target_date=risk.target_date,
        financial_year=risk.financial_year,

        risk_status=risk.risk_status,
        risk_progress=risk.risk_progress,

        # ---------------- FUNCTION HEAD ----------------

        risk_function_head_approval_status=
            risk.risk_function_head_approval_status,

        risk_function_head_approval_remark=
            risk.risk_function_head_approval_remark,

        risk_function_head_approval_on=
            risk.risk_function_head_approval_on,

        risk_function_head_approval_by=
            risk.risk_function_head_approval_by,

        # ---------------- RISK HEAD ----------------

        risk_head_approval_status=
            risk.risk_head_approval_status,

        risk_head_approved_on=
            risk.risk_head_approved_on,

        risk_head_approval_remark=
            risk.risk_head_approval_remark,

        risk_head_approval_by=
            risk.risk_head_approval_by,

        # ---------------- RISK MANAGER ----------------

        risk_manager_approval_status=
            risk.risk_manager_approval_status,

        risk_manager_approved_on=
            risk.risk_manager_approved_on,

        risk_manager_approval_remark=
            risk.risk_manager_approval_remark,

        risk_manager_approval_by=
            risk.risk_manager_approval_by,

        # ---------------- AUDIT ----------------

        created_by=risk.created_by,
        created_on=risk.created_on,

        modified_by=user_id,
        modified_on=current_time,

        is_active=risk.is_active,
        is_deleted=risk.is_deleted
    )

    db.add(hist)
    
    
    #reset approval
    # APPROVED
    if status_req_id == 1:
        send_function_approval_email_seq(db,risk.risk_register_id, data.approval_level)
    elif status_req_id == -1:
    
        role_map = {
            1: "Functional Head",
            2: "Risk Manager",
            3: "Risk Head"
        }

        send_risk_rejection_email(
            db=db,
            risk_register_id=risk.risk_register_id,
            rejected_by_role=role_map[data.approval_level],
            remark=data.remark
        )

    if (
        risk.risk_function_head_approval_status == 1 and
        risk.risk_manager_approval_status == 1 and
        risk.risk_head_approval_status == 1
    ):
        send_treatment_email_after_approval(
            db,
            risk.risk_register_id
        )
    # ---------------- SINGLE COMMIT ----------------

    db.commit()

    db.refresh(risk)

    return (
        risk,

        data.approval_status_id,
        approval_status_name,

        risk.risk_status,
        risk_status_name
    )



#----------------Force Approval--------------------------

def force_approve_risk(db, data, user_id, user_type):
    risk = db.query(RiskRegister).filter(
        RiskRegister.risk_register_id == data.risk_register_id,
        RiskRegister.is_deleted == 0
    ).first()

    if not risk:
        raise Exception("Risk not found")
    
    current_time = datetime.now(timezone.utc)
    
    role_levels = {
        "Functional Head": [1],
        "Risk Manager": [1, 2],
        "Risk Head": [1, 2, 3]
    }

    approval_levels = role_levels.get(user_type)

    if not approval_levels:
        raise Exception(
            "You are not authorized to perform force approval."
        )
    
    approved_levels = []

    for level in approval_levels:
        
        # FH
        if level == 1:
            if risk.risk_function_head_approval_status == 1:
                continue

            risk.risk_function_head_approval_status = 1
            risk.risk_function_head_approval_remark = data.remark
            risk.risk_function_head_approval_by = user_id
            risk.risk_function_head_approval_on = current_time

            approved_levels.append(1)
            
        # RM
        elif level == 2:

            if risk.risk_manager_approval_status == 1:
                continue

            risk.risk_manager_approval_status = 1
            risk.risk_manager_approval_remark = data.remark
            risk.risk_manager_approval_by = user_id
            risk.risk_manager_approved_on = current_time

            approved_levels.append(2)
            
        # RH
        elif level == 3:

            if risk.risk_head_approval_status == 1:
                continue

            risk.risk_head_approval_status = 1
            risk.risk_head_approval_remark = data.remark
            risk.risk_head_approval_by = user_id
            risk.risk_head_approved_on = current_time

            approved_levels.append(3)
            
    if not approved_levels:
        raise Exception("Risk is already fully approved.")
            
        # ---------------- STATUS QUERY ----------------

    statuses = db.query(Status).filter(
        Status.status_name.in_([
            "Pending for Action"
        ]),
        Status.is_deleted == 0
    ).all()

    status_map = {
        s.status_name: s.id
        for s in statuses
    }

    pending_id = status_map.get("Pending for Action")
    
    approvals = [
        risk.risk_function_head_approval_status,
        risk.risk_manager_approval_status,
        risk.risk_head_approval_status
    ]

    risk_status_name = None

    if -1 in approvals:

        risk.risk_status = pending_id
        risk_status_name = "Pending for Action"

    else:

        current_status = db.query(Status).filter(
            Status.id == risk.risk_status
        ).first()

        risk_status_name = (
            current_status.status_name
            if current_status
            else None
        )
    
        # ---------------- HISTORY INSERT ----------------

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

        # ---------------- FUNCTION HEAD ----------------

        risk_function_head_approval_status=
            risk.risk_function_head_approval_status,

        risk_function_head_approval_remark=
            risk.risk_function_head_approval_remark,

        risk_function_head_approval_on=
            risk.risk_function_head_approval_on,

        risk_function_head_approval_by=
            risk.risk_function_head_approval_by,

        # ---------------- RISK HEAD ----------------

        risk_head_approval_status=
            risk.risk_head_approval_status,

        risk_head_approved_on=
            risk.risk_head_approved_on,

        risk_head_approval_remark=
            risk.risk_head_approval_remark,

        risk_head_approval_by=
            risk.risk_head_approval_by,

        # ---------------- RISK MANAGER ----------------

        risk_manager_approval_status=
            risk.risk_manager_approval_status,

        risk_manager_approved_on=
            risk.risk_manager_approved_on,

        risk_manager_approval_remark=
            risk.risk_manager_approval_remark,

        risk_manager_approval_by=
            risk.risk_manager_approval_by,

        # ---------------- AUDIT ----------------

        created_by=risk.created_by,
        created_on=risk.created_on,

        modified_by=user_id,
        modified_on=current_time,

        is_active=risk.is_active,
        is_deleted=risk.is_deleted

    )

    db.add(hist)
    
        # ---------------- EMAILS ----------------

    for level in approved_levels:

        send_function_approval_email_seq(
            db,
            risk.risk_register_id,
            level
        )

    if (
        risk.risk_function_head_approval_status == 1
        and
        risk.risk_manager_approval_status == 1
        and
        risk.risk_head_approval_status == 1
    ):
        send_treatment_email_after_approval(
            db,
            risk.risk_register_id
        )
        
    db.commit()

    db.refresh(risk)

    return (
        risk,
        approved_levels,
        risk.risk_status,
        risk_status_name
    )