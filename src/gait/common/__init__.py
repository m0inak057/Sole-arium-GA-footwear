"""Shared utilities, types, and constants for the gait analysis pipeline."""

from gait.common.types import (
    CameraCalibration,
    CalibrationLoadError,
    FrameSyncError,
    IngestionError,
    IngestionResult,
    PersonTrack,
    SyncedFrameSet,
    TrackingLostError,
    VideoDecodeError,
)
from gait.common.geometry import (
    BBox,
    bbox_area_px2,
    clip_bbox,
    compute_angle_deg,
    compute_iou,
    compute_midpoint,
    expand_bbox,
    frame_index_to_timestamp_ms,
    normalize_vector,
    signed_angle_deg,
)
from gait.common.logging_utils import (
    get_logger,
    log_stage_timing,
    timed_stage,
)

__all__ = [
    # types
    "CameraCalibration",
    "SyncedFrameSet",
    "PersonTrack",
    "IngestionResult",
    # exceptions
    "IngestionError",
    "VideoDecodeError",
    "FrameSyncError",
    "CalibrationLoadError",
    "TrackingLostError",
    # geometry
    "BBox",
    "compute_iou",
    "bbox_area_px2",
    "expand_bbox",
    "clip_bbox",
    "compute_angle_deg",
    "normalize_vector",
    "compute_midpoint",
    "signed_angle_deg",
    "frame_index_to_timestamp_ms",
    # logging
    "get_logger",
    "log_stage_timing",
    "timed_stage",
]

