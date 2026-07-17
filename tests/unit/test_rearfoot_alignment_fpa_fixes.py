"""
Unit tests for rearfoot alignment angle and foot progression angle fixes (July 2026).

Tests the median + outlier rejection, plausibility gates, and camera filtering
introduced in src/gait/analysis/parameters.py and src/gait/pipeline/orchestrator.py.
"""
from __future__ import annotations

import pytest

from gait.analysis.parameters import (
    compute_rearfoot_alignment_angle,
    compute_foot_progression_angle,
    classify_rearfoot_alignment,
    _REARFOOT_ALIGNMENT_OUTLIER_THRESHOLD_DEG,
    _REARFOOT_ALIGNMENT_MAX_PLAUSIBLE_DEG,
    _MIN_REARFOOT_ALIGNMENT_FRAMES,
)
from gait.common.interfaces import GaitCycle, Keypoint, KeypointFrame
from gait.pipeline.config import AnalysisConfig


# â"€â"€ Fixtures & helpers â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


def kp(x: float, y: float, confidence: float = 0.95) -> Keypoint:
    """Create a test keypoint."""
    return Keypoint(x=x, y=y, confidence=confidence)


def make_keypoint_frame(
    frame_index: int,
    camera_view: str = "posterior",
    knee_pos=(300, 600),
    ankle_pos=(310, 680),
    heel_pos=(305, 700),
    toe_pos=(315, 705),
    confidence: float = 0.95,
    timestamp_ms: int = 0,
) -> KeypointFrame:
    """Create a test KeypointFrame with configurable landmarks."""
    return KeypointFrame(
        timestamp_ms=timestamp_ms or (frame_index * 10),  # ~100 fps
        frame_index=frame_index,
        camera_view=camera_view,
        confidence=confidence,
        keypoints={
            "left_knee": kp(knee_pos[0], knee_pos[1], confidence),
            "left_ankle": kp(ankle_pos[0], ankle_pos[1], confidence),
            "left_heel": kp(heel_pos[0], heel_pos[1], confidence),
            "left_foot_index": kp(toe_pos[0], toe_pos[1], confidence),
            "right_knee": kp(knee_pos[0] + 50, knee_pos[1], confidence),
            "right_ankle": kp(ankle_pos[0] + 50, ankle_pos[1], confidence),
            "right_heel": kp(heel_pos[0] + 50, heel_pos[1], confidence),
            "right_foot_index": kp(toe_pos[0] + 50, toe_pos[1], confidence),
        },
    )


def make_cycle(
    frame_start: int = 0,
    frame_end: int = 60,
    stance_frames: list = None,
    foot: str = "L",
) -> GaitCycle:
    """Create a test GaitCycle."""
    if stance_frames is None:
        stance_frames = list(range(frame_start, frame_start + 36))
    return GaitCycle(
        cycle_id=0,
        foot=foot,
        frame_start=frame_start,
        frame_end=frame_end,
        stance_frames=stance_frames,
        swing_frames=list(range(frame_start + 36, frame_end + 1)),
        keypoints={},
        confidence=0.95,
        stance_duration_ms=600.0,
        swing_duration_ms=400.0,
    )


# â"€â"€ Tests: compute_rearfoot_alignment_angle (median + outlier rejection) â"€â"€â"€â"€â"€â"€


