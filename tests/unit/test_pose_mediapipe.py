"""Unit tests for MediaPipePoseDetector (src.gait.pose.mediapipe_detector).

MediaPipe model inference is mocked â€” no GPU/camera/internet required.
The mock patches `mp` in the mediapipe_detector module so that
`mp.solutions.pose.Pose(...)` returns a MagicMock whose `.process()` method
returns synthetic landmark results.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from gait.common.interfaces import Frame, KeypointFrame
from gait.pose.mediapipe_detector import MediaPipePoseDetector, _LANDMARK_NAMES
from gait.pipeline.config import PoseConfig

# â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

IMG_H, IMG_W = 240, 320


def make_frame(idx: int = 0, h: int = IMG_H, w: int = IMG_W) -> Frame:
    return Frame(
        image=np.zeros((h, w, 3), dtype=np.uint8),
        timestamp_ms=idx * 8,
        camera_view="sagittal",
        frame_index=idx,
        confidence=1.0,
    )


def make_landmark(x: float = 0.5, y: float = 0.5, z: float = 0.0, vis: float = 0.9):
    return SimpleNamespace(x=x, y=y, z=z, visibility=vis)


def make_results(landmarks=None):
    """Build a fake mp.solutions.pose.Pose().process() return value."""
    if landmarks is None:
        return SimpleNamespace(pose_landmarks=None)
    return SimpleNamespace(
        pose_landmarks=SimpleNamespace(landmark=landmarks)
    )


def make_full_landmarks(vis: float = 0.9):
    """33 landmarks all at (0.5, 0.5) with given visibility."""
    return [make_landmark(vis=vis) for _ in range(33)]


@pytest.fixture
def cfg():
    return PoseConfig(confidence_threshold=0.5, use_3d_lifting=False)


@pytest.fixture
def cfg_3d():
    return PoseConfig(confidence_threshold=0.5, use_3d_lifting=True)


@pytest.fixture
def mp_patch():
    """Patch `mp` in the detector module; yield (mock_mp, pose_instance)."""
    with patch("gait.pose.mediapipe_detector.mp") as mock_mp:
        instance = MagicMock()
        mock_mp.solutions.pose.Pose.return_value = instance
        yield mock_mp, instance


# â”€â”€ detect: successful detection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestDetectWithLandmarks:
    def test_returns_keypoint_frame(self, mp_patch, cfg):
        _, inst = mp_patch
        inst.process.return_value = make_results(make_full_landmarks())
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert isinstance(kf, KeypointFrame)

    def test_keypoints_dict_not_empty(self, mp_patch, cfg):
        _, inst = mp_patch
        inst.process.return_value = make_results(make_full_landmarks(vis=0.9))
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert len(kf.keypoints) > 0

    def test_all_keypoints_above_threshold(self, mp_patch, cfg):
        _, inst = mp_patch
        inst.process.return_value = make_results(make_full_landmarks(vis=0.9))
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert all(kp.confidence >= cfg.confidence_threshold for kp in kf.keypoints.values())

    def test_landmark_names_are_strings(self, mp_patch, cfg):
        _, inst = mp_patch
        inst.process.return_value = make_results(make_full_landmarks())
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert all(isinstance(n, str) and len(n) > 0 for n in kf.keypoints)

    def test_coordinate_scaling_x(self, mp_patch, cfg):
        _, inst = mp_patch
        lm = [make_landmark(x=0.5, y=0.5, vis=0.9)] + [make_landmark(vis=0.0)] * 32
        inst.process.return_value = make_results(lm)
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame(w=IMG_W))
        # nose (idx 0) should be at x â‰ˆ 0.5 * IMG_W
        if "nose" in kf.keypoints:
            assert kf.keypoints["nose"].x == pytest.approx(0.5 * IMG_W)

    def test_coordinate_scaling_y(self, mp_patch, cfg):
        _, inst = mp_patch
        lm = [make_landmark(x=0.25, y=0.75, vis=0.9)] + [make_landmark(vis=0.0)] * 32
        inst.process.return_value = make_results(lm)
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        if "nose" in kf.keypoints:
            assert kf.keypoints["nose"].y == pytest.approx(0.75 * IMG_H)

    def test_z_none_when_use_3d_lifting_false(self, mp_patch, cfg):
        _, inst = mp_patch
        inst.process.return_value = make_results(make_full_landmarks())
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert all(kp.z is None for kp in kf.keypoints.values())

    def test_z_set_when_use_3d_lifting_true(self, mp_patch, cfg_3d):
        _, inst = mp_patch
        inst.process.return_value = make_results(make_full_landmarks())
        det = MediaPipePoseDetector(cfg_3d)
        kf = det.detect(make_frame())
        # At least some keypoints should have z set
        assert any(kp.z is not None for kp in kf.keypoints.values())

    def test_confidence_is_min_of_keypoints(self, mp_patch, cfg):
        _, inst = mp_patch
        # Two landmarks with vis=0.8 and vis=0.6; rest below threshold
        lms = [make_landmark(vis=0.0)] * 33
        lms[23] = make_landmark(vis=0.8)  # left_hip
        lms[24] = make_landmark(vis=0.6)  # right_hip
        inst.process.return_value = make_results(lms)
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert kf.confidence == pytest.approx(0.6, abs=1e-6)


# â”€â”€ detect: below-threshold and no-detection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestDetectBelowThreshold:
    def test_low_visibility_landmarks_excluded(self, mp_patch, cfg):
        _, inst = mp_patch
        # All landmarks at visibility=0.1 (below threshold=0.5)
        inst.process.return_value = make_results(make_full_landmarks(vis=0.1))
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert len(kf.keypoints) == 0

    def test_empty_keypoints_confidence_is_zero(self, mp_patch, cfg):
        _, inst = mp_patch
        inst.process.return_value = make_results(make_full_landmarks(vis=0.1))
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert kf.confidence == 0.0

    def test_no_landmarks_returns_empty_keypoints(self, mp_patch, cfg):
        _, inst = mp_patch
        inst.process.return_value = make_results(None)
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert len(kf.keypoints) == 0

    def test_no_landmarks_confidence_is_zero(self, mp_patch, cfg):
        _, inst = mp_patch
        inst.process.return_value = make_results(None)
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert kf.confidence == 0.0


# â”€â”€ detect: metadata propagation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestDetectMetadata:
    def test_timestamp_ms_preserved(self, mp_patch, cfg):
        _, inst = mp_patch
        inst.process.return_value = make_results(None)
        det = MediaPipePoseDetector(cfg)
        frame = make_frame(idx=7)
        kf = det.detect(frame)
        assert kf.timestamp_ms == frame.timestamp_ms

    def test_frame_index_preserved(self, mp_patch, cfg):
        _, inst = mp_patch
        inst.process.return_value = make_results(None)
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame(idx=42))
        assert kf.frame_index == 42

    def test_camera_view_preserved(self, mp_patch, cfg):
        _, inst = mp_patch
        inst.process.return_value = make_results(None)
        det = MediaPipePoseDetector(cfg)
        frame = Frame(
            image=np.zeros((IMG_H, IMG_W, 3), dtype=np.uint8),
            timestamp_ms=0,
            camera_view="posterior",
            frame_index=0,
        )
        kf = det.detect(frame)
        assert kf.camera_view == "posterior"


# â”€â”€ batch_detect â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestBatchDetect:
    def test_empty_list_returns_empty(self, mp_patch, cfg):
        _, inst = mp_patch
        det = MediaPipePoseDetector(cfg)
        assert det.batch_detect([]) == []

    def test_batch_length_matches_input(self, mp_patch, cfg):
        _, inst = mp_patch
        inst.process.return_value = make_results(make_full_landmarks())
        det = MediaPipePoseDetector(cfg)
        frames = [make_frame(idx=i) for i in range(5)]
        results = det.batch_detect(frames)
        assert len(results) == 5

    def test_batch_frame_indices_preserved(self, mp_patch, cfg):
        _, inst = mp_patch
        inst.process.return_value = make_results(None)
        det = MediaPipePoseDetector(cfg)
        frames = [make_frame(idx=i) for i in range(3)]
        results = det.batch_detect(frames)
        assert [kf.frame_index for kf in results] == [0, 1, 2]


# â”€â”€ resource management â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestResourceManagement:
    def test_close_does_not_raise(self, mp_patch, cfg):
        _, inst = mp_patch
        det = MediaPipePoseDetector(cfg)
        det.close()  # must not raise

    def test_close_twice_does_not_raise(self, mp_patch, cfg):
        _, inst = mp_patch
        det = MediaPipePoseDetector(cfg)
        det.close()
        det.close()

    def test_context_manager_returns_self(self, mp_patch, cfg):
        _, inst = mp_patch
        det = MediaPipePoseDetector(cfg)
        with det as d:
            assert d is det

    def test_context_manager_calls_close(self, mp_patch, cfg):
        _, inst = mp_patch
        det = MediaPipePoseDetector(cfg)
        with det:
            pass
        inst.close.assert_called()


# â”€â”€ landmark name map â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestLandmarkNames:
    def test_map_has_33_entries(self):
        assert len(_LANDMARK_NAMES) == 33

    def test_foot_keypoints_present(self):
        values = set(_LANDMARK_NAMES.values())
        for name in ("left_ankle", "right_ankle", "left_heel", "right_heel",
                     "left_foot_index", "right_foot_index"):
            assert name in values

    def test_indices_contiguous_0_to_32(self):
        assert set(_LANDMARK_NAMES.keys()) == set(range(33))


