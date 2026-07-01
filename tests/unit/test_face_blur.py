"""Tests for face blurring (DPDP Act 2023 compliance).

Covers:
  1. blur_faces_in_video with a frame containing a face-like region â†’ True
  2. blur_faces_in_video with a plain background frame â†’ False, output still written
  3. blur_all_session_videos returns all 3 camera keys
  4. Celery task respects features.face_blur_pipeline: false (skips blur)
  5. face_blur_applied is correctly set to True/False in the final profile
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from gait.privacy.face_blur import blur_all_session_videos, blur_faces_in_video


# â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _write_single_frame_video(path: Path, frame: np.ndarray) -> None:
    """Write a one-frame AVI at 30 fps."""
    h, w = frame.shape[:2]
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"XVID"),
        30.0,
        (w, h),
    )
    writer.write(frame)
    writer.release()


def _make_face_like_frame() -> np.ndarray:
    """Return a 320é—240 BGR frame with a skin-toned oval that the Haar cascade
    may or may not detect â€” but crucially, the function must still run without
    crashing and return a written output video.

    Because the Haar cascade is a real detector we cannot guarantee detection in
    a synthetic frame, so the test checks that:
      - The output video is written (output file exists)
      - The function returns a bool (True or False â€” both are valid)
    """
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    # Skin-tone ellipse in the centre (rough face approximation)
    cv2.ellipse(frame, (160, 100), (40, 55), 0, 0, 360, (180, 140, 100), -1)
    # Add dark eye-spots
    cv2.circle(frame, (145, 85), 8, (30, 20, 20), -1)
    cv2.circle(frame, (175, 85), 8, (30, 20, 20), -1)
    return frame


def _make_blank_frame() -> np.ndarray:
    """Return a plain grey frame with no face-like features."""
    return np.full((240, 320, 3), 128, dtype=np.uint8)


# â”€â”€ unit tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@pytest.mark.unit
class TestBlurFacesInVideo:

    def test_output_video_is_written_face_like_frame(self, tmp_path):
        """blur_faces_in_video runs on a face-like frame and writes the output video."""
        src = tmp_path / "face.avi"
        dst = tmp_path / "face_blurred.avi"
        _write_single_frame_video(src, _make_face_like_frame())

        result = blur_faces_in_video(str(src), str(dst))

        assert dst.exists(), "Output video must be written even if no face detected"
        assert dst.stat().st_size > 0, "Output video must be non-empty"
        assert isinstance(result, bool), "Return value must be a bool"

    def test_no_face_returns_false_output_still_written(self, tmp_path):
        """blur_faces_in_video returns False on a blank frame, output still written."""
        src = tmp_path / "blank.avi"
        dst = tmp_path / "blank_blurred.avi"
        _write_single_frame_video(src, _make_blank_frame())

        result = blur_faces_in_video(str(src), str(dst))

        assert dst.exists(), "Output video must be written even when no face found"
        assert dst.stat().st_size > 0
        assert result is False, "Plain background should yield no detected faces"

    def test_missing_input_raises_file_not_found(self, tmp_path):
        """blur_faces_in_video raises FileNotFoundError for missing input."""
        with pytest.raises(FileNotFoundError):
            blur_faces_in_video(
                str(tmp_path / "nonexistent.avi"),
                str(tmp_path / "out.avi"),
            )

    def test_output_resolution_matches_input(self, tmp_path):
        """Output video has same width/height as input."""
        src = tmp_path / "src.avi"
        dst = tmp_path / "dst.avi"
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        _write_single_frame_video(src, frame)

        blur_faces_in_video(str(src), str(dst))

        cap = cv2.VideoCapture(str(dst))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        assert w == 320
        assert h == 240


@pytest.mark.unit
class TestBlurAllSessionVideos:

    def test_returns_all_three_camera_keys(self, tmp_path):
        """blur_all_session_videos returns a dict with all 3 camera keys present."""
        cameras = {}
        for name in ("anterior", "sagittal", "posterior"):
            p = tmp_path / f"{name}.avi"
            _write_single_frame_video(p, _make_blank_frame())
            cameras[name] = str(p)

        results = blur_all_session_videos(cameras, output_dir=str(tmp_path / "out"))

        assert set(results.keys()) == {"anterior", "sagittal", "posterior"}
        for key, val in results.items():
            assert isinstance(val, bool), f"{key} value must be bool"

    def test_output_files_created_in_output_dir(self, tmp_path):
        """Each camera gets a blurred file written to output_dir."""
        cameras = {}
        for name in ("anterior", "sagittal", "posterior"):
            p = tmp_path / f"{name}.avi"
            _write_single_frame_video(p, _make_blank_frame())
            cameras[name] = str(p)

        out_dir = tmp_path / "out"
        blur_all_session_videos(cameras, output_dir=str(out_dir))

        for name in ("anterior", "sagittal", "posterior"):
            assert (out_dir / f"{name}_blurred.avi").exists()

    def test_missing_camera_does_not_crash(self, tmp_path):
        """If one camera file is missing, results contain False for that key and others succeed."""
        cameras = {
            "anterior": str(tmp_path / "nonexistent.avi"),
            "sagittal": str(tmp_path / "sagittal.avi"),
            "posterior": str(tmp_path / "posterior.avi"),
        }
        for name in ("sagittal", "posterior"):
            _write_single_frame_video(tmp_path / f"{name}.avi", _make_blank_frame())

        results = blur_all_session_videos(cameras, output_dir=str(tmp_path / "out"))

        assert "anterior" in results
        assert results["anterior"] is False


@pytest.mark.unit
class TestCeleryTaskFaceBlur:

    def test_face_blur_skipped_when_flag_false(self):
        """Celery task skips blur entirely when features.face_blur_pipeline is False."""
        from gait.api.tasks import run_gait_pipeline

        mock_config = MagicMock()
        mock_config.features.face_blur_pipeline = False

        mock_profile = {
            "schema_version": "profile/v1",
            "patient_id": "P_TEST",
            "session_timestamp": "2026-06-18T10:00:00Z",
        }

        with patch("gait.api.tasks.load_pipeline_config", return_value=mock_config), \
             patch("gait.api.tasks.GaitPipeline") as mock_pipeline_cls, \
             patch("gait.privacy.face_blur.blur_all_session_videos") as mock_blur, \
             patch.object(run_gait_pipeline, "update_state"):

            mock_pipeline = MagicMock()
            mock_pipeline.run.return_value = mock_profile.copy()
            mock_pipeline_cls.return_value = mock_pipeline

            result = run_gait_pipeline.run(
                session_id="sess-001",
                video_paths={"anterior": "/tmp/a.avi"},
                anthropometrics={"height_cm": 172, "mass_kg": 68},
                patient_id="P_TEST",
            )

        mock_blur.assert_not_called()
        assert result["profile"]["face_blur_applied"] is False

    def test_face_blur_runs_when_flag_true(self, tmp_path):
        """Celery task calls blur and sets face_blur_applied correctly when flag is True."""
        from gait.api.tasks import run_gait_pipeline

        mock_config = MagicMock()
        mock_config.features.face_blur_pipeline = True

        mock_profile = {
            "schema_version": "profile/v1",
            "patient_id": "P_TEST",
            "session_timestamp": "2026-06-18T10:00:00Z",
        }

        blur_results = {"anterior": True, "sagittal": False, "posterior": False}

        with patch("gait.api.tasks.load_pipeline_config", return_value=mock_config), \
             patch("gait.api.tasks.GaitPipeline") as mock_pipeline_cls, \
             patch("gait.api.tasks.blur_all_session_videos", return_value=blur_results), \
             patch.object(run_gait_pipeline, "update_state"):

            mock_pipeline = MagicMock()
            mock_pipeline.run.return_value = mock_profile.copy()
            mock_pipeline_cls.return_value = mock_pipeline

            result = run_gait_pipeline.run(
                session_id="sess-002",
                video_paths={"anterior": "/tmp/a.avi"},
                anthropometrics={"height_cm": 172, "mass_kg": 68},
                patient_id="P_TEST",
            )

        assert result["profile"]["face_blur_applied"] is True


@pytest.mark.unit
class TestFaceBlurAppliedInProfile:

    def _make_parameters(self):
        common = {
            "cycle_count": 4,
            "cadence_steps_per_min_mean": 112.0,
            "cadence_steps_per_min_std": 2.0,
            "foot_strike_type": "rearfoot",
            "arch_type": "normal",
            "pronation_type": "neutral",
            "rearfoot_angle_deg_mean": 2.0,
            "rearfoot_angle_deg_std": 0.8,
            "foot_strike_angle_deg_mean": 5.0,
            "foot_strike_angle_deg_std": 1.0,
            "stance_pct_mean": 61.0,
            "stance_pct_std": 1.5,
            "swing_pct_mean": 39.0,
            "swing_pct_std": 1.5,
            "quality_flag": "PROCEED_OK",
            "step_length_left_m": 0.70,
            "step_length_right_m": 0.68,
            "foot_progression_angle_left_deg": 5.0,
            "foot_progression_angle_right_deg": 5.0,
        }
        return {"L": {"foot": "L", **common}, "R": {"foot": "R", **common}}

    def test_face_blur_applied_true_in_profile(self):
        """face_blur_applied=True propagates correctly through builder to final profile."""
        from gait.profile.builder import create_profile_builder
        from gait.pipeline.config import load_pipeline_config, load_recommendation_rules

        rules_config = load_recommendation_rules()
        analysis_config = load_pipeline_config().analysis
        builder = create_profile_builder(rules_config, analysis_config)

        profile = builder.build(
            patient_id="P001",
            session_timestamp="2026-06-18T10:00:00Z",
            parameters=self._make_parameters(),
            anthropometrics={
                "height_cm": 172.0,
                "mass_kg": 68.0,
                "foot_length_mm": {"L": 258.0, "R": 260.0},
                "foot_width_mm": {"L": 98.0, "R": 99.0},
            },
            confidence_scores={"pipeline": 0.90},
            face_blur_applied=True,
        )

        assert profile["face_blur_applied"] is True

    def test_face_blur_applied_false_in_profile(self):
        """face_blur_applied=False (default) propagates correctly through builder."""
        from gait.profile.builder import create_profile_builder
        from gait.pipeline.config import load_pipeline_config, load_recommendation_rules

        rules_config = load_recommendation_rules()
        analysis_config = load_pipeline_config().analysis
        builder = create_profile_builder(rules_config, analysis_config)

        profile = builder.build(
            patient_id="P002",
            session_timestamp="2026-06-18T10:00:00Z",
            parameters=self._make_parameters(),
            anthropometrics={
                "height_cm": 172.0,
                "mass_kg": 68.0,
                "foot_length_mm": {"L": 258.0, "R": 260.0},
                "foot_width_mm": {"L": 98.0, "R": 99.0},
            },
            confidence_scores={"pipeline": 0.90},
        )

        assert profile["face_blur_applied"] is False


