from sqlalchemy import Column, Integer, String, DateTime
from app.core.database import Base
from app.core.config import settings   
from sqlalchemy.orm import relationship


# EmailServer model representing the email_server table in the database
class EmailServer(Base):
    __tablename__ = "email_server"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    email_server_id = Column(Integer, primary_key=True, index=True)

    outgoing_server_type = Column(String(20))
    outgoing_server_ip = Column(String(100))
    outgoing_email_user = Column(String(250))
    outgoing_email_password = Column(String(100))
    outgoing_email_encryption = Column(Integer, default=0)
    outgoing_email_port = Column(Integer)

    created_on = Column(DateTime)
    created_by = Column(Integer)
    modified_on = Column(DateTime)
    modified_by = Column(Integer)

    is_deleted = Column(Integer, default=0)
    
    email_jobs = relationship("EmailJobMst", back_populates="email_server")