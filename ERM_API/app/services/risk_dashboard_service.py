from sqlalchemy.orm import Session
from sqlalchemy import func, case, desc
from datetime import datetime, timedelta
from typing import Optional, Union, Tuple, List, Dict, Any

from app.models.risk_register import RiskRegister
from app.models.risk_description import RiskDescription
from app.models.department import Department
from app.models.user import User
from app.models.mst_status import Status
from app.services.risk_service import get_color


def normalize_date_range(
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None
) -> Tuple[datetime, datetime]:
    """
    Normalizes start_date and end_date into full-day datetime boundaries.
    Default range covers the active Indian Financial Year (April 1 to March 31).
    """
    now = datetime.now()
    if now.month >= 4:
        default_start = datetime(now.year, 4, 1, 0, 0, 0)
        default_end = datetime(now.year + 1, 3, 31, 23, 59, 59, 999999)
    else:
        default_start = datetime(now.year - 1, 4, 1, 0, 0, 0)
        default_end = datetime(now.year, 3, 31, 23, 59, 59, 999999)

    if not start_date:
        parsed_start = default_start
    elif isinstance(start_date, datetime):
        parsed_start = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    elif isinstance(start_date, str):
        try:
            dt = datetime.fromisoformat(start_date.strip())
            parsed_start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        except Exception:
            parsed_start = default_start
    else:
        parsed_start = default_start

    if not end_date:
        parsed_end = default_end
    elif isinstance(end_date, datetime):
        parsed_end = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif isinstance(end_date, str):
        try:
            dt = datetime.fromisoformat(end_date.strip())
            parsed_end = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        except Exception:
            parsed_end = default_end
    else:
        parsed_end = default_end

    return parsed_start, parsed_end


# 1. KPI for Risk Dashboard
def get_dashboard_summary_service(
    db: Session,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None
) -> Dict[str, Any]:
    start_dt, end_dt = normalize_date_range(start_date, end_date)

    status_counts = db.query(
        Status.id,
        Status.status_name,
        func.count(RiskRegister.risk_register_id).label("total")
    ).join(
        Status, RiskRegister.risk_status == Status.id
    ).filter(
        RiskRegister.is_deleted == 0,
        Status.is_deleted == 0,
        RiskRegister.created_on >= start_dt,
        RiskRegister.created_on <= end_dt
    ).group_by(
        Status.id, Status.status_name
    ).all()

    counts = {s.status_name.lower(): s.total for s in status_counts}
    total_val = sum(s.total for s in status_counts)

    open_count = (
        counts.get("draft", 0) + 
        counts.get("submitted to function head", 0) + 
        counts.get("open", 0) + 
        counts.get("new", 0) + 
        counts.get("pending", 0)
    )

    in_progress_count = (
        counts.get("in progress", 0) + 
        counts.get("in_progress", 0) +
        counts.get("function head approved", 0)
    )

    completed_count = (
        counts.get("completed", 0) + 
        counts.get("complete", 0) + 
        counts.get("close", 0)
    )

    approved_count = (
        counts.get("risk manager approved", 0) + 
        counts.get("risk head approved (final)", 0) + 
        counts.get("approved", 0)
    )

    rejected_count = (
        counts.get("rejected / returned", 0) + 
        counts.get("rejected", 0)
    )

    return {
        "start_date": start_dt.strftime("%Y-%m-%d"),
        "end_date": end_dt.strftime("%Y-%m-%d"),
        "total": total_val,
        "open_risks": open_count,
        "in_progress": in_progress_count,
        "completed": completed_count,
        "approved": approved_count,
        "rejected": rejected_count,
        # Backward compatibility aliases
        "New": counts.get("new", 0) or counts.get("draft", 0),
        "Open": open_count,
        "Close": counts.get("close", 0) or counts.get("completed", 0),
        "Pending": counts.get("pending", 0) or counts.get("submitted to function head", 0),
        "Complete": completed_count,
        "Approved": approved_count,
        "Rejected": rejected_count
    }


