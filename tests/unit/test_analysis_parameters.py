"""Unit tests for pure biomechanical parameter functions (src.gait.analysis.parameters)."""
from __future__ import annotations

import math

import pytest

from gait.analysis.parameters import (
    classify_arch,
    classify_foot_strike,
    classify_pronation,
    compute_arch_height_index,
    compute_foot_strike_angle,
    compute_rearfoot_angle,
    compute_spatiotemporal,
    compute_symmetry_index,
)
from gait.common.interfaces import GaitCycle, Keypoint
from gait.pipeline.config import AnalysisConfig

# â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def default_cfg(**overrides) -> AnalysisConfig:
    params = dict(
        rearfoot_min_deg=5.0,
        forefoot_max_deg=-5.0,
        overpronation_min_deg=8.0,
        mild_pronation_min_deg=4.0,
        neutral_min_deg=0.0,
        mild_supination_min_deg=-4.0,
        high_ahi_min=0.30,
        normal_ahi_min=0.20,
    )
    params.update(overrides)
    return AnalysisConfig(**params)


def kp(x: float, y: float) -> Keypoint:
    return Keypoint(x=x, y=y, confidence=0.9)


def make_cycle(
    frame_start: int = 0,
    frame_end: int = 60,
    stance_ms: float = 600.0,
    swing_ms: float = 400.0,
    foot: str = "L",
) -> GaitCycle:
    return GaitCycle(
        cycle_id=0,
        foot=foot,
        frame_start=frame_start,
        frame_end=frame_end,
        stance_frames=list(range(frame_start, frame_start + 36)),
        swing_frames=list(range(frame_start + 36, frame_end + 1)),
        keypoints={},
        confidence=0.9,
        stance_duration_ms=stance_ms,
        swing_duration_ms=swing_ms,
    )


# â”€â”€ compute_spatiotemporal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestComputeSpatiotemporal:
    def test_returns_all_expected_keys(self):
        result = compute_spatiotemporal(make_cycle(), fps=120.0)
        for key in ("stance_time_ms", "swing_time_ms", "gait_cycle_time_ms",
                    "stance_pct", "swing_pct", "cadence_steps_per_min"):
            assert key in result

    def test_stance_time_matches_cycle(self):
        cycle = make_cycle(stance_ms=600.0, swing_ms=400.0)
        result = compute_spatiotemporal(cycle, fps=120.0)
        assert result["stance_time_ms"] == pytest.approx(600.0)

    def test_swing_time_matches_cycle(self):
        cycle = make_cycle(stance_ms=600.0, swing_ms=400.0)
        result = compute_spatiotemporal(cycle, fps=120.0)
        assert result["swing_time_ms"] == pytest.approx(400.0)

    def test_gait_cycle_time_is_sum(self):
        cycle = make_cycle(stance_ms=600.0, swing_ms=400.0)
        result = compute_spatiotemporal(cycle, fps=120.0)
        assert result["gait_cycle_time_ms"] == pytest.approx(1000.0)

    def test_stance_pct(self):
        cycle = make_cycle(stance_ms=600.0, swing_ms=400.0)
        result = compute_spatiotemporal(cycle, fps=120.0)
        assert result["stance_pct"] == pytest.approx(60.0)

    def test_swing_pct(self):
        cycle = make_cycle(stance_ms=600.0, swing_ms=400.0)
        result = compute_spatiotemporal(cycle, fps=120.0)
        assert result["swing_pct"] == pytest.approx(40.0)

    def test_stance_swing_pct_sum_to_100(self):
        result = compute_spatiotemporal(make_cycle(stance_ms=650.0, swing_ms=350.0), fps=120.0)
        assert result["stance_pct"] + result["swing_pct"] == pytest.approx(100.0)

    def test_cadence_1000ms_cycle(self):
        # 1 stride = 2 steps; 1 stride/sec â†’ cadence = 120 steps/min
        cycle = make_cycle(stance_ms=600.0, swing_ms=400.0)  # 1000ms total
        result = compute_spatiotemporal(cycle, fps=120.0)
        assert result["cadence_steps_per_min"] == pytest.approx(120.0)

    def test_cadence_500ms_cycle(self):
        cycle = make_cycle(stance_ms=300.0, swing_ms=200.0)  # 500ms total
        result = compute_spatiotemporal(cycle, fps=120.0)
        assert result["cadence_steps_per_min"] == pytest.approx(240.0)

    def test_zero_duration_cadence_is_zero(self):
        cycle = make_cycle(stance_ms=0.0, swing_ms=0.0)
        result = compute_spatiotemporal(cycle, fps=120.0)
        assert result["cadence_steps_per_min"] == pytest.approx(0.0)

    def test_none_duration_treated_as_zero(self):
        cycle = GaitCycle(
            cycle_id=0, foot="L", frame_start=0, frame_end=60,
            stance_frames=[], swing_frames=[], keypoints={}, confidence=0.9,
            stance_duration_ms=None, swing_duration_ms=None,
        )
        result = compute_spatiotemporal(cycle, fps=120.0)
        assert result["gait_cycle_time_ms"] == pytest.approx(0.0)