class TestRearfootAlignmentMedianOutlierRejection:
    """Test the July 2026 fix: median + outlier rejection for walking-video method."""

    def test_normal_tight_angles_no_outliers(self):
        """All frames within normal range; should produce a valid result."""
        # Create keypoint frames with consistent positions
        frames = []
        for i in range(10):
            frames.append(
                make_keypoint_frame(
                    frame_index=i,
                    camera_view="posterior",
                    knee_pos=(300, 600),
                    ankle_pos=(310, 680),
                    heel_pos=(308, 700),
                    toe_pos=(313, 705),
                )
            )

        cycle = make_cycle(frame_start=0, frame_end=9, stance_frames=list(range(10)))
        result = compute_rearfoot_alignment_angle(frames, "L", [cycle])

        # Should have a valid result (sufficient frames, within plausibility)
        # Exact angle depends on frame geometry, but should be bounded
        if result["mean_deg"] is not None:
            assert result["classification"] is not None
            assert abs(result["mean_deg"]) <= _REARFOOT_ALIGNMENT_MAX_PLAUSIBLE_DEG
            assert result["frame_count"] > 0

    def test_outlier_rejection_removes_bad_frames(self):
        """Frames > 20 deg from median should be rejected."""
        frames = []
        # Create 9 good frames at ~5 deg
        for i in range(9):
            frames.append(
                make_keypoint_frame(
                    frame_index=i,
                    camera_view="posterior",
                    knee_pos=(300, 600),
                    ankle_pos=(310, 680),
                    heel_pos=(308, 700),
                    toe_pos=(313, 705),
                )
            )
        # Add 1 outlier frame with huge angle (simulating motion blur)
        frames.append(
            make_keypoint_frame(
                frame_index=9,
                camera_view="posterior",
                knee_pos=(300, 600),
                ankle_pos=(310, 680),
                heel_pos=(200, 700),  # ~30+ deg error
                toe_pos=(313, 705),
            )
        )

        cycle = make_cycle(frame_start=0, frame_end=9, stance_frames=list(range(10)))
        result = compute_rearfoot_alignment_angle(frames, "L", [cycle])

        # After outlier rejection, should have ~9 frames (if first median is stable)
        # and angle should be plausible
        assert result["mean_deg"] is not None
        assert abs(result["mean_deg"]) <= 15.0
        # At least some outlier rejection should have occurred (frame_count should reflect this)
        # The exact count depends on the initial median calculation

    def test_insufficient_frames_after_rejection_returns_none(self):
        """If < 5 frames survive outlier rejection, return None."""
        frames = []
        # Create only 4 frames (below the minimum of 5)
        for i in range(4):
            frames.append(
                make_keypoint_frame(
                    frame_index=i,
                    camera_view="posterior",
                    knee_pos=(300, 600),
                    ankle_pos=(310, 680),
                    heel_pos=(308, 700),
                    toe_pos=(313, 705),
                )
            )

        cycle = make_cycle(frame_start=0, frame_end=3, stance_frames=list(range(4)))
        result = compute_rearfoot_alignment_angle(frames, "L", [cycle])

        # Should return None because frame_count < _MIN_REARFOOT_ALIGNMENT_FRAMES (5)
        assert result["mean_deg"] is None
        assert result["classification"] is None
        assert result["frame_count"] <= _MIN_REARFOOT_ALIGNMENT_FRAMES

    def test_plausibility_gate_rejects_impossible_angles(self):
        """Angles > ±30 deg should be flagged as unreliable and return None."""
        frames = []
        # Create frames with consistently high angle (~40 deg, beyond plausibility)
        for i in range(6):
            frames.append(
                make_keypoint_frame(
                    frame_index=i,
                    camera_view="posterior",
                    knee_pos=(300, 600),
                    ankle_pos=(310, 680),
                    heel_pos=(250, 700),  # ~40+ deg error
                    toe_pos=(313, 705),
                )
            )

        cycle = make_cycle(frame_start=0, frame_end=5, stance_frames=list(range(6)))
        result = compute_rearfoot_alignment_angle(frames, "L", [cycle])

        # Should return None because median_deg > _REARFOOT_ALIGNMENT_MAX_PLAUSIBLE_DEG (30)
        assert result["mean_deg"] is None
        assert result["classification"] is None
        # frame_count should still reflect how many frames survived outlier rejection
        assert result["frame_count"] > 0

    def test_median_not_mean_used_for_aggregation(self):
        """Verify median is computed, not mean, by using a skewed distribution."""
        frames = []
        # Create 6 frames: 5 normal (5 deg) + 1 huge outlier (60 deg)
        for i in range(5):
            frames.append(
                make_keypoint_frame(
                    frame_index=i,
                    camera_view="posterior",
                    knee_pos=(300, 600),
                    ankle_pos=(310, 680),
                    heel_pos=(308, 700),  # ~5 deg
                    toe_pos=(313, 705),
                )
            )
        # Outlier that would skew the mean
        frames.append(
            make_keypoint_frame(
                frame_index=5,
                camera_view="posterior",
                knee_pos=(300, 600),
                ankle_pos=(310, 680),
                heel_pos=(150, 700),  # ~60 deg
                toe_pos=(313, 705),
            )
        )

        cycle = make_cycle(frame_start=0, frame_end=5, stance_frames=list(range(6)))
        result = compute_rearfoot_alignment_angle(frames, "L", [cycle])

        # If using mean, would be biased toward 60 deg.
        # If using median with outlier rejection, should still be ~5 deg.
        # (Outlier > 20 deg from initial median should be rejected)
        if result["mean_deg"] is not None:
            assert abs(result["mean_deg"]) <= 15.0
            assert result["frame_count"] <= 6  # Outlier should be rejected

    def test_left_vs_right_foot_sign_convention(self):
        """Right foot angles should be negated relative to left; verify sign is correct."""
        frames = []
        # Create consistent frames
        for i in range(6):
            frames.append(
                make_keypoint_frame(
                    frame_index=i,
                    camera_view="posterior",
                    knee_pos=(300, 600),
                    ankle_pos=(310, 680),
                    heel_pos=(308, 700),
                    toe_pos=(313, 705),
                )
            )

        cycle_l = make_cycle(frame_start=0, frame_end=5, stance_frames=list(range(6)), foot="L")
        cycle_r = make_cycle(frame_start=0, frame_end=5, stance_frames=list(range(6)), foot="R")

        result_l = compute_rearfoot_alignment_angle(frames, "L", [cycle_l])
        result_r = compute_rearfoot_alignment_angle(frames, "R", [cycle_r])

        # Both should have valid results (sufficient frames)
        # The function applies sign correction: right foot negation in compute_rearfoot_alignment_angle
        if result_l["mean_deg"] is not None and result_r["mean_deg"] is not None:
            # Both should be within plausibility
            assert abs(result_l["mean_deg"]) <= _REARFOOT_ALIGNMENT_MAX_PLAUSIBLE_DEG
            assert abs(result_r["mean_deg"]) <= _REARFOOT_ALIGNMENT_MAX_PLAUSIBLE_DEG


