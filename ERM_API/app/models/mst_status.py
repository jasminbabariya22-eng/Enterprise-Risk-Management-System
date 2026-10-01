from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from app.core.database import Base
from app.core.config import settings


# Status model representing the mst_status table in the database
class Status(Base):
    __tablename__ = "mst_status"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    id = Column(Integer, primary_key=True, index=True)

    status_name = Column(String(200), nullable=False)

    created_by = Column(Integer, default=1)
    created_on = Column(DateTime, server_default=func.current_timestamp())

    modified_by = Column(Integer, default=1)
    modified_on = Column(DateTime, server_default=func.current_timestamp())

    is_deleted = Column(Integer, default=0)

    type = Column(Text)