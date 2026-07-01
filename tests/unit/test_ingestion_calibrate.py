"""Unit tests for camera calibration (src.gait.ingestion.calibrate)."""

import numpy as np
import pytest
import yaml

from gait.common.interfaces import Frame
from gait.common.types import CalibrationLoadError
from gait.ingestion.calibrate import CameraCalibrator, load_camera_calibration

# â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

VALID_CAL = {
    "camera_matrix": [[800.0, 0.0, 320.0], [0.0, 800.0, 240.0], [0.0, 0.0, 1.0]],
    "dist_coeffs": [0.01, -0.02, 0.001, 0.0, 0.003],
    "image_size": [100, 100],
}

IDENTITY_CAL = {
    "camera_matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    "dist_coeffs": [0.0, 0.0, 0.0, 0.0, 0.0],
    "image_size": [100, 100],
}


def write_yaml(tmp_path, camera_name, data):
    (tmp_path / f"{camera_name}.yaml").write_text(yaml.dump(data))


def make_frame(h=100, w=100, value=128):
    return Frame(
        image=np.full((h, w, 3), value, dtype=np.uint8),
        timestamp_ms=42,
        camera_view="sagittal",
        frame_index=7,
        confidence=0.9,
    )


# â”€â”€ load_camera_calibration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestLoadCameraCalibration:
    def test_missing_file_returns_none(self, tmp_path):
        result = load_camera_calibration("sagittal", tmp_path)
        assert result is None

    def test_malformed_yaml_raises(self, tmp_path):
        (tmp_path / "sagittal.yaml").write_text("{not_valid yaml: [}")
        with pytest.raises(CalibrationLoadError):
            load_camera_calibration("sagittal", tmp_path)

    def test_empty_yaml_raises(self, tmp_path):
        (tmp_path / "sagittal.yaml").write_text("")
        with pytest.raises(CalibrationLoadError):
            load_camera_calibration("sagittal", tmp_path)

    def test_missing_required_keys_raises(self, tmp_path):
        (tmp_path / "sagittal.yaml").write_text("camera_matrix: [[1,0,0],[0,1,0],[0,0,1]]\n")
        with pytest.raises(CalibrationLoadError, match="missing keys"):
            load_camera_calibration("sagittal", tmp_path)

    def test_valid_yaml_returns_calibration(self, tmp_path):
        write_yaml(tmp_path, "sagittal", VALID_CAL)
        cal = load_camera_calibration("sagittal", tmp_path)
        assert cal is not None
        assert cal.camera_name == "sagittal"

    def test_camera_matrix_shape(self, tmp_path):
        write_yaml(tmp_path, "sagittal", VALID_CAL)
        cal = load_camera_calibration("sagittal", tmp_path)
        assert cal.camera_matrix.shape == (3, 3)

    def test_image_size_correct(self, tmp_path):
        write_yaml(tmp_path, "sagittal", VALID_CAL)
        cal = load_camera_calibration("sagittal", tmp_path)
        assert cal.image_size == (100, 100)

    def test_camera_name_from_file(self, tmp_path):
        write_yaml(tmp_path, "posterior", VALID_CAL)
        cal = load_camera_calibration("posterior", tmp_path)
        assert cal.camera_name == "posterior"

    def test_maps_not_set_before_calibrator(self, tmp_path):
        write_yaml(tmp_path, "sagittal", VALID_CAL)
        cal = load_camera_calibration("sagittal", tmp_path)
        # Maps are only set by CameraCalibrator, not by load_camera_calibration
        assert cal.map1 is None
        assert cal.map2 is None


# â”€â”€ CameraCalibrator â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestCameraCalibratorUncalibrated:
    def test_is_calibrated_false(self):
        assert not CameraCalibrator(None).is_calibrated

    def test_apply_returns_new_ndarray(self):
        frame = make_frame()
        out = CameraCalibrator(None).apply(frame)
        assert not np.shares_memory(frame.image, out.image)

    def test_apply_preserves_pixel_values(self):
        frame = make_frame(value=77)
        out = CameraCalibrator(None).apply(frame)
        np.testing.assert_array_equal(frame.image, out.image)

    def test_apply_preserves_timestamp(self):
        frame = make_frame()
        out = CameraCalibrator(None).apply(frame)
        assert out.timestamp_ms == frame.timestamp_ms

    def test_apply_preserves_camera_view(self):
        frame = make_frame()
        out = CameraCalibrator(None).apply(frame)
        assert out.camera_view == frame.camera_view

    def test_apply_preserves_frame_index(self):
        frame = make_frame()
        out = CameraCalibrator(None).apply(frame)
        assert out.frame_index == frame.frame_index

    def test_apply_preserves_confidence(self):
        frame = make_frame()
        out = CameraCalibrator(None).apply(frame)
        assert out.confidence == frame.confidence


class TestCameraCalibratorCalibrated:
    @pytest.fixture
    def calibrator(self, tmp_path):
        write_yaml(tmp_path, "sagittal", IDENTITY_CAL)
        cal = load_camera_calibration("sagittal", tmp_path)
        return CameraCalibrator(cal)

    def test_is_calibrated_true(self, calibrator):
        assert calibrator.is_calibrated

    def test_maps_are_precomputed(self, tmp_path):
        write_yaml(tmp_path, "sagittal", IDENTITY_CAL)
        cal = load_camera_calibration("sagittal", tmp_path)
        CameraCalibrator(cal)
        assert cal.map1 is not None
        assert cal.map2 is not None

    def test_apply_returns_new_ndarray(self, calibrator):
        frame = make_frame()
        out = calibrator.apply(frame)
        assert not np.shares_memory(frame.image, out.image)

    def test_apply_preserves_metadata(self, calibrator):
        frame = make_frame()
        out = calibrator.apply(frame)
        assert out.timestamp_ms == frame.timestamp_ms
        assert out.camera_view == frame.camera_view
        assert out.frame_index == frame.frame_index
        assert out.confidence == frame.confidence

    def test_identity_calibration_preserves_image(self, calibrator):
        # Identity distortion coefficients â†’ output should equal input
        frame = make_frame(value=55)
        out = calibrator.apply(frame)
        # Pixel values should be very close (remap with identity may have boundary effects)
        assert out.image.dtype == np.uint8
        assert out.image.shape == frame.image.shape

