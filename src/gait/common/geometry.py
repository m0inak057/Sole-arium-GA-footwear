"""Pure 2D geometry utilities for the gait analysis pipeline.

All functions are stateless and have no I/O — inputs in, values out.
Callers are responsible for passing correctly-shaped arrays.

BBox convention throughout: (x, y, w, h) in integer pixels,
where (x, y) is the top-left corner.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np


# Type alias — (x, y, w, h)
BBox = Tuple[int, int, int, int]


# ── Bounding-box operations ───────────────────────────────────────────────────


def compute_iou(bbox_a: BBox, bbox_b: BBox) -> float:
    """Intersection-over-Union of two (x, y, w, h) bounding boxes.

    Returns 0.0 when either box has zero area or they do not overlap.
    """
    ax, ay, aw, ah = bbox_a
    bx, by, bw, bh = bbox_b

    inter_x1 = max(ax, bx)
    inter_y1 = max(ay, by)
    inter_x2 = min(ax + aw, bx + bw)
    inter_y2 = min(ay + ah, by + bh)

    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    union_area = aw * ah + bw * bh - inter_area
    if union_area <= 0:
        return 0.0
    return inter_area / union_area


def bbox_area_px2(bbox: BBox) -> int:
    """Area of a (x, y, w, h) bounding box in square pixels."""
    return bbox[2] * bbox[3]


def expand_bbox(
    bbox: BBox,
    margin_px: int,
    image_width: int,
    image_height: int,
) -> BBox:
    """Expand (x, y, w, h) by margin_px on all four sides, clamped to image bounds.

    Returns a new (x, y, w, h) tuple. The returned box is always non-negative
    and fits within [0, image_width] × [0, image_height].
    """
    x, y, w, h = bbox
    x1 = max(0, x - margin_px)
    y1 = max(0, y - margin_px)
    x2 = min(image_width, x + w + margin_px)
    y2 = min(image_height, y + h + margin_px)
    return (x1, y1, x2 - x1, y2 - y1)


def clip_bbox(bbox: BBox, image_width: int, image_height: int) -> BBox:
    """Clip a (x, y, w, h) bbox so it lies entirely within the image."""
    x, y, w, h = bbox
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(image_width, x + w)
    y2 = min(image_height, y + h)
    return (x1, y1, max(0, x2 - x1), max(0, y2 - y1))


# ── Angle / vector operations ─────────────────────────────────────────────────


def compute_angle_deg(
    p1: Tuple[float, float],
    vertex: Tuple[float, float],
    p2: Tuple[float, float],
) -> float:
    """Angle at `vertex` between rays vertex→p1 and vertex→p2, in degrees [0, 180].

    Raises ValueError when either ray has zero length (points coincident with vertex).
    """
    v1 = np.array([p1[0] - vertex[0], p1[1] - vertex[1]], dtype=np.float64)
    v2 = np.array([p2[0] - vertex[0], p2[1] - vertex[1]], dtype=np.float64)

    norm1 = float(np.linalg.norm(v1))
    norm2 = float(np.linalg.norm(v2))
    if norm1 == 0.0 or norm2 == 0.0:
        raise ValueError(
            f"Cannot compute angle: point coincides with vertex "
            f"(p1={p1}, vertex={vertex}, p2={p2})"
        )

    cos_angle = float(np.clip(np.dot(v1, v2) / (norm1 * norm2), -1.0, 1.0))
    return float(np.degrees(np.arccos(cos_angle)))


def normalize_vector(v: Tuple[float, float]) -> Tuple[float, float]:
    """Return the unit vector in the direction of v.

    Raises ValueError for the zero vector.
    """
    arr = np.array(v, dtype=np.float64)
    norm = float(np.linalg.norm(arr))
    if norm == 0.0:
        raise ValueError(f"Cannot normalize zero vector: {v}")
    result = arr / norm
    return (float(result[0]), float(result[1]))


def compute_midpoint(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
) -> Tuple[float, float]:
    """Midpoint between two 2D points."""
    return ((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5)


def signed_angle_deg(
    v1: Tuple[float, float],
    v2: Tuple[float, float],
) -> float:
    """Signed angle from v1 to v2 in degrees, in [-180, 180].

    Positive = counter-clockwise (standard math convention).
    Used for frontal-plane rearfoot angle computation.
    """
    a1 = np.array(v1, dtype=np.float64)
    a2 = np.array(v2, dtype=np.float64)
    # atan2 of the cross and dot products
    cross = float(a1[0] * a2[1] - a1[1] * a2[0])
    dot = float(np.dot(a1, a2))
    return float(np.degrees(np.arctan2(cross, dot)))


# ── Timestamp conversion ──────────────────────────────────────────────────────


def frame_index_to_timestamp_ms(frame_index: int, fps: int) -> int:
    """Convert frame index to timestamp in milliseconds using integer arithmetic.

    Integer division avoids the float precision loss in int(frame_index / fps * 1000).
    """
    return (frame_index * 1000) // fps
