from sqlalchemy import Column, Integer, String, Float, SmallInteger, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base

from app.models.mst_status import Status
from app.core.config import settings


# RiskRegister Model representing the risk_register table in the database
class RiskRegister(Base):
    __tablename__ = "risk_register"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    risk_register_id = Column(Integer, primary_key=True)

    risk_id = Column(String(10), nullable=False)
    risk_name = Column(String(250), nullable=False)

    dept_id = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.mst_department.id"), nullable=False)
    risk_owner_id = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.mst_users.id"), nullable=False)

    financial_year = Column(String(10))
    risk_status = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.mst_status.id"))
    risk_progress = Column(String(15))

    risk_function_head_approval_status = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.mst_status.id"))
    risk_function_head_approval_remark = Column(String(500))
    risk_function_head_approval_on = Column(DateTime)
    risk_function_head_approval_by = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.mst_users.id"))

    risk_head_approval_status = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.mst_status.id"))
    risk_head_approved_on = Column(DateTime)
    risk_head_approval_remark = Column(String(500))
    risk_head_approval_by = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.mst_users.id"))
    
    risk_manager_approval_status = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.mst_status.id"))
    risk_manager_approved_on = Column(DateTime)
    risk_manager_approval_remark = Column(String(500))
    risk_manager_approval_by = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.mst_users.id"))

    created_by = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.mst_users.id"), nullable=False, default=1)
    created_on = Column(DateTime)
    modified_by = Column(Integer)
    modified_on = Column(DateTime)

    is_active = Column(SmallInteger, default=0)
    is_deleted = Column(SmallInteger, default=0)
    
    risk_co_owner_id = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.mst_users.id"), default = 0)

    # Relationships
    department = relationship("Department", back_populates="risks")

    risk_descriptions = relationship(
        "RiskDescription",
        back_populates="risk_register",
        cascade="all, delete-orphan"
    )

    created_user = relationship(
        "User",
        foreign_keys=[created_by],
        viewonly=True
    )
    
    created_name = relationship(
        "User",
        foreign_keys=[created_by]
    )
    
    risk_owner = relationship(
        "User",
        foreign_keys=[risk_owner_id]
    )

    risk_co_owner = relationship(
        "User",
        foreign_keys=[risk_co_owner_id]
    )
    
    status = relationship(
        "Status",
        foreign_keys=[risk_status]
    )
    
    function_head_status = relationship(
        "Status",
        foreign_keys=[risk_function_head_approval_status]
    )
    risk_function_head_approval_by_name = relationship(
        "User",
        foreign_keys=[risk_function_head_approval_by]
    )

    risk_head_status = relationship(
        "Status",
        foreign_keys=[risk_head_approval_status]
    )
    risk_head_approval_by_name = relationship(
        "User",
        foreign_keys=[risk_head_approval_by]
    )
    
    risk_manager_status = relationship(
    "Status",
    foreign_keys=[risk_manager_approval_status]
    )
    risk_manager_approval_by_name = relationship(
        "User",
        foreign_keys=[risk_manager_approval_by]
    )
