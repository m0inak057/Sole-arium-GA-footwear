"""Unit tests for ROI crop (src.gait.ingestion.roi)."""

import numpy as np
import pytest

from gait.common.interfaces import Frame
from gait.common.types import PersonTrack
from gait.ingestion.roi import compute_roi_bbox, crop_roi

# â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

IMG_H, IMG_W = 480, 640


def make_frame(h: int = IMG_H, w: int = IMG_W, value: int = 128) -> Frame:
    return Frame(
        image=np.full((h, w, 3), value, dtype=np.uint8),
        timestamp_ms=33,
        camera_view="posterior",
        frame_index=5,
        confidence=0.85,
    )


def make_track(x: int, y: int, w: int, h: int) -> PersonTrack:
    return PersonTrack(track_id=1, bbox=(x, y, w, h), confidence=1.0, frames_since_update=0)


# â”€â”€ compute_roi_bbox â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestComputeRoiBbox:
    def test_margin_expands_bbox(self):
        track = make_track(100, 100, 200, 300)
        x, y, w, h = compute_roi_bbox(track, 20, IMG_W, IMG_H)
        assert x == 80 and y == 80
        assert w == 240 and h == 340

    def test_zero_margin_unchanged(self):
        track = make_track(100, 100, 200, 300)
        assert compute_roi_bbox(track, 0, IMG_W, IMG_H) == (100, 100, 200, 300)

    def test_margin_clamped_at_left_top(self):
        track = make_track(5, 5, 100, 100)
        x, y, w, h = compute_roi_bbox(track, 20, IMG_W, IMG_H)
        assert x == 0 and y == 0

    def test_margin_clamped_at_right(self):
        track = make_track(560, 100, 60, 100)
        x, y, w, h = compute_roi_bbox(track, 20, IMG_W, IMG_H)
        assert x + w == IMG_W

    def test_margin_clamped_at_bottom(self):
        track = make_track(100, 400, 100, 70)
        x, y, w, h = compute_roi_bbox(track, 20, IMG_W, IMG_H)
        assert y + h == IMG_H

    def test_result_within_image_bounds(self):
        track = make_track(0, 0, IMG_W, IMG_H)
        x, y, w, h = compute_roi_bbox(track, 50, IMG_W, IMG_H)
        assert x >= 0 and y >= 0
        assert x + w <= IMG_W
        assert y + h <= IMG_H


# â”€â”€ crop_roi â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestCropRoi:
    def test_crop_returns_smaller_image(self):
        frame = make_frame()
        track = make_track(100, 100, 200, 300)
        out = crop_roi(frame, track, margin_px=10)
        assert out.image.shape[0] < IMG_H and out.image.shape[1] < IMG_W

    def test_zero_margin_crops_exactly_to_bbox(self):
        frame = make_frame()
        track = make_track(100, 100, 200, 300)
        out = crop_roi(frame, track, margin_px=0)
        assert out.image.shape == (300, 200, 3)

    def test_returns_new_ndarray(self):
        frame = make_frame()
        track = make_track(100, 100, 200, 300)
        out = crop_roi(frame, track, margin_px=10)
        assert not np.shares_memory(frame.image, out.image)

    def test_mutating_output_does_not_affect_input(self):
        frame = make_frame(value=128)
        track = make_track(100, 100, 200, 300)
        out = crop_roi(frame, track, margin_px=0)
        out.image[:] = 0
        # Input frame must be unchanged
        assert (frame.image == 128).all()

    def test_pixel_values_preserved(self):
        frame = make_frame(value=77)
        track = make_track(100, 100, 200, 300)
        out = crop_roi(frame, track, margin_px=0)
        assert (out.image == 77).all()

    def test_preserves_timestamp(self):
        frame = make_frame()
        out = crop_roi(frame, make_track(50, 50, 100, 100), margin_px=5)
        assert out.timestamp_ms == frame.timestamp_ms

    def test_preserves_camera_view(self):
        frame = make_frame()
        out = crop_roi(frame, make_track(50, 50, 100, 100), margin_px=5)
        assert out.camera_view == frame.camera_view

    def test_preserves_frame_index(self):
        frame = make_frame()
        out = crop_roi(frame, make_track(50, 50, 100, 100), margin_px=5)
        assert out.frame_index == frame.frame_index

    def test_preserves_confidence(self):
        frame = make_frame()
        out = crop_roi(frame, make_track(50, 50, 100, 100), margin_px=5)
        assert out.confidence == frame.confidence

    def test_zero_area_track_raises(self):
        frame = make_frame(h=10, w=10)
        track = make_track(0, 0, 0, 0)
        with pytest.raises(ValueError, match="zero area"):
            crop_roi(frame, track, margin_px=0)

    def test_margin_clamped_stays_in_bounds(self):
        frame = make_frame()
        # Track at top-left corner; large margin would go negative
        track = make_track(5, 5, 100, 100)
        out = crop_roi(frame, track, margin_px=50)
        h, w = out.image.shape[:2]
        assert h > 0 and w > 0

    def test_output_dtype_preserved(self):
        frame = make_frame()
        out = crop_roi(frame, make_track(100, 100, 200, 300), margin_px=0)
        assert out.image.dtype == np.uint8

    def test_output_is_3_channel(self):
        frame = make_frame()
        out = crop_roi(frame, make_track(100, 100, 200, 300), margin_px=0)
        assert out.image.ndim == 3

