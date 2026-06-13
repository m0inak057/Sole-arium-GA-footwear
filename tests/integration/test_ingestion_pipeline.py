"""Integration tests for the full ingestion pipeline (IngestionPreprocessor).

Uses cv2.VideoWriter to create synthetic videos. No hardware cameras required.
The synthetic video design:
  - N_BG static-background frames → MOG2 learns background before warmup ends
  - N_FG frames with a white rectangle (the simulated "person")

With max_lost_frames set well above N_FG, the stale-bbox path covers the
entire person segment, so the pipeline always runs to completion.
"""

import cv2
import numpy as np
import pytest
from pathlib import Path

from src.gait.common.interfaces import Frame
from src.gait.common.types import VideoDecodeError
from src.gait.ingestion import IngestionPreprocessor
from src.gait.pipeline.config import IngestionConfig

# ── synthetic video parameters ────────────────────────────────────────────────

W, H, FPS = 320, 240, 30
N_BG = 25   # background-only frames (> mog2_history so warmup ends in time)
N_FG = 30   # frames with the "person" rectangle
N_TOTAL = N_BG + N_FG


# ── fixtures ──────────────────────────────────────────────────────────────────


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
def video_path(module_tmp):
    p = module_tmp / "sagittal.avi"
    write_synthetic_video(p)
    return p


@pytest.fixture(scope="module")
def dual_video_paths(module_tmp):
    sag = module_tmp / "sagittal_dual.avi"
    pos = module_tmp / "posterior_dual.avi"
    write_synthetic_video(sag)
    write_synthetic_video(pos)
    return {"sagittal": sag, "posterior": pos}


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


# ── single-camera tests ───────────────────────────────────────────────────────


@pytest.mark.integration
class TestSingleCamera:
    def test_runs_without_error(self, video_path, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run({"sagittal": video_path})
        assert result is not None

    def test_output_frames_are_frame_objects(self, video_path, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run({"sagittal": video_path})
        assert all(isinstance(f, Frame) for f in result.frames)

    def test_output_frames_are_uint8(self, video_path, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run({"sagittal": video_path})
        assert all(f.image.dtype == np.uint8 for f in result.frames)

    def test_output_frames_are_3_channel(self, video_path, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run({"sagittal": video_path})
        assert all(f.image.ndim == 3 for f in result.frames)

    def test_output_frames_are_cropped(self, video_path, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run({"sagittal": video_path})
        assert all(
            f.image.shape[0] < H and f.image.shape[1] < W
            for f in result.frames
        )

    def test_frame_accounting(self, video_path, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run({"sagittal": video_path})
        assert result.total_input_frames == N_TOTAL
        assert result.total_input_frames == len(result.frames) + result.dropped_frames

    def test_produces_at_least_one_frame(self, video_path, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run({"sagittal": video_path})
        assert len(result.frames) > 0

    def test_camera_views_field(self, video_path, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run({"sagittal": video_path})
        assert result.camera_views == ["sagittal"]

    def test_frames_do_not_share_memory(self, video_path, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run({"sagittal": video_path})
        for a, b in zip(result.frames, result.frames[1:]):
            assert not np.shares_memory(a.image, b.image)

    def test_processing_time_is_positive(self, video_path, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run({"sagittal": video_path})
        assert result.processing_time_sec > 0.0

    def test_deterministic_frame_count(self, video_path, cfg, tmp_path):
        """Same video processed twice yields the same frame count."""
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        r1 = pp.run({"sagittal": video_path})
        r2 = pp.run({"sagittal": video_path})
        assert len(r1.frames) == len(r2.frames)
        assert r1.total_input_frames == r2.total_input_frames


# ── error cases ───────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestErrorCases:
    def test_missing_video_raises_video_decode_error(self, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        with pytest.raises(VideoDecodeError):
            pp.run({"sagittal": tmp_path / "nonexistent.avi"})

    def test_empty_video_paths_raises_value_error(self, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        with pytest.raises(ValueError, match="at least one"):
            pp.run({})


# ── uncalibrated passthrough ──────────────────────────────────────────────────


@pytest.mark.integration
class TestUncalibratedPassthrough:
    def test_no_calibration_files_does_not_raise(self, video_path, cfg, tmp_path):
        # tmp_path has no YAML files → passthrough mode
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run({"sagittal": video_path})
        assert result is not None

    def test_uncalibrated_frame_dimensions_still_cropped(self, video_path, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run({"sagittal": video_path})
        assert all(
            f.image.shape[0] < H and f.image.shape[1] < W
            for f in result.frames
        )


# ── dual-camera tests ─────────────────────────────────────────────────────────


@pytest.mark.integration
class TestDualCamera:
    def test_dual_camera_runs_without_error(self, dual_video_paths, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run(dual_video_paths)
        assert result is not None

    def test_dual_camera_total_input_is_doubled(self, dual_video_paths, cfg, tmp_path):
        # With 2 cameras and perfect sync, total_input_frames = 2 × N_TOTAL
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run(dual_video_paths)
        assert result.total_input_frames == 2 * N_TOTAL

    def test_dual_camera_accounting(self, dual_video_paths, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run(dual_video_paths)
        assert result.total_input_frames == len(result.frames) + result.dropped_frames

    def test_dual_camera_both_views_in_result(self, dual_video_paths, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run(dual_video_paths)
        assert set(result.camera_views) == {"sagittal", "posterior"}

    def test_dual_camera_output_frames_cropped(self, dual_video_paths, cfg, tmp_path):
        pp = IngestionPreprocessor(cfg, cameras_config_dir=tmp_path)
        result = pp.run(dual_video_paths)
        assert all(
            f.image.shape[0] < H and f.image.shape[1] < W
            for f in result.frames
        )
