"""Unit tests for StandardBiomechanicalAnalyzer (src.gait.analysis.analyzer)."""
from __future__ import annotations

from typing import Dict

import pytest

from gait.analysis.analyzer import (
    StandardBiomechanicalAnalyzer,
    _quality_flag,
    create_biomechanical_analyzer,
)
from gait.common.interfaces import GaitCycle, Keypoint, KeypointFrame
from gait.pipeline.config import AnalysisConfig

# â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def default_cfg(**overrides) -> AnalysisConfig:
    params = dict(
        target_clean_cycles_per_foot=8,
        min_clean_cycles_per_foot=4,
    )
    params.update(overrides)
    return AnalysisConfig(**params)


def kp(x: float, y: float, name: str = "") -> Keypoint:
    return Keypoint(x=x, y=y, confidence=0.9, name=name)


def make_full_keypoints(side: str = "left") -> Dict[str, Keypoint]:
    """Keypoints for a physically plausible left/right foot at a typical frame."""
    return {
        f"{side}_heel":       kp(100, 220, f"{side}_heel"),
        f"{side}_foot_index": kp(200, 200, f"{side}_foot_index"),
        f"{side}_ankle":      kp(110, 160, f"{side}_ankle"),
        f"{side}_knee":       kp(115, 80,  f"{side}_knee"),
    }


def make_cycle(
    foot: str = "L",
    frame_start: int = 0,
    frame_end: int = 60,
    stance_ms: float = 600.0,
    swing_ms: float = 400.0,
    with_keypoints: bool = True,
    cycle_id: int = 0,
) -> GaitCycle:
    side = "left" if foot == "L" else "right"
    # Build keypoints at HS frame and midstance frame
    kps = {}
    if with_keypoints:
        kps[frame_start] = make_full_keypoints(side)
        mid = (frame_start + frame_end) // 2
        kps[mid] = make_full_keypoints(side)

    return GaitCycle(
        cycle_id=cycle_id,
        foot=foot,
        frame_start=frame_start,
        frame_end=frame_end,
        stance_frames=list(range(frame_start, frame_start + 36)),
        swing_frames=list(range(frame_start + 36, frame_end + 1)),
        keypoints=kps,
        confidence=0.9,
        stance_duration_ms=stance_ms,
        swing_duration_ms=swing_ms,
    )


# â”€â”€ _quality_flag â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestQualityFlag:
    def test_proceed_ok_at_target(self):
        cfg = default_cfg(target_clean_cycles_per_foot=8, min_clean_cycles_per_foot=4)
        assert _quality_flag(8, cfg) == "PROCEED_OK"

    def test_proceed_ok_above_target(self):
        cfg = default_cfg(target_clean_cycles_per_foot=8, min_clean_cycles_per_foot=4)
        assert _quality_flag(10, cfg) == "PROCEED_OK"

    def test_proceed_with_warning_at_min(self):
        cfg = default_cfg(target_clean_cycles_per_foot=8, min_clean_cycles_per_foot=4)
        assert _quality_flag(4, cfg) == "PROCEED_WITH_WARNING"

    def test_proceed_with_warning_between(self):
        cfg = default_cfg(target_clean_cycles_per_foot=8, min_clean_cycles_per_foot=4)
        assert _quality_flag(6, cfg) == "PROCEED_WITH_WARNING"

    def test_rerecord_below_min(self):
        cfg = default_cfg(target_clean_cycles_per_foot=8, min_clean_cycles_per_foot=4)
        assert _quality_flag(3, cfg) == "RERECORD"

    def test_rerecord_zero_cycles(self):
        cfg = default_cfg(target_clean_cycles_per_foot=8, min_clean_cycles_per_foot=4)
        assert _quality_flag(0, cfg) == "RERECORD"


