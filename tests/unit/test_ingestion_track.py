"""Unit tests for person tracking (src.gait.ingestion.track)."""

import logging

import numpy as np
import pytest

from src.gait.common.interfaces import Frame
from src.gait.common.types import TrackingLostError
from src.gait.ingestion.track import SimpleIoUTracker, create_person_tracker
from src.gait.pipeline.config import IngestionConfig

# ── helpers ───────────────────────────────────────────────────────────────────

IMG_H, IMG_W = 480, 640


def make_cfg(**overrides):
    # Build via dict so callers can override any default without duplicate-kwarg errors
    params = dict(iou_threshold=0.3, max_lost_frames=5, min_blob_area_px2=100)
    params.update(overrides)
    return IngestionConfig(**params)


def make_frame(idx: int = 0) -> Frame:
    return Frame(
        image=np.zeros((IMG_H, IMG_W, 3), dtype=np.uint8),
        timestamp_ms=idx * 8,
        camera_view="sagittal",
        frame_index=idx,
        confidence=1.0,
    )


def mask_with_rect(x: int, y: int, w: int, h: int) -> np.ndarray:
    mask = np.zeros((IMG_H, IMG_W), dtype=np.uint8)
    mask[y : y + h, x : x + w] = 255
    return mask


def empty_mask() -> np.ndarray:
    return np.zeros((IMG_H, IMG_W), dtype=np.uint8)


# ── SimpleIoUTracker: initialisation ─────────────────────────────────────────


class TestFirstFrameInit:
    def test_blob_above_min_area_initialises_track(self):
        tracker = SimpleIoUTracker(make_cfg())
        track = tracker.update(make_frame(0), mask_with_rect(100, 100, 200, 300))
        assert track is not None

    def test_initial_track_confidence_is_1(self):
        tracker = SimpleIoUTracker(make_cfg())
        track = tracker.update(make_frame(0), mask_with_rect(100, 100, 200, 300))
        assert track.confidence == pytest.approx(1.0)

    def test_initial_frames_since_update_is_0(self):
        tracker = SimpleIoUTracker(make_cfg())
        track = tracker.update(make_frame(0), mask_with_rect(100, 100, 200, 300))
        assert track.frames_since_update == 0

    def test_empty_mask_before_init_returns_none(self):
        tracker = SimpleIoUTracker(make_cfg())
        track = tracker.update(make_frame(0), empty_mask())
        assert track is None

    def test_blob_below_min_area_filtered_before_init(self):
        # 5×5 = 25 px², well below min_blob_area_px2=100
        tracker = SimpleIoUTracker(make_cfg(min_blob_area_px2=100))
        track = tracker.update(make_frame(0), mask_with_rect(10, 10, 5, 5))
        assert track is None

    def test_largest_blob_chosen_on_init(self):
        tracker = SimpleIoUTracker(make_cfg(min_blob_area_px2=10))
        # Two blobs: small one (10×10=100) and large one (100×100=10000)
        mask = empty_mask()
        mask[10:20, 10:20] = 255   # small
        mask[200:300, 200:300] = 255  # large
        track = tracker.update(make_frame(0), mask)
        # Large blob: x=200, y=200, w=100, h=100
        assert track.bbox == (200, 200, 100, 100)


# ── SimpleIoUTracker: matching ────────────────────────────────────────────────


