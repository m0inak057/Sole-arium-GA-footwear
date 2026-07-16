"""Unit tests for PoseEstimator and create_pose_detector (src.gait.pose.estimator).

The MediaPipe detector is replaced with a FakeDetector so no model inference
runs. The smoother is real â€” its behaviour is covered separately in
test_pose_smoother.py.
"""
from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest

from gait.common.interfaces import Frame, Keypoint, KeypointFrame, PoseDetector
from gait.pipeline.config import PoseConfig
from gait.pose.estimator import PoseEstimator, create_pose_detector
from gait.pose.mediapipe_detector import MediaPipePoseDetector

# â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

FPS = 120.0


def make_frame(idx: int = 0) -> Frame:
    return Frame(
        image=np.zeros((240, 320, 3), dtype=np.uint8),
        timestamp_ms=idx * 8,
        camera_view="sagittal",
        frame_index=idx,
        confidence=1.0,
    )


def make_kp(x: float = 50.0, y: float = 100.0) -> Keypoint:
    return Keypoint(x=x, y=y, confidence=0.9, name="left_ankle")


def make_kf(frame: Frame, has_keypoints: bool = True) -> KeypointFrame:
    kps = {"left_ankle": make_kp()} if has_keypoints else {}
    return KeypointFrame(
        timestamp_ms=frame.timestamp_ms,
        frame_index=frame.frame_index,
        camera_view=frame.camera_view,
        keypoints=kps,
        confidence=0.9 if has_keypoints else 0.0,
    )


class FakeDetector(PoseDetector):
    """Deterministic fake: returns KeypointFrames from a pre-built list."""

    def __init__(self, kf_list: list[KeypointFrame]) -> None:
        self._kf_list = kf_list
        self._idx = 0

    def __enter__(self) -> "FakeDetector":
        return self

    def __exit__(self, *_) -> None:
        pass

    def detect(self, frame: Frame) -> KeypointFrame:
        kf = self._kf_list[self._idx % len(self._kf_list)]
        self._idx += 1
        return kf

    def batch_detect(self, frames: list[Frame]) -> list[KeypointFrame]:
        return [self.detect(f) for f in frames]


def fake_factory(kf_list: list[KeypointFrame]):
    """Return a patching context that makes create_pose_detector return a FakeDetector."""
    return patch(
        "gait.pose.estimator.create_pose_detector",
        return_value=FakeDetector(kf_list),
    )


# â”€â”€ PoseEstimator.run â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestRun:
    def test_empty_frames_returns_empty(self):
        cfg = PoseConfig()
        est = PoseEstimator(cfg, fps=FPS)
        frames = [make_frame(i) for i in range(3)]
        kfs = [make_kf(f) for f in frames]
        with fake_factory(kfs):
            assert est.run([]) == []

    def test_output_length_equals_detected_frames(self):
        cfg = PoseConfig()
        est = PoseEstimator(cfg, fps=FPS)
        frames = [make_frame(i) for i in range(5)]
        kfs = [make_kf(f, has_keypoints=True) for f in frames]
        with fake_factory(kfs):
            result = est.run(frames)
        assert len(result) == 5

    def test_frames_with_no_keypoints_dropped(self):
        cfg = PoseConfig()
        est = PoseEstimator(cfg, fps=FPS)
        frames = [make_frame(i) for i in range(4)]
        # Alternating: frame 0 has keypoints, frame 1 doesn't, ...
        kfs = [make_kf(f, has_keypoints=(i % 2 == 0)) for i, f in enumerate(frames)]
        with fake_factory(kfs):
            result = est.run(frames)
        assert len(result) == 2  # only frames 0 and 2 have keypoints

    def test_output_elements_are_keypoint_frames(self):
        cfg = PoseConfig()
        est = PoseEstimator(cfg, fps=FPS)
        frames = [make_frame(i) for i in range(3)]
        kfs = [make_kf(f) for f in frames]
        with fake_factory(kfs):
            result = est.run(frames)
        assert all(isinstance(kf, KeypointFrame) for kf in result)

    def test_batch_size_respected(self):
        """PoseEstimator with batch_size=2 must still process all 5 frames."""
        cfg = PoseConfig(batch_size=2)
        est = PoseEstimator(cfg, fps=FPS)
        frames = [make_frame(i) for i in range(5)]
        kfs = [make_kf(f) for f in frames]
        with fake_factory(kfs):
            result = est.run(frames)
        assert len(result) == 5

    def test_all_dropped_returns_empty(self):
        cfg = PoseConfig()
        est = PoseEstimator(cfg, fps=FPS)
        frames = [make_frame(i) for i in range(3)]
        kfs = [make_kf(f, has_keypoints=False) for f in frames]
        with fake_factory(kfs):
            result = est.run(frames)
        assert result == []

    def test_camera_views_preserved_after_smoothing(self):
        cfg = PoseConfig()
        est = PoseEstimator(cfg, fps=FPS)
        frames = [make_frame(i) for i in range(3)]
        kfs = [make_kf(f) for f in frames]
        with fake_factory(kfs):
            result = est.run(frames)
        assert all(kf.camera_view == "sagittal" for kf in result)

    def test_frame_indices_preserved_after_smoothing(self):
        cfg = PoseConfig()
        est = PoseEstimator(cfg, fps=FPS)
        frames = [make_frame(i) for i in range(4)]
        kfs = [make_kf(f) for f in frames]
        with fake_factory(kfs):
            result = est.run(frames)
        assert [kf.frame_index for kf in result] == [0, 1, 2, 3]


# â”€â”€ create_pose_detector factory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestCreatePoseDetector:
    def test_mediapipe_returns_correct_type(self):
        cfg = PoseConfig(model="mediapipe")
        with patch("gait.pose.mediapipe_detector.mp") as mock_mp:
            mock_mp.solutions.pose.Pose.return_value = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
            det = create_pose_detector(cfg)
        assert isinstance(det, MediaPipePoseDetector)

    def test_mediapipe_case_insensitive(self):
        cfg = PoseConfig(model="MediaPipe")
        with patch("gait.pose.mediapipe_detector.mp") as mock_mp:
            mock_mp.solutions.pose.Pose.return_value = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
            det = create_pose_detector(cfg)
        assert isinstance(det, MediaPipePoseDetector)

    def test_unknown_model_raises_value_error(self):
        cfg = PoseConfig(model="openpose")
        with pytest.raises(ValueError, match="Unknown pose model"):
            create_pose_detector(cfg)

    def test_unknown_model_error_message_includes_name(self):
        cfg = PoseConfig(model="deep_lab")
        with pytest.raises(ValueError, match="deep_lab"):
            create_pose_detector(cfg)


