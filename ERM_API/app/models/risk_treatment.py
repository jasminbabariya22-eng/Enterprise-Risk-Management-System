from sqlalchemy import Column, Integer, String, Float, SmallInteger, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.config import settings


# RiskTreatment model representing the risk_treatment table in the database
class RiskTreatment(Base):
    __tablename__ = "risk_treatment"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    risk_treatment_id = Column(Integer, primary_key=True, index=True)

    risk_description_id = Column(
        Integer,
        ForeignKey(f"{settings.DB_SCHEMA}.risk_description.risk_description_id"),
        nullable=False
    )

    risk_register_id = Column(
        Integer,
        ForeignKey(f"{settings.DB_SCHEMA}.risk_register.risk_register_id")
    )

    risk_id = Column(String(10))

    action_plan = Column(Text, nullable=False)
    action_owner_id = Column(
        Integer,
        ForeignKey(f"{settings.DB_SCHEMA}.mst_users.id"),
        nullable=False
    )

    target_date = Column(DateTime)
    progress = Column(String(15))
    action_status_id = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.mst_status.id"))

    next_followup_date = Column(DateTime)
    
    # approved_by = Column(Integer)
    approved_by = Column(
        Integer,
        ForeignKey(
            f"{settings.DB_SCHEMA}.mst_users.id"
        )
    )
    
    approved_on = Column(DateTime)
    approval_remark = Column(String(500))
    approval_status = Column(Integer)

    created_on = Column(DateTime)
    created_by = Column(Integer, nullable=False)

    modified_on = Column(DateTime)
    modified_by = Column(Integer)

    is_deleted = Column(SmallInteger, default=0)

    # Relationships
    risk_description = relationship("RiskDescription", back_populates="treatments")
    risk_register = relationship("RiskRegister")
    action_owner = relationship("User", foreign_keys=[action_owner_id])
    status = relationship("Status")
    
    approved_user = relationship("User", foreign_keys=[approved_by])