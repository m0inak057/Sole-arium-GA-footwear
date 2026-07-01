"""FastAPI application â€” Gait Analysis REST API.

Endpoints:
  GET  /health                                 â†’ health check
  GET  /api/v1/                                â†’ API information
  POST /api/v1/sessions                        â†’ create session
  POST /api/v1/sessions/{id}/uploads           â†’ upload video file(s)
  POST /api/v1/sessions/{id}/process           â†’ trigger pipeline
  GET  /api/v1/sessions/{id}/status            â†’ poll job status
  GET  /api/v1/sessions/{id}/profile           â†’ retrieve completed profile
  DELETE /api/v1/sessions/{id}                 â†’ delete session

File uploads are written to {UPLOAD_DIR}/{session_id}/.
UPLOAD_DIR defaults to "data/uploads" (relative to cwd).
"""
from __future__ import annotations

import mimetypes
import os
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()
from pathlib import Path
from typing import Any, Dict

from fastapi import Depends, FastAPI, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from gait.api.models import (
    ComparisonResponse,
    ConditionMetrics,
    HealthResponse,
    ProcessRequest,
    ProfileResponse,
    SessionCreate,
    SessionResponse,
    SessionStatus,
    StatusResponse,
    TrialConditionEnum,
    UploadResponse,
)
from gait.api.session_store import SessionState, SessionStore, get_session_store
from gait.common.logging_utils import get_logger

logger = get_logger(__name__)

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "data/uploads"))

# â”€â”€ FastAPI app â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

app = FastAPI(
    title="Sole-Arium Gait Analysis API",
    description=(
        "Transforms synchronized multi-camera video into structured "
        "orthopedic gait profiles and shoe design recommendations."
    ),
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# â”€â”€ task dependency (injectable for tests) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def get_pipeline_task() -> Any:
    """Return the Celery task object (injectable in tests)."""
    from gait.api.tasks import run_gait_pipeline

    return run_gait_pipeline


# â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _require_session(session_id: str, store: SessionStore) -> SessionState:
    """Raise 404 if session is not found."""
    state = store.get(session_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id!r} not found.",
        )
    return state


def _sync_task_status(state: SessionState, store: SessionStore) -> SessionState:
    """Check the Celery result backend and update session store if task finished.

    Called lazily from the status and profile endpoints so the session store
    always reflects the latest Celery state even when the worker hasn't pushed
    an explicit callback.
    """
    if state.status not in (SessionStatus.QUEUED, SessionStatus.PROCESSING):
        return state
    if not state.task_id:
        return state

    try:
        from gait.api.tasks import celery_app

        result = celery_app.AsyncResult(state.task_id)

        if result.state == "SUCCESS":
            payload = result.result or {}
            profile = payload.get("profile")
            store.update_status(
                state.session_id,
                SessionStatus.COMPLETED,
                profile=profile,
                progress_pct=100.0,
            )
            state = store.get(state.session_id) or state  # refresh

        elif result.state in ("FAILURE", "REVOKED"):
            error = str(result.result) if result.result else "Pipeline failed"
            store.update_status(
                state.session_id,
                SessionStatus.FAILED,
                error_message=error,
            )
            state = store.get(state.session_id) or state

        elif result.state == "STARTED":
            if state.status == SessionStatus.QUEUED:
                store.update_status(state.session_id, SessionStatus.PROCESSING)
                state = store.get(state.session_id) or state

        elif result.state == "PROGRESS":
            meta = result.info or {}
            store.update_status(
                state.session_id,
                SessionStatus.PROCESSING,
                progress_pct=meta.get("progress_pct"),
            )
            state = store.get(state.session_id) or state

    except Exception as exc:  # pragma: no cover
        logger.warning(
            "status_sync.failed",
            extra={"session_id": state.session_id, "error": str(exc)},
        )

    return state


# â”€â”€ comparison helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _extract_condition_metrics(
    session_id: str,
    condition: TrialConditionEnum,
    profile: Dict[str, Any],
) -> ConditionMetrics:
    st = profile.get("spatiotemporal", {})
    pron = profile.get("pronation", {})
    fs = profile.get("foot_strike", {})
    arch = profile.get("arch", {})
    return ConditionMetrics(
        session_id=session_id,
        trial_condition=condition,
        cadence_spm=st.get("cadence_spm"),
        pronation_classification=pron.get("classification"),
        foot_strike_pattern=fs.get("pattern"),
        arch_type=arch.get("type"),
    )


def _build_delta(barefoot: ConditionMetrics, shod: ConditionMetrics) -> Dict[str, Any]:
    """Compute numeric deltas (shod âˆ’ barefoot) and changed flags for classifications."""
    delta: Dict[str, Any] = {}

    # Cadence: numeric delta
    if barefoot.cadence_spm is not None and shod.cadence_spm is not None:
        delta["cadence_spm"] = round(shod.cadence_spm - barefoot.cadence_spm, 3)

    # L/R classification fields: flag which sides changed
    for attr in ("pronation_classification", "foot_strike_pattern", "arch_type"):
        bf_val: Dict[str, Any] = getattr(barefoot, attr) or {}
        sh_val: Dict[str, Any] = getattr(shod, attr) or {}
        delta[attr] = {
            side: {
                "barefoot": bf_val.get(side),
                "shod": sh_val.get(side),
                "changed": bf_val.get(side) != sh_val.get(side),
            }
            for side in ("L", "R")
        }

    return delta


