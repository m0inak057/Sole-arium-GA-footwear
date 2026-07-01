"""PoseEstimator â€” orchestrates detector + 1-Euro smoother for a session."""
from __future__ import annotations

import time
from typing import List

from gait.common.interfaces import Frame, KeypointFrame, PoseDetector
from gait.common.logging_utils import get_logger, log_stage_timing
from gait.pipeline.config import PoseConfig
from gait.pose.mediapipe_detector import MediaPipePoseDetector
from gait.pose.smoother import OneEuroSmoother

logger = get_logger(__name__)


def create_pose_detector(config: PoseConfig) -> MediaPipePoseDetector:
    """Return the pose detector requested by config.model."""
    if config.model.lower() == "mediapipe":
        return MediaPipePoseDetector(config)
    raise ValueError(
        f"Unknown pose model: {config.model!r}. Supported: 'mediapipe'"
    )


class PoseEstimator:
    """Run pose detection and 1-Euro smoothing on a sequence of frames.

    Usage:
        estimator = PoseEstimator(config, fps=120.0)
        keypoint_frames = estimator.run(frames)
    """

    def __init__(self, config: PoseConfig, fps: float = 120.0) -> None:
        self._config = config
        self._smoother = OneEuroSmoother(fps=fps, smoothing_window=config.smoothing_window)

    def run(self, frames: List[Frame]) -> List[KeypointFrame]:
        """Detect and smooth keypoints for all frames.

        Frames where MediaPipe finds no pose are dropped (logged as WARNING).
        Returns smoothed KeypointFrame objects in input order.
        """
        if not frames:
            return []

        t0 = time.perf_counter()

        # â”€â”€ Detection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        raw: List[KeypointFrame] = []
        dropped = 0
        batch_size = self._config.batch_size

        with create_pose_detector(self._config) as detector:
            for start in range(0, len(frames), batch_size):
                batch = frames[start : start + batch_size]
                for kf in detector.batch_detect(batch):
                    if kf.keypoints:
                        raw.append(kf)
                    else:
                        dropped += 1
                        logger.warning(
                            "pose_frame_dropped",
                            extra={
                                "frame_index": kf.frame_index,
                                "camera_view": kf.camera_view,
                            },
                        )

        logger.info(
            "pose_detection_complete",
            extra={
                "total_frames": len(frames),
                "detected_frames": len(raw),
                "dropped_frames": dropped,
            },
        )

        # â”€â”€ Smoothing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        smoothed = self._smoother.smooth_frame(raw)

        log_stage_timing(
            logger,
            "pose_estimation",
            duration_sec=time.perf_counter() - t0,
            frame_count=len(smoothed),
            dropped_frames=dropped,
        )

        return smoothed

