"""Celery application and background task definitions.

The Celery worker is launched via:
    celery -A src.gait.api.tasks worker --loglevel=info --concurrency=4

The broker and result backend URLs are read from environment variables so that
docker-compose and local dev can use different Redis instances without touching
source code.
"""
from __future__ import annotations

import json
import os
import uuid as uuid_lib
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()
from pathlib import Path
from typing import Any, Dict, Optional

from celery import Celery
from celery.utils.log import get_task_logger

from gait.common.logging_utils import get_logger
from gait.common.types import IngestionError, InsufficientGaitDataError, TrackingLostError
from gait.pipeline.config import load_pipeline_config
from gait.pipeline.orchestrator import GaitPipeline
from gait.privacy.face_blur import blur_all_session_videos_detailed

logger = get_logger(__name__)
task_logger = get_task_logger(__name__)


def _persist_profile_to_db(
    session_id: str,
    patient_id: str,
    session_timestamp: str,
    profile: Dict[str, Any],
    video_paths: Optional[Dict[str, str]] = None,
) -> None:
    """Persist the completed profile to Postgres (gait.sessions / gait.profiles).

    Best-effort: the profile is already returned to the caller via the Celery
    result backend, so a DB failure here must not fail the task â€” it is
    logged at ERROR level with the full exception instead.
    """
    import psycopg2

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        task_logger.error(
            "db.persist_skipped",
            extra={"session_id": session_id, "reason": "DATABASE_URL not set"},
        )
        return

    # gait.patients/gait.sessions use UUID primary keys, but patient_id here
    # is an app-generated string (e.g. "patient_1783849080912"). Derive a
    # stable UUID so repeated sessions for the same patient_id map to the
    # same gait.patients row.
    patient_uuid = str(uuid_lib.uuid5(uuid_lib.NAMESPACE_DNS, patient_id))
    quality_metrics = profile.get("quality_metrics") or {}
    confidence_scores = profile.get("confidence_scores")
    confidence_score = (
        confidence_scores.get("pipeline")
        if isinstance(confidence_scores, dict)
        else None
    )
    schema_version = profile.get("schema_version", "v1")

    conn = None
    try:
        conn = psycopg2.connect(database_url)
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO gait.patients (id, name)
                    VALUES (%s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (patient_uuid, patient_id),
                )
                cur.execute(
                    """
                    INSERT INTO gait.sessions (id, patient_id, session_timestamp, status)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        status = EXCLUDED.status,
                        updated_at = NOW()
                    """,
                    (session_id, patient_uuid, session_timestamp, "complete"),
                )
                cur.execute(
                    """
                    INSERT INTO gait.profiles
                        (session_id, schema_version, profile_json, confidence_score, quality_flags, processed_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (session_id) DO UPDATE SET
                        schema_version = EXCLUDED.schema_version,
                        profile_json = EXCLUDED.profile_json,
                        confidence_score = EXCLUDED.confidence_score,
                        quality_flags = EXCLUDED.quality_flags,
                        processed_at = NOW(),
                        updated_at = NOW()
                    """,
                    (
                        session_id,
                        schema_version,
                        json.dumps(profile),
                        confidence_score,
                        json.dumps(quality_metrics),
                    ),
                )
                # Record where each camera's video lives (local disk is the
                # primary copy; minio_path is where the upload endpoint
                # mirrors it) so storage location is queryable from the DB.
                for camera_view, local_path in (video_paths or {}).items():
                    filename = Path(local_path).name
                    minio_path = f"{session_id}/{camera_view}/{filename}"
                    cur.execute(
                        """
                        INSERT INTO gait.videos
                            (session_id, camera_view, filename, file_path, minio_path, upload_complete)
                        VALUES (%s, %s, %s, %s, %s, TRUE)
                        """,
                        (session_id, camera_view, filename, str(local_path), minio_path),
                    )
        task_logger.info("db.profile_persisted", extra={"session_id": session_id})
    except Exception as exc:
        task_logger.error(
            "db.persist_failed",
            extra={"session_id": session_id, "error": str(exc)},
            exc_info=True,
        )
    finally:
        if conn is not None:
            conn.close()

# â”€â”€ Celery application â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

celery_app = Celery(
    "gait_analysis",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,  # 24 hours
)


