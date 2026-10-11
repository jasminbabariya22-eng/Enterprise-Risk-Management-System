from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, and_
from datetime import datetime, timezone

from app.models.department import Department
from app.models.risk_register import RiskRegister
from app.models.risk_description import RiskDescription
from app.models.risk_treatment import RiskTreatment
from app.models.mst_status import Status
from app.models.user import User
from app.models.role import UserRole
from app.models.user_type import UserType


def get_score_and_level(likelihood, impact):
    try:
        lh = int(likelihood) if likelihood is not None else 0
        im = int(impact) if impact is not None else 0
        score = lh * im
        if score <= 0:
            return 0, "Not Assessed", "#94A3B8"
        elif score <= 4:
            return score, "Low", "#10B981"
        elif score <= 9:
            return score, "Medium", "#F59E0B"
        elif score <= 16:
            return score, "High", "#F97316"
        else:
            return score, "Critical", "#EF4444"
    except (ValueError, TypeError):
        return 0, "Not Assessed", "#94A3B8"


def determine_approval_stage(risk):
    if risk.risk_function_head_approval_status == -1 or risk.risk_manager_approval_status == -1 or risk.risk_head_approval_status == -1:
        return "Needs Revision / Rejected", "danger"
    
    if risk.risk_function_head_approval_status is None:
        return "Stage 1: Functional Head Review", "warning"
    elif risk.risk_function_head_approval_status == 1 and risk.risk_manager_approval_status is None:
        return "Stage 2: Risk Manager Review", "info"
    elif risk.risk_manager_approval_status == 1 and risk.risk_head_approval_status is None:
        return "Stage 3: Risk Head Final Review", "primary"
    elif risk.risk_head_approval_status == 1:
        return "Approved & Active", "success"
    else:
        return "Under Review", "secondary"


