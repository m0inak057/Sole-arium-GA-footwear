"""Unit tests for VelocityBasedEventDetector and its helpers.

Synthetic keypoint trajectories are generated mathematically so tests require
no video files and no external models.

Gait simulation:
  - cycle_len=60 frames at FPS=30 â†’ 2 Hz step rate
  - heel.y   = 150 + 80*sin(2Ï€*i/cycle_len)  â†’ peaks at iâ‰ˆ15, 75, 135 ...
  - toe.y    = 150 + 80*sin(2Ï€*(i-20)/cycle_len) â†’ peaks 20 frames after each heel peak
"""
from __future__ import annotations

import math
from typing import Dict, List

import pytest

from gait.common.interfaces import GaitEvent, Keypoint, KeypointFrame
from gait.events.velocity_detector import (
    VelocityBasedEventDetector,
    _find_peaks,
    _smooth,
    create_event_detector,
)
from gait.pipeline.config import EventDetectionConfig

# â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

FPS = 30
CYCLE_LEN = 60   # frames per step (2 Hz at 30fps)
N_CYCLES = 4     # full cycles in synthetic data


def make_cfg(**overrides) -> EventDetectionConfig:
    params = dict(
        heel_strike_threshold=0.15,   # low prominence threshold â†’ easy to detect
        toe_off_threshold=0.15,
        event_confidence_min=0.5,
        min_frames_between_events=10,
        smoothing_window_frames=3,
    )
    params.update(overrides)
    return EventDetectionConfig(**params)


