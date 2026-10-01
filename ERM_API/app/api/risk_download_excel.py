from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional

from sqlalchemy.inspection import inspect

from app.core.database import get_db
from app.core.dependencies import get_current_user

from fastapi.responses import StreamingResponse
from app.services.risk_export import generate_risk_excel


router = APIRouter(prefix="/risk", tags=["Risk"])

@router.get("/download/{risk_id}")
def download_risk_excel(
    risk_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    file = generate_risk_excel(db, risk_id)

    return StreamingResponse(
        file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=risk_{risk_id}.xlsx"
        }
    )