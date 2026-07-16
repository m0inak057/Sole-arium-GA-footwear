"""Session state store.

`RedisSessionStore` is the production-facing implementation: it persists
`SessionState` as JSON in Redis (DB 2 — DB 0 is the Celery broker, DB 1 is
the Celery result backend) so session data survives API process restarts
and is shared across replicas. It degrades to an in-memory dict, per
operation, if Redis is temporarily unreachable.

`InMemorySessionStore` is kept as a fallback/test implementation — it has
no persistence and is what `RedisSessionStore` falls back to internally,
and what tests use via `app.dependency_overrides` to avoid a live Redis
dependency.

Both classes implement the same public interface (method names, signatures,
and return types), so call sites never need to know which one they're
holding.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse, urlunparse

import redis

from gait.api.models import SessionStatus, TrialConditionEnum
from gait.common.logging_utils import get_logger

logger = get_logger(__name__)

SESSION_TTL_SECONDS = 86400  # same as the Celery result TTL
SESSION_KEY_PREFIX = "session:"


@dataclass
class SessionState:
    """All mutable state for one analysis session."""

    session_id: str
    patient_id: str
    status: SessionStatus
    anthropometrics: Dict[str, Any]
    created_at: datetime
    trial_condition: TrialConditionEnum = TrialConditionEnum.BAREFOOT
    linked_session_id: Optional[str] = None
    task_id: Optional[str] = None
    error_message: Optional[str] = None
    profile: Optional[Dict[str, Any]] = None
    uploaded_files: List[str] = field(default_factory=list)
    progress_pct: Optional[float] = None


def _serialize_state(state: SessionState) -> str:
    """Serialize a SessionState to a JSON string.

    datetimes become ISO strings, enums become their `.value`, and Optional
    fields are emitted as `null` (never omitted) so deserialization is total.
    """
    return json.dumps(
        {
            "session_id": state.session_id,
            "patient_id": state.patient_id,
            "status": state.status.value,
            "anthropometrics": state.anthropometrics,
            "created_at": state.created_at.isoformat(),
            "trial_condition": state.trial_condition.value,
            "linked_session_id": state.linked_session_id,
            "task_id": state.task_id,
            "error_message": state.error_message,
            "profile": state.profile,
            "uploaded_files": state.uploaded_files,
            "progress_pct": state.progress_pct,
        }
    )


def _deserialize_state(raw: str) -> SessionState:
    """Inverse of `_serialize_state`."""
    d = json.loads(raw)
    return SessionState(
        session_id=d["session_id"],
        patient_id=d["patient_id"],
        status=SessionStatus(d["status"]),
        anthropometrics=d["anthropometrics"],
        created_at=datetime.fromisoformat(d["created_at"]),
        trial_condition=TrialConditionEnum(d["trial_condition"]),
        linked_session_id=d.get("linked_session_id"),
        task_id=d.get("task_id"),
        error_message=d.get("error_message"),
        profile=d.get("profile"),
        uploaded_files=d.get("uploaded_files", []),
        progress_pct=d.get("progress_pct"),
    )


class InMemorySessionStore:
    """Thread-safe, in-memory session store.

    No persistence — state is lost on process restart and isn't shared
    across replicas. Used as `RedisSessionStore`'s per-operation fallback
    when Redis is unreachable, and directly by tests.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionState] = {}
        self._lock = threading.Lock()

    # ── write ──────────────────────────────────────────────────────────────

    def create(
        self,
        patient_id: str,
        anthropometrics: Dict[str, Any],
        trial_condition: TrialConditionEnum = TrialConditionEnum.BAREFOOT,
        linked_session_id: Optional[str] = None,
    ) -> SessionState:
        """Create a new session and return its initial state."""
        session_id = str(uuid.uuid4())
        state = SessionState(
            session_id=session_id,
            patient_id=patient_id,
            status=SessionStatus.CREATED,
            anthropometrics=anthropometrics,
            created_at=datetime.utcnow(),
            trial_condition=trial_condition,
            linked_session_id=linked_session_id,
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

    def has_session(self, session_id: str) -> bool:
        """Return True if the session exists, without materializing it."""
        with self._lock:
            return session_id in self._sessions

    def list_sessions(self) -> List[SessionState]:
        """Return all sessions (snapshot, not live reference)."""
        with self._lock:
            return list(self._sessions.values())


class RedisSessionStore:
    """Redis-backed session store.

    Persists each `SessionState` as a JSON string under key
    `session:{session_id}` in Redis DB 2, with a 24h TTL refreshed on every
    write. Falls back to an in-memory dict, per operation, if Redis raises
    a `redis.RedisError` — the request never crashes because of a Redis
    outage, but any state written during an outage is not shared across
    replicas or process restarts until Redis is available again.
    """

    def __init__(self, redis_client: Optional["redis.Redis"] = None) -> None:
        self._redis = redis_client or self._build_client()
        self._fallback = InMemorySessionStore()

    @staticmethod
    def _build_client() -> "redis.Redis":
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        # `redis.Redis.from_url` keeps the DB number embedded in the URL path
        # and ignores an explicit `db=` kwarg, so the path has to be rewritten
        # to point at DB 2 rather than passed as a separate argument.
        parsed = urlparse(url)
        db_url = urlunparse(parsed._replace(path="/2"))
        return redis.Redis.from_url(
            db_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True,
        )

    @staticmethod
    def _key(session_id: str) -> str:
        return f"{SESSION_KEY_PREFIX}{session_id}"

    @staticmethod
    def _apply_update(
        state: SessionState,
        status: SessionStatus,
        task_id: Optional[str],
        error_message: Optional[str],
        profile: Optional[Dict[str, Any]],
        progress_pct: Optional[float],
    ) -> SessionState:
        state.status = status
        if task_id is not None:
            state.task_id = task_id
        if error_message is not None:
            state.error_message = error_message
        if profile is not None:
            state.profile = profile
        if progress_pct is not None:
            state.progress_pct = progress_pct
        return state

    # ── write ──────────────────────────────────────────────────────────────

    def create(
        self,
        patient_id: str,
        anthropometrics: Dict[str, Any],
        trial_condition: TrialConditionEnum = TrialConditionEnum.BAREFOOT,
        linked_session_id: Optional[str] = None,
    ) -> SessionState:
        """Create a new session and return its initial state."""
        session_id = str(uuid.uuid4())
        state = SessionState(
            session_id=session_id,
            patient_id=patient_id,
            status=SessionStatus.CREATED,
            anthropometrics=anthropometrics,
            created_at=datetime.utcnow(),
            trial_condition=trial_condition,
            linked_session_id=linked_session_id,
        )
        try:
            self._redis.set(self._key(session_id), _serialize_state(state), ex=SESSION_TTL_SECONDS)
        except redis.RedisError as exc:
            logger.warning(
                "redis_session_store.create_fallback",
                extra={"session_id": session_id, "error": str(exc)},
            )
            with self._fallback._lock:
                self._fallback._sessions[session_id] = state
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
        key = self._key(session_id)
        try:
            raw = self._redis.get(key)
            if raw is None:
                return
            state = self._apply_update(
                _deserialize_state(raw), status, task_id, error_message, profile, progress_pct
            )
            self._redis.set(key, _serialize_state(state), ex=SESSION_TTL_SECONDS)
        except redis.RedisError as exc:
            logger.warning(
                "redis_session_store.update_status_fallback",
                extra={"session_id": session_id, "error": str(exc)},
            )
            with self._fallback._lock:
                state = self._fallback._sessions.get(session_id)
                if state is None:
                    return
                self._apply_update(state, status, task_id, error_message, profile, progress_pct)

    def add_uploaded_file(self, session_id: str, file_path: str) -> None:
        """Append a file path to the session's uploaded files list."""
        key = self._key(session_id)
        try:
            raw = self._redis.get(key)
            if raw is None:
                return
            state = _deserialize_state(raw)
            state.uploaded_files.append(file_path)
            self._redis.set(key, _serialize_state(state), ex=SESSION_TTL_SECONDS)
        except redis.RedisError as exc:
            logger.warning(
                "redis_session_store.add_uploaded_file_fallback",
                extra={"session_id": session_id, "error": str(exc)},
            )
            with self._fallback._lock:
                state = self._fallback._sessions.get(session_id)
                if state is not None:
                    state.uploaded_files.append(file_path)

    def delete(self, session_id: str) -> bool:
        """Remove a session; returns True if it existed."""
        deleted = False
        try:
            deleted = bool(self._redis.delete(self._key(session_id)))
        except redis.RedisError as exc:
            logger.warning(
                "redis_session_store.delete_fallback",
                extra={"session_id": session_id, "error": str(exc)},
            )
        with self._fallback._lock:
            deleted = (self._fallback._sessions.pop(session_id, None) is not None) or deleted
        return deleted

    # ── read ───────────────────────────────────────────────────────────────

    def get(self, session_id: str) -> Optional[SessionState]:
        """Return session state or None if not found."""
        try:
            raw = self._redis.get(self._key(session_id))
            if raw is not None:
                return _deserialize_state(raw)
        except redis.RedisError as exc:
            logger.warning(
                "redis_session_store.get_fallback",
                extra={"session_id": session_id, "error": str(exc)},
            )
            return self._fallback.get(session_id)
        return self._fallback.get(session_id)

    def has_session(self, session_id: str) -> bool:
        """Return True if the session exists, without fetching the full state.

        Uses Redis EXISTS rather than GET; falls back to the in-memory dict
        if Redis is unreachable.
        """
        try:
            if bool(self._redis.exists(self._key(session_id))):
                return True
        except redis.RedisError as exc:
            logger.warning(
                "redis_session_store.has_session_fallback",
                extra={"session_id": session_id, "error": str(exc)},
            )
            return self._fallback.has_session(session_id)
        return self._fallback.has_session(session_id)

    def list_sessions(self) -> List[SessionState]:
        """Return all sessions (snapshot, not live reference)."""
        sessions: List[SessionState] = []
        try:
            for key in self._redis.scan_iter(match=f"{SESSION_KEY_PREFIX}*"):
                raw = self._redis.get(key)
                if raw is not None:
                    sessions.append(_deserialize_state(raw))
        except redis.RedisError as exc:
            logger.warning("redis_session_store.list_sessions_fallback", extra={"error": str(exc)})
            return self._fallback.list_sessions()
        return sessions


# ── FastAPI dependency ───────────────────────────────────────────────────────

# `SessionStore` is kept as the public name of the in-memory implementation
# for backward compatibility: existing tests construct it directly via
# `SessionStore()` to get an isolated, non-persistent store per test.
SessionStore = InMemorySessionStore
AnySessionStore = Union[InMemorySessionStore, RedisSessionStore]

# Module-level singleton used by the production app.
# Tests override this via app.dependency_overrides.
_default_store: AnySessionStore = RedisSessionStore()


def get_session_store() -> AnySessionStore:
    """FastAPI dependency that returns the active session store."""
    return _default_store
