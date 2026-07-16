"""PoseEstimator â€” orchestrates detector + 1-Euro smoother for a session."""
from __future__ import annotations

import time
from typing import Dict, List

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

        Frames are grouped by camera_view and processed independently: MediaPipe
        VIDEO mode requires strictly increasing timestamps per detector instance,
        and the 1-Euro smoother keys trajectories by frame_index (which collides
        across cameras that each start their own frame_index at 0). Interleaving
        unrelated camera angles into a single temporal sequence would also corrupt
        MediaPipe's internal pose tracking between frames. Frames where MediaPipe
        finds no pose are dropped (logged as WARNING).
        """
        if not frames:
            return []

        t0 = time.perf_counter()

        frames_by_camera: Dict[str, List[Frame]] = {}
        for f in frames:
            frames_by_camera.setdefault(f.camera_view, []).append(f)

        dropped = 0
        batch_size = self._config.batch_size
        smoothed: List[KeypointFrame] = []

        for camera_view in sorted(frames_by_camera):
            camera_frames = frames_by_camera[camera_view]

            # â”€â”€ Detection (one detector instance per camera) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            raw: List[KeypointFrame] = []
            with create_pose_detector(self._config) as detector:
                for start in range(0, len(camera_frames), batch_size):
                    batch = camera_frames[start : start + batch_size]
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

            # â”€â”€ Smoothing (per camera, avoids cross-camera frame_index collisions) â”€â”€
            smoothed.extend(self._smoother.smooth_frame(raw))

        logger.info(
            "pose_detection_complete",
            extra={
                "total_frames": len(frames),
                "detected_frames": len(smoothed),
                "dropped_frames": dropped,
            },
        )

        log_stage_timing(
            logger,
            "pose_estimation",
            duration_sec=time.perf_counter() - t0,
            frame_count=len(smoothed),
            dropped_frames=dropped,
        )

        return smoothed

