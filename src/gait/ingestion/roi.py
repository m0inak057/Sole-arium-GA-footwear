"""ROI cropping — extract the region of interest around the tracked person.

crop_roi() is a pure function: given a Frame and a PersonTrack, it expands
the track bbox by margin_px on all sides (clamped to image bounds) and
returns a new Frame containing only that crop. The returned image array never
shares memory with the input frame.
"""

from __future__ import annotations

import numpy as np

from src.gait.common.geometry import BBox, clip_bbox, expand_bbox
from src.gait.common.interfaces import Frame
from src.gait.common.types import PersonTrack


def compute_roi_bbox(
    track: PersonTrack,
    margin_px: int,
    image_width: int,
    image_height: int,
) -> BBox:
    """Expand the track bbox by margin_px and clamp it to image bounds."""
    expanded = expand_bbox(track.bbox, margin_px, image_width, image_height)
    return clip_bbox(expanded, image_width, image_height)


def crop_roi(
    frame: Frame,
    track: PersonTrack,
    margin_px: int,
) -> Frame:
    """Crop a frame to the ROI around the tracked person.

    Returns a new Frame with a np.copy of the cropped region — never shares
    memory with the input frame.

    Raises ValueError if the computed ROI has zero area.
    """
    h, w = frame.image.shape[:2]
    roi_bbox = compute_roi_bbox(track, margin_px, image_width=w, image_height=h)

    rx, ry, rw, rh = roi_bbox
    if rw <= 0 or rh <= 0:
        raise ValueError(
            f"ROI has zero area for frame {frame.frame_index} "
            f"(track bbox={track.bbox}, margin={margin_px}px, "
            f"image={w}x{h})"
        )

    cropped = np.copy(frame.image[ry : ry + rh, rx : rx + rw])

    return Frame(
        image=cropped,
        timestamp_ms=frame.timestamp_ms,
        camera_view=frame.camera_view,
        frame_index=frame.frame_index,
        confidence=frame.confidence,
    )