# â”€â”€ Pipeline task â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@celery_app.task(
    bind=True,
    name="gait.tasks.run_pipeline",
    max_retries=1,
    soft_time_limit=300,  # 5 minutes
    time_limit=360,
)
def run_gait_pipeline(
    self,
    session_id: str,
    video_paths: Dict[str, str],  # camera_name â†’ str path (JSON-serialisable)
    anthropometrics: Dict[str, Any],
    patient_id: str,
    session_timestamp: Optional[str] = None,
    config_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the full gait analysis pipeline for one session.

    Returns:
        {"status": "COMPLETED", "profile": {...}}  on success
        (on failure, Celery stores the exception in the result backend)
    """
    if session_timestamp is None:
        session_timestamp = datetime.now(timezone.utc).isoformat()

    task_logger.info(
        "task.start",
        extra={"session_id": session_id, "patient_id": patient_id},
    )

    try:
        self.update_state(
            state="PROGRESS",
            meta={"progress_pct": 5, "stage": "initialising"},
        )

        config = load_pipeline_config()

        self.update_state(
            state="PROGRESS",
            meta={"progress_pct": 10, "stage": "ingestion"},
        )

        pipeline = GaitPipeline(config)
        profile = pipeline.run(
            video_paths={k: Path(v) for k, v in video_paths.items()},
            anthropometrics=anthropometrics,
            patient_id=patient_id,
            session_timestamp=session_timestamp,
        )

        # â”€â”€ Face blurring (DPDP Act 2023 compliance) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Runs AFTER profile.json is written, BEFORE videos are stored in MinIO.
        # Controlled by features.face_blur_pipeline in pipeline.yaml.
        face_blur_applied = False
        face_blur_partial = False
        if config.features.face_blur_pipeline:
            self.update_state(
                state="PROGRESS",
                meta={"progress_pct": 90, "stage": "face_blur"},
            )
            try:
                import tempfile

                blur_output_dir = os.path.join(
                    tempfile.gettempdir(), "gait_blurred", session_id
                )
                blur_results = blur_all_session_videos_detailed(
                    session_video_paths=video_paths,
                    output_dir=blur_output_dir,
                )
                # face_blur_applied reflects whether processing actually ran
                # successfully on at least one camera â€” NOT whether a face
                # happened to be visible in that footage. A camera that ran
                # cleanly but found no face (e.g. sagittal/posterior views)
                # is a success; a camera whose detector/video I/O crashed is not.
                successes = [r["success"] for r in blur_results.values()]
                face_blur_applied = any(successes)
                face_blur_partial = any(successes) and not all(successes)
                task_logger.info(
                    "task.face_blur_complete",
                    extra={
                        "session_id": session_id,
                        "face_blur_applied": face_blur_applied,
                        "face_blur_partial": face_blur_partial,
                        "per_camera": blur_results,
                    },
                )
            except Exception as blur_exc:
                # Blur failure is logged but does NOT fail the pipeline task.
                task_logger.warning(
                    "task.face_blur_failed",
                    extra={"session_id": session_id, "error": str(blur_exc)},
                )

        # Stamp face_blur_applied into the profile so it reaches the consumer.
        profile["face_blur_applied"] = face_blur_applied
        profile["face_blur_partial"] = face_blur_partial

        _persist_profile_to_db(session_id, patient_id, session_timestamp, profile, video_paths)

        task_logger.info("task.complete", extra={"session_id": session_id})
        return {"status": "COMPLETED", "profile": profile}

    except InsufficientGaitDataError as exc:
        # Zero gait cycles detected — not a worker crash, a data-quality failure.
        # Return a structured RERECORD payload so the frontend can show a clear
        # "please re-record" message instead of a generic error screen.
        task_logger.warning(
            "task.insufficient_gait_data",
            extra={
                "session_id": session_id,
                "foot": exc.foot,
                "cycle_count": exc.cycle_count,
            },
        )
        return {
            "status": "RERECORD",
            "reason": str(exc),
            "foot": exc.foot,
        }

    except (TrackingLostError, IngestionError) as exc:
        # Ingestion-stage data-quality failures (person left frame, sync issues,
        # decode failures, etc.) — prompt re-record rather than crashing the task.
        task_logger.warning(
            "task.ingestion_rerecord",
            extra={
                "session_id": session_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        return {
            "status": "RERECORD",
            "reason": (
                f"{str(exc)} "
                "Please ensure the subject walks continuously through the camera "
                "frame for at least 10 seconds."
            ),
        }

    except Exception as exc:
        task_logger.error(
            "task.failed",
            extra={"session_id": session_id, "error": str(exc)},
            exc_info=True,
        )
        raise

