from sqlalchemy import Column, Integer, String, DateTime, Float, SmallInteger, Text
from sqlalchemy.sql import func
from app.core.database import Base
from app.core.config import settings


# RiskTreatmentHist model representing the risk_treatment_hist table in the database
class RiskTreatmentHist(Base):
    __tablename__ = "risk_treatment_hist"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    risk_treatment_id = Column(Integer, primary_key=True)
    risk_description_id = Column(Integer, nullable=False)
    risk_register_id = Column(Integer)
    risk_id = Column(String(10))

    action_plan = Column(Text, nullable=False)
    action_owner_id = Column(Integer, nullable=False)

    target_date = Column(DateTime)
    progress = Column(String(15))
    action_status_id = Column(Integer)

    next_followup_date = Column(DateTime)

    created_on = Column(DateTime, server_default=func.now(), nullable=False)
    created_by = Column(Integer, default=1, nullable=False)

    modified_on = Column(DateTime)
    modified_by = Column(Integer)

    is_deleted = Column(SmallInteger, default=0)