# â”€â”€ compute_parameters â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestComputeParameters:
    def test_returns_dict(self):
        az = StandardBiomechanicalAnalyzer(default_cfg())
        result = az.compute_parameters(make_cycle())
        assert isinstance(result, dict)

    def test_spatiotemporal_keys_present(self):
        az = StandardBiomechanicalAnalyzer(default_cfg())
        result = az.compute_parameters(make_cycle())
        for key in ("stance_time_ms", "swing_time_ms", "gait_cycle_time_ms",
                    "stance_pct", "swing_pct", "cadence_steps_per_min"):
            assert key in result, f"Missing key: {key}"

    def test_metadata_keys_present(self):
        az = StandardBiomechanicalAnalyzer(default_cfg())
        result = az.compute_parameters(make_cycle(foot="L", cycle_id=3))
        assert result["foot"] == "L"
        assert result["cycle_id"] == 3

    def test_foot_right_assignment(self):
        az = StandardBiomechanicalAnalyzer(default_cfg())
        result = az.compute_parameters(make_cycle(foot="R"))
        assert result["foot"] == "R"

    def test_foot_strike_keys_when_keypoints_present(self):
        az = StandardBiomechanicalAnalyzer(default_cfg())
        result = az.compute_parameters(make_cycle(with_keypoints=True))
        assert "foot_strike_angle_deg" in result
        assert "foot_strike_type" in result

    def test_foot_strike_type_is_valid_string(self):
        az = StandardBiomechanicalAnalyzer(default_cfg())
        result = az.compute_parameters(make_cycle(with_keypoints=True))
        assert result["foot_strike_type"] in ("rearfoot", "midfoot", "forefoot")

    def test_no_foot_strike_without_keypoints(self):
        az = StandardBiomechanicalAnalyzer(default_cfg())
        result = az.compute_parameters(make_cycle(with_keypoints=False))
        assert "foot_strike_type" not in result

    def test_pronation_keys_when_keypoints_present(self):
        az = StandardBiomechanicalAnalyzer(default_cfg())
        result = az.compute_parameters(make_cycle(with_keypoints=True))
        assert "rearfoot_angle_deg" in result
        assert "pronation_type" in result

    def test_pronation_type_is_valid_string(self):
        valid = {"overpronation", "mild_pronation", "neutral", "mild_supination", "oversupination"}
        az = StandardBiomechanicalAnalyzer(default_cfg())
        result = az.compute_parameters(make_cycle(with_keypoints=True))
        assert result["pronation_type"] in valid

    def test_arch_keys_when_keypoints_present(self):
        az = StandardBiomechanicalAnalyzer(default_cfg())
        result = az.compute_parameters(make_cycle(with_keypoints=True))
        # AHI may or may not be present depending on geometry â€” just check type if present
        if "arch_height_index" in result:
            assert isinstance(result["arch_height_index"], float)
            assert result["arch_type"] in ("high", "normal", "low")

    def test_stance_ms_matches_cycle(self):
        az = StandardBiomechanicalAnalyzer(default_cfg())
        result = az.compute_parameters(make_cycle(stance_ms=650.0))
        assert result["stance_time_ms"] == pytest.approx(650.0)

    def test_cadence_1000ms_cycle(self):
        az = StandardBiomechanicalAnalyzer(default_cfg())
        result = az.compute_parameters(make_cycle(stance_ms=600.0, swing_ms=400.0))
        assert result["cadence_steps_per_min"] == pytest.approx(120.0)

    def test_right_foot_rearfoot_angle_sign(self):
        """Right-foot eversion = heel tilts right (+x) â†’ raw angle negative â†’ negated to positive."""
        az = StandardBiomechanicalAnalyzer(default_cfg())
        side = "right"
        # Right-foot pronation: heel to the RIGHT of ankle (outward/lateral for right foot)
        kps = {
            f"{side}_heel":       kp(140, 220),  # heel is right of ankle (x=140 > ankle.x=110)
            f"{side}_foot_index": kp(200, 200),
            f"{side}_ankle":      kp(110, 160),
            f"{side}_knee":       kp(115, 80),
        }
        cycle = GaitCycle(
            cycle_id=0, foot="R", frame_start=0, frame_end=60,
            stance_frames=[], swing_frames=[],
            keypoints={0: kps, 30: kps},
            confidence=0.9, stance_duration_ms=600.0, swing_duration_ms=400.0,
        )
        result = az.compute_parameters(cycle)
        # Raw angle is negative (heel right); negated for right foot â†’ positive (pronation)
        assert result["rearfoot_angle_deg"] > 0