# â”€â”€ endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health() -> HealthResponse:
    """Liveness probe: returns 200 when the API process is alive."""
    return HealthResponse(status="ok", version=app.version, timestamp=datetime.utcnow())


@app.get("/api/v1/", tags=["System"])
async def api_info() -> Dict[str, str]:
    """API root â€” version and documentation links."""
    return {
        "name": "Sole-Arium Gait Analysis API",
        "version": app.version,
        "docs": "/api/docs",
    }


# â”€â”€ sessions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@app.post(
    "/api/v1/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Sessions"],
)
async def create_session(
    body: SessionCreate,
    store: SessionStore = Depends(get_session_store),
) -> SessionResponse:
    """Create a new gait analysis session.

    Returns the `session_id` needed for subsequent upload / process / status calls.
    """
    state = store.create(
        patient_id=body.patient_id,
        anthropometrics=body.anthropometrics.model_dump(),
        trial_condition=body.trial_condition,
        linked_session_id=body.linked_session_id,
    )
    logger.info(
        "session.created",
        extra={
            "session_id": state.session_id,
            "patient_id": body.patient_id,
            "trial_condition": body.trial_condition,
            "linked_session_id": body.linked_session_id,
        },
    )
    return SessionResponse(
        session_id=state.session_id,
        patient_id=state.patient_id,
        status=state.status,
        created_at=state.created_at,
    )


@app.post(
    "/api/v1/sessions/{session_id}/uploads",
    response_model=UploadResponse,
    status_code=status.HTTP_200_OK,
    tags=["Sessions"],
)
async def upload_video(
    session_id: str,
    file: UploadFile,
    camera_view: str = Query(default="sagittal", description="Camera view for this file"),
    store: SessionStore = Depends(get_session_store),
) -> UploadResponse:
    """Upload a video file for a session.

    Call once per camera view (sagittal, posterior, etc.).
    The session must be in CREATED or UPLOADING state.
    """
    state = _require_session(session_id, store)

    if state.status not in (SessionStatus.CREATED, SessionStatus.UPLOADING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot upload to session in {state.status} state.",
        )

    # Save file to disk under a per-camera subfolder so the view can be recovered later
    dest_dir = UPLOAD_DIR / session_id / camera_view
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / (file.filename or "upload.mp4")

    content = await file.read()
    dest_path.write_bytes(content)
    size_bytes = len(content)

    store.add_uploaded_file(session_id, str(dest_path))
    store.update_status(session_id, SessionStatus.UPLOADING)

    logger.info(
        "upload.received",
        extra={
            "session_id": session_id,
            "upload_filename": file.filename,
            "camera_view": camera_view,
            "size_bytes": size_bytes,
        },
    )

    return UploadResponse(
        session_id=session_id,
        filename=file.filename or "upload.mp4",
        size_bytes=size_bytes,
        camera_view=camera_view,
        status=SessionStatus.UPLOADING,
    )


@app.post(
    "/api/v1/sessions/{session_id}/process",
    response_model=StatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Sessions"],
)
async def process_session(
    session_id: str,
    body: ProcessRequest,
    store: SessionStore = Depends(get_session_store),
    pipeline_task: Any = Depends(get_pipeline_task),
) -> StatusResponse:
    """Trigger the gait analysis pipeline for a session.

    The task is dispatched to a Celery worker asynchronously; this endpoint
    returns 202 Accepted immediately.  Poll `/status` to track progress.
    """
    state = _require_session(session_id, store)

    if state.status in (SessionStatus.QUEUED, SessionStatus.PROCESSING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is already {state.status}; processing has been initiated.",
        )
    if state.status == SessionStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Session is already COMPLETED. Create a new session to reprocess.",
        )

    # Build video_paths dict from uploaded files; camera view is the parent folder name
    video_paths: Dict[str, str] = {}
    for fp in state.uploaded_files:
        path = Path(fp)
        video_paths[path.parent.name] = fp

    # Submit task
    task_result = pipeline_task.delay(
        session_id=session_id,
        video_paths=video_paths,
        anthropometrics=state.anthropometrics,
        patient_id=state.patient_id,
        session_timestamp=datetime.utcnow().isoformat(),
        config_overrides=body.config_overrides,
    )

    store.update_status(session_id, SessionStatus.QUEUED, task_id=str(task_result.id))

    logger.info(
        "session.queued",
        extra={
            "session_id": session_id,
            "task_id": str(task_result.id),
            "n_videos": len(video_paths),
        },
    )

    refreshed = store.get(session_id)
    return StatusResponse(
        session_id=session_id,
        patient_id=state.patient_id,
        status=SessionStatus.QUEUED,
        task_id=str(task_result.id),
        uploaded_files=refreshed.uploaded_files if refreshed else [],
    )