# â”€â”€ compute_foot_strike_angle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestComputeFootStrikeAngle:
    def test_heel_lower_than_toe_gives_positive_angle(self):
        # heel.y > foot_index.y â†’ heel lower in frame â†’ rearfoot â†’ positive FSA
        heel = kp(x=100, y=200)   # lower in frame
        toe = kp(x=200, y=150)    # higher in frame
        angle = compute_foot_strike_angle(heel, toe)
        assert angle > 0

    def test_toe_lower_than_heel_gives_negative_angle(self):
        # toe.y > heel.y â†’ toe lower â†’ forefoot â†’ negative FSA
        heel = kp(x=100, y=150)
        toe = kp(x=200, y=200)
        angle = compute_foot_strike_angle(heel, toe)
        assert angle < 0

    def test_flat_foot_gives_zero_angle(self):
        heel = kp(x=100, y=150)
        toe = kp(x=200, y=150)
        angle = compute_foot_strike_angle(heel, toe)
        assert angle == pytest.approx(0.0, abs=1e-6)

    def test_45_degree_rearfoot_angle(self):
        # dy = dx â†’ 45Â°
        heel = kp(x=0, y=100)
        toe = kp(x=100, y=0)   # dy = 100-0 = 100, dx = 100
        angle = compute_foot_strike_angle(heel, toe)
        assert angle == pytest.approx(45.0, abs=0.01)

    def test_angle_independent_of_walking_direction(self):
        # Walking right-to-left vs left-to-right should give same magnitude
        heel_lr = kp(x=100, y=200)
        toe_lr = kp(x=200, y=150)
        heel_rl = kp(x=200, y=200)
        toe_rl = kp(x=100, y=150)
        assert compute_foot_strike_angle(heel_lr, toe_lr) == pytest.approx(
            compute_foot_strike_angle(heel_rl, toe_rl), abs=0.01
        )


# â”€â”€ classify_foot_strike â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestClassifyFootStrike:
    def test_above_rearfoot_threshold(self):
        assert classify_foot_strike(10.0, default_cfg()) == "rearfoot"

    def test_at_rearfoot_boundary_is_midfoot(self):
        # Not strictly greater than 5.0
        assert classify_foot_strike(5.0, default_cfg()) == "midfoot"

    def test_below_forefoot_threshold(self):
        assert classify_foot_strike(-10.0, default_cfg()) == "forefoot"

    def test_at_forefoot_boundary_is_midfoot(self):
        # Not strictly less than -5.0
        assert classify_foot_strike(-5.0, default_cfg()) == "midfoot"

    def test_zero_is_midfoot(self):
        assert classify_foot_strike(0.0, default_cfg()) == "midfoot"

    def test_midfoot_between_thresholds(self):
        assert classify_foot_strike(3.0, default_cfg()) == "midfoot"


# â”€â”€ compute_rearfoot_angle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestComputeRearfootAngle:
    def test_heel_directly_below_ankle_gives_zero(self):
        ankle = kp(x=100, y=100)
        heel = kp(x=100, y=200)  # same x, lower y
        knee = kp(x=100, y=50)   # same x, above ankle
        angle = compute_rearfoot_angle(knee, ankle, heel)
        assert angle == pytest.approx(0.0, abs=0.1)

    def test_heel_tilted_right_gives_negative_angle(self):
        # signed_angle_deg((0,1), v) = atan2(-v.x, v.y); heel right â†’ v.x>0 â†’ negative
        ankle = kp(x=100, y=100)
        heel = kp(x=120, y=200)  # tilted right (+x)
        knee = kp(x=100, y=50)
        angle = compute_rearfoot_angle(knee, ankle, heel)
        assert angle < 0

    def test_heel_tilted_left_gives_positive_angle(self):
        ankle = kp(x=100, y=100)
        heel = kp(x=80, y=200)   # tilted left (-x) â†’ positive raw angle
        knee = kp(x=100, y=50)
        angle = compute_rearfoot_angle(knee, ankle, heel)
        assert angle > 0

    def test_magnitude_proportional_to_tilt(self):
        ankle = kp(x=100, y=100)
        knee = kp(x=100, y=50)
        small_tilt = compute_rearfoot_angle(knee, ankle, kp(x=110, y=200))
        large_tilt = compute_rearfoot_angle(knee, ankle, kp(x=130, y=200))
        assert abs(large_tilt) > abs(small_tilt)