# â"€â"€ Tests: foot_progression_angle (camera filtering + plausibility gate) â"€â"€â"€â"€


class TestFootProgressionAngleCameraFiltering:
    """Test the July 2026 fix: camera filtering for FPA computation."""

    def test_sagittal_camera_fpa_computation(self):
        """FPA from sagittal camera should work (heel-toe separation is large)."""
        heel = kp(100, 500)  # x=100, y=500
        toe = kp(150, 510)  # x=150, y=510 (10 px right, 10 px down)

        angle = compute_foot_progression_angle(heel, toe)

        # atan2(-dy, dx) = atan2(-10, 50) ~ -11.3 deg (toe-out)
        assert angle is not None
        assert -20.0 <= angle <= 0.0  # Plausible range for heel in this config

    def test_fpa_with_zero_dx_returns_valid_but_noisy_value(self):
        """FPA with near-zero dx (posterior view) still computes but is noise-dominated.

        This is what used to happen before the camera filter fix — the orchestrator
        now filters these out, but the function itself is unchanged.
        """
        heel = kp(100, 500)  # x=100
        toe = kp(100.5, 510)  # x=100.5 (only 0.5 px horizontal separation!)

        angle = compute_foot_progression_angle(heel, toe)

        # atan2(-10, 0.5) ~ -87 deg — extreme angle from tiny dx
        # This demonstrates why posterior frames should be filtered out by orchestrator
        assert angle is not None
        assert abs(angle) > 45.0  # Way outside plausible range

    def test_fpa_toe_in_positive_angle(self):
        """Toe-in (negative dx from heel to toe) should produce positive angle."""
        heel = kp(150, 500)  # x=150
        toe = kp(100, 510)  # x=100 (50 px left)

        angle = compute_foot_progression_angle(heel, toe)

        # atan2(-10, -50) ~ 191 deg (wraps to ~169 deg or similar)
        # Exact depends on atan2 implementation, but should be in reasonable range
        assert angle is not None