# â”€â”€ aggregate_parameters â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestAggregateParameters:
    def test_empty_cycles_returns_rerecord(self):
        az = StandardBiomechanicalAnalyzer(default_cfg())
        result = az.aggregate_parameters([], "L")
        assert result["quality_flag"] == "RERECORD"
        assert result["cycle_count"] == 0

    def test_cycle_count_correct(self):
        az = StandardBiomechanicalAnalyzer(default_cfg())
        cycles = [make_cycle(cycle_id=i) for i in range(5)]
        result = az.aggregate_parameters(cycles, "L")
        assert result["cycle_count"] == 5

    def test_mean_keys_present_for_numerics(self):
        az = StandardBiomechanicalAnalyzer(default_cfg())
        cycles = [make_cycle(cycle_id=i) for i in range(3)]
        result = az.aggregate_parameters(cycles, "L")
        assert "stance_time_ms_mean" in result
        assert "cadence_steps_per_min_mean" in result

    def test_std_keys_present(self):
        az = StandardBiomechanicalAnalyzer(default_cfg())
        cycles = [make_cycle(cycle_id=i) for i in range(3)]
        result = az.aggregate_parameters(cycles, "L")
        assert "stance_time_ms_std" in result

    def test_cadence_mean_correct(self):
        # All cycles identical: 1000ms â†’ 120 steps/min
        az = StandardBiomechanicalAnalyzer(default_cfg())
        cycles = [make_cycle(stance_ms=600.0, swing_ms=400.0, cycle_id=i) for i in range(4)]
        result = az.aggregate_parameters(cycles, "L")
        assert result["cadence_steps_per_min_mean"] == pytest.approx(120.0)

    def test_cadence_std_zero_identical_cycles(self):
        az = StandardBiomechanicalAnalyzer(default_cfg())
        cycles = [make_cycle(stance_ms=600.0, swing_ms=400.0, cycle_id=i) for i in range(4)]
        result = az.aggregate_parameters(cycles, "L")
        assert result["cadence_steps_per_min_std"] == pytest.approx(0.0, abs=1e-6)

    def test_foot_assignment_in_aggregate(self):
        az = StandardBiomechanicalAnalyzer(default_cfg())
        result = az.aggregate_parameters([make_cycle()], "R")
        assert result["foot"] == "R"

    def test_quality_flag_proceed_ok(self):
        az = StandardBiomechanicalAnalyzer(default_cfg(target_clean_cycles_per_foot=4))
        cycles = [make_cycle(cycle_id=i) for i in range(5)]
        result = az.aggregate_parameters(cycles, "L")
        assert result["quality_flag"] == "PROCEED_OK"

    def test_quality_flag_proceed_warning(self):
        az = StandardBiomechanicalAnalyzer(
            default_cfg(target_clean_cycles_per_foot=8, min_clean_cycles_per_foot=4)
        )
        cycles = [make_cycle(cycle_id=i) for i in range(5)]  # 5 < 8
        result = az.aggregate_parameters(cycles, "L")
        assert result["quality_flag"] == "PROCEED_WITH_WARNING"

    def test_quality_flag_rerecord(self):
        az = StandardBiomechanicalAnalyzer(
            default_cfg(target_clean_cycles_per_foot=8, min_clean_cycles_per_foot=4)
        )
        cycles = [make_cycle(cycle_id=i) for i in range(2)]  # 2 < 4
        result = az.aggregate_parameters(cycles, "L")
        assert result["quality_flag"] == "RERECORD"

    def test_classification_mode_in_aggregate(self):
        az = StandardBiomechanicalAnalyzer(default_cfg())
        cycles = [make_cycle(with_keypoints=True, cycle_id=i) for i in range(4)]
        result = az.aggregate_parameters(cycles, "L")
        if "foot_strike_type" in result:
            assert result["foot_strike_type"] in ("rearfoot", "midfoot", "forefoot")


# â”€â”€ factory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestFactory:
    def test_returns_correct_type(self):
        az = create_biomechanical_analyzer(default_cfg())
        assert isinstance(az, StandardBiomechanicalAnalyzer)

    def test_custom_fps_accepted(self):
        az = create_biomechanical_analyzer(default_cfg(), fps=30.0)
        assert az._fps == pytest.approx(30.0)

    def test_default_fps(self):
        az = create_biomechanical_analyzer(default_cfg())
        assert az._fps == pytest.approx(120.0)

