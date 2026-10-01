from sqlalchemy import Column, Integer, String, DateTime
from app.core.database import Base
from app.core.config import settings
from sqlalchemy.orm import relationship


# UserType model representing the mst_user_type table in the database
class UserType(Base):
    __tablename__ = "mst_user_type"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    description = Column(String(100))
    created_by = Column(Integer, default=1)
    created_on = Column(DateTime)
    modified_by = Column(Integer)
    modified_on = Column(DateTime)
    is_deleted = Column(Integer, default=0)
    
    users = relationship("User", back_populates="user_type")