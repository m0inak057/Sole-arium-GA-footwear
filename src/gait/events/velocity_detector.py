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

import statistics
from typing import Any, Dict, List, Optional, Tuple

from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks as _scipy_find_peaks

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

# Heel-keypoint fallback chain, tried in priority order. MediaPipe presence
# for the heel landmark specifically can be low/absent in side-view footage
# (partial occlusion, ROI edge); the ankle or foot-index landmark is often
# detected confidently even when the heel is not.
_HEEL_FALLBACK_CHAIN = {
    "L": ["left_heel", "left_ankle", "left_foot_index"],
    "R": ["right_heel", "right_ankle", "right_foot_index"],
}


def _select_best_keypoint(
    keypoint_frames: List[KeypointFrame],
    candidates: List[str],
    min_confidence: float,
) -> str:
    """Return whichever candidate keypoint name has the most frames at/above min_confidence.

    Candidates are tried in priority order; ties keep the earlier (higher
    priority) candidate since replacement requires a strictly higher count.
    """
    best_name = candidates[0]
    best_count = -1
    for name in candidates:
        count = sum(
            1
            for kf in keypoint_frames
            if (kp := kf.keypoints.get(name)) is not None and kp.confidence >= min_confidence
        )
        if count > best_count:
            best_count = count
            best_name = name
    return best_name


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


def _count_local_maxima(values: List[float]) -> int:
    """Count raw local maxima before any prominence filtering (diagnostics only)."""
    n = len(values)
    if n < 3:
        return 0
    return sum(
        1 for i in range(1, n - 1) if values[i] > values[i - 1] and values[i] >= values[i + 1]
    )


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
        logger.info(
            "peak_detection_debug",
            extra={
                "trajectory_length": n,
                "y_min": None,
                "y_max": None,
                "y_range": None,
                "prominence_fraction": prominence_fraction,
                "min_prominence_px": None,
                "raw_candidate_peaks": 0,
                "peaks_after_prominence_filter": 0,
            },
        )
        return []

    y_min = min(values)
    y_max = max(values)
    y_range = y_max - y_min
    min_prominence = prominence_fraction * y_range

    raw_candidate_count = 0
    candidates: List[Tuple[int, float, float]] = []  # (idx, height, prominence)
    for i in range(1, n - 1):
        if values[i] > values[i - 1] and values[i] >= values[i + 1]:
            raw_candidate_count += 1
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

    result = sorted(selected)

    logger.info(
        "peak_detection_debug",
        extra={
            "trajectory_length": n,
            "y_min": y_min,
            "y_max": y_max,
            "y_range": y_range,
            "prominence_fraction": prominence_fraction,
            "min_prominence_px": min_prominence,
            "raw_candidate_peaks": raw_candidate_count,
            "peaks_after_prominence_filter": len(candidates),
            "peaks_after_min_distance": len(result),
        },
    )

    return result


