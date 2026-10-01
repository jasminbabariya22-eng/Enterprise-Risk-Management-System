from sqlalchemy import Column, Integer, String, Text, SmallInteger, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.config import settings


# RiskDescription model representing the risk_description table in the database
class RiskDescription(Base):
    __tablename__ = "risk_description"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    risk_description_id = Column(Integer, primary_key=True, index=True)

    risk_register_id = Column(
        Integer,
        ForeignKey(f"{settings.DB_SCHEMA}.risk_register.risk_register_id"),
        nullable=False
    )

    risk_id = Column(String(10))
    risk_description = Column(Text)

    inherent_risk_likelihood_id = Column(Integer)
    inherent_risk_impact_id = Column(Integer)

    mitigation = Column(Text)

    current_risk_likelihood_id = Column(Integer)
    current_risk_impact_id = Column(Integer)

    created_by = Column(Integer, default=1)
    created_on = Column(DateTime)
    modified_by = Column(Integer)
    modified_on = Column(DateTime)

    is_deleted = Column(SmallInteger, default=0)

    # Relationship
    risk_register = relationship("RiskRegister", back_populates="risk_descriptions")
    
    treatments = relationship("RiskTreatment",back_populates="risk_description",cascade="all,delete-orphan")