"""Velocity-based gait event detector.

Algorithm (position peak detection):
- Heel-strike (HS): local maximum of heel.y â€” heel at lowest point in frame
  (image y increases downward, so maximum y = ground level).
- Toe-off (TO):     local maximum of foot_index.y â€” toe at lowest point before liftoff.

Both use a moving-average pre-smoother and a prominence filter to suppress noise.
Peak selection uses a greedy largest-first strategy so closely spaced spurious peaks
are dropped in favour of the most prominent candidate within each min_distance window.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from gait.common.interfaces import (
    EventDetector,
    GaitCycle,
    GaitEvent,
    KeypointFrame,
)
from gait.common.logging_utils import get_logger
from gait.pipeline.config import EventDetectionConfig

logger = get_logger(__name__)

# Keypoint name templates for each foot
_HEEL = {"L": "left_heel", "R": "right_heel"}
_TOE = {"L": "left_foot_index", "R": "right_foot_index"}


def _smooth(values: List[float], window: int) -> List[float]:
    """Simple centred moving-average smoothing."""
    if window <= 1 or len(values) <= window:
        return list(values)
    half = window // 2
    n = len(values)
    result = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        result.append(sum(values[lo:hi]) / (hi - lo))
    return result


def _find_peaks(
    values: List[float],
    min_distance: int,
    prominence_fraction: float,
) -> List[int]:
    """Find indices of prominent local maxima with minimum separation.

    Prominence is measured relative to the local minimum within Â±min_distance
    of each candidate peak, and filtered against `prominence_fraction * y_range`.

    Returns indices in ascending order.
    """
    n = len(values)
    if n < 3:
        return []

    y_range = max(values) - min(values)
    min_prominence = prominence_fraction * y_range

    candidates: List[Tuple[int, float, float]] = []  # (idx, height, prominence)
    for i in range(1, n - 1):
        if values[i] > values[i - 1] and values[i] >= values[i + 1]:
            lo = max(0, i - min_distance)
            hi = min(n, i + min_distance + 1)
            left_min = min(values[lo:i]) if lo < i else values[i]
            right_min = min(values[i + 1 : hi]) if i + 1 < hi else values[i]
            prominence = values[i] - min(left_min, right_min)
            if prominence >= min_prominence:
                candidates.append((i, values[i], prominence))

    # Greedy selection: process most prominent first, enforce min_distance
    candidates.sort(key=lambda c: -c[2])
    selected: List[int] = []
    for idx, _, _ in candidates:
        if all(abs(idx - s) >= min_distance for s in selected):
            selected.append(idx)

    return sorted(selected)


def _extract_y_traj(
    keypoint_frames: List[KeypointFrame],
    keypoint_name: str,
    min_confidence: float,
) -> Tuple[List[int], List[float], Dict[int, int]]:
    """Extract (frame_indices, y_values, frameâ†’timestamp_ms) for a keypoint.

    Frames where the keypoint is absent or below min_confidence are skipped.
    """
    indices: List[int] = []
    y_values: List[float] = []
    ts_map: Dict[int, int] = {}
    for kf in keypoint_frames:
        kp = kf.keypoints.get(keypoint_name)
        if kp is not None and kp.confidence >= min_confidence:
            indices.append(kf.frame_index)
            y_values.append(kp.y)
            ts_map[kf.frame_index] = kf.timestamp_ms
    return indices, y_values, ts_map


def _confidence_at(
    keypoint_frames: List[KeypointFrame],
    frame_index: int,
    keypoint_name: str,
) -> float:
    """Return keypoint confidence at a specific frame (0.0 if absent)."""
    for kf in keypoint_frames:
        if kf.frame_index == frame_index:
            kp = kf.keypoints.get(keypoint_name)
            return kp.confidence if kp else 0.0
    return 0.0


class VelocityBasedEventDetector(EventDetector):
    """MVP gait event detector using y-position peak detection."""

    def __init__(self, config: EventDetectionConfig) -> None:
        self._cfg = config

    # â”€â”€ EventDetector ABC â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def detect_heel_strikes(
        self, keypoint_frames: List[KeypointFrame], foot: str
    ) -> List[GaitEvent]:
        """Detect heel-strike events as local maxima of heel.y."""
        if foot not in ("L", "R"):
            raise ValueError(f"foot must be 'L' or 'R', got {foot!r}")

        heel_key = _HEEL[foot]
        indices, y_vals, ts_map = _extract_y_traj(
            keypoint_frames, heel_key, self._cfg.event_confidence_min
        )
        if not y_vals:
            return []

        smoothed = _smooth(y_vals, self._cfg.smoothing_window_frames)
        peak_positions = _find_peaks(
            smoothed,
            min_distance=self._cfg.min_frames_between_events,
            prominence_fraction=self._cfg.heel_strike_threshold,
        )

        events: List[GaitEvent] = []
        for pos in peak_positions:
            frame_idx = indices[pos]
            conf = _confidence_at(keypoint_frames, frame_idx, heel_key)
            events.append(
                GaitEvent(
                    event_type="heel_strike",
                    frame_index=frame_idx,
                    timestamp_ms=ts_map[frame_idx],
                    foot=foot,
                    confidence=conf,
                )
            )

        logger.info(
            "heel_strikes_detected",
            extra={"foot": foot, "count": len(events)},
        )
        return events

    def detect_toe_offs(
        self, keypoint_frames: List[KeypointFrame], foot: str
    ) -> List[GaitEvent]:
        """Detect toe-off events as local maxima of foot_index.y."""
        if foot not in ("L", "R"):
            raise ValueError(f"foot must be 'L' or 'R', got {foot!r}")

        toe_key = _TOE[foot]
        indices, y_vals, ts_map = _extract_y_traj(
            keypoint_frames, toe_key, self._cfg.event_confidence_min
        )
        if not y_vals:
            return []

        smoothed = _smooth(y_vals, self._cfg.smoothing_window_frames)
        peak_positions = _find_peaks(
            smoothed,
            min_distance=self._cfg.min_frames_between_events,
            prominence_fraction=self._cfg.toe_off_threshold,
        )

        events: List[GaitEvent] = []
        for pos in peak_positions:
            frame_idx = indices[pos]
            conf = _confidence_at(keypoint_frames, frame_idx, toe_key)
            events.append(
                GaitEvent(
                    event_type="toe_off",
                    frame_index=frame_idx,
                    timestamp_ms=ts_map[frame_idx],
                    foot=foot,
                    confidence=conf,
                )
            )

        logger.info(
            "toe_offs_detected",
            extra={"foot": foot, "count": len(events)},
        )
        return events

    def segment_gait_cycles(
        self,
        keypoint_frames: List[KeypointFrame],
        heel_strikes: List[GaitEvent],
        toe_offs: List[GaitEvent],
        foot: str,
    ) -> List[GaitCycle]:
        """Segment HS â†’ TO â†’ HS triplets into GaitCycle objects.

        One cycle = the interval between two consecutive HS events on the same
        foot, provided exactly one TO falls between them.  Cycles with no TO
        between a pair of HS events are skipped (logged at DEBUG).
        """
        hs = sorted(heel_strikes, key=lambda e: e.frame_index)
        to = sorted(toe_offs, key=lambda e: e.frame_index)

        ts_map: Dict[int, int] = {kf.frame_index: kf.timestamp_ms for kf in keypoint_frames}

        cycles: List[GaitCycle] = []
        for cycle_id, (hs_start, hs_end) in enumerate(zip(hs, hs[1:])):
            # TO must fall strictly between the two HS
            to_between = [
                e for e in to
                if hs_start.frame_index < e.frame_index < hs_end.frame_index
            ]
            if not to_between:
                logger.debug(
                    "cycle_skipped_no_toe_off",
                    extra={
                        "cycle_id": cycle_id,
                        "foot": foot,
                        "hs_start": hs_start.frame_index,
                        "hs_end": hs_end.frame_index,
                    },
                )
                continue

            to_event = to_between[0]  # first TO after HS start

            stance_frames = list(range(hs_start.frame_index, to_event.frame_index + 1))
            swing_frames = list(range(to_event.frame_index + 1, hs_end.frame_index + 1))

            cycle_kps = {
                kf.frame_index: kf.keypoints
                for kf in keypoint_frames
                if hs_start.frame_index <= kf.frame_index <= hs_end.frame_index
            }

            stance_ms = float(
                ts_map.get(to_event.frame_index, 0) - ts_map.get(hs_start.frame_index, 0)
            )
            swing_ms = float(
                ts_map.get(hs_end.frame_index, 0) - ts_map.get(to_event.frame_index, 0)
            )

            confidence = min(
                hs_start.confidence, hs_end.confidence, to_event.confidence
            )

            cycles.append(
                GaitCycle(
                    cycle_id=cycle_id,
                    foot=foot,
                    frame_start=hs_start.frame_index,
                    frame_end=hs_end.frame_index,
                    stance_frames=stance_frames,
                    swing_frames=swing_frames,
                    keypoints=cycle_kps,
                    confidence=confidence,
                    stance_duration_ms=stance_ms,
                    swing_duration_ms=swing_ms,
                )
            )

        logger.info(
            "gait_cycles_segmented",
            extra={"foot": foot, "cycle_count": len(cycles)},
        )
        return cycles


def create_event_detector(
    model: str, config: EventDetectionConfig
) -> VelocityBasedEventDetector:
    """Factory: return the event detector for `model`.

    Currently only 'velocity_based' is supported. Extend here for future models.
    """
    if model.lower() == "velocity_based":
        return VelocityBasedEventDetector(config)
    raise ValueError(
        f"Unknown heel_strike_model: {model!r}. Supported: 'velocity_based'"
    )

