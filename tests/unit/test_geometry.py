"""Unit tests for src.gait.common.geometry — all pure functions, no I/O."""

import pytest
import numpy as np

from src.gait.common.geometry import (
    bbox_area_px2,
    clip_bbox,
    compute_angle_deg,
    compute_iou,
    compute_midpoint,
    expand_bbox,
    frame_index_to_timestamp_ms,
    normalize_vector,
    signed_angle_deg,
)


# ── compute_iou ───────────────────────────────────────────────────────────────


class TestComputeIoU:
    def test_identical_boxes(self):
        assert compute_iou((0, 0, 100, 100), (0, 0, 100, 100)) == pytest.approx(1.0)

    def test_no_overlap(self):
        assert compute_iou((0, 0, 10, 10), (20, 20, 10, 10)) == 0.0

    def test_adjacent_boxes_no_overlap(self):
        # Touching at the right edge but no actual intersection
        assert compute_iou((0, 0, 10, 10), (10, 0, 10, 10)) == 0.0

    def test_partial_overlap(self):
        # Two 10x10 boxes overlapping by 5x10 pixels
        # intersection=50, union=100+100-50=150
        assert compute_iou((0, 0, 10, 10), (5, 0, 10, 10)) == pytest.approx(50 / 150)

    def test_containment_small_inside_large(self):
        # 4x4 box fully inside a 10x10 box
        # intersection=16, union=16+100-16=100
        assert compute_iou((0, 0, 4, 4), (0, 0, 10, 10)) == pytest.approx(16 / 100)

    def test_zero_area_box_a(self):
        assert compute_iou((0, 0, 0, 10), (0, 0, 10, 10)) == 0.0

    def test_zero_area_both(self):
        assert compute_iou((5, 5, 0, 0), (5, 5, 0, 0)) == 0.0

    def test_symmetry(self):
        a = (10, 20, 50, 60)
        b = (30, 40, 50, 60)
        assert compute_iou(a, b) == pytest.approx(compute_iou(b, a))


# ── bbox_area_px2 ─────────────────────────────────────────────────────────────


class TestBboxAreaPx2:
    def test_normal(self):
        assert bbox_area_px2((0, 0, 50, 30)) == 1500

    def test_zero_width(self):
        assert bbox_area_px2((0, 0, 0, 100)) == 0

    def test_one_pixel(self):
        assert bbox_area_px2((5, 5, 1, 1)) == 1


# ── expand_bbox ───────────────────────────────────────────────────────────────


class TestExpandBbox:
    def test_no_clamping(self):
        assert expand_bbox((50, 50, 100, 100), 10, 640, 480) == (40, 40, 120, 120)

    def test_zero_margin_unchanged(self):
        bbox = (10, 20, 50, 60)
        assert expand_bbox(bbox, 0, 640, 480) == bbox

    def test_clamp_left_edge(self):
        x, y, w, h = expand_bbox((5, 50, 100, 100), 10, 640, 480)
        assert x == 0

    def test_clamp_top_edge(self):
        x, y, w, h = expand_bbox((50, 3, 100, 100), 10, 640, 480)
        assert y == 0

    def test_clamp_right_edge(self):
        x, y, w, h = expand_bbox((550, 50, 80, 100), 10, 640, 480)
        assert x + w == 640

    def test_clamp_bottom_edge(self):
        x, y, w, h = expand_bbox((50, 380, 100, 90), 10, 640, 480)
        assert y + h == 480

    def test_all_four_edges_clamped(self):
        # Box that butts against every edge
        x, y, w, h = expand_bbox((0, 0, 640, 480), 20, 640, 480)
        assert x == 0 and y == 0 and w == 640 and h == 480


# ── clip_bbox ─────────────────────────────────────────────────────────────────


class TestClipBbox:
    def test_already_inside(self):
        assert clip_bbox((10, 10, 50, 50), 640, 480) == (10, 10, 50, 50)

    def test_negative_origin_clamped(self):
        x, y, w, h = clip_bbox((-5, -3, 100, 100), 640, 480)
        assert x == 0 and y == 0

    def test_right_edge_clamped(self):
        x, y, w, h = clip_bbox((600, 0, 100, 100), 640, 480)
        assert x + w == 640

    def test_bottom_edge_clamped(self):
        x, y, w, h = clip_bbox((0, 400, 100, 200), 640, 480)
        assert y + h == 480


