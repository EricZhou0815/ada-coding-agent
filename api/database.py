import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, String, DateTime, Text, text, Integer, Index, BigInteger, JSON, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# Get database URL from env, default to local SQLite for local dev if not provided
# In production/docker, this will be: postgresql://ada_user:ada_password@db:5432/ada_db
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ada_jobs.db")

engine = create_engine(
    DATABASE_URL, 
    # connect_args is needed for SQLite, ignored by others like Postgres
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class StoryJob(Base):
    __tablename__ = "story_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    repo_url = Column(String, nullable=False)
    story_title = Column(String, nullable=True) 
    status = Column(String, default="PENDING")  # PENDING, RUNNING, SUCCESS, FAILED
    logs = Column(Text, default="[]")  # DEPRECATED: Will be removed in future version
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationship to new logs table
    log_entries = relationship("JobLog", back_populates="job", cascade="all, delete-orphan")


class JobLog(Base):
    """
    Structured log entries for jobs.
    
    Optimized for:
    - Fast inserts (no JSON parsing overhead)
    - Efficient queries (indexed by job_id and timestamp)
    - PostgreSQL JSONB support for metadata (falls back to JSON/Text in SQLite)
    """
    __tablename__ = "job_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    job_id = Column(String, ForeignKey('story_jobs.id'), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    level = Column(String(20), nullable=False)  # info, error, warning, thought, tool, success
    prefix = Column(String(100), nullable=False)  # Agent/component name
    message = Column(Text, nullable=False)
    # Use JSON for SQLite compatibility, PostgreSQL will use JSONB automatically
    # Note: 'metadata' is reserved by SQLAlchemy, so we use 'meta'
    meta = Column(JSON, nullable=True)
    
    # Relationship back to job
    job = relationship("StoryJob", back_populates="log_entries")
    
    # Composite index for efficient queries: "get logs for job X ordered by time"
    __table_args__ = (
        Index('idx_job_timestamp', 'job_id', 'timestamp'),
    )

# Create tables (In a real production environment, we would use Alembic)
def init_db():
    Base.metadata.create_all(bind=engine)

# Run initialization on import for simplicity in this stage
init_db()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
