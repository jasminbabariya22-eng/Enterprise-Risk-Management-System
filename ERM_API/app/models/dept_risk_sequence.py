from sqlalchemy import Column, Integer, String
from app.core.database import Base

class DeptRiskSequence(Base):
    __tablename__ = "dept_risk_sequence"
    __table_args__ = {"schema": "ers"}

    dept_id = Column(Integer, primary_key=True)
    dept_short_name = Column(String(10))
    last_number = Column(Integer, default=0)