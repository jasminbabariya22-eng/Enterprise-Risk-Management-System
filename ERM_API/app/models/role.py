from sqlalchemy import Column, Integer, String, DateTime, SmallInteger
from app.core.database import Base
from app.core.config import settings
from sqlalchemy.orm import relationship


# UserRole model representing the mst_user_role table in the database
class UserRole(Base):
    __tablename__ = "mst_user_role"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(String(2000))
    created_on = Column(DateTime)
    created_by = Column(Integer, default=1)
    modified_on = Column(DateTime)
    modified_by = Column(Integer)
    is_deleted = Column(SmallInteger, default=0)
    
    users = relationship("User", back_populates="role")