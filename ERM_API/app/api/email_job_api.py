from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.dependencies import get_current_user
from app.core.response import success_response, error_response

from app.core.database import get_db
from app.models.email_job_mst import EmailJobMst


router = APIRouter(prefix="/email-job", tags=["Email Job"], dependencies=[Depends(get_current_user)])



# for the api through send the email (optinal)
@router.post("/create")
def create_email_job(
    email_server_id: int,
    email_to: str,
    email_subject: str,
    email_body: str,
    db: Session = Depends(get_db)
):
    
    try:
        job = EmailJobMst(
            email_server_id=email_server_id,
            email_to=email_to,
            email_subject=email_subject,
            email_body=email_body,
            email_type = "HTML",
            send_status="New",
            next_attempt_at=datetime.now(),
            created_on=datetime.now(),
            is_deleted=0
        )

        db.add(job)
        db.commit()
        db.refresh(job)

        return success_response({
            "email_job_id": job.email_job_id})
        
    except Exception as e:
        db.rollback()
        return error_response(str(e), 400)