def _find_peaks_with_fallback(
    values: List[float],
    min_distance: int,
    prominence_fraction: float,
) -> Tuple[List[int], Dict[str, Any]]:
    """Primary prominence-based peak detection; if it finds zero peaks, fall
    back to scipy.signal.find_peaks using only a minimum-distance constraint
    and a median-height threshold. Catches periodic gait patterns with very
    small vertical amplitude (e.g. posterior/anterior camera views) that the
    prominence filter rejects outright.

    Returns (peak_indices, debug_stats) â€” debug_stats is suitable for
    inclusion in a summary log without re-deriving trajectory statistics.
    """
    n = len(values)
    y_range = (max(values) - min(values)) if n > 0 else 0.0
    stats: Dict[str, Any] = {
        "prominence_fraction": prominence_fraction,
        "min_prominence_px": prominence_fraction * y_range,
        "raw_candidate_peaks": _count_local_maxima(values),
        "fallback_used": False,
        "fallback_peaks_found": 0,
    }

    primary = _find_peaks(values, min_distance, prominence_fraction)
    if primary or n < 3:
        return primary, stats

    median_height = statistics.median(values)
    fallback_indices, _ = _scipy_find_peaks(
        values, distance=max(1, min_distance), height=median_height
    )
    fallback_list = sorted(int(i) for i in fallback_indices)

    stats["fallback_used"] = True
    stats["fallback_peaks_found"] = len(fallback_list)

    logger.info(
        "peak_detection_fallback_used",
        extra={
            "trajectory_length": n,
            "median_height": median_height,
            "min_distance": min_distance,
            "fallback_peaks_found": len(fallback_list),
        },
    )

    return fallback_list, stats


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
    present_confidences: List[float] = []

    for kf in keypoint_frames:
        kp = kf.keypoints.get(keypoint_name)
        if kp is not None:
            present_confidences.append(kp.confidence)
        if kp is not None and kp.confidence >= min_confidence:
            indices.append(kf.frame_index)
            y_values.append(kp.y)
            ts_map[kf.frame_index] = kf.timestamp_ms

    logger.info(
        "trajectory_extraction_debug",
        extra={
            "keypoint_name": keypoint_name,
            "total_frames": len(keypoint_frames),
            "frames_with_keypoint": len(present_confidences),
            "frames_above_threshold": len(y_values),
            "min_confidence_threshold": min_confidence,
            "confidence_min": min(present_confidences) if present_confidences else None,
            "confidence_max": max(present_confidences) if present_confidences else None,
            "confidence_mean": (
                sum(present_confidences) / len(present_confidences)
                if present_confidences
                else None
            ),
        },
    )

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
        # Per-signal peak-detection stats from the most recent detect_*() call,
        # keyed e.g. "heel_L", "toe_R" â€” lets callers (orchestrator summary log)
        # report the prominence threshold and raw candidate count actually used
        # without re-deriving them.
        self._last_peak_debug: Dict[str, Dict[str, Any]] = {}

    def get_peak_debug_summary(self) -> Dict[str, Dict[str, Any]]:
        """Return the most recent per-signal peak-detection stats."""
        return dict(self._last_peak_debug)

    # â”€â”€ EventDetector ABC â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def detect_heel_strikes(
        self, keypoint_frames: List[KeypointFrame], foot: str
    ) -> List[GaitEvent]:
        """Detect heel-strike events as local maxima of heel.y."""
        if foot not in ("L", "R"):
            raise ValueError(f"foot must be 'L' or 'R', got {foot!r}")

        heel_key = _select_best_keypoint(
            keypoint_frames, _HEEL_FALLBACK_CHAIN[foot], self._cfg.event_confidence_min
        )
        indices, y_vals, ts_map = _extract_y_traj(
            keypoint_frames, heel_key, self._cfg.event_confidence_min
        )
        if not y_vals:
            return []

        # Gaussian pre-smoothing (sigma=2) ahead of the moving-average pass:
        # a jittery ROI crop introduces high-frequency noise that can obscure
        # genuine heel-strike valleys before they reach peak detection.
        gaussian_smoothed = list(gaussian_filter1d(y_vals, sigma=2))
        smoothed = _smooth(gaussian_smoothed, self._cfg.smoothing_window_frames)
        peak_positions, peak_stats = _find_peaks_with_fallback(
            smoothed,
            min_distance=self._cfg.min_frames_between_events,
            prominence_fraction=self._cfg.heel_strike_threshold,
        )
        self._last_peak_debug[f"heel_{foot}"] = peak_stats

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
        peak_positions, peak_stats = _find_peaks_with_fallback(
            smoothed,
            min_distance=self._cfg.min_frames_between_events,
            prominence_fraction=self._cfg.toe_off_threshold,
        )
        self._last_peak_debug[f"toe_{foot}"] = peak_stats

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
                    quality_flag="COMPLETE",
                )
            )

        # Partial-cycle fallback: a short clip may contain only one heel
        # strike per foot, which can never form a complete HS->TO->HS cycle
        # (zip(hs, hs[1:]) is empty when len(hs) < 2). Rather than discard
        # this real, single-stride data, anchor a partial cycle on that one
        # heel strike and the nearest toe-off after it. No closing heel
        # strike means no swing-phase duration is known, so this cycle is
        # stance-only and tagged at reduced confidence.
        if not cycles and len(hs) == 1:
            hs_only = hs[0]
            to_after = [e for e in to if e.frame_index > hs_only.frame_index]
            if to_after:
                to_event = min(to_after, key=lambda e: e.frame_index)
                stance_frames = list(range(hs_only.frame_index, to_event.frame_index + 1))
                cycle_kps = {
                    kf.frame_index: kf.keypoints
                    for kf in keypoint_frames
                    if hs_only.frame_index <= kf.frame_index <= to_event.frame_index
                }
                stance_ms = float(
                    ts_map.get(to_event.frame_index, 0) - ts_map.get(hs_only.frame_index, 0)
                )
                cycles.append(
                    GaitCycle(
                        cycle_id=0,
                        foot=foot,
                        frame_start=hs_only.frame_index,
                        frame_end=to_event.frame_index,
                        stance_frames=stance_frames,
                        swing_frames=[],
                        keypoints=cycle_kps,
                        confidence=0.3,
                        stance_duration_ms=stance_ms,
                        swing_duration_ms=None,
                        quality_flag="PARTIAL_CYCLE",
                    )
                )
                logger.info(
                    "partial_cycle_formed",
                    extra={
                        "foot": foot,
                        "hs_frame": hs_only.frame_index,
                        "to_frame": to_event.frame_index,
                    },
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

