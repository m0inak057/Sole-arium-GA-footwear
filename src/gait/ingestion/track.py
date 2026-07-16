"""Person tracking — locks onto the subject across frames using IoU matching.

SimpleIoUTracker strategy:
  1. Extract foreground blobs via cv2.connectedComponentsWithStats.
  2. Filter blobs below min_blob_area_px2.
  3. First detection: choose the largest blob as the initial track.
  4. Subsequent frames: find the blob with highest IoU to the last known bbox.
     - IoU >= iou_threshold → fresh track, confidence=1.0.
     - IoU < iou_threshold → return last-known bbox with decaying confidence.
  5. After max_lost_frames consecutive misses AFTER initialisation, or when no
     blob is ever found, fall back to a low-confidence full-frame track instead
     of aborting — the tracker never raises TrackingLostError.

Warmup guard:
  _handle_miss() will NOT increment lost_frames while frame_index < warmup_frames
  AND self._initialized is False.

ByteTrack is planned for Phase 2; the factory falls back to SimpleIoUTracker
with a WARNING so the pipeline does not fail when bytetrack is configured.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

import cv2
import numpy as np

from gait.common.geometry import bbox_area_px2, clip_bbox, compute_iou
from gait.common.interfaces import Frame
from gait.common.logging_utils import get_logger
from gait.common.types import PersonTrack
from gait.pipeline.config import IngestionConfig

logger = get_logger(__name__)

# Type alias: (x, y, w, h)
_BBox = Tuple[int, int, int, int]

# Default warmup window — must match the bg subtractor's stabilisation period.
_DEFAULT_WARMUP_FRAMES = 50

# Stale-bbox linear extrapolation is capped at this many frames; beyond it we
# stop extrapolating and freeze at the last known (non-extrapolated) position
# to avoid drifting far from the subject during a long occlusion.
_MAX_EXTRAPOLATION_FRAMES = 10


def _bbox_center(bbox: _BBox) -> Tuple[float, float]:
    x, y, w, h = bbox
    return (x + w / 2.0, y + h / 2.0)


class PersonTracker(ABC):
    """Abstract tracker — locks onto the subject across frames."""

    @abstractmethod
    def update(
        self,
        frame: Frame,
        foreground_mask: np.ndarray,
    ) -> Optional[PersonTrack]:
        """Update with the current frame's foreground mask.

        Returns PersonTrack when the subject is found (confidence < 1.0 when
        using a stale last-known or full-frame fallback bbox), or None only
        during early warmup before any subject has been detected. Never raises
        — once past warmup it always returns a track, falling back to a
        low-confidence full-frame bbox if blob detection fails.
        """

    @abstractmethod
    def reset(self) -> None:
        """Reset all tracker state."""


class SimpleIoUTracker(PersonTracker):
    """Minimal IoU-based tracker for the MVP.

    Parameters
    ----------
    config : IngestionConfig
        Pipeline configuration (iou_threshold, max_lost_frames, etc.).
    warmup_frames : int
        Number of frames at the start of a video during which background
        subtractor output is unreliable.  _handle_miss() is a silent no-op
        during this window if tracking has not yet initialized.
    """

    def __init__(
        self,
        config: IngestionConfig,
        warmup_frames: int = _DEFAULT_WARMUP_FRAMES,
    ) -> None:
        self._config = config
        self._warmup_frames = warmup_frames
        self._track: Optional[PersonTrack] = None
        self._lost_frames = 0
        # Set to True on the first successful detection; used to distinguish
        # "still warming up" misses from "lost after locking on" misses.
        self._initialized = False
        # Fires once per tracker instance (i.e. once per camera per session) to
        # confirm whether the incoming mask is empty, noisy, or has real content.
        self._blob_debug_logged = False
        # Per-frame (center_x, center_y) velocity between the last two fresh
        # detections — used to linearly extrapolate the bbox position while
        # the tracker is using a stale (last-known) bbox.
        self._velocity: Tuple[float, float] = (0.0, 0.0)

    def update(
        self,
        frame: Frame,
        foreground_mask: np.ndarray,
    ) -> Optional[PersonTrack]:
        blobs = self._extract_blobs(foreground_mask)

        if not blobs:
            return self._handle_miss(frame.frame_index, frame)

        if self._track is None:
            # First detection — initialise with the largest blob
            best_bbox = max(blobs, key=bbox_area_px2)
            self._track = PersonTrack(
                track_id=1,
                bbox=best_bbox,
                confidence=1.0,
                frames_since_update=0,
            )
            self._lost_frames = 0
            self._initialized = True
            return self._track

        # Find blob with highest IoU to current track
        best_bbox = max(blobs, key=lambda b: compute_iou(b, self._track.bbox))
        best_iou = compute_iou(best_bbox, self._track.bbox)

        if best_iou >= self._config.iou_threshold:
            self._update_velocity(self._track.bbox, best_bbox)
            self._track = PersonTrack(
                track_id=self._track.track_id,
                bbox=best_bbox,
                confidence=1.0,
                frames_since_update=0,
            )
            self._lost_frames = 0
            return self._track

        return self._handle_miss(frame.frame_index, frame)

    def reset(self) -> None:
        self._track = None
        self._lost_frames = 0
        self._initialized = False

    # ── Private ────────────────────────────────────────────────────────────────

    def _extract_blobs(self, mask: np.ndarray) -> List[_BBox]:
        """Return (x, y, w, h) bboxes for all blobs above min_blob_area_px2."""
        num_labels, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)

        if not self._blob_debug_logged:
            self._blob_debug_logged = True
            non_zero_px = int(np.count_nonzero(mask))
            largest_area_px2 = (
                int(stats[1:, cv2.CC_STAT_AREA].max()) if num_labels > 1 else 0
            )
            logger.warning(
                "tracker_blob_debug_first_frame",
                extra={
                    "non_zero_pixels": non_zero_px,
                    "num_components": num_labels - 1,  # exclude background label 0
                    "largest_component_area_px2": largest_area_px2,
                    "min_blob_area_px2_threshold": self._config.min_blob_area_px2,
                },
            )

        bboxes: List[_BBox] = []
        for label in range(1, num_labels):  # skip label 0 (background)
            x = int(stats[label, cv2.CC_STAT_LEFT])
            y = int(stats[label, cv2.CC_STAT_TOP])
            w = int(stats[label, cv2.CC_STAT_WIDTH])
            h = int(stats[label, cv2.CC_STAT_HEIGHT])
            if w * h >= self._config.min_blob_area_px2:
                bboxes.append((x, y, w, h))
        return bboxes

    def _update_velocity(self, old_bbox: _BBox, new_bbox: _BBox) -> None:
        """Recompute per-frame center velocity from the last two fresh bboxes."""
        old_cx, old_cy = _bbox_center(old_bbox)
        new_cx, new_cy = _bbox_center(new_bbox)
        self._velocity = (new_cx - old_cx, new_cy - old_cy)

    def _extrapolated_stale_bbox(self, frame: Optional[Frame]) -> _BBox:
        """Linearly extrapolate the last-known bbox center using self._velocity.

        Capped at _MAX_EXTRAPOLATION_FRAMES: beyond that, extrapolation stops
        and the original last-known bbox is returned unchanged, to avoid
        drifting far from the subject during a long occlusion.
        """
        last_bbox = self._track.bbox
        if self._lost_frames > _MAX_EXTRAPOLATION_FRAMES:
            return last_bbox

        vx, vy = self._velocity
        if vx == 0.0 and vy == 0.0:
            return last_bbox

        cx, cy = _bbox_center(last_bbox)
        w, h = last_bbox[2], last_bbox[3]
        new_cx = cx + vx * self._lost_frames
        new_cy = cy + vy * self._lost_frames
        extrapolated = (int(new_cx - w / 2.0), int(new_cy - h / 2.0), w, h)

        if frame is not None:
            fh, fw = frame.image.shape[:2]
            extrapolated = clip_bbox(extrapolated, fw, fh)
            if extrapolated[2] <= 0 or extrapolated[3] <= 0:
                # Extrapolated fully off-frame — fall back to last-known position.
                return last_bbox

        return extrapolated

    def _full_frame_bbox(self, frame: Frame) -> _BBox:
        """Return a bbox covering the entire frame — used as a last-resort
        fallback so pose estimation always has a region to work with, even
        when blob detection finds nothing (short/noisy/low-res video)."""
        h, w = frame.image.shape[:2]
        return (0, 0, w, h)

    def _handle_miss(self, frame_index: int, frame: Optional[Frame] = None) -> Optional[PersonTrack]:
        """Handle a frame where no valid blob detection was found.

        The tracker never raises TrackingLostError and never permanently
        gives up: once past warmup, a miss falls back to a low-confidence
        track — either the last-known bbox (decaying confidence) or, if we
        have never locked onto anyone at all, the full frame. This lets
        pose estimation proceed on any video, however short or noisy,
        instead of aborting the whole session.

        During warmup (frame_index < warmup_frames) AND before first init,
        misses are silently discarded without incrementing lost_frames.
        """
        logger.warning(
            "tracker_handle_miss_called",
            extra={"frame_index": frame_index, "has_frame": frame is not None},
        )
        # ── Warmup guard ───────────────────────────────────────────────────────
        # If the background subtractor has not yet stabilised AND we have never
        # successfully locked onto a person, treat this as a benign warmup miss.
        # Do NOT increment lost_frames.
        if not self._initialized and frame_index < self._warmup_frames:
            logger.debug(
                "tracker_warmup_miss",
                extra={
                    "frame_index": frame_index,
                    "warmup_frames": self._warmup_frames,
                    "lost_frames": self._lost_frames,
                },
            )
            return None

        # ── Normal miss handling (post-warmup or post-init) ────────────────────
        self._lost_frames += 1

        if self._initialized and self._lost_frames >= self._config.max_lost_frames:
            # Previously raised TrackingLostError here. Now: fall back to a
            # low-confidence full-frame track instead of aborting the session.
            logger.warning(
                "tracker_fallback_full_frame",
                extra={
                    "frame_index": frame_index,
                    "lost_frames": self._lost_frames,
                    "note": "subject lost beyond max_lost_frames; using full-frame fallback",
                },
            )
            if frame is not None:
                return PersonTrack(
                    track_id=self._track.track_id if self._track else 1,
                    bbox=self._full_frame_bbox(frame),
                    confidence=0.1,
                    frames_since_update=self._lost_frames,
                )

        if self._track is None:
            # Past warmup window but still haven't found anyone via blob
            # detection — fall back to the full frame so downstream pose
            # estimation still has something to work with.
            logger.warning(
                "tracker_no_blob_full_frame_fallback",
                extra={
                    "frame_index": frame_index,
                    "warmup_frames": self._warmup_frames,
                    "lost_frames": self._lost_frames,
                },
            )
            if frame is not None:
                return PersonTrack(
                    track_id=1,
                    bbox=self._full_frame_bbox(frame),
                    confidence=0.1,
                    frames_since_update=self._lost_frames,
                )
            return None

        # Return stale bbox (linearly extrapolated from last known velocity,
        # capped at _MAX_EXTRAPOLATION_FRAMES) with linearly decaying confidence
        decay = 1.0 - (self._lost_frames / self._config.max_lost_frames)
        stale = PersonTrack(
            track_id=self._track.track_id,
            bbox=self._extrapolated_stale_bbox(frame),
            confidence=max(0.05, decay),
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
    warmup_frames: int = _DEFAULT_WARMUP_FRAMES,
) -> PersonTracker:
    """Factory — return the requested PersonTracker.

    'simple_iou' → SimpleIoUTracker
    'bytetrack'  → WARNING (not yet implemented) then SimpleIoUTracker
    Unknown name → ValueError
    """
    name = model_name.lower()
    if name == "simple_iou":
        return SimpleIoUTracker(config, warmup_frames=warmup_frames)
    if name == "bytetrack":
        logger.warning(
            "bytetrack_not_implemented",
            extra={"fallback": "simple_iou"},
        )
        return SimpleIoUTracker(config, warmup_frames=warmup_frames)
    raise ValueError(
        f"Unknown person_tracking_model {model_name!r}. "
        f"Supported: 'simple_iou', 'bytetrack' (falls back to simple_iou)"
    )
