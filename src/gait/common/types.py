"""Ingestion-stage data transfer objects and typed exceptions.

DTOs crossing stage boundaries use these types so every handoff is
statically verifiable. Exceptions form a typed hierarchy so callers can
catch at the right granularity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import numpy as np

if TYPE_CHECKING:
    from src.gait.common.interfaces import Frame, Keypoint


class TrialCondition(str, Enum):
    """Footwear condition under which a gait trial was captured."""

    BAREFOOT = "barefoot"
    SHOD = "shod"


# ── DTOs ──────────────────────────────────────────────────────────────────────


@dataclass
class CameraCalibration:
    """Intrinsic calibration data for a single camera.

    Remap maps (map1, map2) are precomputed once at startup via
    cv2.initUndistortRectifyMap() and stored here for fast per-frame
    cv2.remap() calls. When maps are None the camera is uncalibrated
    and frames pass through unchanged.
    """

    camera_name: str
    camera_matrix: np.ndarray       # shape (3, 3), float64
    dist_coeffs: np.ndarray         # shape (1, N) where N ∈ {4, 5, 8}, float64
    image_size: Tuple[int, int]     # (width, height) in pixels

    # Precomputed — set by CameraCalibrator.__init__, None until then
    map1: Optional[np.ndarray] = field(default=None, repr=False)  # float32
    map2: Optional[np.ndarray] = field(default=None, repr=False)  # float32

    @property
    def is_calibrated(self) -> bool:
        """True when remap maps are ready; False → passthrough mode."""
        return self.map1 is not None and self.map2 is not None


@dataclass
class SyncedFrameSet:
    """Time-aligned frames from all active cameras at one instant.

    anchor_timestamp_ms is the reference timestamp (taken from the first
    camera in alphabetical order). All frames in the set are within
    IngestionConfig.sync_tolerance_ms of this anchor.
    """

    anchor_timestamp_ms: int
    frames: Dict[str, "Frame"]     # camera_name → Frame


@dataclass
class PersonTrack:
    """Subject bounding-box for a single frame from the tracker.

    confidence is reduced proportionally when the tracker returns a
    last-known bbox after the subject was momentarily lost — stale tracks
    never carry full 1.0 confidence.
    """

    track_id: int
    bbox: Tuple[int, int, int, int]   # (x, y, w, h) in pixels
    confidence: float                  # 0.0–1.0
    frames_since_update: int = 0       # 0 = fresh detection


@dataclass
class IngestionResult:
    """Output of the full ingestion preprocessing stage.

    frames is the ordered sequence of preprocessed Frame objects passed to
    the pose estimation stage. Every Frame.image is a new ndarray
    (np.copy was called) — safe to mutate downstream.
    """

    frames: List["Frame"]
    total_input_frames: int
    dropped_frames: int
    processing_time_sec: float
    camera_views: List[str]           # which cameras contributed frames


@dataclass
class StaticTrial:
    """Calibration artefact produced from a ~3-second quiet-standing capture.

    `keypoints` holds the time-averaged position of every detected keypoint
    during the standing trial.  `joint_angle_offsets` maps anatomical joint
    labels (e.g. ``"left_ankle_deg"``) to the baseline angle measured in that
    posture; these offsets are subtracted from dynamic measurements so that
    joint angles are expressed relative to the subject's own anatomical zero.
    """

    session_id: str
    duration_frames: int
    keypoints: Dict[str, "Keypoint"]       # averaged standing posture
    joint_angle_offsets: Dict[str, float]  # anatomical zero references


# ── Typed exception hierarchy ─────────────────────────────────────────────────


class IngestionError(RuntimeError):
    """Base for all ingestion-stage failures.

    Catch this to handle any ingestion problem; catch subclasses for
    specific recovery strategies.
    """


class VideoDecodeError(IngestionError):
    """Video file cannot be opened, or consecutive decode failures exceeded
    IngestionConfig.max_consecutive_decode_failure_pct.
    """


class FrameSyncError(IngestionError):
    """Multi-camera frame alignment persistently fails.

    Raised when the number of consecutive un-syncable frame windows exceeds
    IngestionConfig.max_unsync_frames_before_error.
    """


class CalibrationLoadError(IngestionError):
    """A calibration YAML file exists but is structurally malformed.

    A *missing* calibration file is NOT this error — missing → WARNING and
    the pipeline continues in uncalibrated (passthrough) mode. Only raise
    this when the file is present but unreadable or structurally wrong.
    """


class TrackingLostError(IngestionError):
    """Subject tracker lost the person for more than
    IngestionConfig.max_lost_frames consecutive frames without recovery.
    """
