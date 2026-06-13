"""Celery application and background task definitions.

The Celery worker is launched via:
    celery -A src.gait.api.tasks worker --loglevel=info --concurrency=4

The broker and result backend URLs are read from environment variables so that
docker-compose and local dev can use different Redis instances without touching
source code.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from celery import Celery
from celery.utils.log import get_task_logger

from src.gait.common.logging_utils import get_logger

logger = get_logger(__name__)
task_logger = get_task_logger(__name__)

# ── Celery application ────────────────────────────────────────────────────────

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


# ── Pipeline task ─────────────────────────────────────────────────────────────


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
    video_paths: Dict[str, str],  # camera_name → str path (JSON-serialisable)
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

        from src.gait.pipeline.config import load_pipeline_config
        from src.gait.pipeline.orchestrator import GaitPipeline

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

        task_logger.info("task.complete", extra={"session_id": session_id})
        return {"status": "COMPLETED", "profile": profile}

    except Exception as exc:
        task_logger.error(
            "task.failed",
            extra={"session_id": session_id, "error": str(exc)},
            exc_info=True,
        )
        raise
