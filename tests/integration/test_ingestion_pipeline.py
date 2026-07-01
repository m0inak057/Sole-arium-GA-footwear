"""Integration tests for the full ingestion pipeline (IngestionPreprocessor).

Uses cv2.VideoWriter to create synthetic videos. No hardware cameras required.
The system now requires exactly 3 cameras: anterior, sagittal, posterior.
The synthetic video design:
  - N_BG static-background frames â†’ MOG2 learns background before warmup ends
  - N_FG frames with a white rectangle (the simulated "person")

With max_lost_frames set well above N_FG, the stale-bbox path covers the
entire person segment, so the pipeline always runs to completion.
"""

import cv2
import numpy as np
import pytest
from pathlib import Path

from gait.common.interfaces import Frame
from gait.common.types import VideoDecodeError
from gait.ingestion import IngestionPreprocessor
from gait.pipeline.config import IngestionConfig

# â”€â”€ synthetic video parameters â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

W, H, FPS = 320, 240, 30
N_BG = 25   # background-only frames (> mog2_history so warmup ends in time)
N_FG = 30   # frames with the "person" rectangle
N_TOTAL = N_BG + N_FG


# â”€â”€ fixtures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def write_synthetic_video(path: Path) -> None:
    """Write N_BG background frames then N_FG frames with a moving rectangle."""
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"XVID"), float(FPS), (W, H)
    )
    for _ in range(N_BG):
        writer.write(np.zeros((H, W, 3), dtype=np.uint8))
    for i in range(N_FG):
        frame = np.zeros((H, W, 3), dtype=np.uint8)
        cv2.rectangle(frame, (50 + i, 50), (150 + i, 180), (200, 200, 200), -1)
        writer.write(frame)
    writer.release()


@pytest.fixture(scope="module")
def module_tmp(tmp_path_factory):
    return tmp_path_factory.mktemp("integration")


@pytest.fixture(scope="module")
def triple_video_paths(module_tmp):
    """Create all three required camera videos: anterior, sagittal, posterior."""
    ant = module_tmp / "anterior.avi"
    sag = module_tmp / "sagittal.avi"
    pos = module_tmp / "posterior.avi"
    write_synthetic_video(ant)
    write_synthetic_video(sag)
    write_synthetic_video(pos)
    return {"anterior": ant, "sagittal": sag, "posterior": pos}


@pytest.fixture
def cfg(tmp_path):
    return IngestionConfig(
        fps=FPS,
        resolution=[W, H],
        mog2_history=20,        # warmup ends before person appears (N_BG=25)
        min_blob_area_px2=500,
        max_lost_frames=100,    # high enough to span all N_FG frames via stale bbox
        iou_threshold=0.1,
        person_tracking_model="simple_iou",
        background_subtraction_model="mog2",
        roi_margin_px=10,
    )


# â”€â”€ triple-camera tests (required: anterior, sagittal, posterior) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@pytest.mark.integration
class TestTripleCamera:
    def test_runs_without_error(self, triple_video_paths, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run(triple_video_paths)
        assert result is not None

    def test_output_frames_are_frame_objects(self, triple_video_paths, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run(triple_video_paths)
        assert all(isinstance(f, Frame) for f in result.frames)

    def test_output_frames_are_uint8(self, triple_video_paths, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run(triple_video_paths)
        assert all(f.image.dtype == np.uint8 for f in result.frames)

    def test_output_frames_are_3_channel(self, triple_video_paths, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run(triple_video_paths)
        assert all(f.image.ndim == 3 for f in result.frames)

    def test_output_frames_are_cropped(self, triple_video_paths, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run(triple_video_paths)
        assert all(
            f.image.shape[0] < H and f.image.shape[1] < W
            for f in result.frames
        )

    def test_frame_accounting(self, triple_video_paths, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run(triple_video_paths)
        assert result.total_input_frames == 3 * N_TOTAL  # 3 cameras
        assert result.total_input_frames == len(result.frames) + result.dropped_frames

    def test_produces_at_least_one_frame(self, triple_video_paths, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run(triple_video_paths)
        assert len(result.frames) > 0

    def test_camera_views_field(self, triple_video_paths, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run(triple_video_paths)
        assert sorted(result.camera_views) == ["anterior", "posterior", "sagittal"]

    def test_frames_do_not_share_memory(self, triple_video_paths, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run(triple_video_paths)
        for a, b in zip(result.frames, result.frames[1:]):
            assert not np.shares_memory(a.image, b.image)

    def test_processing_time_is_positive(self, triple_video_paths, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run(triple_video_paths)
        assert result.processing_time_sec > 0.0

    def test_deterministic_frame_count(self, triple_video_paths, cfg, tmp_path):
        """Same videos processed twice yield the same frame count."""
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        r1 = pp.run(triple_video_paths)
        r2 = pp.run(triple_video_paths)
        assert len(r1.frames) == len(r2.frames)
        assert r1.total_input_frames == r2.total_input_frames


# â”€â”€ error cases â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@pytest.mark.integration
class TestErrorCases:
    def test_missing_video_raises_video_decode_error(self, triple_video_paths, cfg, tmp_path):
        """Test that missing video file raises error."""
        bad_paths = triple_video_paths.copy()
        bad_paths["anterior"] = tmp_path / "nonexistent.avi"
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        with pytest.raises(VideoDecodeError):
            pp.run(bad_paths)

    def test_empty_video_paths_raises_error(self, cfg, tmp_path):
        """Test that empty video dict raises error."""
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        with pytest.raises(ValueError):
            pp.run({})

    def test_missing_anterior_camera_raises_error(self, cfg, tmp_path, module_tmp):
        """Test that missing anterior camera raises FrameSyncError."""
        sag = module_tmp / "sagittal_err.avi"
        pos = module_tmp / "posterior_err.avi"
        write_synthetic_video(sag)
        write_synthetic_video(pos)
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        with pytest.raises(Exception):  # FrameSyncError
            pp.run({"sagittal": sag, "posterior": pos})

    def test_missing_sagittal_camera_raises_error(self, cfg, tmp_path, module_tmp):
        """Test that missing sagittal camera raises FrameSyncError."""
        ant = module_tmp / "anterior_err.avi"
        pos = module_tmp / "posterior_err.avi"
        write_synthetic_video(ant)
        write_synthetic_video(pos)
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        with pytest.raises(Exception):  # FrameSyncError
            pp.run({"anterior": ant, "posterior": pos})

    def test_missing_posterior_camera_raises_error(self, cfg, tmp_path, module_tmp):
        """Test that missing posterior camera raises FrameSyncError."""
        ant = module_tmp / "anterior_err.avi"
        sag = module_tmp / "sagittal_err.avi"
        write_synthetic_video(ant)
        write_synthetic_video(sag)
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        with pytest.raises(Exception):  # FrameSyncError
            pp.run({"anterior": ant, "sagittal": sag})


# â”€â”€ uncalibrated passthrough â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@pytest.mark.integration
class TestUncalibratedPassthrough:
    def test_no_calibration_files_does_not_raise(self, triple_video_paths, cfg, tmp_path):
        # tmp_path has no YAML files â†’ passthrough mode
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run(triple_video_paths)
        assert result is not None

    def test_uncalibrated_frame_dimensions_still_cropped(self, triple_video_paths, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run(triple_video_paths)
        assert all(
            f.image.shape[0] < H and f.image.shape[1] < W
            for f in result.frames
        )



