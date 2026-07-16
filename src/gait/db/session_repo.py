"""Session repository â€” database-backed alternative to in-memory SessionStore.

Thread-safe and suitable for multi-instance deployments.
Replaces src.gait.api.session_store.SessionStore for production use.
"""
from __future__ import annotations

MODULE_STATUS = "UNUSED"
# Not imported by the live API: gait.api.main.get_session_store() returns
# RedisSessionStore (gait.api.session_store), not this SQLAlchemy-backed
# SessionRepository. Kept as an alternative persistence strategy for a
# Postgres-of-record deployment. To activate: swap get_session_store() to
# construct SessionRepository(db_session) with an injected SQLAlchemy Session,
# and update main.py's SessionStore type alias accordingly.

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session as SQLSession

from gait.api.models import SessionStatus
from gait.common.logging_utils import get_logger
from gait.db.models import Session, Upload

logger = get_logger(__name__)


class SessionRepository:
    """Database-backed session repository."""

    def __init__(self, db_session: SQLSession) -> None:
        """Initialize with a SQLAlchemy session.

        Args:
            db_session: SQLAlchemy Session object (injected by FastAPI)
        """
        self._db = db_session

    # â”€â”€ Create â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def create(
        self,
        session_id: str,
        user_id: int,
        patient_id: str,
        anthropometrics: Dict[str, Any],
    ) -> Session:
        """Create a new session.

        Args:
            session_id: UUID string
            user_id: Database user ID
            patient_id: Patient identifier
            anthropometrics: Patient measurements dict

        Returns:
            Created Session object
        """
        session = Session(
            id=session_id,
            user_id=user_id,
            patient_id=patient_id,
            status=SessionStatus.CREATED.value,
            anthropometrics=anthropometrics,
        )
        self._db.add(session)
        self._db.commit()
        self._db.refresh(session)
        logger.info("session.created", extra={"session_id": session_id, "user_id": user_id})
        return session

    # â”€â”€ Read â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def get(self, session_id: str) -> Optional[Session]:
        """Get a session by ID.

        Args:
            session_id: Session UUID

        Returns:
            Session object or None if not found
        """
        stmt = select(Session).where(Session.id == session_id)
        return self._db.execute(stmt).scalars().first()

    def get_by_user(self, user_id: int) -> List[Session]:
        """Get all sessions for a user.

        Args:
            user_id: User ID

        Returns:
            List of Session objects
        """
        stmt = select(Session).where(Session.user_id == user_id).order_by(Session.created_at.desc())
        return self._db.execute(stmt).scalars().all()

    def list_sessions(self, user_id: Optional[int] = None) -> List[Session]:
        """List all sessions, optionally filtered by user.

        Args:
            user_id: Optional user ID filter

        Returns:
            List of Session objects
        """
        if user_id:
            return self.get_by_user(user_id)
        stmt = select(Session).order_by(Session.created_at.desc())
        return self._db.execute(stmt).scalars().all()

    # â”€â”€ Update â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def update_status(
        self,
        session_id: str,
        status: SessionStatus,
        *,
        task_id: Optional[str] = None,
        error_message: Optional[str] = None,
        progress_pct: Optional[int] = None,
    ) -> Optional[Session]:
        """Update session status and optional fields.

        Args:
            session_id: Session UUID
            status: New SessionStatus
            task_id: Optional Celery task ID
            error_message: Optional error description
            progress_pct: Optional progress percentage (0-100)

        Returns:
            Updated Session object or None if not found
        """
        session = self.get(session_id)
        if session is None:
            return None

        session.status = status.value
        session.updated_at = datetime.now(timezone.utc)
        if task_id is not None:
            session.task_id = task_id
        if error_message is not None:
            session.error_message = error_message
        if progress_pct is not None:
            if not (0 <= progress_pct <= 100):
                raise ValueError(f"progress_pct must be 0-100, got {progress_pct}")
            session.progress_pct = progress_pct

        self._db.commit()
        self._db.refresh(session)
        logger.info("session.updated", extra={"session_id": session_id, "status": status.value})
        return session

    def add_uploaded_file(self, session_id: str, filename: str, camera_view: str, file_path: str, size_bytes: int) -> Optional[Upload]:
        """Add an uploaded file to a session.

        Args:
            session_id: Session UUID
            filename: Original filename
            camera_view: Camera view (sagittal, posterior, etc.)
            file_path: Storage path (S3 URI or local path)
            size_bytes: File size in bytes

        Returns:
            Created Upload object or None if session not found
        """
        session = self.get(session_id)
        if session is None:
            return None

        upload = Upload(
            session_id=session_id,
            filename=filename,
            camera_view=camera_view,
            file_path=file_path,
            size_bytes=size_bytes,
            upload_status="UPLOADED",
        )
        self._db.add(upload)
        session.status = SessionStatus.UPLOADING.value
        session.updated_at = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(upload)
        logger.info("upload.added", extra={"session_id": session_id, "upload_filename": filename})
        return upload

    def get_uploads(self, session_id: str) -> List[Upload]:
        """Get all uploads for a session.

        Args:
            session_id: Session UUID

        Returns:
            List of Upload objects
        """
        stmt = select(Upload).where(Upload.session_id == session_id).order_by(Upload.created_at)
        return self._db.execute(stmt).scalars().all()

    # â”€â”€ Delete â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def delete(self, session_id: str) -> bool:
        """Delete a session and all associated data.

        Args:
            session_id: Session UUID

        Returns:
            True if deleted, False if not found
        """
        session = self.get(session_id)
        if session is None:
            return False

        self._db.delete(session)
        self._db.commit()
        logger.info("session.deleted", extra={"session_id": session_id})
        return True

    # â”€â”€ Utility â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def can_access(self, session_id: str, user_id: int) -> bool:
        """Check if a user can access a session.

        Args:
            session_id: Session UUID
            user_id: User ID

        Returns:
            True if user owns the session
        """
        stmt = select(Session).where(and_(Session.id == session_id, Session.user_id == user_id))
        return self._db.execute(stmt).scalars().first() is not None

