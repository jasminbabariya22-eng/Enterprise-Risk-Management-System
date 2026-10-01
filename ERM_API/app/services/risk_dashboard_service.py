from sqlalchemy.orm import Session
from sqlalchemy import func, case
from app.models.mst_status import Status
from datetime import datetime, timedelta

from app.models.risk_register import RiskRegister
from app.models.risk_description import RiskDescription
from app.models.department import Department
from app.models.user import User
from app.models.mst_status import Status
from app.services.risk_service import get_color

# KPI for Risk Dashboard - Total Risks, New, Open, Closed, In Progress, Pending, Completed, Approved, Rejected
def get_dashboard_summary_service(db: Session, start_date: datetime, end_date: datetime):
    result = db.query(
        func.count(RiskRegister.risk_register_id).label("total"),
        
        func.count().filter(Status.status_name == "New").label("New"),
        func.count().filter(Status.status_name == "Open").label("Open"),  
        func.count().filter(Status.status_name == "In Progress").label("in_progress"),
        func.count().filter(Status.status_name == "Close").label("Close"),
        func.count().filter(Status.status_name == "Pending").label("Pending"),
        func.count().filter(Status.status_name == "Complete").label("Complete"),  
        func.count().filter(Status.status_name == "Approved").label("Approved"),  
        func.count().filter(Status.status_name == "Rejected").label("Rejected")  
    ).join(
        Status, RiskRegister.risk_status == Status.id
    ).filter(
        RiskRegister.is_deleted == 0,
        Status.is_deleted == 0,
        RiskRegister.created_on >= start_date,
        RiskRegister.created_on <= end_date
    ).first()

    return {
        "start_date": start_date,
        "end_date": end_date,
        "total": result.total or 0,
        "New": result.New or 0,
        "Open": result.Open or 0,  
        "Close": result.Close or 0,
        "in_progress": result.in_progress or 0,
        "Pending": result.Pending or 0,
        "Complete": result.Complete or 0,  
        "Approved": result.Approved or 0,  
        "Rejected": result.Rejected or 0  
    }
    
    
# Dept wise risk count (Bar Chart)
def department_wise_risk_count(db: Session, start_date: datetime, end_date: datetime):

    results = db.query(
        Department.dept_name.label("department"),
        func.count(RiskRegister.risk_register_id).label("total")
    ).join(
        Department, RiskRegister.dept_id == Department.id
    ).filter(
        RiskRegister.is_deleted == 0,
        Department.is_deleted == 0,
        RiskRegister.created_on >= start_date,
        RiskRegister.created_on < end_date + timedelta(days=1)
    ).group_by(
        Department.dept_name
    ).order_by(
        Department.dept_name
    ).all()

    return [
        {
            "department": row.department,
            "total": row.total
        }
        for row in results
    ]
    
    
    
