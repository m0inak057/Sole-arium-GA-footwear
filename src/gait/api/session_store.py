"""In-memory session state store.

Thread-safe via a simple threading.Lock.  For production at scale, swap this
out for a Redis- or PostgreSQL-backed store — the interface is identical.

FastAPI dependency injection lets tests replace the module-level singleton
with a fresh `SessionStore()` instance per test, preventing state leak.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.gait.api.models import SessionStatus


@dataclass
class SessionState:
    """All mutable state for one analysis session."""

    session_id: str
    patient_id: str
    status: SessionStatus
    anthropometrics: Dict[str, Any]
    created_at: datetime
    task_id: Optional[str] = None
    error_message: Optional[str] = None
    profile: Optional[Dict[str, Any]] = None
    uploaded_files: List[str] = field(default_factory=list)
    progress_pct: Optional[float] = None


class SessionStore:
    """Thread-safe, in-memory session store.

    All public methods are safe to call from multiple FastAPI async handlers
    because the GIL protects dict operations and we additionally hold a lock
    for read-modify-write sequences.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionState] = {}
        self._lock = threading.Lock()

    # ── write ──────────────────────────────────────────────────────────────

    def create(
        self,
        patient_id: str,
        anthropometrics: Dict[str, Any],
    ) -> SessionState:
        """Create a new session and return its initial state."""
        session_id = str(uuid.uuid4())
        state = SessionState(
            session_id=session_id,
            patient_id=patient_id,
            status=SessionStatus.CREATED,
            anthropometrics=anthropometrics,
            created_at=datetime.utcnow(),
        )
        with self._lock:
            self._sessions[session_id] = state
        return state

    def update_status(
        self,
        session_id: str,
        status: SessionStatus,
        *,
        task_id: Optional[str] = None,
        error_message: Optional[str] = None,
        profile: Optional[Dict[str, Any]] = None,
        progress_pct: Optional[float] = None,
    ) -> None:
        """Update mutable fields on an existing session.

        Only non-None keyword arguments overwrite the current values.
        """
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return
            state.status = status
            if task_id is not None:
                state.task_id = task_id
            if error_message is not None:
                state.error_message = error_message
            if profile is not None:
                state.profile = profile
            if progress_pct is not None:
                state.progress_pct = progress_pct

    def add_uploaded_file(self, session_id: str, file_path: str) -> None:
        """Append a file path to the session's uploaded files list."""
        with self._lock:
            state = self._sessions.get(session_id)
            if state is not None:
                state.uploaded_files.append(file_path)

    def delete(self, session_id: str) -> bool:
        """Remove a session; returns True if it existed."""
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    # ── read ───────────────────────────────────────────────────────────────

    def get(self, session_id: str) -> Optional[SessionState]:
        """Return session state or None if not found."""
        return self._sessions.get(session_id)

    def list_sessions(self) -> List[SessionState]:
        """Return all sessions (snapshot, not live reference)."""
        with self._lock:
            return list(self._sessions.values())


# ── FastAPI dependency ────────────────────────────────────────────────────────

# Module-level singleton used by the production app.
# Tests override this via app.dependency_overrides.
_default_store = SessionStore()


def get_session_store() -> SessionStore:
    """FastAPI dependency that returns the active session store."""
    return _default_store