@app.get(
    "/api/v1/sessions/{session_id}/status",
    response_model=StatusResponse,
    tags=["Sessions"],
)
async def get_status(
    session_id: str,
    store: SessionStore = Depends(get_session_store),
) -> StatusResponse:
    """Poll the processing status of a session.

    Lazily syncs the session store with the Celery result backend so that
    COMPLETED / FAILED transitions are reflected immediately on the next poll.
    """
    state = _require_session(session_id, store)
    state = _sync_task_status(state, store)

    return StatusResponse(
        session_id=session_id,
        patient_id=state.patient_id,
        status=state.status,
        task_id=state.task_id,
        error_message=state.error_message,
        progress_pct=state.progress_pct,
        uploaded_files=state.uploaded_files,
    )


@app.get(
    "/api/v1/sessions/{session_id}/profile",
    response_model=ProfileResponse,
    tags=["Sessions"],
)
async def get_profile(
    session_id: str,
    store: SessionStore = Depends(get_session_store),
) -> ProfileResponse:
    """Retrieve the completed gait analysis profile.

    Returns 200 with the profile dict when the session is COMPLETED.
    Returns 200 with `profile: null` when still processing.
    """
    state = _require_session(session_id, store)
    state = _sync_task_status(state, store)

    if state.status == SessionStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=state.error_message or "Pipeline processing failed.",
        )

    return ProfileResponse(
        session_id=session_id,
        patient_id=state.patient_id,
        status=state.status,
        profile=state.profile,
    )


@app.get(
    "/api/v1/sessions/{session_id}/videos/{camera_view}",
    tags=["Sessions"],
)
async def get_video(
    session_id: str,
    camera_view: str,
    store: SessionStore = Depends(get_session_store),
) -> FileResponse:
    """Serve an uploaded video file for synchronized browser playback.

    Supports range requests so the browser can seek within the video.
    """
    _require_session(session_id, store)

    allowed_views = {"anterior", "sagittal", "posterior"}
    if camera_view not in allowed_views:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"camera_view must be one of {sorted(allowed_views)}, got {camera_view!r}",
        )

    video_dir = UPLOAD_DIR / session_id / camera_view
    if not video_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No video found for session {session_id!r}, view {camera_view!r}",
        )

    for pattern in ("*.mp4", "*.mov", "*.avi", "*.MP4", "*.MOV", "*.AVI"):
        matches = list(video_dir.glob(pattern))
        if matches:
            video_path = matches[0]
            media_type, _ = mimetypes.guess_type(str(video_path))
            return FileResponse(
                path=video_path,
                media_type=media_type or "video/mp4",
                headers={"Cache-Control": "no-cache"},
            )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"No video file found for view {camera_view!r} in session {session_id!r}",
    )


@app.delete(
    "/api/v1/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Sessions"],
)
async def delete_session(
    session_id: str,
    store: SessionStore = Depends(get_session_store),
) -> None:
    """Delete a session and its associated state (does not delete uploaded files)."""
    state = _require_session(session_id, store)

    if state.status in (SessionStatus.QUEUED, SessionStatus.PROCESSING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a session that is currently being processed.",
        )

    store.delete(session_id)
    logger.info("session.deleted", extra={"session_id": session_id})


@app.get(
    "/api/v1/sessions/{session_id}/comparison",
    response_model=ComparisonResponse,
    tags=["Sessions"],
)
async def get_comparison(
    session_id: str,
    store: SessionStore = Depends(get_session_store),
) -> ComparisonResponse:
    """Return a side-by-side comparison of key gait metrics between the barefoot
    and shod trials linked to this session.

    Requires:
    - The requested session must have ``linked_session_id`` set.
    - Both sessions must be in COMPLETED state with profiles available.
    """
    state = _require_session(session_id, store)
    state = _sync_task_status(state, store)

    if not state.linked_session_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Session has no linked_session_id; pair a barefoot and shod session first.",
        )

    linked_state = store.get(state.linked_session_id)
    if linked_state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Linked session {state.linked_session_id!r} not found.",
        )
    linked_state = _sync_task_status(linked_state, store)

    for s in (state, linked_state):
        if s.status != SessionStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Session {s.session_id!r} is not yet COMPLETED (status: {s.status}).",
            )
        if s.profile is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Session {s.session_id!r} has no profile data.",
            )

    metrics_a = _extract_condition_metrics(
        session_id, state.trial_condition, state.profile  # type: ignore[arg-type]
    )
    metrics_b = _extract_condition_metrics(
        state.linked_session_id,
        linked_state.trial_condition,
        linked_state.profile,  # type: ignore[arg-type]
    )

    # Assign barefoot / shod roles regardless of which session was requested
    if state.trial_condition == TrialConditionEnum.BAREFOOT:
        barefoot, shod = metrics_a, metrics_b
    else:
        barefoot, shod = metrics_b, metrics_a

    logger.info(
        "comparison.served",
        extra={"session_id": session_id, "linked_session_id": state.linked_session_id},
    )
    return ComparisonResponse(
        session_id=session_id,
        linked_session_id=state.linked_session_id,
        barefoot=barefoot,
        shod=shod,
        delta=_build_delta(barefoot, shod),
    )

