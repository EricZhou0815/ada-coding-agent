import os
import uuid
from datetime import datetime
from sqlalchemy import create_engine, Column, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

# Get database URL from env, default to local SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ada_jobs.db")

engine = create_engine(
    DATABASE_URL, 
    # check_same_thread is needed for SQLite, ignored by others
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class StoryJob(Base):
    __tablename__ = "story_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    repo_url = Column(String, nullable=False)
    status = Column(String, default="PENDING")  # PENDING, RUNNING, SUCCESS, FAILED
    logs = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Create tables
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
