"""Person tracking â€” locks onto the subject across frames using IoU matching.

SimpleIoUTracker strategy:
  1. Extract foreground blobs via cv2.connectedComponentsWithStats.
  2. Filter blobs below min_blob_area_px2.
  3. First detection: choose the largest blob as the initial track.
  4. Subsequent frames: find the blob with highest IoU to the last known bbox.
     - IoU >= iou_threshold â†’ fresh track, confidence=1.0.
     - IoU < iou_threshold â†’ return last-known bbox with decaying confidence.
  5. After max_lost_frames consecutive misses â†’ raise TrackingLostError.

ByteTrack is planned for Phase 2; the factory falls back to SimpleIoUTracker
with a WARNING so the pipeline does not fail when bytetrack is configured.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

import cv2
import numpy as np

from gait.common.geometry import bbox_area_px2, compute_iou
from gait.common.interfaces import Frame
from gait.common.logging_utils import get_logger
from gait.common.types import PersonTrack, TrackingLostError
from gait.pipeline.config import IngestionConfig

logger = get_logger(__name__)

# Type alias: (x, y, w, h)
_BBox = Tuple[int, int, int, int]


class PersonTracker(ABC):
    """Abstract tracker â€” locks onto the subject across frames."""

    @abstractmethod
    def update(
        self,
        frame: Frame,
        foreground_mask: np.ndarray,
    ) -> Optional[PersonTrack]:
        """Update with the current frame's foreground mask.

        Returns PersonTrack when the subject is found (confidence < 1.0 when
        using a stale last-known bbox), or None during early warmup before any
        subject has been detected. Raises TrackingLostError when permanently lost.
        """

    @abstractmethod
    def reset(self) -> None:
        """Reset all tracker state."""


class SimpleIoUTracker(PersonTracker):
    """Minimal IoU-based tracker for the MVP."""

    def __init__(self, config: IngestionConfig) -> None:
        self._config = config
        self._track: Optional[PersonTrack] = None
        self._lost_frames = 0

    def update(
        self,
        frame: Frame,
        foreground_mask: np.ndarray,
    ) -> Optional[PersonTrack]:
        blobs = self._extract_blobs(foreground_mask)

        if not blobs:
            return self._handle_miss(frame.frame_index)

        if self._track is None:
            # First detection â€” initialise with the largest blob
            best_bbox = max(blobs, key=bbox_area_px2)
            self._track = PersonTrack(
                track_id=1,
                bbox=best_bbox,
                confidence=1.0,
                frames_since_update=0,
            )
            self._lost_frames = 0
            return self._track

        # Find blob with highest IoU to current track
        best_bbox = max(blobs, key=lambda b: compute_iou(b, self._track.bbox))
        best_iou = compute_iou(best_bbox, self._track.bbox)

        if best_iou >= self._config.iou_threshold:
            self._track = PersonTrack(
                track_id=self._track.track_id,
                bbox=best_bbox,
                confidence=1.0,
                frames_since_update=0,
            )
            self._lost_frames = 0
            return self._track

        return self._handle_miss(frame.frame_index)

    def reset(self) -> None:
        self._track = None
        self._lost_frames = 0

    # â”€â”€ Private â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _extract_blobs(self, mask: np.ndarray) -> List[_BBox]:
        """Return (x, y, w, h) bboxes for all blobs above min_blob_area_px2."""
        num_labels, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        bboxes: List[_BBox] = []
        for label in range(1, num_labels):  # skip label 0 (background)
            x = int(stats[label, cv2.CC_STAT_LEFT])
            y = int(stats[label, cv2.CC_STAT_TOP])
            w = int(stats[label, cv2.CC_STAT_WIDTH])
            h = int(stats[label, cv2.CC_STAT_HEIGHT])
            if w * h >= self._config.min_blob_area_px2:
                bboxes.append((x, y, w, h))
        return bboxes

    def _handle_miss(self, frame_index: int) -> Optional[PersonTrack]:
        self._lost_frames += 1

        if self._lost_frames >= self._config.max_lost_frames:
            raise TrackingLostError(
                f"Person tracker lost subject for {self._lost_frames} consecutive "
                f"frames (limit {self._config.max_lost_frames}). Re-record the session."
            )

        if self._track is None:
            # Haven't found anyone yet â€” still in warmup
            logger.debug(
                "tracker_warmup_miss",
                extra={"frame_index": frame_index, "lost_frames": self._lost_frames},
            )
            return None

        # Return stale last-known bbox with linearly decaying confidence
        decay = 1.0 - (self._lost_frames / self._config.max_lost_frames)
        stale = PersonTrack(
            track_id=self._track.track_id,
            bbox=self._track.bbox,
            confidence=max(0.0, decay),
            frames_since_update=self._lost_frames,
        )
        logger.warning(
            "tracker_using_stale_bbox",
            extra={
                "frame_index": frame_index,
                "lost_frames": self._lost_frames,
                "confidence": stale.confidence,
            },
        )
        return stale


def create_person_tracker(
    model_name: str,
    config: IngestionConfig,
) -> PersonTracker:
    """Factory â€” return the requested PersonTracker.

    'simple_iou' â†’ SimpleIoUTracker
    'bytetrack'  â†’ WARNING (not yet implemented) then SimpleIoUTracker
    Unknown name â†’ ValueError
    """
    name = model_name.lower()
    if name == "simple_iou":
        return SimpleIoUTracker(config)
    if name == "bytetrack":
        logger.warning(
            "bytetrack_not_implemented",
            extra={"fallback": "simple_iou"},
        )
        return SimpleIoUTracker(config)
    raise ValueError(
        f"Unknown person_tracking_model {model_name!r}. "
        f"Supported: 'simple_iou', 'bytetrack' (falls back to simple_iou)"
    )

