from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.core.database import Base
from sqlalchemy.orm import relationship
from sqlalchemy import LargeBinary
from sqlalchemy import Text
from app.core.config import settings


# RiskActionFollowup model representing the risk_action_followup table in the database
class RiskActionFollowup(Base):

    __tablename__ = "risk_action_followup"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    followup_id = Column(Integer, primary_key=True, index=True)

    reference_id = Column(Integer, nullable=False)

    module_name = Column(String(50))

    remark = Column(String(500), nullable=False)

    progress = Column(String(15))

    status = Column(Integer)

    next_followup_date = Column(DateTime)

    created_on = Column(DateTime, server_default=func.now())

    created_by = Column(Integer, nullable=False, default=1)
    
    file_name = Column(Text)
    
    file_extension= Column(String(100))
    
    file_type = Column(String(100))
    
    file_data = Column(LargeBinary)
    
    # Relationship
    created_user = relationship(
        "User",
        primaryjoin="RiskActionFollowup.created_by == User.id",
        foreign_keys=[created_by],
        viewonly=True
    )
    
    status_master  = relationship(
        "Status",
        primaryjoin="RiskActionFollowup.status == Status.id",
        foreign_keys=[status],
        viewonly=True
    )
    