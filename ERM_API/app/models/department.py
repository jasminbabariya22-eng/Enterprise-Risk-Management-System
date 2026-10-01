from sqlalchemy import Column, Integer, String, Text, DateTime, SmallInteger
from app.core.database import Base
from sqlalchemy.orm import relationship
from app.core.config import settings

class Department(Base):                     # Define the Department model representing the mst_department table
    __tablename__ = "mst_department"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    id = Column(Integer, primary_key=True, index=True)
    dept_name = Column(String(255))
    # assigned_to = Column(Integer)
    # assigned_on = Column(DateTime)
    created_by = Column(Integer, default=1)
    created_on = Column(DateTime)
    modified_by = Column(Integer, default=1)
    modified_on = Column(DateTime)
    is_deleted = Column(SmallInteger, default=0)
    description = Column(Text)
    dept_short_name = Column(String(10))
    last_risk_number = Column(Integer, default=0)
    
    # Relationship
    risks = relationship("RiskRegister", back_populates="department") 
    users = relationship("User", back_populates="department")