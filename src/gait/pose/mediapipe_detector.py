"""MediaPipe Pose detector — wraps mp.solutions.pose for the pipeline."""
from __future__ import annotations

import contextlib
from typing import Dict, List

import cv2
import mediapipe as mp

from src.gait.common.interfaces import Frame, Keypoint, KeypointFrame, PoseDetector
from src.gait.common.logging_utils import get_logger
from src.gait.pipeline.config import PoseConfig

logger = get_logger(__name__)

# MediaPipe BlazePose: 33 landmarks, index → name
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
    """Thin wrapper around MediaPipe Pose for sequential video frames.

    Keeps MediaPipe in video mode (static_image_mode=False) so it can
    maintain inter-frame tracking state. Consequently, batch_detect must
    process frames in order and cannot be parallelised.
    """

    def __init__(self, config: PoseConfig) -> None:
        self._config = config
        self._pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=config.confidence_threshold,
            min_tracking_confidence=config.confidence_threshold,
        )

    # ── context manager ───────────────────────────────────────────────────

    def __enter__(self) -> "MediaPipePoseDetector":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._pose.close()

    # ── PoseDetector ABC ──────────────────────────────────────────────────

    def detect(self, frame: Frame) -> KeypointFrame:
        """Detect pose keypoints in one frame.

        Returns a KeypointFrame with an empty keypoints dict and confidence=0.0
        when MediaPipe finds no pose or all landmarks are below threshold.
        """
        h, w = frame.image.shape[:2]
        rgb = cv2.cvtColor(frame.image, cv2.COLOR_BGR2RGB)
        results = self._pose.process(rgb)

        keypoints: Dict[str, Keypoint] = {}
        if results.pose_landmarks:
            for idx, lm in enumerate(results.pose_landmarks.landmark):
                if lm.visibility < self._config.confidence_threshold:
                    continue
                name = _LANDMARK_NAMES.get(idx, f"landmark_{idx}")
                keypoints[name] = Keypoint(
                    x=float(lm.x * w),
                    y=float(lm.y * h),
                    z=float(lm.z * w) if self._config.use_3d_lifting else None,
                    confidence=float(lm.visibility),
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
        """Run detect sequentially — preserves MediaPipe inter-frame tracking."""
        return [self.detect(f) for f in frames]