# ── compute_angle_deg ─────────────────────────────────────────────────────────


class TestComputeAngleDeg:
    def test_right_angle(self):
        # p1=(1,0), vertex=(0,0), p2=(0,1) → 90°
        assert compute_angle_deg((1, 0), (0, 0), (0, 1)) == pytest.approx(90.0)

    def test_straight_angle(self):
        assert compute_angle_deg((-1, 0), (0, 0), (1, 0)) == pytest.approx(180.0)

    def test_zero_angle_same_direction(self):
        assert compute_angle_deg((2, 0), (0, 0), (5, 0)) == pytest.approx(0.0)

    def test_p1_coincident_with_vertex_raises(self):
        with pytest.raises(ValueError, match="Cannot compute angle"):
            compute_angle_deg((0, 0), (0, 0), (1, 0))

    def test_p2_coincident_with_vertex_raises(self):
        with pytest.raises(ValueError, match="Cannot compute angle"):
            compute_angle_deg((1, 0), (0, 0), (0, 0))

    def test_off_axis_angle(self):
        # Equilateral-triangle angle = 60°
        angle = compute_angle_deg((1, 0), (0, 0), (0.5, 0.866))
        assert angle == pytest.approx(60.0, abs=0.5)


# ── normalize_vector ──────────────────────────────────────────────────────────


class TestNormalizeVector:
    def test_unit_x_vector(self):
        assert normalize_vector((3.0, 0.0)) == pytest.approx((1.0, 0.0))

    def test_unit_y_vector(self):
        assert normalize_vector((0.0, 5.0)) == pytest.approx((0.0, 1.0))

    def test_diagonal_has_unit_length(self):
        v = normalize_vector((1.0, 1.0))
        assert v[0] ** 2 + v[1] ** 2 == pytest.approx(1.0)

    def test_zero_vector_raises(self):
        with pytest.raises(ValueError, match="Cannot normalize zero vector"):
            normalize_vector((0.0, 0.0))


# ── compute_midpoint ──────────────────────────────────────────────────────────


class TestComputeMidpoint:
    def test_basic(self):
        assert compute_midpoint((0, 0), (10, 10)) == pytest.approx((5.0, 5.0))

    def test_same_point(self):
        assert compute_midpoint((3, 7), (3, 7)) == pytest.approx((3.0, 7.0))

    def test_negative_coords(self):
        assert compute_midpoint((-4, -6), (4, 6)) == pytest.approx((0.0, 0.0))


# ── signed_angle_deg ─────────────────────────────────────────────────────────


class TestSignedAngleDeg:
    def test_ccw_positive(self):
        # Counter-clockwise from (1,0) to (0,1) = +90°
        assert signed_angle_deg((1, 0), (0, 1)) == pytest.approx(90.0)

    def test_cw_negative(self):
        # Clockwise from (0,1) to (1,0) = -90°
        assert signed_angle_deg((0, 1), (1, 0)) == pytest.approx(-90.0)

    def test_same_direction_zero(self):
        assert signed_angle_deg((1, 0), (2, 0)) == pytest.approx(0.0)


# ── frame_index_to_timestamp_ms ───────────────────────────────────────────────


class TestFrameIndexToTimestampMs:
    def test_zero_frame(self):
        assert frame_index_to_timestamp_ms(0, 120) == 0

    def test_integer_arithmetic_not_float(self):
        # float path: int(1 / 120 * 1000) = int(8.333) = 8
        # integer path: (1 * 1000) // 120 = 1000 // 120 = 8
        assert frame_index_to_timestamp_ms(1, 120) == 8

    def test_exact_second(self):
        assert frame_index_to_timestamp_ms(120, 120) == 1000

    def test_30fps(self):
        # frame 7 at 30fps: 7000 // 30 = 233
        assert frame_index_to_timestamp_ms(7, 30) == 233

    def test_monotonically_increasing(self):
        timestamps = [frame_index_to_timestamp_ms(i, 120) for i in range(10)]
        assert timestamps == sorted(timestamps)
