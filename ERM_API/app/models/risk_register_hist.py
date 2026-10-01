from sqlalchemy import Column, Integer, String, Float, SmallInteger, DateTime
from app.core.database import Base
from app.core.config import settings
from sqlalchemy.orm import relationship, foreign
from app.models.mst_status import Status
from app.models.user import User


# RiskRegisterHist model representing the risk_register_hist table in the database
class RiskRegisterHist(Base):
    __tablename__ = "risk_register_hist"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    risk_register_id = Column(Integer, primary_key=True)

    risk_id = Column(String(10), nullable=False)
    risk_name = Column(String(250), nullable=False)

    dept_id = Column(Integer, nullable=False)
    risk_owner_id = Column(Integer, nullable=False)
    risk_co_owner_id = Column(Integer)

    target_date = Column(DateTime)

    financial_year = Column(String(10))

    risk_status = Column(Integer)
    risk_progress = Column(String(15))

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

    created_by = Column(Integer)
    created_on = Column(DateTime, primary_key=True)

    modified_by = Column(Integer)
    modified_on = Column(DateTime, primary_key=True)

    is_active = Column(SmallInteger)
    is_deleted = Column(SmallInteger)

    # ================= RELATIONSHIPS =================

    # 🔹 Risk Status
    status = relationship(
        "Status",
        primaryjoin="foreign(RiskRegisterHist.risk_status) == Status.id",
        viewonly=True
    )

    # 🔹 Function Head
    function_head_status = relationship(
        "Status",
        primaryjoin="foreign(RiskRegisterHist.risk_function_head_approval_status) == Status.id",
        viewonly=True
    )

    function_head_user = relationship(
        "User",
        primaryjoin="foreign(RiskRegisterHist.risk_function_head_approval_by) == User.id",
        viewonly=True
    )

    # 🔹 Risk Head
    risk_head_status_rel = relationship(
        "Status",
        primaryjoin="foreign(RiskRegisterHist.risk_head_approval_status) == Status.id",
        viewonly=True
    )

    risk_head_user = relationship(
        "User",
        primaryjoin="foreign(RiskRegisterHist.risk_head_approval_by) == User.id",
        viewonly=True
    )

    # 🔹 Risk Manager
    risk_manager_status_rel = relationship(
        "Status",
        primaryjoin="foreign(RiskRegisterHist.risk_manager_approval_status) == Status.id",
        viewonly=True
    )

    risk_manager_user = relationship(
        "User",
        primaryjoin="foreign(RiskRegisterHist.risk_manager_approval_by) == User.id",
        viewonly=True
    )

    # 🔹 Created By
    created_user = relationship(
        "User",
        primaryjoin="foreign(RiskRegisterHist.created_by) == User.id",
        viewonly=True
    )