from sqlalchemy import Column, Integer, String, SmallInteger, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base
from app.core.config import settings


# User model representing the mst_users table in the database
class User(Base):
    __tablename__ = "mst_users"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    id = Column(Integer, primary_key=True, index=True)

    log_id = Column(String, nullable=False, unique=True)
    password = Column(String(255), nullable=False)

    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)

    photo = Column(String)
    contact_no = Column(String(20))
    country_code = Column(Integer)
    std_code = Column(Integer)

    country = Column(String)
    address = Column(String)
    user_city = Column(String)

    created_by = Column(Integer)
    created_on = Column(DateTime, nullable=False, default=datetime.utcnow)

    modified_by = Column(Integer)
    modified_on = Column(DateTime)

    dept_id = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.mst_department.id"), nullable=False)
    role_id = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.mst_user_role.id"), nullable=False)
    user_type_id = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.mst_user_type.id"), default=0)

    status = Column(String, nullable=False)
    is_deleted = Column(SmallInteger, default=0)

    # Relationships
    department = relationship("Department", back_populates="users")
    role = relationship("UserRole", back_populates="users")
    user_type = relationship("UserType", back_populates="users")