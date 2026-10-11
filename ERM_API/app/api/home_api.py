from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.response import success_response, error_response
from app.services.home_service import get_home_workload_and_summary

router = APIRouter(prefix="/home", tags=["Home"])


@router.get("/workload")
def get_home_workload(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Returns role-scoped summary KPIs and actionable workload items for the authenticated user.
    """
    try:
        data = get_home_workload_and_summary(db, current_user)
        return success_response(data=data, message="Home workload retrieved successfully")
    except Exception as e:
        return error_response(message=str(e), status_code=500)
