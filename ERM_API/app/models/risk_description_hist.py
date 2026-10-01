from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from app.core.database import Base
from app.core.config import settings


# RiskDescriptionHist model representing the risk_description_hist table in the database
class RiskDescriptionHist(Base):
    __tablename__ = "risk_description_hist"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    risk_description_id = Column(Integer, primary_key=True, index=True)

    risk_register_id = Column(Integer, nullable=False)
    risk_id = Column(String(10))

    risk_description = Column(Text)

    inherent_risk_likelihood_id = Column(Integer)
    inherent_risk_impact_id = Column(Integer)

    mitigation = Column(Text)

    current_risk_likelihood_id = Column(Integer)
    current_risk_impact_id = Column(Integer)

    created_by = Column(Integer, default=1)
    created_on = Column(DateTime, server_default=func.now())

    modified_by = Column(Integer)
    modified_on = Column(DateTime)

    is_deleted = Column(Integer, default=0)