# 2. Dept wise risk count (Bar Chart)
def department_wise_risk_count(
    db: Session,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None
) -> List[Dict[str, Any]]:
    start_dt, end_dt = normalize_date_range(start_date, end_date)

    results = db.query(
        Department.dept_name.label("department"),
        func.count(RiskRegister.risk_register_id).label("total")
    ).join(
        Department, RiskRegister.dept_id == Department.id
    ).filter(
        RiskRegister.is_deleted == 0,
        Department.is_deleted == 0,
        RiskRegister.created_on >= start_dt,
        RiskRegister.created_on <= end_dt
    ).group_by(
        Department.dept_name
    ).order_by(
        func.count(RiskRegister.risk_register_id).desc()
    ).all()

    return [
        {
            "department": row.department,
            "total": row.total
        }
        for row in results
    ]


# 3. User Wise Risk Count (Bar Chart)
def user_wise_risk_count(
    db: Session,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None
) -> List[Dict[str, Any]]:
    start_dt, end_dt = normalize_date_range(start_date, end_date)

    results = db.query(
        func.concat(User.first_name, " ", User.last_name).label("employee_name"),
        func.count(RiskRegister.risk_register_id).label("total")
    ).join(
        RiskRegister, RiskRegister.risk_owner_id == User.id
    ).filter(
        RiskRegister.is_deleted == 0,
        User.is_deleted == 0,
        RiskRegister.created_on >= start_dt,
        RiskRegister.created_on <= end_dt
    ).group_by(
        User.id
    ).order_by(
        func.count(RiskRegister.risk_register_id).desc()
    ).all()

    return [
        {
            "employee_name": row.employee_name,
            "total": row.total
        }
        for row in results
    ]


# 4. Status wise Risk Count (Donut/Pie Chart)
def status_wise_Risk_Count(
    db: Session,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None
) -> List[Dict[str, Any]]:
    start_dt, end_dt = normalize_date_range(start_date, end_date)

    results = db.query(
        Status.status_name.label("status"),
        func.count(RiskRegister.risk_register_id).label("total")
    ).join(
        Status, RiskRegister.risk_status == Status.id
    ).filter(
        RiskRegister.is_deleted == 0,
        Status.is_deleted == 0,
        RiskRegister.created_on >= start_dt,
        RiskRegister.created_on <= end_dt
    ).group_by(
        Status.status_name
    ).order_by(
        func.count(RiskRegister.risk_register_id).desc()
    ).all()

    return [
        {
            "status": row.status,
            "total": row.total
        }
        for row in results
    ]


# 5. Dept wise Progress (Horizontal Bar Chart)
def department_wise_progress(
    db: Session,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None
) -> List[Dict[str, Any]]:
    start_dt, end_dt = normalize_date_range(start_date, end_date)

    rows = db.query(
        Department.dept_name.label("department"),
        RiskRegister.risk_progress
    ).join(
        Department, RiskRegister.dept_id == Department.id
    ).filter(
        RiskRegister.is_deleted == 0,
        Department.is_deleted == 0,
        RiskRegister.created_on >= start_dt,
        RiskRegister.created_on <= end_dt
    ).all()

    dept_progress_map = {}
    for row in rows:
        dept = row.department
        if dept not in dept_progress_map:
            dept_progress_map[dept] = []
        val_str = str(row.risk_progress or "0").strip().replace("%", "")
        try:
            val_num = float(''.join(c for c in val_str if c.isdigit() or c == '.') or 0.0)
        except Exception:
            val_num = 0.0
        dept_progress_map[dept].append(val_num)

    all_depts = db.query(Department).filter(Department.is_deleted == 0).order_by(Department.dept_name).all()
    result = []
    for d in all_depts:
        progress_list = dept_progress_map.get(d.dept_name, [])
        avg_progress = round(sum(progress_list) / len(progress_list), 2) if progress_list else 0.0
        result.append({
            "department": d.dept_name,
            "progress": avg_progress
        })

    result.sort(key=lambda x: x["progress"], reverse=True)
    return result


