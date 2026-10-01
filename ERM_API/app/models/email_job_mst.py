from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.config import settings


# EmailJobMst model representing the mst_email_job table in the database
class EmailJobMst(Base):
    __tablename__ = "mst_email_job"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    email_job_id = Column(Integer, primary_key=True, index=True)

    email_server_id = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.email_server.email_server_id"), nullable=False)

    email_module = Column(String(50))
    email_to = Column(String(500), nullable=False)
    email_cc = Column(String(500))
    email_bcc = Column(String(500))
    email_subject = Column(String(500), nullable=False)
    email_type = Column(String(50))
    email_body = Column(Text)

    email_attachment_count = Column(Integer)

    total_attempts = Column(Integer, default=3)
    send_attempts = Column(Integer, default=0)
    attempt_delay = Column(Integer, default=5000)
    next_attempt_at = Column(DateTime)

    send_status = Column(String(20))

    created_on = Column(DateTime)
    created_by = Column(Integer)

    is_deleted = Column(Integer, default=0)

    # Relationship
    email_server = relationship("EmailServer", back_populates="email_jobs")