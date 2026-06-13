"""Video preprocessing and ingestion modules.

Phase B+C public surface — import from here, not from sub-modules directly.
"""

from src.gait.ingestion.preprocessor import IngestionPreprocessor
from src.gait.ingestion.calibrate import (
    CameraCalibrator,
    load_camera_calibration,
)
from src.gait.ingestion.decode import VideoFileSource
from src.gait.ingestion.roi import compute_roi_bbox, crop_roi
from src.gait.ingestion.segment_bg import (
    BackgroundSubtractor,
    MOG2BackgroundSubtractor,
    create_background_subtractor,
)
from src.gait.ingestion.sync import align_frames, flatten_synced_frames
from src.gait.ingestion.track import (
    PersonTracker,
    SimpleIoUTracker,
    create_person_tracker,
)

__all__ = [
    # orchestrator
    "IngestionPreprocessor",
    # decode
    "VideoFileSource",
    # sync
    "align_frames",
    "flatten_synced_frames",
    # calibrate
    "load_camera_calibration",
    "CameraCalibrator",
    # segment_bg
    "BackgroundSubtractor",
    "MOG2BackgroundSubtractor",
    "create_background_subtractor",
    # track
    "PersonTracker",
    "SimpleIoUTracker",
    "create_person_tracker",
    # roi
    "compute_roi_bbox",
    "crop_roi",
]
