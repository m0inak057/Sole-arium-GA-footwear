"""MediaPipe Pose detector - wraps mediapipe.tasks.vision.PoseLandmarker for the pipeline."""
from __future__ import annotations

import contextlib
import urllib.request
from pathlib import Path
from typing import Dict, List

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision as mp_vision

from gait.common.interfaces import Frame, Keypoint, KeypointFrame, PoseDetector
from gait.common.logging_utils import get_logger
from gait.pipeline.config import PoseConfig

logger = get_logger(__name__)

_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"

# MediaPipe BlazePose: 33 landmarks, index -> name
_LANDMARK_NAMES: Dict[int, str] = {
    0: "nose",
    1: "left_eye_inner",
    2: "left_eye",
    3: "left_eye_outer",
    4: "right_eye_inner",
    5: "right_eye",
    6: "right_eye_outer",
    7: "left_ear",
    8: "right_ear",
    9: "mouth_left",
    10: "mouth_right",
    11: "left_shoulder",
    12: "right_shoulder",
    13: "left_elbow",
    14: "right_elbow",
    15: "left_wrist",
    16: "right_wrist",
    17: "left_pinky",
    18: "right_pinky",
    19: "left_index",
    20: "right_index",
    21: "left_thumb",
    22: "right_thumb",
    23: "left_hip",
    24: "right_hip",
    25: "left_knee",
    26: "right_knee",
    27: "left_ankle",
    28: "right_ankle",
    29: "left_heel",
    30: "right_heel",
    31: "left_foot_index",
    32: "right_foot_index",
}


class MediaPipePoseDetector(PoseDetector):
    """Thin wrapper around MediaPipe Pose Landmarker Tasks API for sequential video frames.

    Uses the new MediaPipe Tasks API (mediapipe >= 0.10.0). Maintains inter-frame
    tracking state through the Landmarker. batch_detect processes frames in order
    to preserve tracking state and cannot be parallelised.
    """

    def __init__(self, config: PoseConfig) -> None:
        self._config = config

        # Ensure model file exists, download if necessary
        model_path = Path(config.model_path)
        if not model_path.exists():
            self._download_model(model_path)

        # Create PoseLandmarker with Tasks API
        options = mp_vision.PoseLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp_vision.RunningMode.VIDEO,
        )
        self._landmarker = mp_vision.PoseLandmarker.create_from_options(options)
        self._last_timestamp_ms = -1  # Track for monotonic timestamp check

    def _download_model(self, model_path: Path) -> None:
        """Download the pose_landmarker_lite.task model if it does not exist."""
        model_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(
            "pose_model_downloading",
            extra={"model_url": _MODEL_URL, "destination": str(model_path)},
        )
        try:
            urllib.request.urlretrieve(_MODEL_URL, model_path)
            logger.info(
                "pose_model_downloaded",
                extra={"path": str(model_path), "size_bytes": model_path.stat().st_size},
            )
        except Exception as exc:
            logger.error(
                "pose_model_download_failed",
                extra={"error": str(exc)},
            )
            raise

    # ── context manager ────────────────────────────────────────────────────────

    def __enter__(self) -> "MediaPipePoseDetector":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._landmarker.close()

    # ── PoseDetector ABC ───────────────────────────────────────────────────────

    def detect(self, frame: Frame) -> KeypointFrame:
        """Detect pose keypoints in one frame using MediaPipe Tasks API.

        Returns a KeypointFrame with an empty keypoints dict and confidence=0.0
        when MediaPipe finds no pose or all landmarks are below threshold.
        """
        h, w = frame.image.shape[:2]
        rgb = cv2.cvtColor(frame.image, cv2.COLOR_BGR2RGB)

        # Convert to MediaPipe Image format (RGB, uint8)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        # MediaPipe VIDEO mode requires strictly monotonically increasing
        # timestamps per detector instance. Each detector instance is fed only
        # one camera's frames in original temporal order (see
        # PoseEstimator.run), so this should never trigger in normal
        # operation. Kept as a defensive guard: nudge forward by 1ms instead
        # of crashing the task on any out-of-order input.
        current_timestamp_ms = int(frame.timestamp_ms)
        if current_timestamp_ms <= self._last_timestamp_ms:
            corrected_timestamp_ms = self._last_timestamp_ms + 1
            logger.warning(
                "pose_timestamp_nonmonotonic_corrected",
                extra={
                    "last_timestamp_ms": self._last_timestamp_ms,
                    "original_timestamp_ms": current_timestamp_ms,
                    "corrected_timestamp_ms": corrected_timestamp_ms,
                    "camera_view": frame.camera_view,
                },
            )
            current_timestamp_ms = corrected_timestamp_ms

        self._last_timestamp_ms = current_timestamp_ms

        # Detect pose landmarks in video mode (requires timestamp in milliseconds)
        results = self._landmarker.detect_for_video(mp_image, current_timestamp_ms)

        keypoints: Dict[str, Keypoint] = {}
        if results.pose_landmarks:
            # pose_landmarks is a list of Landmark objects; we use the first (and only) pose
            pose = results.pose_landmarks[0]
            for idx, lm in enumerate(pose):
                # presence field indicates confidence in this landmark (0.0 to 1.0)
                if lm.presence < self._config.confidence_threshold:
                    continue
                name = _LANDMARK_NAMES.get(idx, f"landmark_{idx}")
                keypoints[name] = Keypoint(
                    x=float(lm.x * w),
                    y=float(lm.y * h),
                    z=float(lm.z * w) if self._config.use_3d_lifting else None,
                    confidence=float(lm.presence),
                    name=name,
                )

        if not keypoints:
            logger.debug(
                "pose_no_detection",
                extra={"frame_index": frame.frame_index, "camera_view": frame.camera_view},
            )

        frame_confidence = min(kp.confidence for kp in keypoints.values()) if keypoints else 0.0

        return KeypointFrame(
            timestamp_ms=frame.timestamp_ms,
            frame_index=frame.frame_index,
            camera_view=frame.camera_view,
            keypoints=keypoints,
            confidence=frame_confidence,
        )

    def batch_detect(self, frames: List[Frame]) -> List[KeypointFrame]:
        """Run detect sequentially - preserves MediaPipe inter-frame tracking."""
        return [self.detect(f) for f in frames]