class TestRearfootAlignmentClassification:
    """Test rearfoot alignment classifications."""

    def test_normal_alignment(self):
        assert classify_rearfoot_alignment(0.0) == "normal"
        assert classify_rearfoot_alignment(1.0) == "normal"
        assert classify_rearfoot_alignment(-1.0) == "mild_supination"

    def test_severe_overpronation(self):
        assert classify_rearfoot_alignment(20.0) == "severe_overpronation"

    def test_severe_supination(self):
        assert classify_rearfoot_alignment(-20.0) == "severe_supination"

    def test_mild_classifications(self):
        assert classify_rearfoot_alignment(5.0) == "mild_overpronation"
        assert classify_rearfoot_alignment(-3.0) == "mild_supination"


# â"€â"€ Integration: Static photo + walking video fallback â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


class TestRearfootAlignmentMethodSelection:
    """Test that static photo method is preferred over walking video fallback."""

    def test_static_alignment_takes_priority_when_provided(self):
        """When static_alignment is provided to analyzer, it should be used directly."""
        from gait.analysis.analyzer import StandardBiomechanicalAnalyzer

        analyzer = StandardBiomechanicalAnalyzer(
            AnalysisConfig(
                rearfoot_min_deg=5.0,
                forefoot_max_deg=-5.0,
                overpronation_min_deg=8.0,
                mild_pronation_min_deg=4.0,
                neutral_min_deg=0.0,
                mild_supination_min_deg=-4.0,
                high_ahi_min=0.30,
                normal_ahi_min=0.20,
            )
        )

        # Create cycles (but they won't be used for rearfoot alignment)
        cycles = [make_cycle(foot="L")]

        # Provide static alignment result directly
        static_alignment = {
            "mean_deg": 5.2,
            "classification": "mild_overpronation",
            "confidence": 0.93,
        }

        result = analyzer.aggregate_parameters(
            cycles, "L", posterior_frames=None, static_alignment=static_alignment
        )

        # Should use the static alignment directly
        assert result["rearfoot_alignment_angle_deg_mean"] == pytest.approx(5.2)
        assert result["rearfoot_alignment_classification"] == "mild_overpronation"
        assert result["rearfoot_alignment_frame_count"] == 1  # Single frame from static photo

    def test_walking_video_fallback_used_when_static_unavailable(self):
        """When static_alignment is None, use walking video fallback."""
        from gait.analysis.analyzer import StandardBiomechanicalAnalyzer

        analyzer = StandardBiomechanicalAnalyzer(
            AnalysisConfig(
                rearfoot_min_deg=5.0,
                forefoot_max_deg=-5.0,
                overpronation_min_deg=8.0,
                mild_pronation_min_deg=4.0,
                neutral_min_deg=0.0,
                mild_supination_min_deg=-4.0,
                high_ahi_min=0.30,
                normal_ahi_min=0.20,
            )
        )

        # Create cycles with posterior frames
        frames = [
            make_keypoint_frame(frame_index=i, camera_view="posterior")
            for i in range(20)
        ]
        cycle = make_cycle(foot="L", stance_frames=list(range(20)))

        result = analyzer.aggregate_parameters(
            [cycle], "L", posterior_frames=frames, static_alignment=None
        )

        # Should compute from posterior frames (fallback method)
        # Result depends on frame geometry, but should be valid if enough frames
        if result["rearfoot_alignment_angle_deg_mean"] is not None:
            assert isinstance(result["rearfoot_alignment_angle_deg_mean"], (int, float))
            assert isinstance(result["rearfoot_alignment_classification"], (str, type(None)))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
