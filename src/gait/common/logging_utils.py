"""JSON-structured logging utilities for the gait analysis pipeline.

Usage:
    from gait.common.logging_utils import get_logger, log_stage_timing

    logger = get_logger(__name__)
    logger.info("frame dropped", extra={"reason": "low_confidence", "frame_index": 42})

    log_stage_timing(logger, "ingestion", duration_sec=1.4, frame_count=168, dropped_frames=3)

When python-json-logger is installed (it is in pyproject.toml dev deps) every
log record is a single JSON line on stdout â€” easy to ingest by any log
aggregator. Falls back to plain text if the package is missing.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Generator, Optional

try:
    from pythonjsonlogger import jsonlogger  # type: ignore[import]

    _JSON_AVAILABLE = True
except ImportError:  # pragma: no cover
    _JSON_AVAILABLE = False


_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

# Module-level cache so repeated get_logger(__name__) calls return the same
# already-configured logger without adding duplicate handlers.
_configured: set[str] = set()


def get_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """Return a configured logger for `name`.

    If python-json-logger is installed, emits JSON lines.
    Otherwise falls back to plain text with the same format.

    Safe to call multiple times with the same name â€” idempotent.
    """
    logger = logging.getLogger(name)
    if name in _configured:
        return logger

    handler = logging.StreamHandler()
    if _JSON_AVAILABLE:
        formatter = jsonlogger.JsonFormatter(_FORMAT)
    else:
        formatter = logging.Formatter(_FORMAT)

    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    _configured.add(name)
    return logger


def log_stage_timing(
    logger: logging.Logger,
    stage: str,
    duration_sec: float,
    frame_count: int,
    dropped_frames: int,
    *,
    extra: Optional[dict] = None,
) -> None:
    """Emit a structured timing summary for one pipeline stage.

    Fields emitted (always present):
        stage, duration_sec, frame_count, dropped_frames, drop_pct, fps_achieved
    """
    fps_achieved = frame_count / duration_sec if duration_sec > 0.0 else 0.0
    drop_pct = (dropped_frames / frame_count * 100.0) if frame_count > 0 else 0.0

    payload: dict = {
        "stage": stage,
        "duration_sec": round(duration_sec, 3),
        "frame_count": frame_count,
        "dropped_frames": dropped_frames,
        "drop_pct": round(drop_pct, 1),
        "fps_achieved": round(fps_achieved, 1),
    }
    if extra:
        payload.update(extra)

    logger.info("stage_timing", extra=payload)


@contextmanager
def timed_stage(
    logger: logging.Logger,
    stage: str,
    *,
    frame_count: int = 0,
    dropped_frames: int = 0,
) -> Generator[None, None, None]:
    """Context manager that logs stage timing on exit â€” even on exception.

    Usage:
        with timed_stage(logger, "ingestion", frame_count=len(frames)):
            process(frames)
    """
    t0 = time.perf_counter()
    try:
        yield
    finally:
        log_stage_timing(
            logger,
            stage,
            duration_sec=time.perf_counter() - t0,
            frame_count=frame_count,
            dropped_frames=dropped_frames,
        )