# User Wise Risk Count (Bar Chart)
def user_wise_risk_count(db: Session, start_date: datetime, end_date: datetime):

    results = db.query(
        func.concat(User.first_name, " ", User.last_name).label("employee_name"),
        func.count(RiskRegister.risk_register_id).label("total")
    ).join(
        RiskRegister, RiskRegister.risk_owner_id == User.id
    ).filter(
        RiskRegister.is_deleted == 0,
        User.is_deleted == 0,
        RiskRegister.created_on >= start_date,
        RiskRegister.created_on < end_date + timedelta(days=1)
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
    


# Status wise Risk Count (Pie Chart)
def status_wise_Risk_Count(db: Session, start_date: datetime, end_date: datetime):

    results = db.query(
        Status.status_name.label("status"),
        func.count(RiskRegister.risk_register_id).label("total")
    ).join(
        Status, RiskRegister.risk_status == Status.id
    ).filter(
        RiskRegister.is_deleted == 0,
        Status.is_deleted == 0,
        RiskRegister.created_on >= start_date,
        RiskRegister.created_on < end_date + timedelta(days=1)
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
    

# Dept wise Progress (Horizontal Bar Chart)
def department_wise_progress(db: Session, start_date, end_date):

    results = db.query(
        Department.dept_name.label("department"),
        func.avg(RiskRegister.risk_progress).label("progress")
    ).join(
        Department, RiskRegister.dept_id == Department.id
    ).filter(
        RiskRegister.is_deleted == 0,
        Department.is_deleted == 0,
        RiskRegister.created_on >= start_date,
        RiskRegister.created_on < end_date + timedelta(days=1)
    ).group_by(
        Department.dept_name
    ).order_by(
        func.avg(RiskRegister.risk_progress).desc()
    ).all()

    return [
        {
            "department": row.department,
            "progress": round(row.progress or 0, 2)
        }
        for row in results
    ]
    
    
# Dept wise stacked Bar Chart for Status

def department_wise_status(db: Session, start_date, end_date):

    results = db.query(
        Department.dept_name.label("department"),

        func.count(case((Status.status_name == "New", 1))).label("New"),

        func.count(case((Status.status_name == "In Progress", 1))).label("in_progress"),

        func.count(case((Status.status_name == "Pending", 1))).label("Pending"),

        func.count(case((Status.status_name == "Approved", 1))).label("Approved"),

        func.count(case((Status.status_name == "Rejected", 1))).label("Rejected"),

    ).select_from(RiskRegister).join(Department, RiskRegister.dept_id == Department.id
                                     
    ).join(Status, RiskRegister.risk_status == Status.id
           
    ).filter(
        RiskRegister.is_deleted == 0,
        Department.is_deleted == 0,
        Status.is_deleted == 0,
        RiskRegister.created_on >= start_date,
        RiskRegister.created_on <= end_date
    ).group_by(
        Department.dept_name
    ).order_by(
        Department.dept_name
    ).all()

    return [
        {
            "department": row.department,
            "New": row.New or 0,
            "In_Progress": row.in_progress or 0,
            "Pending": row.Pending or 0,
            "Approved": row.Approved or 0,
            "Rejected": row.Rejected or 0
        }
        for row in results
    ]
    
    
# Top 10 Risk based on Likelihood and Impact

from sqlalchemy import desc

def top_10_risk(db: Session, start_date, end_date):

    results = db.query(
        RiskRegister.risk_register_id,
        RiskRegister.risk_id,
        RiskRegister.risk_name,

        RiskDescription.risk_description_id,
        RiskDescription.current_risk_likelihood_id.label("likelihood"),
        RiskDescription.current_risk_impact_id.label("impact"),

        (
            RiskDescription.current_risk_likelihood_id *
            RiskDescription.current_risk_impact_id
        ).label("risk_score")

    ).join(
        RiskDescription,
        RiskRegister.risk_register_id == RiskDescription.risk_register_id
    ).filter(
        RiskRegister.is_deleted == 0,
        RiskDescription.is_deleted == 0,
        RiskRegister.created_on >= start_date,
        RiskRegister.created_on <= end_date
    ).order_by(
        desc("risk_score")
    ).limit(10).all()

    return [
        {
            "risk_register_id": row.risk_register_id,
            "risk_id": row.risk_id,
            "risk_name": row.risk_name,
            "risk_description_id": row.risk_description_id,
            "likelihood": row.likelihood,
            "impact": row.impact,
            "risk_score": row.risk_score
        }
        for row in results
    ]
    
    

# Based on Risk_Score categorized(Circular chart)

def risk_percentage_chart(db: Session, start_date, end_date):

    results = db.query(

        case(
            (
                (RiskDescription.current_risk_likelihood_id *
                 RiskDescription.current_risk_impact_id) <= 4,
                "Low Risk"
            ),
            (
                (RiskDescription.current_risk_likelihood_id *
                 RiskDescription.current_risk_impact_id) <= 9,
                "Medium Risk"
            ),
            (
                (RiskDescription.current_risk_likelihood_id *
                 RiskDescription.current_risk_impact_id) <= 16,
                "Critical Risk"
            ),
            else_="High Risk"
        ).label("category"),

        func.count().label("total")

    ).join(
        RiskRegister,
        RiskRegister.risk_register_id == RiskDescription.risk_register_id
    ).filter(
        RiskRegister.is_deleted == 0,
        RiskDescription.is_deleted == 0,
        RiskRegister.created_on >= start_date,
        RiskRegister.created_on <= end_date
    ).group_by("category").all()


    # --- PREVIOUS UNOPTIMIZED CODE (Commented out) ---
    # # total risks count
    # total_risks = sum(row.total for row in results)
    # 
    # return [
    #     {
    #         "category": row.category,
    #         "percentage": round((row.total / total_risks) * 100, 2)
    #     }
    #     for row in results
    # ]

    # --- OPTIMIZED CODE (Safeguard against ZeroDivisionError when total_risks is 0) ---
    total_risks = sum(row.total for row in results)
    if total_risks == 0:
        return [
            {"category": row.category, "percentage": 0.0}
            for row in results
        ]

    return [
        {
            "category": row.category,
            "percentage": round((row.total / total_risks) * 100, 2)
        }
        for row in results
    ]
    
    
    
# Total of Risk Rating

def risk_heatmap(db: Session, start_date, end_date):

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
        RiskRegister.created_on >= start_date,
        RiskRegister.created_on <= end_date
    ).group_by(
        RiskDescription.current_risk_likelihood_id,
        RiskDescription.current_risk_impact_id
    ).all()
    
    
    impact_map = {1:"A",2:"B",3:"C",4:"D",5:"E"}
    
    return [
        {
            "likelihood": row.likelihood,
            "impact": row.impact,
            "count": row.total,
            "color": get_color(row.likelihood * row.impact),
            "code": f"{row.likelihood}{impact_map.get(row.impact)}"
        }
        for row in results
    ]
    

# Count with Heatmap

def risk_transition_heatmap(db: Session, start_date, end_date, dept_id=None):
    
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
        RiskRegister.created_on >= start_date,
        RiskRegister.created_on <= end_date
    )

    # Apply department filter ONLY if provided
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
            "inherent_code": f"{row.inh_likelihood}{impact_map.get(row.inh_impact)}",
            "current_code": f"{row.cur_likelihood}{impact_map.get(row.cur_impact)}"
        }
        for row in results
    ]