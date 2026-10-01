from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)   # False at a production time

SessionLocal = sessionmaker(             # Create a session factory
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()            # Base class for our models


# Dependency for FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()