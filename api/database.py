import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, String, DateTime, Text, text, Integer, Index, BigInteger, JSON, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# Get database URL from env, default to local SQLite for local dev if not provided
# In production/docker, this will be: postgresql://ada_user:ada_password@db:5432/ada_db
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ada_jobs.db")

# Connection pool settings for multi-instance deployment
# Each API instance gets its own pool
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))  # Connections per instance
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))  # Extra connections during spikes
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))  # Seconds to wait for connection
POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "3600"))  # Recycle connections after 1 hour

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    # SQLite-specific settings
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    # Connection pooling (ignored by SQLite, used by PostgreSQL)
    pool_size=POOL_SIZE if "postgresql" in DATABASE_URL else 5,
    max_overflow=MAX_OVERFLOW if "postgresql" in DATABASE_URL else 0,
    pool_timeout=POOL_TIMEOUT,
    pool_recycle=POOL_RECYCLE,
    pool_pre_ping=True,  # Verify connections before using them
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


class PlanningBatch(Base):
    """
    Batch of user story requests submitted together for planning.
    
    Tracks multiple planning sessions and execution jobs as a unit.
    Supports sequential or parallel planning modes.
    """
    __tablename__ = "planning_batches"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    repo_url = Column(String, nullable=False)
    planning_mode = Column(String(20), default="sequential")  # "sequential" | "parallel"
    auto_execute = Column(Integer, default=1)  # 1=true, 0=false (SQLite-compatible boolean)
    
    # Celery job tracking
    celery_task_id = Column(String, nullable=True, index=True)  # Celery async task ID
    status = Column(String(50), default="PENDING")  # "PENDING", "PROCESSING", "COMPLETE", "FAILED"
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    sessions = relationship("PlanningSession", back_populates="batch", cascade="all, delete-orphan")


class PlanningSession(Base):
    """
    Individual planning conversation session for clarifying a user story.
    
    Stores conversation history as JSON for stateless API design.
    Can be part of a batch or standalone.
    """
    __tablename__ = "planning_sessions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_id = Column(String, ForeignKey('planning_batches.id'), nullable=True, index=True)
    
    # Input and state
    user_input = Column(Text, nullable=False)  # Original user request
    state = Column(String(50), default="pending")  # "pending", "active", "complete", "error", "cancelled"
    
    # Conversation data
    conversation_history = Column(JSON, default=list)  # [{role: "user"|"assistant", content: str}, ...]
    current_question = Column(Text, nullable=True)  # Latest question from LLM
    story_result = Column(JSON, nullable=True)  # Final story when state="complete"
    
    # Execution linkage
    execution_job_id = Column(String, nullable=True)  # FK to StoryJob when auto-queued
    
    # Metadata
    iteration = Column(Integer, default=0)
    questions_asked = Column(Integer, default=0)
    max_iterations = Column(Integer, default=10)
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    batch = relationship("PlanningBatch", back_populates="sessions")
    
    # Index for batch queries
    __table_args__ = (
        Index('idx_batch_state', 'batch_id', 'state'),
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
