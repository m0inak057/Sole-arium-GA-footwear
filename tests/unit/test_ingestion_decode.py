"""Unit tests for VideoFileSource (src.gait.ingestion.decode)."""

import logging

import cv2
import numpy as np
import pytest

from gait.common.interfaces import Frame
from gait.common.types import VideoDecodeError
from gait.ingestion.decode import VideoFileSource
from gait.pipeline.config import IngestionConfig

FPS = 30
W, H = 320, 240
N_FRAMES = 10


@pytest.fixture
def cfg():
    return IngestionConfig(fps=FPS, resolution=[W, H])


@pytest.fixture
def tiny_video(tmp_path):
    """10-frame 320é—240 video at 30 fps with per-frame colour variation."""
    path = tmp_path / "test.avi"
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"XVID"), float(FPS), (W, H)
    )
    for i in range(N_FRAMES):
        img = np.zeros((H, W, 3), dtype=np.uint8)
        img[:, :, 0] = i * 20  # vary blue channel so frames differ
        writer.write(img)
    writer.release()
    return path


# â”€â”€ open / close / context manager â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestOpenClose:
    def test_open_valid_file_succeeds(self, tiny_video, cfg):
        src = VideoFileSource(tiny_video, "sagittal", cfg)
        src.open()
        src.close()

    def test_open_nonexistent_file_raises(self, tmp_path, cfg):
        with pytest.raises(VideoDecodeError, match="not found"):
            VideoFileSource(tmp_path / "missing.mp4", "sagittal", cfg).open()

    def test_close_without_open_is_safe(self, tmp_path, cfg):
        src = VideoFileSource(tmp_path / "x.mp4", "sagittal", cfg)
        src.close()  # must not raise

    def test_context_manager_opens_cap(self, tiny_video, cfg):
        with VideoFileSource(tiny_video, "sagittal", cfg) as src:
            assert src._cap is not None

    def test_context_manager_closes_cap_on_exit(self, tiny_video, cfg):
        with VideoFileSource(tiny_video, "sagittal", cfg) as src:
            pass
        assert src._cap is None

    def test_context_manager_closes_on_exception(self, tiny_video, cfg):
        try:
            with VideoFileSource(tiny_video, "sagittal", cfg) as src:
                raise RuntimeError("test error")
        except RuntimeError:
            pass
        assert src._cap is None

    def test_get_frames_without_open_raises(self, tiny_video, cfg):
        src = VideoFileSource(tiny_video, "sagittal", cfg)
        with pytest.raises(RuntimeError):
            list(src.get_frames())


# â”€â”€ frame content â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestFrameContent:
    def test_yields_correct_frame_count(self, tiny_video, cfg):
        with VideoFileSource(tiny_video, "sagittal", cfg) as src:
            frames = list(src.get_frames())
        assert len(frames) == N_FRAMES

    def test_frame_indices_are_sequential(self, tiny_video, cfg):
        with VideoFileSource(tiny_video, "sagittal", cfg) as src:
            frames = list(src.get_frames())
        assert [f.frame_index for f in frames] == list(range(N_FRAMES))

    def test_timestamp_uses_integer_arithmetic(self, tiny_video, cfg):
        with VideoFileSource(tiny_video, "sagittal", cfg) as src:
            frames = list(src.get_frames())
        # frame 1 at 30fps: (1 * 1000) // 30 = 33ms
        assert frames[1].timestamp_ms == (1 * 1000) // FPS

    def test_camera_view_propagated(self, tiny_video, cfg):
        with VideoFileSource(tiny_video, "posterior", cfg) as src:
            frames = list(src.get_frames())
        assert all(f.camera_view == "posterior" for f in frames)

    def test_frames_are_uint8(self, tiny_video, cfg):
        with VideoFileSource(tiny_video, "sagittal", cfg) as src:
            frames = list(src.get_frames())
        assert all(f.image.dtype == np.uint8 for f in frames)

    def test_frames_are_3_channel(self, tiny_video, cfg):
        with VideoFileSource(tiny_video, "sagittal", cfg) as src:
            frames = list(src.get_frames())
        assert all(f.image.ndim == 3 for f in frames)

    def test_frames_are_independent_ndarrays(self, tiny_video, cfg):
        with VideoFileSource(tiny_video, "sagittal", cfg) as src:
            frames = list(src.get_frames())
        for a, b in zip(frames, frames[1:]):
            assert not np.shares_memory(a.image, b.image)

    def test_timestamps_monotonically_non_decreasing(self, tiny_video, cfg):
        with VideoFileSource(tiny_video, "sagittal", cfg) as src:
            frames = list(src.get_frames())
        timestamps = [f.timestamp_ms for f in frames]
        assert timestamps == sorted(timestamps)


# â”€â”€ mismatch warnings â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestMismatchWarnings:
    # get_logger sets propagate=False on module loggers so pytest caplog (which
    # adds its handler to the root logger) cannot capture records by default.
    # We temporarily re-enable propagation for the duration of each assertion.

    def _enable_propagation(self, monkeypatch):
        logger_obj = logging.getLogger("gait.ingestion.decode")
        monkeypatch.setattr(logger_obj, "propagate", True)

    def test_fps_mismatch_logs_warning(self, tiny_video, caplog, monkeypatch):
        self._enable_propagation(monkeypatch)
        cfg_120 = IngestionConfig(fps=120, resolution=[W, H])
        with caplog.at_level(logging.WARNING):
            with VideoFileSource(tiny_video, "sagittal", cfg_120):
                pass
        assert any("fps_mismatch" in r.getMessage() for r in caplog.records)

    def test_matching_fps_no_warning(self, tiny_video, caplog, monkeypatch):
        self._enable_propagation(monkeypatch)
        with caplog.at_level(logging.WARNING):
            with VideoFileSource(tiny_video, "sagittal", IngestionConfig(fps=FPS, resolution=[W, H])):
                pass
        fps_warnings = [r for r in caplog.records if "fps_mismatch" in r.getMessage()]
        assert len(fps_warnings) == 0

    def test_resolution_mismatch_logs_warning(self, tiny_video, caplog, monkeypatch):
        self._enable_propagation(monkeypatch)
        cfg_hd = IngestionConfig(fps=FPS, resolution=[1920, 1080])
        with caplog.at_level(logging.WARNING):
            with VideoFileSource(tiny_video, "sagittal", cfg_hd):
                pass
        assert any("resolution_mismatch" in r.getMessage() for r in caplog.records)

