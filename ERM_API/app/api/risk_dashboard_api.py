from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.database import get_db
from app.core.dependencies import require_dashboard_access
from app.core.response import success_response, error_response

from app.schemas.risk_dashboard import (
    RiskDashboardSummaryResponse,
    DepartmentWiseRiskResponse,
    EmployeeWiseRiskResponse,
    StatusWisePieResponse,
    DeptartmentwiseprogressResponse,
    DepartmentWiseStatusStackedResponse,
    TopRiskResponse,
    RiskPercentageResponse,
    RiskHeatmapResponse,
    RiskHeatmapcountResponse
)
from app.services.risk_dashboard_service import (
    get_dashboard_summary_service,
    department_wise_risk_count,
    user_wise_risk_count,
    status_wise_Risk_Count,
    department_wise_progress,
    department_wise_status,
    top_10_risk,
    risk_percentage_chart,
    risk_heatmap,
    risk_transition_heatmap
)

# Enforce strict RBAC at router level: only Admin, Risk Manager, and Risk Head are authorized
router = APIRouter(
    prefix="/risk-dashboard",
    tags=["Risk Dashboard"],
    dependencies=[Depends(require_dashboard_access)]
)


# 1. KPI Summary for the dashboard
@router.get("/summary", response_model=RiskDashboardSummaryResponse)
def get_dashboard_summary(
    start_date: Optional[str] = Query(None, description="Start Date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End Date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_dashboard_access)
):
    try:
        data = get_dashboard_summary_service(db, start_date, end_date)
        return success_response(data)
    except Exception as e:
        return error_response(str(e), 400)


# 2. Department wise Risk Count
@router.get("/department-wise-Bar", response_model=List[DepartmentWiseRiskResponse])
def get_department_wise_risk(
    start_date: Optional[str] = Query(None, description="Start Date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End Date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_dashboard_access)
):
    try:
        data = department_wise_risk_count(db, start_date, end_date)
        return success_response(data)
    except Exception as e:
        return error_response(str(e), 400)


# 3. User wise Risk Count
@router.get("/User-wise-Bar", response_model=List[EmployeeWiseRiskResponse])
def get_employee_wise_risk(
    start_date: Optional[str] = Query(None, description="Start Date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End Date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_dashboard_access)
):
    try:
        data = user_wise_risk_count(db, start_date, end_date)
        return success_response(data)
    except Exception as e:
        return error_response(str(e), 400)


# 4. Status wise Risk Count
@router.get("/status-wise-pie", response_model=List[StatusWisePieResponse])
def get_status_wise_pie(
    start_date: Optional[str] = Query(None, description="Start Date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End Date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_dashboard_access)
):
    try:
        data = status_wise_Risk_Count(db, start_date, end_date)
        return success_response(data)
    except Exception as e:
        return error_response(str(e), 400)


# 5. Department wise progress
@router.get("/department-wise-progress-HBar", response_model=List[DeptartmentwiseprogressResponse])
def get_department_wise_progress(
    start_date: Optional[str] = Query(None, description="Start Date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End Date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_dashboard_access)
):
    try:
        data = department_wise_progress(db, start_date, end_date)
        return success_response(data)
    except Exception as e:
        return error_response(str(e), 400)


# 6. Department wise Stacked Bar Chart for Status
@router.get("/department-wise-status-stackedBar", response_model=List[DepartmentWiseStatusStackedResponse])
def get_department_wise_status(
    start_date: Optional[str] = Query(None, description="Start Date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End Date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_dashboard_access)
):
    try:
        data = department_wise_status(db, start_date, end_date)
        return success_response(data)
    except Exception as e:
        return error_response(str(e), 400)


# 7. Top 10 Risks based on Likelihood and impact
@router.get("/top-10-risk", response_model=List[TopRiskResponse])
def get_top_10_risk(
    start_date: Optional[str] = Query(None, description="Start Date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End Date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_dashboard_access)
):
    try:
        data = top_10_risk(db, start_date, end_date)
        return success_response(data)
    except Exception as e:
        return error_response(str(e), 400)


# 8. Based on Risk_Score categorized (Circular chart)
@router.get("/risk-percentage", response_model=List[RiskPercentageResponse])
def get_risk_percentage(
    start_date: Optional[str] = Query(None, description="Start Date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End Date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_dashboard_access)
):
    try:
        data = risk_percentage_chart(db, start_date, end_date)
        return success_response(data)
    except Exception as e:
        return error_response(str(e), 400)


# 9. Total of Risk Rating (5x5 Heatmap)
@router.get("/heatmap", response_model=List[RiskHeatmapResponse])
def get_risk_heatmap(
    start_date: Optional[str] = Query(None, description="Start Date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End Date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_dashboard_access)
):
    try:
        data = risk_heatmap(db, start_date, end_date)
        return success_response(data)
    except Exception as e:
        return error_response(str(e), 400)


# 10. Risk Transition Heatmap (Inherent vs Current)
@router.get("/risk-transition-heatmap", response_model=List[RiskHeatmapcountResponse])
def get_risk_transition_heatmap(
    start_date: Optional[str] = Query(None, description="Start Date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End Date (YYYY-MM-DD)"),
    dept_id: Optional[int] = Query(None, description="Optional Department ID Filter"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_dashboard_access)
):
    try:
        data = risk_transition_heatmap(db, start_date, end_date, dept_id)
        return success_response(data)
    except Exception as e:
        return error_response(str(e), 400)