# 6. Dept wise stacked Bar Chart for Status
def department_wise_status(
    db: Session,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None
) -> List[Dict[str, Any]]:
    start_dt, end_dt = normalize_date_range(start_date, end_date)

    results = db.query(
        Department.dept_name.label("department"),
        func.count(case((Status.status_name.in_(["New", "Draft"]), 1))).label("New"),
        func.count(case((Status.status_name.in_(["Open", "Submitted to Function Head"]), 1))).label("Open"),
        func.count(case((Status.status_name.in_(["In Progress", "Function Head Approved"]), 1))).label("in_progress"),
        func.count(case((Status.status_name.in_(["Pending", "Under Review"]), 1))).label("Pending"),
        func.count(case((Status.status_name.in_(["Approved", "Risk Manager Approved", "Risk Head Approved (Final)"]), 1))).label("Approved"),
        func.count(case((Status.status_name.in_(["Rejected", "Rejected / Returned"]), 1))).label("Rejected"),
        func.count(case((Status.status_name == "Completed", 1))).label("Complete"),
        func.count(case((Status.status_name == "Close", 1))).label("Close"),
    ).select_from(RiskRegister).join(
        Department, RiskRegister.dept_id == Department.id
    ).join(
        Status, RiskRegister.risk_status == Status.id
    ).filter(
        RiskRegister.is_deleted == 0,
        Department.is_deleted == 0,
        Status.is_deleted == 0,
        RiskRegister.created_on >= start_dt,
        RiskRegister.created_on <= end_dt
    ).group_by(
        Department.dept_name
    ).order_by(
        Department.dept_name
    ).all()

    return [
        {
            "department": row.department,
            "New": row.New or 0,
            "Open": row.Open or 0,
            "In_Progress": row.in_progress or 0,
            "Pending": row.Pending or 0,
            "Approved": row.Approved or 0,
            "Rejected": row.Rejected or 0,
            "Complete": row.Complete or 0,
            "Close": row.Close or 0
        }
        for row in results
    ]


# 7. Top 10 Risk based on Likelihood and Impact with rich metadata
def top_10_risk(
    db: Session,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None
) -> List[Dict[str, Any]]:
    start_dt, end_dt = normalize_date_range(start_date, end_date)

    results = db.query(
        RiskRegister.risk_register_id,
        RiskRegister.risk_id,
        RiskRegister.risk_name,
        RiskRegister.risk_progress,
        Department.dept_name.label("department"),
        func.concat(User.first_name, " ", User.last_name).label("risk_owner"),
        Status.status_name.label("status"),
        RiskDescription.risk_description_id,
        RiskDescription.current_risk_likelihood_id.label("likelihood"),
        RiskDescription.current_risk_impact_id.label("impact"),
        (
            func.coalesce(RiskDescription.current_risk_likelihood_id, 1) *
            func.coalesce(RiskDescription.current_risk_impact_id, 1)
        ).label("risk_score")
    ).join(
        RiskDescription,
        RiskRegister.risk_register_id == RiskDescription.risk_register_id
    ).outerjoin(
        Department,
        RiskRegister.dept_id == Department.id
    ).outerjoin(
        User,
        RiskRegister.risk_owner_id == User.id
    ).outerjoin(
        Status,
        RiskRegister.risk_status == Status.id
    ).filter(
        RiskRegister.is_deleted == 0,
        RiskDescription.is_deleted == 0,
        RiskRegister.created_on >= start_dt,
        RiskRegister.created_on <= end_dt
    ).order_by(
        desc("risk_score")
    ).limit(10).all()

    def get_severity_label(score: int) -> str:
        if score >= 17:
            return "Critical"
        elif score >= 10:
            return "High"
        elif score >= 5:
            return "Medium"
        return "Low"

    return [
        {
            "risk_register_id": row.risk_register_id,
            "risk_id": row.risk_id or f"RSK-{row.risk_register_id:04d}",
            "risk_name": row.risk_name,
            "department": row.department or "General",
            "risk_owner": row.risk_owner.strip() if row.risk_owner else "Unassigned",
            "status": row.status or "Open",
            "progress": str(row.risk_progress or "0").strip() + ("%" if not str(row.risk_progress or "").endswith("%") else ""),
            "risk_description_id": row.risk_description_id,
            "likelihood": row.likelihood or 1,
            "impact": row.impact or 1,
            "risk_score": row.risk_score or 1,
            "severity_level": get_severity_label(row.risk_score or 1),
            "color": get_color(row.risk_score or 1)
        }
        for row in results
    ]