class TestTracking:
    def test_same_position_continues_track_fresh(self):
        tracker = SimpleIoUTracker(make_cfg())
        m = mask_with_rect(100, 100, 200, 300)
        tracker.update(make_frame(0), m)
        track = tracker.update(make_frame(1), m)
        assert track.confidence == pytest.approx(1.0)
        assert track.frames_since_update == 0

    def test_non_overlapping_blob_gives_stale_bbox(self):
        tracker = SimpleIoUTracker(make_cfg())
        tracker.update(make_frame(0), mask_with_rect(100, 100, 200, 300))
        # Blob far away — IoU with initial bbox is 0
        track = tracker.update(make_frame(1), mask_with_rect(500, 400, 100, 60))
        assert track is not None
        assert track.confidence < 1.0
        assert track.frames_since_update == 1

    def test_stale_confidence_decays_linearly(self):
        cfg = make_cfg(max_lost_frames=10)
        tracker = SimpleIoUTracker(cfg)
        tracker.update(make_frame(0), mask_with_rect(100, 100, 200, 300))
        for i in range(1, 5):
            track = tracker.update(make_frame(i), empty_mask())
        # 4 consecutive misses, max_lost=10 → confidence = 1 - 4/10 = 0.6
        assert track.confidence == pytest.approx(1.0 - 4 / 10)

    def test_stale_confidence_not_below_zero(self):
        cfg = make_cfg(max_lost_frames=5)
        tracker = SimpleIoUTracker(cfg)
        tracker.update(make_frame(0), mask_with_rect(100, 100, 200, 300))
        # 4 misses (max is 5, so last valid stale is at 4)
        for i in range(1, 5):
            track = tracker.update(make_frame(i), empty_mask())
        assert track.confidence >= 0.0

    def test_recovery_resets_lost_count(self):
        cfg = make_cfg(max_lost_frames=10)
        tracker = SimpleIoUTracker(cfg)
        m = mask_with_rect(100, 100, 200, 300)
        tracker.update(make_frame(0), m)
        # 2 misses
        tracker.update(make_frame(1), empty_mask())
        tracker.update(make_frame(2), empty_mask())
        # Recovery with matching blob
        track = tracker.update(make_frame(3), m)
        assert track.confidence == pytest.approx(1.0)
        assert tracker._lost_frames == 0

    def test_too_many_misses_raises(self):
        cfg = make_cfg(max_lost_frames=3)
        tracker = SimpleIoUTracker(cfg)
        tracker.update(make_frame(0), mask_with_rect(100, 100, 200, 300))
        with pytest.raises(TrackingLostError):
            for i in range(1, 10):
                tracker.update(make_frame(i), empty_mask())


# ── SimpleIoUTracker: reset ───────────────────────────────────────────────────


class TestReset:
    def test_reset_clears_track(self):
        tracker = SimpleIoUTracker(make_cfg())
        tracker.update(make_frame(0), mask_with_rect(100, 100, 200, 300))
        tracker.reset()
        assert tracker._track is None

    def test_reset_clears_lost_count(self):
        tracker = SimpleIoUTracker(make_cfg())
        tracker.update(make_frame(0), mask_with_rect(100, 100, 200, 300))
        tracker.update(make_frame(1), empty_mask())
        tracker.reset()
        assert tracker._lost_frames == 0

    def test_after_reset_can_reinitialise(self):
        tracker = SimpleIoUTracker(make_cfg())
        tracker.update(make_frame(0), mask_with_rect(100, 100, 200, 300))
        tracker.reset()
        track = tracker.update(make_frame(0), mask_with_rect(10, 10, 50, 50))
        assert track is not None


# ── factory ───────────────────────────────────────────────────────────────────


class TestCreatePersonTracker:
    def test_simple_iou_returns_correct_type(self):
        tracker = create_person_tracker("simple_iou", make_cfg())
        assert isinstance(tracker, SimpleIoUTracker)

    def test_bytetrack_falls_back_to_simple_iou(self):
        tracker = create_person_tracker("bytetrack", make_cfg())
        assert isinstance(tracker, SimpleIoUTracker)

    def test_bytetrack_fallback_logs_warning(self, caplog, monkeypatch):
        # Re-enable propagation so pytest caplog (which hooks the root logger) sees the record
        monkeypatch.setattr(logging.getLogger("src.gait.ingestion.track"), "propagate", True)
        with caplog.at_level(logging.WARNING):
            create_person_tracker("bytetrack", make_cfg())
        assert any("bytetrack_not_implemented" in r.getMessage() for r in caplog.records)

    def test_unknown_name_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown person_tracking_model"):
            create_person_tracker("deep_sort", make_cfg())

    def test_case_insensitive_simple_iou(self):
        tracker = create_person_tracker("Simple_IoU", make_cfg())
        assert isinstance(tracker, SimpleIoUTracker)
