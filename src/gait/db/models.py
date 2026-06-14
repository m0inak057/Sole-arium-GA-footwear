"""SQLAlchemy ORM models for gait analysis persistence.

Tables:
  - users: API users/clients
  - api_keys: API authentication tokens
  - sessions: Gait analysis sessions
  - uploads: Video file uploads
  - profiles: Completed gait analysis profiles
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    """API user/client."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Integer, default=1, nullable=False)  # SQLite compat: bool as int
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("email", name="uq_user_email"),
        UniqueConstraint("username", name="uq_user_username"),
    )


class APIKey(Base):
    """API authentication key for a user."""

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key_hash = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    is_active = Column(Integer, default=1, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="api_keys")

    __table_args__ = (
        UniqueConstraint("key_hash", name="uq_apikey_hash"),
    )


class Session(Base):
    """Gait analysis session."""

    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, index=True)  # UUID
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    patient_id = Column(String(255), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="CREATED")  # CREATED, UPLOADING, QUEUED, PROCESSING, COMPLETED, FAILED
    trial_condition = Column(String(20), nullable=False, default="barefoot")  # "barefoot" or "shod"
    linked_session_id = Column(String(36), nullable=True, index=True)  # paired barefoot/shod session
    task_id = Column(String(255), nullable=True, index=True)  # Celery task ID
    error_message = Column(Text, nullable=True)
    progress_pct = Column(Integer, nullable=True)
    anthropometrics = Column(JSON, nullable=False)  # Stored as JSON
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    user = relationship("User", back_populates="sessions")
    uploads = relationship("Upload", back_populates="session", cascade="all, delete-orphan")
    profile = relationship("Profile", back_populates="session", uselist=False, cascade="all, delete-orphan")


class Upload(Base):
    """Video file upload for a session."""

    __tablename__ = "uploads"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    camera_view = Column(String(50), nullable=False)  # sagittal, posterior, etc.
    file_path = Column(String(511), nullable=False)  # S3 path or local path
    size_bytes = Column(Integer, nullable=False)
    upload_status = Column(String(50), nullable=False, default="PENDING")  # PENDING, UPLOADED, PROCESSING, PROCESSED, FAILED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    session = relationship("Session", back_populates="uploads")


class Profile(Base):
    """Completed gait analysis profile."""

    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, unique=True)
    patient_id = Column(String(255), nullable=False, index=True)
    schema_version = Column(String(20), nullable=False, default="profile/v1")
    profile_data = Column(JSON, nullable=False)  # Full profile JSON
    quality_flag = Column(String(50), nullable=False)  # PROCEED_OK, PROCEED_WITH_WARNING, RERECORD
    needs_human_review = Column(Integer, default=0, nullable=False)  # bool as int
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    session = relationship("Session", back_populates="profile")


# ============================================================================
# Database Engine & Session Factory
# ============================================================================


def create_database_url(
    db_user: str,
    db_password: str,
    db_host: str,
    db_port: int,
    db_name: str,
    driver: str = "postgresql",
) -> str:
    """Create a database URL from components.

    Args:
        db_user: Database username
        db_password: Database password
        db_host: Database host
        db_port: Database port
        db_name: Database name
        driver: Database driver (postgresql, sqlite)

    Returns:
        SQLAlchemy database URL string
    """
    if driver == "sqlite":
        return f"sqlite:///{db_name}"
    if driver == "postgresql":
        return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    raise ValueError(f"Unsupported database driver: {driver}")


def init_db(database_url: str) -> None:
    """Initialize database tables.

    Args:
        database_url: SQLAlchemy database URL
    """
    engine = create_engine(database_url, echo=False)
    Base.metadata.create_all(bind=engine)
    engine.dispose()
