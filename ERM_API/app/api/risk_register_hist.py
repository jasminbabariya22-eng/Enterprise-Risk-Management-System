from sqlalchemy import Column, Integer, String, Float, SmallInteger, DateTime
from datetime import datetime
from app.core.database import Base


class RiskRegisterHist(Base):
    __tablename__ = "risk_register_hist"
    __table_args__ = {"schema": "ers"}

    risk_register_id = Column(Integer)

    risk_id = Column(String(10), nullable=False)
    risk_name = Column(String(50), nullable=False)

    dept_id = Column(Integer, nullable=False)
    risk_owner_id = Column(Integer, nullable=False)
    risk_co_owner_id = Column(Integer)

    target_date = Column(DateTime)
    financial_year = Column(String(10))

    risk_status = Column(Integer)
    risk_progress = Column(Float)

    risk_function_head_approval_status = Column(Integer)
    risk_function_head_approval_remark = Column(String(500))
    risk_function_head_approval_on = Column(DateTime)
    risk_function_head_approval_by = Column(Integer)

    risk_head_approval_status = Column(Integer)
    risk_head_approved_on = Column(DateTime)
    risk_head_approval_remark = Column(String(500))
    risk_head_approval_by = Column(Integer)

    risk_manager_approval_status = Column(Integer)
    risk_manager_approved_on = Column(DateTime)
    risk_manager_approval_remark = Column(String(500))
    risk_manager_approval_by = Column(Integer)

    created_by = Column(Integer, default=1)
    created_on = Column(DateTime, default=datetime.utcnow)

    modified_by = Column(Integer)
    modified_on = Column(DateTime)

    is_active = Column(SmallInteger, default=0)
    is_deleted = Column(SmallInteger, default=0)