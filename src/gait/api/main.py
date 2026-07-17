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
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urlunparse

import redis
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from minio import Minio
from minio.error import S3Error

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

# ── auth ─────────────────────────────────────────────────────────────────────

_raw_api_keys = os.getenv("GAIT_API_KEYS", "")
API_KEYS: Optional[set] = (
    {key.strip() for key in _raw_api_keys.split(",") if key.strip()} if _raw_api_keys else None
)
if API_KEYS is None:
    logger.warning("auth_disabled", extra={"reason": "GAIT_API_KEYS not set; all requests allowed"})


def check_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> None:
    """Dependency guarding every session/patient-data endpoint.

    No-op when GAIT_API_KEYS is unset (development mode). When set, requires
    the X-API-Key header to match one of the configured keys.
    """
    if API_KEYS is None:
        return
    if x_api_key is None or x_api_key not in API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


# ── MinIO video storage ──────────────────────────────────────────────────────

MINIO_VIDEO_BUCKET = "gait-videos"
_minio_client: Optional[Minio] = None


def _init_minio_client() -> None:
    """Initialize the MinIO client and ensure the video bucket exists.

    Best-effort: if MinIO is unreachable at startup, log a warning and leave
    _minio_client as None so uploads/fetches degrade to local-disk-only.
    """
    global _minio_client
    endpoint = os.getenv("S3_ENDPOINT", "localhost:9000")
    access_key = os.getenv("S3_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("S3_SECRET_KEY", "minioadmin")
    secure = endpoint.startswith("https://")
    host = endpoint.replace("https://", "").replace("http://", "")

    try:
        client = Minio(host, access_key=access_key, secret_key=secret_key, secure=secure)
        if not client.bucket_exists(MINIO_VIDEO_BUCKET):
            client.make_bucket(MINIO_VIDEO_BUCKET)
        _minio_client = client
        logger.info("minio.ready", extra={"bucket": MINIO_VIDEO_BUCKET, "endpoint": host})
    except Exception as exc:
        logger.warning("minio_unavailable", extra={"endpoint": host, "error": str(exc)})
        _minio_client = None


def _upload_video_to_minio(local_path: Path, object_path: str) -> None:
    """BackgroundTask: mirror an uploaded video to MinIO. Never raises."""
    if _minio_client is None:
        return
    try:
        _minio_client.fput_object(MINIO_VIDEO_BUCKET, object_path, str(local_path))
        logger.info("minio.video_uploaded", extra={"object_path": object_path})
    except Exception as exc:
        logger.warning(
            "minio_upload_failed",
            extra={"object_path": object_path, "error": str(exc)},
        )


# â”€â”€ rate limiting â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#
# A plain Redis INCR+EXPIRE fixed-window counter, not the existing
# gait.rate_limit.TokenBucketLimiter: that limiter's Redis GET returns None on
# a cold key, so `current_tokens` starts at 0 rather than a full bucket â€”
# the very first request in a fresh window is rejected, which contradicts
# "N requests per minute allowed". Fixed-window INCR/EXPIRE has no such
# cold-start bug and maps directly onto "N per minute per IP".
#
# DB 3 is dedicated to rate-limit counters (DB 0=Celery broker, DB 1=Celery
# results, DB 2=sessions).

_rate_limit_redis: Optional["redis.Redis"] = None


def _get_rate_limit_redis() -> Optional["redis.Redis"]:
    """Lazily build the DB-3 Redis client; returns None if unreachable."""
    global _rate_limit_redis
    if _rate_limit_redis is not None:
        return _rate_limit_redis
    try:
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        parsed = urlparse(url)
        db3_url = urlunparse(parsed._replace(path="/3"))
        client = redis.Redis.from_url(db3_url, decode_responses=True, socket_connect_timeout=5)
        client.ping()
        _rate_limit_redis = client
    except redis.RedisError as exc:
        logger.warning("rate_limit_redis_unavailable", extra={"error": str(exc)})
        return None
    return _rate_limit_redis


def _enforce_rate_limit(request: Request, endpoint_name: str, limit: int, window_seconds: int = 60) -> None:
    """Raise 429 if `client_ip` has made more than `limit` requests to
    `endpoint_name` in the current `window_seconds` window. Fails open
    (allows the request) if Redis is unreachable.
    """
    client_ip = request.client.host if request.client else "unknown"
    r = _get_rate_limit_redis()
    if r is None:
        return

    key = f"ratelimit:{endpoint_name}:{client_ip}"
    try:
        count = r.incr(key)
        if count == 1:
            r.expire(key, window_seconds)
    except redis.RedisError as exc:
        logger.warning("rate_limit_check_failed", extra={"endpoint": endpoint_name, "error": str(exc)})
        return

    if count > limit:
        noun = "analysis" if endpoint_name == "process" else "upload"
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {limit} {noun} requests per minute.",
        )