# 8. Based on Risk_Score categorized (Circular chart)
def risk_percentage_chart(
    db: Session,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None
) -> List[Dict[str, Any]]:
    start_dt, end_dt = normalize_date_range(start_date, end_date)

    results = db.query(
        case(
            (
                (func.coalesce(RiskDescription.current_risk_likelihood_id, 1) *
                 func.coalesce(RiskDescription.current_risk_impact_id, 1)) <= 4,
                "Low Risk"
            ),
            (
                (func.coalesce(RiskDescription.current_risk_likelihood_id, 1) *
                 func.coalesce(RiskDescription.current_risk_impact_id, 1)) <= 9,
                "Medium Risk"
            ),
            (
                (func.coalesce(RiskDescription.current_risk_likelihood_id, 1) *
                 func.coalesce(RiskDescription.current_risk_impact_id, 1)) <= 16,
                "High Risk"
            ),
            else_="Critical Risk"
        ).label("category"),
        func.count().label("total")
    ).join(
        RiskRegister,
        RiskRegister.risk_register_id == RiskDescription.risk_register_id
    ).filter(
        RiskRegister.is_deleted == 0,
        RiskDescription.is_deleted == 0,
        RiskRegister.created_on >= start_dt,
        RiskRegister.created_on <= end_dt
    ).group_by("category").all()

    total_risks = sum(row.total for row in results)
    if total_risks == 0:
        return [
            {"category": "Low Risk", "count": 0, "percentage": 0.0},
            {"category": "Medium Risk", "count": 0, "percentage": 0.0},
            {"category": "High Risk", "count": 0, "percentage": 0.0},
            {"category": "Critical Risk", "count": 0, "percentage": 0.0}
        ]

    category_order = ["Critical Risk", "High Risk", "Medium Risk", "Low Risk"]
    found_map = {row.category: row.total for row in results}

    return [
        {
            "category": cat,
            "count": found_map.get(cat, 0),
            "percentage": round((found_map.get(cat, 0) / total_risks) * 100, 2)
        }
        for cat in category_order
        if found_map.get(cat, 0) > 0
    ]


# 9. Total of Risk Rating (5x5 Heatmap)
def risk_heatmap(
    db: Session,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None
) -> List[Dict[str, Any]]:
    start_dt, end_dt = normalize_date_range(start_date, end_date)

    results = db.query(
        RiskDescription.current_risk_likelihood_id.label("likelihood"),
        RiskDescription.current_risk_impact_id.label("impact"),
        func.count().label("total")
    ).join(
        RiskRegister,
        RiskRegister.risk_register_id == RiskDescription.risk_register_id
    ).filter(
        RiskRegister.is_deleted == 0,
        RiskDescription.is_deleted == 0,
        RiskRegister.created_on >= start_dt,
        RiskRegister.created_on <= end_dt
    ).group_by(
        RiskDescription.current_risk_likelihood_id,
        RiskDescription.current_risk_impact_id
    ).all()

    impact_map = {1: "A", 2: "B", 3: "C", 4: "D", 5: "E"}

    return [
        {
            "likelihood": row.likelihood or 1,
            "impact": row.impact or 1,
            "count": row.total,
            "color": get_color((row.likelihood or 1) * (row.impact or 1)),
            "code": f"{row.likelihood or 1}{impact_map.get(row.impact, 'A')}"
        }
        for row in results
    ]


# 10. Risk Transition Heatmap (Inherent vs Current)
def risk_transition_heatmap(
    db: Session,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None,
    dept_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    start_dt, end_dt = normalize_date_range(start_date, end_date)

    query = db.query(
        RiskDescription.inherent_risk_likelihood_id.label("inh_likelihood"),
        RiskDescription.inherent_risk_impact_id.label("inh_impact"),
        RiskDescription.current_risk_likelihood_id.label("cur_likelihood"),
        RiskDescription.current_risk_impact_id.label("cur_impact"),
        func.count().label("total")
    ).join(
        RiskRegister,
        RiskRegister.risk_register_id == RiskDescription.risk_register_id
    ).filter(
        RiskRegister.is_deleted == 0,
        RiskDescription.is_deleted == 0,
        RiskRegister.created_on >= start_dt,
        RiskRegister.created_on <= end_dt
    )

    if dept_id:
        query = query.filter(RiskRegister.dept_id == dept_id)

    results = query.group_by(
        RiskDescription.inherent_risk_likelihood_id,
        RiskDescription.inherent_risk_impact_id,
        RiskDescription.current_risk_likelihood_id,
        RiskDescription.current_risk_impact_id
    ).all()

    impact_map = {1: "A", 2: "B", 3: "C", 4: "D", 5: "E"}

    return [
        {
            "count": row.total,
            "inherent_code": f"{row.inh_likelihood or 1}{impact_map.get(row.inh_impact, 'A')}",
            "current_code": f"{row.cur_likelihood or 1}{impact_map.get(row.cur_impact, 'A')}"
        }
        for row in results
    ]