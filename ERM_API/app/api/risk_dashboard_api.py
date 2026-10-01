from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from typing import List, Optional

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.response import success_response, error_response

from app.schemas.risk_dashboard import *
from app.services.risk_dashboard_service import *

router = APIRouter(prefix="/risk-dashboard", tags=["Risk Dashboard"])


# KPI for the dashboard
@router.get("/summary", response_model=RiskDashboardSummaryResponse)
def get_dashboard_summary(
    start_date: str = Query(..., description="Start Date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End Date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:

        if not start_date or not end_date:
            raise ValueError("Start date and end date are required")

        start_date_obj = datetime.fromisoformat(start_date)
        end_date_obj = datetime.fromisoformat(end_date)

        return success_response(
            get_dashboard_summary_service(db, start_date_obj, end_date_obj)
        )

    except ValueError as e:
        return error_response(str(e), 400)
    

# Department wise Risk Count
@router.get("/department-wise-Bar", response_model=List[DepartmentWiseRiskResponse])
def get_department_wise_risk(
    start_date: str,
    end_date: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        start_date = datetime.fromisoformat(start_date)
        end_date = datetime.fromisoformat(end_date)

        return success_response(
            department_wise_risk_count(db, start_date, end_date)
        )

    except ValueError as e:
        return error_response(str(e), 400)
    
    
    
# User wise Risk Count

@router.get("/User-wise-Bar", response_model=List[EmployeeWiseRiskResponse])
def get_employee_wise_risk(
    start_date: str,
    end_date: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        start_date = datetime.fromisoformat(start_date)
        end_date = datetime.fromisoformat(end_date)

        return success_response(
            user_wise_risk_count(db, start_date, end_date)
        )

    except ValueError as e:
        return error_response(str(e), 400)



  
# Staus wise Risk Count

@router.get("/status-wise-pie", response_model=List[StatusWisePieResponse])
def get_status_wise_pie(
    start_date: str,
    end_date: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        start_date = datetime.fromisoformat(start_date)
        end_date = datetime.fromisoformat(end_date)

        return success_response(
            status_wise_Risk_Count(db, start_date, end_date)
        )

    except ValueError as e:
        return error_response(str(e), 400)
    
    
# Dept wise progress
@router.get("/department-wise-progress-HBar", response_model=List[DeptartmentwiseprogressResponse])
def get_department_wise_progress(
    start_date: str,
    end_date: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        start_date = datetime.fromisoformat(start_date)
        end_date = datetime.fromisoformat(end_date)

        return success_response(
            department_wise_progress(db, start_date, end_date)
        )

    except ValueError as e:
        return error_response(str(e), 400)
    
    
# Dept wise Stacked Bar Chart for Status
@router.get("/department-wise-status-stackedBar", response_model=List[DepartmentWiseStatusStackedResponse])
def get_department_wise_status(
    start_date: str,
    end_date: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        start_date = datetime.fromisoformat(start_date)
        end_date = datetime.fromisoformat(end_date)

        return success_response(
            department_wise_status(db, start_date, end_date)
        )

    except ValueError as e:
        return error_response(str(e), 400)
    
    
# Top 10 Risk based on Likelihood and impact
@router.get("/top-10-risk", response_model=List[TopRiskResponse])
def get_top_10_risk(
    start_date: str,
    end_date: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        start_date = datetime.fromisoformat(start_date)
        end_date = datetime.fromisoformat(end_date)

        return success_response(
            top_10_risk(db, start_date, end_date)
        )

    except ValueError as e:
        return error_response(str(e), 400)


# Based on Risk_Score categorized(Circular chart)
@router.get("/risk-percentage", response_model=List[RiskPercentageResponse])
def get_risk_percentage(
    start_date: str,
    end_date: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        start_date = datetime.fromisoformat(start_date)
        end_date = datetime.fromisoformat(end_date)

        return success_response(
            risk_percentage_chart(db, start_date, end_date)
        )

    except ValueError as e:
        return error_response(str(e), 400)
    
    
# Total of Risk Rating

@router.get("/heatmap", response_model=RiskHeatmapResponse)
def get_risk_heatmap(
    start_date: str,
    end_date: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        start_date = datetime.fromisoformat(start_date)
        end_date = datetime.fromisoformat(end_date)

        return success_response(
            risk_heatmap(db, start_date, end_date)
        )

    except ValueError as e:
        return error_response(str(e), 400)


# Count with Risk Rating

@router.get("/risk-transition-heatmap", response_model=List[RiskHeatmapcountResponse])
def get_risk_transition_heatmap(
    start_date: str,
    end_date: str,
    dept_id: Optional[int] = None,   
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        start_date = datetime.fromisoformat(start_date)
        end_date = datetime.fromisoformat(end_date)

        return success_response(
            risk_transition_heatmap(db, start_date, end_date, dept_id)
        )

    except Exception as e:
        return error_response(str(e), 400)