def make_kf(
    idx: int,
    heel_y: float,
    toe_y: float,
    confidence: float = 0.9,
    cam: str = "sagittal",
) -> KeypointFrame:
    kps: Dict[str, Keypoint] = {
        "left_heel":       Keypoint(x=100.0, y=heel_y, confidence=confidence, name="left_heel"),
        "left_foot_index": Keypoint(x=110.0, y=toe_y,  confidence=confidence, name="left_foot_index"),
        "right_heel":      Keypoint(x=200.0, y=heel_y, confidence=confidence, name="right_heel"),
        "right_foot_index":Keypoint(x=210.0, y=toe_y,  confidence=confidence, name="right_foot_index"),
    }
    return KeypointFrame(
        timestamp_ms=idx * (1000 // FPS),
        frame_index=idx,
        camera_view=cam,
        keypoints=kps,
        confidence=confidence,
    )


def make_cyclic_frames(n_cycles: int = N_CYCLES) -> List[KeypointFrame]:
    """Generate sinusoidal heel+toe trajectories with known peaks."""
    total = n_cycles * CYCLE_LEN + CYCLE_LEN // 4  # a bit past the last cycle
    frames = []
    for i in range(total):
        heel_y = 150.0 + 80.0 * math.sin(2 * math.pi * i / CYCLE_LEN)
        toe_y  = 150.0 + 80.0 * math.sin(2 * math.pi * (i - CYCLE_LEN // 3) / CYCLE_LEN)
        frames.append(make_kf(i, heel_y, toe_y))
    return frames


def make_event(
    event_type: str,
    frame_idx: int,
    foot: str = "L",
    ts: int = 0,
    confidence: float = 0.9,
) -> GaitEvent:
    return GaitEvent(
        event_type=event_type,
        frame_index=frame_idx,
        timestamp_ms=ts,
        foot=foot,
        confidence=confidence,
    )


# â”€â”€ _smooth helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestSmooth:
    def test_window_1_returns_copy(self):
        values = [1.0, 2.0, 3.0]
        assert _smooth(values, 1) == values

    def test_constant_signal_unchanged(self):
        values = [5.0] * 20
        result = _smooth(values, 5)
        assert all(abs(v - 5.0) < 1e-9 for v in result)

    def test_length_preserved(self):
        values = list(range(30))
        assert len(_smooth([float(v) for v in values], 5)) == 30

    def test_reduces_amplitude_of_noise(self):
        # Square wave: [0, 10, 0, 10, ...]
        values = [float(i % 2) * 10.0 for i in range(20)]
        smoothed = _smooth(values, 5)
        assert max(smoothed) < max(values)


# â”€â”€ _find_peaks helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestFindPeaks:
    def test_empty_returns_empty(self):
        assert _find_peaks([], min_distance=5, prominence_fraction=0.1) == []

    def test_too_short_returns_empty(self):
        assert _find_peaks([1.0, 2.0], min_distance=5, prominence_fraction=0.1) == []

    def test_single_peak_detected(self):
        # Clear peak in the middle
        values = [0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0]
        peaks = _find_peaks(values, min_distance=2, prominence_fraction=0.1)
        assert peaks == [3]

    def test_two_peaks_separated(self):
        values = [0, 0, 5, 0, 0, 5, 0, 0]
        values = [float(v) for v in values]
        peaks = _find_peaks(values, min_distance=2, prominence_fraction=0.1)
        assert len(peaks) == 2
        assert 2 in peaks and 5 in peaks

    def test_min_distance_prevents_close_peaks(self):
        # Two peaks only 3 apart; with min_distance=5 only 1 should survive
        values = [float(v) for v in [0, 5, 0, 5, 0, 0, 0, 0, 0, 0]]
        peaks = _find_peaks(values, min_distance=5, prominence_fraction=0.1)
        assert len(peaks) == 1

    def test_low_prominence_filtered_out(self):
        # Large peak at idx=3, tiny secondary bump at idx=10 (separation > min_distance=3).
        # y_range=10; min_prominence=0.1*10=1.0; tiny bump prominence=0.3 < 1.0 â†’ filtered.
        values = [float(v) for v in [0, 0, 0, 10, 0, 0, 0, 0, 0, 0, 0.3, 0, 0, 0]]
        peaks = _find_peaks(values, min_distance=3, prominence_fraction=0.1)
        assert peaks == [3]  # only the prominent peak survives

    def test_returns_ascending_order(self):
        values = [0, 10, 0, 0, 0, 10, 0, 0, 0, 10, 0]
        values = [float(v) for v in values]
        peaks = _find_peaks(values, min_distance=2, prominence_fraction=0.1)
        assert peaks == sorted(peaks)

    def test_flat_region_no_false_peaks(self):
        values = [3.0] * 20
        peaks = _find_peaks(values, min_distance=3, prominence_fraction=0.1)
        assert peaks == []


# â”€â”€ detect_heel_strikes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestDetectHeelStrikes:
    def test_empty_frames_returns_empty(self):
        det = VelocityBasedEventDetector(make_cfg())
        assert det.detect_heel_strikes([], "L") == []

    def test_wrong_foot_key_returns_empty(self):
        # Only right-foot keypoints; asking for left
        frames = make_cyclic_frames()
        stripped = [
            KeypointFrame(
                timestamp_ms=kf.timestamp_ms,
                frame_index=kf.frame_index,
                camera_view=kf.camera_view,
                keypoints={k: v for k, v in kf.keypoints.items() if k.startswith("right")},
                confidence=kf.confidence,
            )
            for kf in frames
        ]
        det = VelocityBasedEventDetector(make_cfg())
        assert det.detect_heel_strikes(stripped, "L") == []

    def test_invalid_foot_raises_value_error(self):
        det = VelocityBasedEventDetector(make_cfg())
        with pytest.raises(ValueError, match="foot must be"):
            det.detect_heel_strikes([], "X")

    def test_detects_expected_number_of_hs(self):
        frames = make_cyclic_frames(n_cycles=4)
        det = VelocityBasedEventDetector(make_cfg())
        hs = det.detect_heel_strikes(frames, "L")
        # Sinusoidal: one peak per CYCLE_LEN frames, expect ~4 peaks
        assert 3 <= len(hs) <= 5

    def test_event_type_is_heel_strike(self):
        frames = make_cyclic_frames()
        det = VelocityBasedEventDetector(make_cfg())
        hs = det.detect_heel_strikes(frames, "L")
        assert all(e.event_type == "heel_strike" for e in hs)

    def test_foot_assignment_left(self):
        frames = make_cyclic_frames()
        det = VelocityBasedEventDetector(make_cfg())
        hs = det.detect_heel_strikes(frames, "L")
        assert all(e.foot == "L" for e in hs)

    def test_foot_assignment_right(self):
        frames = make_cyclic_frames()
        det = VelocityBasedEventDetector(make_cfg())
        hs = det.detect_heel_strikes(frames, "R")
        assert all(e.foot == "R" for e in hs)

    def test_events_sorted_by_frame_index(self):
        frames = make_cyclic_frames()
        det = VelocityBasedEventDetector(make_cfg())
        hs = det.detect_heel_strikes(frames, "L")
        indices = [e.frame_index for e in hs]
        assert indices == sorted(indices)

    def test_confidence_below_threshold_skips_frame(self):
        # All keypoints have confidence=0.1 â†’ below event_confidence_min=0.5
        total = N_CYCLES * CYCLE_LEN
        frames = [
            make_kf(
                i,
                150.0 + 80.0 * math.sin(2 * math.pi * i / CYCLE_LEN),
                150.0,
                confidence=0.1,
            )
            for i in range(total)
        ]
        det = VelocityBasedEventDetector(make_cfg(event_confidence_min=0.5))
        hs = det.detect_heel_strikes(frames, "L")
        assert hs == []

    def test_min_frames_between_events_respected(self):
        frames = make_cyclic_frames()
        det = VelocityBasedEventDetector(make_cfg(min_frames_between_events=10))
        hs = det.detect_heel_strikes(frames, "L")
        for a, b in zip(hs, hs[1:]):
            assert b.frame_index - a.frame_index >= 10

    def test_timestamp_matches_frame(self):
        frames = make_cyclic_frames()
        det = VelocityBasedEventDetector(make_cfg())
        hs = det.detect_heel_strikes(frames, "L")
        ts_map = {kf.frame_index: kf.timestamp_ms for kf in frames}
        for e in hs:
            assert e.timestamp_ms == ts_map[e.frame_index]


# â”€â”€ detect_toe_offs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestDetectToeOffs:
    def test_empty_frames_returns_empty(self):
        det = VelocityBasedEventDetector(make_cfg())
        assert det.detect_toe_offs([], "L") == []

    def test_invalid_foot_raises_value_error(self):
        det = VelocityBasedEventDetector(make_cfg())
        with pytest.raises(ValueError, match="foot must be"):
            det.detect_toe_offs([], "Z")

    def test_event_type_is_toe_off(self):
        frames = make_cyclic_frames()
        det = VelocityBasedEventDetector(make_cfg())
        to = det.detect_toe_offs(frames, "L")
        assert all(e.event_type == "toe_off" for e in to)

    def test_detects_expected_number_of_to(self):
        frames = make_cyclic_frames(n_cycles=4)
        det = VelocityBasedEventDetector(make_cfg())
        to = det.detect_toe_offs(frames, "L")
        assert 3 <= len(to) <= 5

    def test_events_sorted_by_frame_index(self):
        frames = make_cyclic_frames()
        det = VelocityBasedEventDetector(make_cfg())
        to = det.detect_toe_offs(frames, "L")
        indices = [e.frame_index for e in to]
        assert indices == sorted(indices)

    def test_toe_events_follow_heel_events(self):
        """Each TO should be ~CYCLE_LEN//3 frames after the corresponding HS."""
        frames = make_cyclic_frames()
        det = VelocityBasedEventDetector(make_cfg())
        hs = det.detect_heel_strikes(frames, "L")
        to = det.detect_toe_offs(frames, "L")
        # At least the first TO should be after the first HS
        if hs and to:
            assert to[0].frame_index > hs[0].frame_index


# â”€â”€ segment_gait_cycles â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestSegmentGaitCycles:
    def _make_triplet(self, hs_frames, to_frames, foot="L", fps=30):
        """Build synthetic HS + TO event lists and minimal keypoint frames."""
        all_frames = sorted(set(hs_frames) | set(to_frames))
        ts_map = {i: i * (1000 // fps) for i in range(max(all_frames) + 2)}
        kf_frames = [
            KeypointFrame(
                timestamp_ms=ts_map[i],
                frame_index=i,
                camera_view="sagittal",
                keypoints={},
                confidence=0.9,
            )
            for i in range(max(all_frames) + 2)
        ]
        hs_events = [make_event("heel_strike", f, foot, ts_map[f]) for f in hs_frames]
        to_events = [make_event("toe_off", f, foot, ts_map[f]) for f in to_frames]
        return kf_frames, hs_events, to_events

    def test_empty_hs_returns_empty(self):
        det = VelocityBasedEventDetector(make_cfg())
        kfs, _, to_events = self._make_triplet([], [10])
        assert det.segment_gait_cycles(kfs, [], to_events, "L") == []

    def test_single_hs_returns_empty(self):
        det = VelocityBasedEventDetector(make_cfg())
        kfs, hs_events, to_events = self._make_triplet([10], [20])
        assert det.segment_gait_cycles(kfs, hs_events, to_events, "L") == []

    def test_two_hs_one_to_gives_one_cycle(self):
        det = VelocityBasedEventDetector(make_cfg())
        kfs, hs_events, to_events = self._make_triplet([0, 60], [30])
        cycles = det.segment_gait_cycles(kfs, hs_events, to_events, "L")
        assert len(cycles) == 1

    def test_cycle_frame_bounds(self):
        det = VelocityBasedEventDetector(make_cfg())
        kfs, hs_events, to_events = self._make_triplet([0, 60], [30])
        cycles = det.segment_gait_cycles(kfs, hs_events, to_events, "L")
        assert cycles[0].frame_start == 0
        assert cycles[0].frame_end == 60

    def test_stance_ends_at_toe_off(self):
        det = VelocityBasedEventDetector(make_cfg())
        kfs, hs, to = self._make_triplet([0, 60], [30])
        cycles = det.segment_gait_cycles(kfs, hs, to, "L")
        assert cycles[0].stance_frames[-1] == 30

    def test_swing_starts_after_toe_off(self):
        det = VelocityBasedEventDetector(make_cfg())
        kfs, hs, to = self._make_triplet([0, 60], [30])
        cycles = det.segment_gait_cycles(kfs, hs, to, "L")
        assert cycles[0].swing_frames[0] == 31

    def test_three_hs_two_to_gives_two_cycles(self):
        det = VelocityBasedEventDetector(make_cfg())
        kfs, hs, to = self._make_triplet([0, 60, 120], [30, 90])
        cycles = det.segment_gait_cycles(kfs, hs, to, "L")
        assert len(cycles) == 2

    def test_cycle_missing_to_is_skipped(self):
        det = VelocityBasedEventDetector(make_cfg())
        # Three HS pairs but only one TO (only between frames 0-60)
        kfs, hs, to = self._make_triplet([0, 60, 120], [30])
        cycles = det.segment_gait_cycles(kfs, hs, to, "L")
        assert len(cycles) == 1  # second pair (60-120) has no TO

    def test_stance_duration_positive(self):
        det = VelocityBasedEventDetector(make_cfg())
        kfs, hs, to = self._make_triplet([0, 60], [30])
        cycles = det.segment_gait_cycles(kfs, hs, to, "L")
        assert cycles[0].stance_duration_ms > 0

    def test_swing_duration_positive(self):
        det = VelocityBasedEventDetector(make_cfg())
        kfs, hs, to = self._make_triplet([0, 60], [30])
        cycles = det.segment_gait_cycles(kfs, hs, to, "L")
        assert cycles[0].swing_duration_ms > 0

    def test_confidence_is_min_of_three_events(self):
        det = VelocityBasedEventDetector(make_cfg())
        kfs = [
            KeypointFrame(
                timestamp_ms=i * 33,
                frame_index=i,
                camera_view="sagittal",
                keypoints={},
                confidence=0.9,
            )
            for i in range(70)
        ]
        hs = [
            make_event("heel_strike", 0, "L", 0, confidence=0.9),
            make_event("heel_strike", 60, "L", 2000, confidence=0.8),
        ]
        to = [make_event("toe_off", 30, "L", 1000, confidence=0.7)]
        cycles = det.segment_gait_cycles(kfs, hs, to, "L")
        assert cycles[0].confidence == pytest.approx(0.7)

    def test_foot_assigned_correctly(self):
        det = VelocityBasedEventDetector(make_cfg())
        kfs, hs, to = self._make_triplet([0, 60], [30], foot="R")
        cycles = det.segment_gait_cycles(kfs, hs, to, "R")
        assert cycles[0].foot == "R"

    def test_full_pipeline_from_cyclic_frames(self):
        """Integration: detect events then segment â€” end-to-end smoke test."""
        frames = make_cyclic_frames(n_cycles=4)
        det = VelocityBasedEventDetector(make_cfg())
        hs = det.detect_heel_strikes(frames, "L")
        to = det.detect_toe_offs(frames, "L")
        cycles = det.segment_gait_cycles(frames, hs, to, "L")
        # With 4-cycle data we expect at least 2 complete cycles
        assert len(cycles) >= 2
        for cycle in cycles:
            assert cycle.frame_start < cycle.frame_end
            assert len(cycle.stance_frames) > 0
            assert len(cycle.swing_frames) > 0


# â”€â”€ create_event_detector factory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestFactory:
    def test_velocity_based_returns_correct_type(self):
        det = create_event_detector("velocity_based", make_cfg())
        assert isinstance(det, VelocityBasedEventDetector)

    def test_case_insensitive(self):
        det = create_event_detector("Velocity_Based", make_cfg())
        assert isinstance(det, VelocityBasedEventDetector)

    def test_unknown_model_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown heel_strike_model"):
            create_event_detector("deep_gait", make_cfg())

    def test_error_includes_model_name(self):
        with pytest.raises(ValueError, match="openpose_gait"):
            create_event_detector("openpose_gait", make_cfg())