def rate_limit_process(request: Request) -> None:
    _enforce_rate_limit(request, "process", limit=10, window_seconds=60)


def rate_limit_upload(request: Request) -> None:
    _enforce_rate_limit(request, "upload", limit=60, window_seconds=60)


# â”€â”€ FastAPI app â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


@app.on_event("startup")
async def _on_startup() -> None:
    _init_minio_client()


# All session/patient-data endpoints require an API key (when GAIT_API_KEYS is
# set); only /health and /api/v1/ stay open. Registered as a router-level
# dependency so individual endpoint signatures never mention auth.
protected_router = APIRouter(dependencies=[Depends(check_api_key)])


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
            task_status = payload.get("status")

            if task_status == "RERECORD":
                # Insufficient gait cycles — not a crash, a data-quality failure.
                store.update_status(
                    state.session_id,
                    SessionStatus.RERECORD,
                    error_message=payload.get("reason", "Insufficient gait data — please re-record."),
                )
            else:
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


@protected_router.post(
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


@protected_router.post(
    "/api/v1/sessions/{session_id}/uploads",
    response_model=UploadResponse,
    status_code=status.HTTP_200_OK,
    tags=["Sessions"],
    dependencies=[Depends(rate_limit_upload)],
)
async def upload_video(
    session_id: str,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    camera_view: str = Query(default="sagittal", description="Camera view for this file"),
    store: SessionStore = Depends(get_session_store),
) -> UploadResponse:
    """Upload a video file for a session, or the static posterior photo.

    Call once per camera view (anterior, sagittal, posterior). Call once more
    with camera_view="static_posterior" for the single standing posture photo
    used for rearfoot alignment / wedging prescription instead of a video.
    The session must be in CREATED or UPLOADING state.
    """
    state = _require_session(session_id, store)

    if state.status not in (SessionStatus.CREATED, SessionStatus.UPLOADING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot upload to session in {state.status} state.",
        )

    if camera_view == "static_posterior":
        ext = "." + (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="static_posterior must be an image file (.jpg, .jpeg, .png, .webp).",
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

    # Local disk write above is what the request's success depends on; MinIO
    # mirroring happens after the response is sent and never fails the request.
    object_path = f"{session_id}/{camera_view}/{dest_path.name}"
    background_tasks.add_task(_upload_video_to_minio, dest_path, object_path)

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


@protected_router.post(
    "/api/v1/sessions/{session_id}/process",
    response_model=StatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Sessions"],
    dependencies=[Depends(rate_limit_process)],
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


@protected_router.get(
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


@protected_router.get(
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

    if state.status == SessionStatus.RERECORD:
        # Return a 200 with a structured profile payload so the frontend
        # can render a clear "please re-record" state instead of an error.
        return ProfileResponse(
            session_id=session_id,
            patient_id=state.patient_id,
            status=state.status,
            profile={
                "__rerecord__": True,
                "reason": state.error_message or "Insufficient gait data — please re-record.",
            },
        )

    return ProfileResponse(
        session_id=session_id,
        patient_id=state.patient_id,
        status=state.status,
        profile=state.profile,
    )


@protected_router.get(
    "/api/v1/sessions/{session_id}/videos/{camera_view}",
    tags=["Sessions"],
)
async def get_video(
    session_id: str,
    camera_view: str,
    store: SessionStore = Depends(get_session_store),
):
    """Serve an uploaded video file for synchronized browser playback.

    Tries local disk first (supports range requests for seeking); if the
    local file is missing, falls back to MinIO before returning 404.
    """
    _require_session(session_id, store)

    allowed_views = {"anterior", "sagittal", "posterior"}
    if camera_view not in allowed_views:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"camera_view must be one of {sorted(allowed_views)}, got {camera_view!r}",
        )

    video_dir = UPLOAD_DIR / session_id / camera_view
    if video_dir.exists():
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

    # Local disk miss — fall back to MinIO.
    if _minio_client is not None:
        try:
            object_prefix = f"{session_id}/{camera_view}/"
            objects = list(_minio_client.list_objects(MINIO_VIDEO_BUCKET, prefix=object_prefix))
            if objects:
                object_name = objects[0].object_name
                response = _minio_client.get_object(MINIO_VIDEO_BUCKET, object_name)
                media_type, _ = mimetypes.guess_type(object_name)
                return StreamingResponse(
                    response,
                    media_type=media_type or "video/mp4",
                    headers={"Cache-Control": "no-cache"},
                )
        except S3Error as exc:
            logger.warning(
                "minio_video_fetch_failed",
                extra={"session_id": session_id, "camera_view": camera_view, "error": str(exc)},
            )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"No video file found for view {camera_view!r} in session {session_id!r}",
    )


@protected_router.delete(
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


@protected_router.get(
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


app.include_router(protected_router)