# â”€â”€ classify_pronation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestClassifyPronation:
    def test_overpronation(self):
        assert classify_pronation(10.0, default_cfg()) == "overpronation"

    def test_at_overpronation_boundary(self):
        assert classify_pronation(8.0, default_cfg()) == "overpronation"

    def test_mild_pronation(self):
        assert classify_pronation(6.0, default_cfg()) == "mild_pronation"

    def test_neutral(self):
        assert classify_pronation(2.0, default_cfg()) == "neutral"

    def test_at_neutral_boundary(self):
        assert classify_pronation(0.0, default_cfg()) == "neutral"

    def test_mild_supination(self):
        assert classify_pronation(-2.0, default_cfg()) == "mild_supination"

    def test_oversupination(self):
        assert classify_pronation(-6.0, default_cfg()) == "oversupination"

    def test_at_mild_supination_boundary(self):
        assert classify_pronation(-4.0, default_cfg()) == "mild_supination"


# â”€â”€ compute_arch_height_index â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestComputeArchHeightIndex:
    def test_normal_arch_returns_positive_value(self):
        # heel at y=200, ankle at y=100, foot_index at y=180
        # navicular_y = (100+180)/2 = 140; nav_height = 200-140 = 60
        # foot_length = sqrt((100-0)^2 + (180-200)^2) = sqrt(10400) â‰ˆ 102
        heel = kp(x=0, y=200)
        foot_index = kp(x=100, y=180)
        ankle = kp(x=50, y=100)
        result = compute_arch_height_index(heel, foot_index, ankle)
        assert result is not None
        assert result > 0

    def test_flat_arch_returns_none_when_nav_below_heel(self):
        # If navicular.y > heel.y (nav lower than heel in image), AHI is invalid
        heel = kp(x=0, y=100)
        foot_index = kp(x=100, y=200)
        ankle = kp(x=50, y=200)  # navicular_y = (200+200)/2 = 200 > heel.y=100
        result = compute_arch_height_index(heel, foot_index, ankle)
        assert result is None

    def test_zero_length_foot_returns_none(self):
        heel = kp(x=100, y=200)
        foot_index = kp(x=100, y=200)  # same position as heel
        ankle = kp(x=100, y=100)
        result = compute_arch_height_index(heel, foot_index, ankle)
        assert result is None

    def test_result_is_dimensionless_ratio(self):
        heel = kp(x=0, y=200)
        foot_index = kp(x=100, y=160)
        ankle = kp(x=50, y=120)
        result = compute_arch_height_index(heel, foot_index, ankle)
        assert result is not None
        assert 0 < result < 2.0  # AHI is a ratio, not a raw pixel count

    def test_higher_arch_gives_higher_ahi(self):
        foot_index = kp(x=100, y=180)
        heel = kp(x=0, y=200)
        low_ankle = kp(x=50, y=190)   # ankle close to ground â†’ low arch
        high_ankle = kp(x=50, y=60)   # ankle high up â†’ high arch
        ahi_low = compute_arch_height_index(heel, foot_index, low_ankle)
        ahi_high = compute_arch_height_index(heel, foot_index, high_ankle)
        assert ahi_high is not None
        if ahi_low is not None:
            assert ahi_high > ahi_low


# â”€â”€ classify_arch â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestClassifyArch:
    def test_high_arch(self):
        assert classify_arch(0.35, default_cfg()) == "high"

    def test_at_high_boundary(self):
        assert classify_arch(0.30, default_cfg()) == "high"

    def test_normal_arch(self):
        assert classify_arch(0.25, default_cfg()) == "normal"

    def test_at_normal_boundary(self):
        assert classify_arch(0.20, default_cfg()) == "normal"

    def test_low_arch(self):
        assert classify_arch(0.10, default_cfg()) == "low"


# â”€â”€ compute_symmetry_index â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestComputeSymmetryIndex:
    def test_perfect_symmetry_is_zero(self):
        assert compute_symmetry_index(100.0, 100.0) == pytest.approx(0.0)

    def test_10_percent_difference(self):
        # |105 - 95| / 100 * 100 = 10%
        assert compute_symmetry_index(105.0, 95.0) == pytest.approx(10.0, abs=0.01)

    def test_zero_both_gives_zero(self):
        assert compute_symmetry_index(0.0, 0.0) == pytest.approx(0.0)

    def test_one_side_zero(self):
        # |100 - 0| / 50 * 100 = 200%
        assert compute_symmetry_index(100.0, 0.0) == pytest.approx(200.0)

    def test_symmetric_regardless_of_order(self):
        assert compute_symmetry_index(120.0, 80.0) == pytest.approx(
            compute_symmetry_index(80.0, 120.0)
        )

    def test_large_asymmetry(self):
        si = compute_symmetry_index(200.0, 100.0)
        assert si > 50.0