def get_home_workload_and_summary(db: Session, current_user: dict):
    """
    Computes role-scoped summary KPIs and actionable workload items for the authenticated user.
    Enforces strict backend authorization and department/ownership scoping.
    """
    user_id = current_user.get("id")
    dept_id = current_user.get("department_id") or current_user.get("dept_id")
    role_name = (
        current_user.get("role_name") or 
        current_user.get("user_type_name") or 
        current_user.get("user_type") or 
        ""
    ).strip()

    user_roles_raw = [
        current_user.get("role_name"),
        current_user.get("user_type_name"),
        current_user.get("user_type"),
    ]
    roles_set = {str(r).strip().lower() for r in user_roles_raw if r}

    is_admin = bool(roles_set & {"admin", "super admin", "superadmin"})
    is_risk_head = "risk head" in roles_set
    is_risk_manager = "risk manager" in roles_set
    is_functional_head = bool(roles_set & {"functional head", "function head"})
    is_risk_owner = "risk owner" in roles_set
    is_action_owner = "action owner" in roles_set

    now_utc = datetime.now(timezone.utc)

    # -------------------------------------------------------------
    # 1. COMPUTE ROLE-SPECIFIC METRIC SUMMARY PILLS
    # -------------------------------------------------------------
    summary = {}

    if is_admin:
        total_risks = db.query(func.count(RiskRegister.risk_register_id)).filter(
            RiskRegister.is_deleted == 0
        ).scalar() or 0

        pending_approvals = db.query(func.count(RiskRegister.risk_register_id)).filter(
            RiskRegister.is_deleted == 0,
            or_(
                RiskRegister.risk_function_head_approval_status.is_(None),
                and_(RiskRegister.risk_function_head_approval_status == 1, RiskRegister.risk_manager_approval_status.is_(None)),
                and_(RiskRegister.risk_manager_approval_status == 1, RiskRegister.risk_head_approval_status.is_(None))
            )
        ).scalar() or 0

        total_users = db.query(func.count(User.id)).filter(
            User.is_deleted == 0
        ).scalar() or 0

        total_depts = db.query(func.count(Department.id)).filter(
            Department.is_deleted == 0
        ).scalar() or 0

        summary = {
            "card_1": {"label": "Total Risks Registered", "value": total_risks, "icon": "bi-shield-check", "color": "primary"},
            "card_2": {"label": "Pending Governance Reviews", "value": pending_approvals, "icon": "bi-hourglass-split", "color": "warning"},
            "card_3": {"label": "Active ERM Users", "value": total_users, "icon": "bi-people", "color": "info"},
            "card_4": {"label": "Functional Departments", "value": total_depts, "icon": "bi-building", "color": "teal"}
        }

    elif is_risk_head:
        # Stage 3 approvals waiting for Risk Head
        pending_approvals = db.query(func.count(RiskRegister.risk_register_id)).filter(
            RiskRegister.is_deleted == 0,
            RiskRegister.risk_manager_approval_status == 1,
            RiskRegister.risk_head_approval_status.is_(None)
        ).scalar() or 0

        # Fully approved risks
        approved_risks = db.query(func.count(RiskRegister.risk_register_id)).filter(
            RiskRegister.is_deleted == 0,
            RiskRegister.risk_head_approval_status == 1
        ).scalar() or 0

        # Total active risks
        total_risks = db.query(func.count(RiskRegister.risk_register_id)).filter(
            RiskRegister.is_deleted == 0
        ).scalar() or 0

        # High / Critical severity count
        high_critical = db.query(func.count(RiskDescription.risk_description_id)).join(
            RiskRegister, RiskDescription.risk_register_id == RiskRegister.risk_register_id
        ).filter(
            RiskRegister.is_deleted == 0,
            RiskDescription.is_deleted == 0,
            or_(
                (RiskDescription.current_risk_likelihood_id * RiskDescription.current_risk_impact_id) >= 15,
                (RiskDescription.inherent_risk_likelihood_id * RiskDescription.inherent_risk_impact_id) >= 15
            )
        ).scalar() or 0

        summary = {
            "card_1": {"label": "Stage 3 Pending Sign-Off", "value": pending_approvals, "icon": "bi-shield-exclamation", "color": "warning"},
            "card_2": {"label": "High & Critical Risks", "value": high_critical, "icon": "bi-exclamation-octagon", "color": "danger"},
            "card_3": {"label": "Fully Approved Risks", "value": approved_risks, "icon": "bi-check2-circle", "color": "success"},
            "card_4": {"label": "Enterprise Risk Register", "value": total_risks, "icon": "bi-collection", "color": "primary"}
        }

    elif is_risk_manager:
        # Stage 2 approvals waiting for Risk Manager
        pending_approvals = db.query(func.count(RiskRegister.risk_register_id)).filter(
            RiskRegister.is_deleted == 0,
            RiskRegister.risk_function_head_approval_status == 1,
            RiskRegister.risk_manager_approval_status.is_(None)
        ).scalar() or 0

        # Total active action plans
        active_treatments = db.query(func.count(RiskTreatment.risk_treatment_id)).filter(
            RiskTreatment.is_deleted == 0
        ).scalar() or 0

        # Total registered risks
        total_risks = db.query(func.count(RiskRegister.risk_register_id)).filter(
            RiskRegister.is_deleted == 0
        ).scalar() or 0

        # Pending action follow-ups
        in_progress_treatments = db.query(func.count(RiskTreatment.risk_treatment_id)).filter(
            RiskTreatment.is_deleted == 0,
            or_(
                RiskTreatment.progress.ilike("%progress%"),
                RiskTreatment.progress.ilike("%open%")
            )
        ).scalar() or 0

        summary = {
            "card_1": {"label": "Stage 2 Pending Review", "value": pending_approvals, "icon": "bi-clipboard-check", "color": "warning"},
            "card_2": {"label": "Active Action Plans", "value": active_treatments, "icon": "bi-tools", "color": "info"},
            "card_3": {"label": "Mitigations In-Progress", "value": in_progress_treatments, "icon": "bi-arrow-repeat", "color": "teal"},
            "card_4": {"label": "Total Enterprise Risks", "value": total_risks, "icon": "bi-shield-shaded", "color": "primary"}
        }

    elif is_functional_head:
        # Stage 1 approvals waiting for Functional Head in user's dept
        dept_pending = db.query(func.count(RiskRegister.risk_register_id)).filter(
            RiskRegister.is_deleted == 0,
            RiskRegister.dept_id == dept_id,
            RiskRegister.risk_function_head_approval_status.is_(None)
        ).scalar() or 0 if dept_id else 0

        dept_total = db.query(func.count(RiskRegister.risk_register_id)).filter(
            RiskRegister.is_deleted == 0,
            RiskRegister.dept_id == dept_id
        ).scalar() or 0 if dept_id else 0

        dept_approved = db.query(func.count(RiskRegister.risk_register_id)).filter(
            RiskRegister.is_deleted == 0,
            RiskRegister.dept_id == dept_id,
            RiskRegister.risk_function_head_approval_status == 1
        ).scalar() or 0 if dept_id else 0

        dept_treatments = db.query(func.count(RiskTreatment.risk_treatment_id)).join(
            RiskRegister, RiskTreatment.risk_register_id == RiskRegister.risk_register_id
        ).filter(
            RiskRegister.is_deleted == 0,
            RiskRegister.dept_id == dept_id,
            RiskTreatment.is_deleted == 0
        ).scalar() or 0 if dept_id else 0

        summary = {
            "card_1": {"label": "Dept Stage 1 Approvals", "value": dept_pending, "icon": "bi-hourglass-top", "color": "warning"},
            "card_2": {"label": "Department Risks", "value": dept_total, "icon": "bi-folder2-open", "color": "primary"},
            "card_3": {"label": "Function Approved", "value": dept_approved, "icon": "bi-patch-check", "color": "success"},
            "card_4": {"label": "Dept Treatment Plans", "value": dept_treatments, "icon": "bi-gear-wide-connected", "color": "teal"}
        }

    elif is_risk_owner:
        # My Owned Risks
        my_total = db.query(func.count(RiskRegister.risk_register_id)).filter(
            RiskRegister.is_deleted == 0,
            or_(
                RiskRegister.risk_owner_id == user_id,
                RiskRegister.risk_co_owner_id == user_id
            )
        ).scalar() or 0

        # My risks pending approval
        my_pending = db.query(func.count(RiskRegister.risk_register_id)).filter(
            RiskRegister.is_deleted == 0,
            or_(
                RiskRegister.risk_owner_id == user_id,
                RiskRegister.risk_co_owner_id == user_id
            ),
            or_(
                RiskRegister.risk_function_head_approval_status.is_(None),
                RiskRegister.risk_manager_approval_status.is_(None),
                RiskRegister.risk_head_approval_status.is_(None)
            ),
            RiskRegister.risk_function_head_approval_status != -1,
            RiskRegister.risk_manager_approval_status != -1,
            RiskRegister.risk_head_approval_status != -1
        ).scalar() or 0

        # My risks rejected/returned for revision
        my_rejected = db.query(func.count(RiskRegister.risk_register_id)).filter(
            RiskRegister.is_deleted == 0,
            or_(
                RiskRegister.risk_owner_id == user_id,
                RiskRegister.risk_co_owner_id == user_id
            ),
            or_(
                RiskRegister.risk_function_head_approval_status == -1,
                RiskRegister.risk_manager_approval_status == -1,
                RiskRegister.risk_head_approval_status == -1
            )
        ).scalar() or 0

        # My fully approved risks
        my_approved = db.query(func.count(RiskRegister.risk_register_id)).filter(
            RiskRegister.is_deleted == 0,
            or_(
                RiskRegister.risk_owner_id == user_id,
                RiskRegister.risk_co_owner_id == user_id
            ),
            RiskRegister.risk_head_approval_status == 1
        ).scalar() or 0

        summary = {
            "card_1": {"label": "My Owned Risks", "value": my_total, "icon": "bi-shield-lock", "color": "primary"},
            "card_2": {"label": "Awaiting Approval", "value": my_pending, "icon": "bi-clock-history", "color": "warning"},
            "card_3": {"label": "Needs Revision / Action", "value": my_rejected, "icon": "bi-exclamation-triangle", "color": "danger"},
            "card_4": {"label": "Approved Risks", "value": my_approved, "icon": "bi-check-all", "color": "success"}
        }

    elif is_action_owner:
        # Assigned Action Plans
        assigned_actions = db.query(func.count(RiskTreatment.risk_treatment_id)).filter(
            RiskTreatment.is_deleted == 0,
            RiskTreatment.action_owner_id == user_id
        ).scalar() or 0

        in_progress = db.query(func.count(RiskTreatment.risk_treatment_id)).filter(
            RiskTreatment.is_deleted == 0,
            RiskTreatment.action_owner_id == user_id,
            or_(
                RiskTreatment.progress.ilike("%progress%"),
                RiskTreatment.progress.ilike("%open%")
            )
        ).scalar() or 0

        completed = db.query(func.count(RiskTreatment.risk_treatment_id)).filter(
            RiskTreatment.is_deleted == 0,
            RiskTreatment.action_owner_id == user_id,
            RiskTreatment.progress.ilike("%complete%")
        ).scalar() or 0

        summary = {
            "card_1": {"label": "Assigned Mitigation Tasks", "value": assigned_actions, "icon": "bi-list-check", "color": "primary"},
            "card_2": {"label": "In Progress Actions", "value": in_progress, "icon": "bi-play-circle", "color": "info"},
            "card_3": {"label": "Completed Mitigations", "value": completed, "icon": "bi-check2-all", "color": "success"},
            "card_4": {"label": "Pending Target Review", "value": max(0, assigned_actions - completed), "icon": "bi-calendar-event", "color": "warning"}
        }

    else:
        # Generic Viewer or Other Role
        total_risks = db.query(func.count(RiskRegister.risk_register_id)).filter(
            RiskRegister.is_deleted == 0
        ).scalar() or 0

        summary = {
            "card_1": {"label": "Risk Register Items", "value": total_risks, "icon": "bi-file-earmark-text", "color": "primary"},
            "card_2": {"label": "System Status", "value": "Active", "icon": "bi-activity", "color": "success"},
            "card_3": {"label": "Access Level", "value": role_name or "Viewer", "icon": "bi-person-badge", "color": "info"},
            "card_4": {"label": "Financial Year", "value": "2026-2027", "icon": "bi-calendar3", "color": "teal"}
        }

    # -------------------------------------------------------------
    # 2. RETRIEVE ACTIONABLE WORKLOAD ITEMS (SCOPED & SECURE)
    # -------------------------------------------------------------
    workload = []
    seen_keys = set()

    def _add_item(item):
        if item and item.get("key") and item["key"] not in seen_keys:
            seen_keys.add(item["key"])
            workload.append(item)

    def _format_risk(r, action_label_override=None, category_override=None, urgency_override=None, stage_override=None, owner_override=None):
        desc = r.risk_descriptions[0] if r.risk_descriptions else None
        inh_score, inh_level, inh_color = (
            get_score_and_level(desc.inherent_risk_likelihood_id, desc.inherent_risk_impact_id)
            if desc else (0, "N/A", "#94A3B8")
        )
        curr_score, curr_level, curr_color = (
            get_score_and_level(desc.current_risk_likelihood_id, desc.current_risk_impact_id)
            if desc else (0, "N/A", "#94A3B8")
        )
        stage_text, stage_badge = determine_approval_stage(r)
        is_rejected = stage_badge == "danger"
        category = category_override or ("returned" if is_rejected else ("approval" if "Stage" in stage_text else "review"))
        urgency = urgency_override or ("high" if is_rejected else ("medium" if "Stage" in stage_text else "normal"))
        action_lbl = action_label_override or ("Update & Resubmit" if is_rejected else ("Review Risk" if "Stage" in stage_text else "View Details"))
        stage_display = stage_override or stage_text
        owner_display = owner_override or (r.risk_owner.log_id if r.risk_owner else "Unassigned")

        return {
            "key": f"rsk_{r.risk_register_id}_{stage_badge}",
            "type": "risk",
            "category": category,
            "urgency": urgency,
            "id": r.risk_register_id,
            "risk_id": r.risk_id,
            "risk_name": r.risk_name,
            "dept_name": r.department.dept_name if r.department else "General",
            "dept_id": r.dept_id,
            "owner_name": owner_display,
            "inherent_score": inh_score,
            "inherent_level": inh_level,
            "inherent_color": inh_color,
            "current_score": curr_score,
            "current_level": curr_level,
            "current_color": curr_color,
            "stage": stage_display,
            "stage_badge": stage_badge,
            "created_on": r.created_on.strftime("%d %b %Y") if r.created_on else "-",
            "action_url": f"/riskDetails?id={r.risk_register_id}",
            "action_label": action_lbl
        }

    def _format_treatment(t, user_dept=0):
        return {
            "key": f"trt_{t.risk_treatment_id}",
            "type": "treatment",
            "category": "treatment",
            "urgency": "medium",
            "id": t.risk_treatment_id,
            "treatment_id": t.risk_treatment_id,
            "description_id": t.risk_description_id,
            "risk_register_id": t.risk_register_id,
            "risk_id": t.risk_id or f"TRT-{t.risk_treatment_id}",
            "risk_name": t.action_plan or "Action Plan",
            "dept_name": "My Action Task",
            "dept_id": user_dept or 0,
            "owner_name": "Me (Action Owner)",
            "inherent_score": 0,
            "inherent_level": t.progress or "Assigned",
            "inherent_color": "#2563EB",
            "current_score": 0,
            "current_level": t.progress or "In Progress",
            "current_color": "#14B8A6",
            "stage": f"Progress: {t.progress or 'Pending Action'}",
            "stage_badge": "info",
            "created_on": t.target_date.strftime("%d %b %Y") if t.target_date else "No Target Date",
            "action_url": f"/riskActionPlan?treatment_id={t.risk_treatment_id}&desc_id={t.risk_description_id}&risk_id={t.risk_register_id}",
            "action_label": "Update Progress"
        }

    if is_admin:
        # Admin sees pending governance approval items
        query = db.query(RiskRegister).options(
            joinedload(RiskRegister.department),
            joinedload(RiskRegister.risk_owner),
            joinedload(RiskRegister.risk_descriptions)
        ).filter(
            RiskRegister.is_deleted == 0,
            or_(
                RiskRegister.risk_function_head_approval_status.is_(None),
                RiskRegister.risk_manager_approval_status.is_(None),
                RiskRegister.risk_head_approval_status.is_(None),
                RiskRegister.risk_function_head_approval_status == -1,
                RiskRegister.risk_manager_approval_status == -1,
                RiskRegister.risk_head_approval_status == -1
            )
        ).order_by(RiskRegister.risk_register_id.desc()).limit(15)

        for r in query.all():
            _add_item(_format_risk(r, action_label_override="Review Risk"))

    elif is_risk_head:
        # Risk Head Stage 3 Approvals waiting for signoff
        query = db.query(RiskRegister).options(
            joinedload(RiskRegister.department),
            joinedload(RiskRegister.risk_owner),
            joinedload(RiskRegister.risk_descriptions)
        ).filter(
            RiskRegister.is_deleted == 0,
            RiskRegister.risk_manager_approval_status == 1,
            RiskRegister.risk_head_approval_status.is_(None)
        ).order_by(RiskRegister.risk_register_id.desc()).limit(15)

        for r in query.all():
            _add_item(_format_risk(
                r,
                action_label_override="Final Sign-Off",
                stage_override="Stage 3: Ready for Risk Head Approval",
                urgency_override="high"
            ))

    elif is_risk_manager:
        # Risk Manager Stage 2 Approvals
        query = db.query(RiskRegister).options(
            joinedload(RiskRegister.department),
            joinedload(RiskRegister.risk_owner),
            joinedload(RiskRegister.risk_descriptions)
        ).filter(
            RiskRegister.is_deleted == 0,
            RiskRegister.risk_function_head_approval_status == 1,
            RiskRegister.risk_manager_approval_status.is_(None)
        ).order_by(RiskRegister.risk_register_id.desc()).limit(15)

        for r in query.all():
            _add_item(_format_risk(
                r,
                action_label_override="Review & Verify",
                stage_override="Stage 2: Ready for Risk Manager Review",
                urgency_override="high"
            ))

    elif is_functional_head:
        # Functional Head Stage 1 Approvals (Strictly dept scoped)
        if dept_id:
            query = db.query(RiskRegister).options(
                joinedload(RiskRegister.department),
                joinedload(RiskRegister.risk_owner),
                joinedload(RiskRegister.risk_descriptions)
            ).filter(
                RiskRegister.is_deleted == 0,
                RiskRegister.dept_id == dept_id,
                RiskRegister.risk_function_head_approval_status.is_(None)
            ).order_by(RiskRegister.risk_register_id.desc()).limit(15)

            for r in query.all():
                _add_item(_format_risk(
                    r,
                    action_label_override="Approve / Return",
                    stage_override="Stage 1: Awaiting Function Head Sign-Off",
                    urgency_override="high"
                ))

    elif is_risk_owner:
        # Risk Owner sees their assigned risks (especially those needing action/pending approval)
        query = db.query(RiskRegister).options(
            joinedload(RiskRegister.department),
            joinedload(RiskRegister.risk_owner),
            joinedload(RiskRegister.risk_descriptions)
        ).filter(
            RiskRegister.is_deleted == 0,
            or_(
                RiskRegister.risk_owner_id == user_id,
                RiskRegister.risk_co_owner_id == user_id
            )
        ).order_by(RiskRegister.risk_register_id.desc()).limit(15)

        for r in query.all():
            _add_item(_format_risk(r, owner_override="Me (Owner)"))

    elif is_action_owner:
        # Action Owner sees their assigned action plans
        query = db.query(RiskTreatment).options(
            joinedload(RiskTreatment.risk_description)
        ).filter(
            RiskTreatment.is_deleted == 0,
            RiskTreatment.action_owner_id == user_id
        ).order_by(RiskTreatment.risk_treatment_id.desc()).limit(15)

        for t in query.all():
            _add_item(_format_treatment(t, user_dept=dept_id))

    else:
        # Viewer / Other: View general authorized register items
        query = db.query(RiskRegister).options(
            joinedload(RiskRegister.department),
            joinedload(RiskRegister.risk_owner),
            joinedload(RiskRegister.risk_descriptions)
        ).filter(
            RiskRegister.is_deleted == 0
        ).order_by(RiskRegister.risk_register_id.desc()).limit(10)

        for r in query.all():
            _add_item(_format_risk(
                r,
                action_label_override="View Risk",
                category_override="review",
                urgency_override="normal"
            ))

    # Supplemental: If the user owns rejected/revision risks, ensure they appear in returned queue
    if user_id and (is_functional_head or is_risk_manager or is_risk_head):
        rejected_owned = db.query(RiskRegister).options(
            joinedload(RiskRegister.department),
            joinedload(RiskRegister.risk_owner),
            joinedload(RiskRegister.risk_descriptions)
        ).filter(
            RiskRegister.is_deleted == 0,
            or_(
                RiskRegister.risk_owner_id == user_id,
                RiskRegister.risk_co_owner_id == user_id
            ),
            or_(
                RiskRegister.risk_function_head_approval_status == -1,
                RiskRegister.risk_manager_approval_status == -1,
                RiskRegister.risk_head_approval_status == -1
            )
        ).order_by(RiskRegister.risk_register_id.desc()).limit(5)

        for r in rejected_owned.all():
            _add_item(_format_risk(
                r,
                action_label_override="Update & Resubmit",
                category_override="returned",
                urgency_override="high",
                owner_override="Me (Owner)"
            ))

    # Supplemental: If user has assigned treatment action plans regardless of governance role
    if user_id and not is_action_owner:
        user_treatments = db.query(RiskTreatment).options(
            joinedload(RiskTreatment.risk_description)
        ).filter(
            RiskTreatment.is_deleted == 0,
            RiskTreatment.action_owner_id == user_id
        ).order_by(RiskTreatment.risk_treatment_id.desc()).limit(10)

        for t in user_treatments.all():
            _add_item(_format_treatment(t, user_dept=dept_id))

    return {
        "role": role_name,
        "role_category": (
            "admin" if is_admin else
            "risk_head" if is_risk_head else
            "risk_manager" if is_risk_manager else
            "functional_head" if is_functional_head else
            "risk_owner" if is_risk_owner else
            "action_owner" if is_action_owner else
            "viewer"
        ),
        "department_id": dept_id,
        "user_id": user_id,
        "summary": summary,
        "workload": workload,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

