"""Unit tests for MediaPipePoseDetector (src.gait.pose.mediapipe_detector).

MediaPipe model inference is mocked - no GPU/camera/internet required.
The detector uses the MediaPipe Tasks API (mediapipe.tasks.python.vision),
not the legacy mp.solutions API. The mock patches
`mp_vision.PoseLandmarker.create_from_options` so no real model file is ever
loaded; `mock_landmarker.detect_for_video.return_value` is set per-test to a
fake `PoseLandmarkerResult`-shaped object (`.pose_landmarks`: a list of poses,
each pose a list of landmark objects with `.x .y .z .presence`).

The model file itself is a real (but fake-content) file created per-test
under `tmp_path`, so `MediaPipePoseDetector.__init__`'s `model_path.exists()`
check is exercised for real without depending on anything in the repo.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from gait.common.interfaces import Frame, KeypointFrame
from gait.pose.mediapipe_detector import MediaPipePoseDetector, _LANDMARK_NAMES
from gait.pipeline.config import PoseConfig

# ── helpers ──────────────────────────────────────────────────────────────────

IMG_H, IMG_W = 240, 320


def make_frame(idx: int = 0, h: int = IMG_H, w: int = IMG_W, timestamp_ms: int | None = None) -> Frame:
    return Frame(
        image=np.zeros((h, w, 3), dtype=np.uint8),
        timestamp_ms=idx * 8 if timestamp_ms is None else timestamp_ms,
        camera_view="sagittal",
        frame_index=idx,
        confidence=1.0,
    )


def make_landmark(x: float = 0.5, y: float = 0.5, z: float = 0.0, presence: float = 0.9):
    """A fake mediapipe.tasks.python.components.containers.NormalizedLandmark.

    Real Tasks API landmarks expose both `.presence` and `.visibility`;
    MediaPipePoseDetector.detect() only reads `.presence`.
    """
    return SimpleNamespace(x=x, y=y, z=z, presence=presence, visibility=presence)


def make_pose_result(landmarks=None):
    """Build a fake PoseLandmarkerResult as returned by detect_for_video().

    `pose_landmarks` is a list of detected poses, each a list of 33 landmarks.
    An empty list (the real API's "no pose found" value) reproduces the
    no-detection path; passing a single pose's landmark list wraps it into
    the one-pose-per-frame shape the detector expects.
    """
    if landmarks is None:
        return SimpleNamespace(pose_landmarks=[])
    return SimpleNamespace(pose_landmarks=[landmarks])


def make_full_landmarks(presence: float = 0.9):
    """33 landmarks all at (0.5, 0.5) with the given presence."""
    return [make_landmark(presence=presence) for _ in range(33)]


def make_model_file(tmp_path) -> str:
    """Create a real (fake-content) model file on disk so
    MediaPipePoseDetector.__init__'s model_path.exists() check passes
    without downloading and without depending on any repo file."""
    model_file = tmp_path / "pose_landmarker_lite.task"
    model_file.write_bytes(b"fake-model-bytes")
    return str(model_file)


@pytest.fixture
def cfg(tmp_path):
    return PoseConfig(
        confidence_threshold=0.5, use_3d_lifting=False, model_path=make_model_file(tmp_path)
    )


@pytest.fixture
def cfg_3d(tmp_path):
    return PoseConfig(
        confidence_threshold=0.5, use_3d_lifting=True, model_path=make_model_file(tmp_path)
    )


@pytest.fixture
def mp_patch():
    """Patch PoseLandmarker.create_from_options so detector construction never
    touches the real MediaPipe runtime/GPU/model loading.

    Yields the mock landmarker instance; set
    `mock_landmarker.detect_for_video.return_value` per test to control what
    "pose" is detected.
    """
    mock_landmarker = MagicMock()
    with patch(
        "gait.pose.mediapipe_detector.mp_vision.PoseLandmarker.create_from_options",
        return_value=mock_landmarker,
    ):
        yield mock_landmarker


# ── detect: successful detection ────────────────────────────────────────────


class TestDetectWithLandmarks:
    def test_returns_keypoint_frame(self, mp_patch, cfg):
        mp_patch.detect_for_video.return_value = make_pose_result(make_full_landmarks())
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert isinstance(kf, KeypointFrame)

    def test_keypoints_dict_not_empty(self, mp_patch, cfg):
        mp_patch.detect_for_video.return_value = make_pose_result(make_full_landmarks(presence=0.9))
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert len(kf.keypoints) > 0

    def test_all_keypoints_above_threshold(self, mp_patch, cfg):
        mp_patch.detect_for_video.return_value = make_pose_result(make_full_landmarks(presence=0.9))
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert all(kp.confidence >= cfg.confidence_threshold for kp in kf.keypoints.values())

    def test_landmark_names_are_strings(self, mp_patch, cfg):
        mp_patch.detect_for_video.return_value = make_pose_result(make_full_landmarks())
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert all(isinstance(n, str) and len(n) > 0 for n in kf.keypoints)

    def test_coordinate_scaling_x(self, mp_patch, cfg):
        lm = [make_landmark(x=0.5, y=0.5, presence=0.9)] + [make_landmark(presence=0.0)] * 32
        mp_patch.detect_for_video.return_value = make_pose_result(lm)
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame(w=IMG_W))
        # nose (idx 0) should be at x ≈ 0.5 * IMG_W
        if "nose" in kf.keypoints:
            assert kf.keypoints["nose"].x == pytest.approx(0.5 * IMG_W)

    def test_coordinate_scaling_y(self, mp_patch, cfg):
        lm = [make_landmark(x=0.25, y=0.75, presence=0.9)] + [make_landmark(presence=0.0)] * 32
        mp_patch.detect_for_video.return_value = make_pose_result(lm)
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        if "nose" in kf.keypoints:
            assert kf.keypoints["nose"].y == pytest.approx(0.75 * IMG_H)

    def test_z_none_when_use_3d_lifting_false(self, mp_patch, cfg):
        mp_patch.detect_for_video.return_value = make_pose_result(make_full_landmarks())
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert all(kp.z is None for kp in kf.keypoints.values())

    def test_z_set_when_use_3d_lifting_true(self, mp_patch, cfg_3d):
        mp_patch.detect_for_video.return_value = make_pose_result(make_full_landmarks())
        det = MediaPipePoseDetector(cfg_3d)
        kf = det.detect(make_frame())
        # At least some keypoints should have z set
        assert any(kp.z is not None for kp in kf.keypoints.values())

    def test_confidence_is_min_of_keypoints(self, mp_patch, cfg):
        # Two landmarks with presence=0.8 and presence=0.6; rest below threshold
        lms = [make_landmark(presence=0.0)] * 33
        lms[23] = make_landmark(presence=0.8)  # left_hip
        lms[24] = make_landmark(presence=0.6)  # right_hip
        mp_patch.detect_for_video.return_value = make_pose_result(lms)
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert kf.confidence == pytest.approx(0.6, abs=1e-6)


# ── detect: below-threshold and no-detection ────────────────────────────────


class TestDetectBelowThreshold:
    def test_low_visibility_landmarks_excluded(self, mp_patch, cfg):
        # All landmarks at presence=0.1 (below threshold=0.5)
        mp_patch.detect_for_video.return_value = make_pose_result(make_full_landmarks(presence=0.1))
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert len(kf.keypoints) == 0

    def test_empty_keypoints_confidence_is_zero(self, mp_patch, cfg):
        mp_patch.detect_for_video.return_value = make_pose_result(make_full_landmarks(presence=0.1))
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert kf.confidence == 0.0

    def test_no_landmarks_returns_empty_keypoints(self, mp_patch, cfg):
        mp_patch.detect_for_video.return_value = make_pose_result(None)
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert len(kf.keypoints) == 0

    def test_no_landmarks_confidence_is_zero(self, mp_patch, cfg):
        mp_patch.detect_for_video.return_value = make_pose_result(None)
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame())
        assert kf.confidence == 0.0


# ── detect: metadata propagation ────────────────────────────────────────────


class TestDetectMetadata:
    def test_timestamp_ms_preserved(self, mp_patch, cfg):
        mp_patch.detect_for_video.return_value = make_pose_result(None)
        det = MediaPipePoseDetector(cfg)
        frame = make_frame(idx=7)
        kf = det.detect(frame)
        assert kf.timestamp_ms == frame.timestamp_ms

    def test_frame_index_preserved(self, mp_patch, cfg):
        mp_patch.detect_for_video.return_value = make_pose_result(None)
        det = MediaPipePoseDetector(cfg)
        kf = det.detect(make_frame(idx=42))
        assert kf.frame_index == 42

    def test_camera_view_preserved(self, mp_patch, cfg):
        mp_patch.detect_for_video.return_value = make_pose_result(None)
        det = MediaPipePoseDetector(cfg)
        frame = Frame(
            image=np.zeros((IMG_H, IMG_W, 3), dtype=np.uint8),
            timestamp_ms=0,
            camera_view="posterior",
            frame_index=0,
        )
        kf = det.detect(frame)
        assert kf.camera_view == "posterior"


# ── detect: timestamp monotonicity guard ────────────────────────────────────


class TestTimestampMonotonicityGuard:
    def test_nonincreasing_timestamp_is_nudged_forward_and_still_detected(self, mp_patch, cfg):
        """MediaPipe VIDEO mode requires strictly increasing timestamps per
        detector instance. If two frames with non-increasing timestamps are
        passed to the same detector, the second call must not be skipped or
        crash - detect_for_video() must still be called, with a corrected
        (strictly greater) timestamp.
        """
        mp_patch.detect_for_video.return_value = make_pose_result(None)
        det = MediaPipePoseDetector(cfg)

        first = make_frame(idx=0, timestamp_ms=100)
        det.detect(first)
        first_call_timestamp = mp_patch.detect_for_video.call_args[0][1]
        assert first_call_timestamp == 100

        # Second frame's timestamp is <= the first (non-increasing input).
        second = make_frame(idx=1, timestamp_ms=50)
        det.detect(second)

        assert mp_patch.detect_for_video.call_count == 2
        second_call_timestamp = mp_patch.detect_for_video.call_args[0][1]
        # Must be nudged strictly forward past the last timestamp, not the
        # raw (non-increasing) input value.
        assert second_call_timestamp > first_call_timestamp
        assert second_call_timestamp == first_call_timestamp + 1

    def test_equal_timestamp_is_also_nudged_forward(self, mp_patch, cfg):
        mp_patch.detect_for_video.return_value = make_pose_result(None)
        det = MediaPipePoseDetector(cfg)

        det.detect(make_frame(idx=0, timestamp_ms=200))
        det.detect(make_frame(idx=1, timestamp_ms=200))  # equal, not just lower

        assert mp_patch.detect_for_video.call_count == 2
        second_call_timestamp = mp_patch.detect_for_video.call_args[0][1]
        assert second_call_timestamp == 201


# ── batch_detect ─────────────────────────────────────────────────────────────


class TestBatchDetect:
    def test_empty_list_returns_empty(self, mp_patch, cfg):
        det = MediaPipePoseDetector(cfg)
        assert det.batch_detect([]) == []

    def test_batch_length_matches_input(self, mp_patch, cfg):
        mp_patch.detect_for_video.return_value = make_pose_result(make_full_landmarks())
        det = MediaPipePoseDetector(cfg)
        frames = [make_frame(idx=i) for i in range(5)]
        results = det.batch_detect(frames)
        assert len(results) == 5

    def test_batch_frame_indices_preserved(self, mp_patch, cfg):
        mp_patch.detect_for_video.return_value = make_pose_result(None)
        det = MediaPipePoseDetector(cfg)
        frames = [make_frame(idx=i) for i in range(3)]
        results = det.batch_detect(frames)
        assert [kf.frame_index for kf in results] == [0, 1, 2]


# ── resource management ──────────────────────────────────────────────────────


class TestResourceManagement:
    def test_close_does_not_raise(self, mp_patch, cfg):
        det = MediaPipePoseDetector(cfg)
        det.close()  # must not raise

    def test_close_twice_does_not_raise(self, mp_patch, cfg):
        det = MediaPipePoseDetector(cfg)
        det.close()
        det.close()

    def test_context_manager_returns_self(self, mp_patch, cfg):
        det = MediaPipePoseDetector(cfg)
        with det as d:
            assert d is det

    def test_context_manager_calls_close(self, mp_patch, cfg):
        det = MediaPipePoseDetector(cfg)
        with det:
            pass
        mp_patch.close.assert_called()


# ── model download ───────────────────────────────────────────────────────────


class TestDownloadModel:
    def test_download_called_when_model_missing(self, mp_patch, tmp_path):
        missing_model_path = tmp_path / "does_not_exist.task"
        assert not missing_model_path.exists()
        cfg = PoseConfig(model_path=str(missing_model_path))

        def _fake_urlretrieve(url, filename):
            # _download_model stats the file afterward to log its size, so
            # the mock must actually create it - a real download would too.
            filename.write_bytes(b"fake-downloaded-model-bytes")

        with patch(
            "gait.pose.mediapipe_detector.urllib.request.urlretrieve",
            side_effect=_fake_urlretrieve,
        ) as mock_urlretrieve:
            MediaPipePoseDetector(cfg)

        mock_urlretrieve.assert_called_once()
        args, _ = mock_urlretrieve.call_args
        assert args[1] == missing_model_path

    def test_download_skipped_when_model_present(self, mp_patch, tmp_path):
        cfg = PoseConfig(model_path=make_model_file(tmp_path))

        with patch("gait.pose.mediapipe_detector.urllib.request.urlretrieve") as mock_urlretrieve:
            MediaPipePoseDetector(cfg)

        mock_urlretrieve.assert_not_called()


# ── landmark name map ────────────────────────────────────────────────────────


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
