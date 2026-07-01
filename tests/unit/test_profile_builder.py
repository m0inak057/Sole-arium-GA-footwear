"""Unit tests for StandardProfileBuilder and StandardGatingEngine."""
from __future__ import annotations

from typing import Any, Dict

import pytest

from gait.common.interfaces import GaitCycle
from gait.pipeline.config import AnalysisConfig, RecommendationRulesConfig
from gait.profile.builder import (
    StandardProfileBuilder,
    _compute_symmetry_flags,
    _derive_rule_parameters,
    _mean_of,
    create_profile_builder,
)
from gait.profile.gating import StandardGatingEngine, create_gating_engine
from gait.profile.rules_engine import RuleBasedRecommendationEngine

# â”€â”€ shared fixtures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

ANTHRO: Dict[str, Any] = {
    "height_cm": 172.0,
    "mass_kg": 68.0,
    "foot_length_mm": {"L": 258.0, "R": 260.0},
    "foot_width_mm": {"L": 98.0, "R": 99.0},
}

CONFIDENCE: Dict[str, float] = {
    "pronation_classification": 0.91,
    "foot_strike_classification": 0.95,
}


def default_cfg(**overrides) -> AnalysisConfig:
    params = {
        "symmetry_flag_threshold_pct": 10.0,
        "min_clean_cycles_per_foot": 4,
        "target_clean_cycles_per_foot": 8,
    }
    params.update(overrides)
    return AnalysisConfig(**params)


def make_agg_params(
    foot: str = "L",
    pronation: str = "neutral",
    arch: str = "normal",
    foot_strike: str = "rearfoot",
    cadence: float = 120.0,
    stance_pct: float = 61.0,
    swing_pct: float = 39.0,
    rearfoot_angle: float = 2.0,
    fsa: float = 10.0,
    ahi: float = 0.25,
    quality_flag: str = "PROCEED_OK",
    cycle_count: int = 8,
) -> Dict[str, Any]:
    return {
        "foot": foot,
        "cycle_count": cycle_count,
        "quality_flag": quality_flag,
        "cadence_steps_per_min_mean": cadence,
        "cadence_steps_per_min_std": 0.5,
        "stance_pct_mean": stance_pct,
        "stance_pct_std": 1.0,
        "swing_pct_mean": swing_pct,
        "swing_pct_std": 1.0,
        "foot_strike_type": foot_strike,
        "foot_strike_angle_deg_mean": fsa,
        "foot_strike_angle_deg_std": 1.0,
        "rearfoot_angle_deg_mean": rearfoot_angle,
        "rearfoot_angle_deg_std": 0.5,
        "pronation_type": pronation,
        "arch_height_index_mean": ahi,
        "arch_height_index_std": 0.02,
        "arch_type": arch,
    }


def empty_rules_engine() -> RuleBasedRecommendationEngine:
    return RuleBasedRecommendationEngine(RecommendationRulesConfig(version=1, rules=[]))


def make_builder(cfg: AnalysisConfig | None = None) -> StandardProfileBuilder:
    return StandardProfileBuilder(empty_rules_engine(), cfg or default_cfg())


def make_parameters(
    params_l: Dict[str, Any] | None = None,
    params_r: Dict[str, Any] | None = None,
    **extra,
) -> Dict[str, Any]:
    return {
        "L": params_l or make_agg_params("L"),
        "R": params_r or make_agg_params("R"),
        **extra,
    }


def make_gait_cycle(foot: str = "L", cycle_id: int = 0) -> GaitCycle:
    return GaitCycle(
        cycle_id=cycle_id,
        foot=foot,
        frame_start=0,
        frame_end=60,
        stance_frames=list(range(36)),
        swing_frames=list(range(36, 61)),
        keypoints={},
        confidence=0.9,
        stance_duration_ms=600.0,
        swing_duration_ms=400.0,
    )


# â”€â”€ _mean_of â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestMeanOf:
    def test_both_none_returns_zero(self):
        assert _mean_of(None, None) == pytest.approx(0.0)

    def test_left_none_returns_right(self):
        assert _mean_of(None, 10.0) == pytest.approx(10.0)

    def test_right_none_returns_left(self):
        assert _mean_of(10.0, None) == pytest.approx(10.0)

    def test_both_present_returns_mean(self):
        assert _mean_of(10.0, 20.0) == pytest.approx(15.0)

    def test_equal_values(self):
        assert _mean_of(5.0, 5.0) == pytest.approx(5.0)


# â”€â”€ _compute_symmetry_flags â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestComputeSymmetryFlags:
    def test_symmetric_cadence_no_flags(self):
        left = make_agg_params("L", cadence=120.0)
        r = make_agg_params("R", cadence=120.0)
        flags = _compute_symmetry_flags(left, r, threshold_pct=10.0)
        assert "high_asymmetry" not in flags

    def test_large_cadence_asymmetry_flags_high_asymmetry(self):
        left = make_agg_params("L", cadence=100.0)
        r = make_agg_params("R", cadence=140.0)
        flags = _compute_symmetry_flags(left, r, threshold_pct=10.0)
        assert "high_asymmetry" in flags

    def test_specific_flag_label_includes_parameter_name(self):
        left = make_agg_params("L", cadence=100.0)
        r = make_agg_params("R", cadence=150.0)
        flags = _compute_symmetry_flags(left, r, threshold_pct=10.0)
        assert any("cadence" in f for f in flags)

    def test_small_asymmetry_below_threshold_no_flag(self):
        left = make_agg_params("L", stance_pct=61.0)
        r = make_agg_params("R", stance_pct=61.5)
        flags = _compute_symmetry_flags(left, r, threshold_pct=10.0)
        assert not flags

    def test_missing_key_on_one_side_skipped(self):
        left = {}  # missing all keys
        r = make_agg_params("R")
        flags = _compute_symmetry_flags(left, r, threshold_pct=10.0)
        assert not flags

    def test_rearfoot_angle_asymmetry_flagged(self):
        left = make_agg_params("L", rearfoot_angle=2.0)
        r = make_agg_params("R", rearfoot_angle=15.0)
        flags = _compute_symmetry_flags(left, r, threshold_pct=10.0)
        assert "high_asymmetry" in flags
        assert any("rearfoot_angle" in f for f in flags)

    def test_high_asymmetry_added_once_even_if_multiple_params_asymmetric(self):
        left = make_agg_params("L", cadence=100.0, stance_pct=50.0)
        r = make_agg_params("R", cadence=160.0, stance_pct=75.0)
        flags = _compute_symmetry_flags(left, r, threshold_pct=10.0)
        assert flags.count("high_asymmetry") == 1


# â”€â”€ _derive_rule_parameters â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestDeriveRuleParameters:
    def test_more_pronated_left_is_dominant(self):
        left = make_agg_params("L", pronation="overpronation", arch="low")
        r = make_agg_params("R", pronation="neutral", arch="normal")
        result = _derive_rule_parameters(left, r, {})
        assert result["pronation_type"] == "overpronation"
        assert result["arch_type"] == "low"

    def test_more_pronated_right_is_dominant(self):
        left = make_agg_params("L", pronation="neutral", arch="normal")
        r = make_agg_params("R", pronation="mild_pronation", arch="low")
        result = _derive_rule_parameters(left, r, {})
        assert result["pronation_type"] == "mild_pronation"

    def test_equal_pronation_left_is_dominant(self):
        left = make_agg_params("L", pronation="neutral", foot_strike="midfoot")
        r = make_agg_params("R", pronation="neutral", foot_strike="forefoot")
        result = _derive_rule_parameters(left, r, {})
        # left wins on tie
        assert result["foot_strike_type"] == "midfoot"

    def test_extra_flags_merged(self):
        left = make_agg_params("L")
        r = make_agg_params("R")
        result = _derive_rule_parameters(left, r, {"flags": ["pathological_gait"]})
        assert "pathological_gait" in result["flags"]

    def test_empty_params_uses_defaults(self):
        result = _derive_rule_parameters({}, {}, {})
        assert result["pronation_type"] == "neutral"
        assert result["arch_type"] == "normal"


# â”€â”€ StandardProfileBuilder.build() â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestBuildProfile:
    def test_returns_dict(self):
        builder = make_builder()
        profile = builder.build("P001", "2026-06-13T10:00:00Z", make_parameters(), ANTHRO, CONFIDENCE)
        assert isinstance(profile, dict)

    def test_patient_id_preserved(self):
        builder = make_builder()
        profile = builder.build("P001", "2026-06-13T10:00:00Z", make_parameters(), ANTHRO, CONFIDENCE)
        assert profile["patient_id"] == "P001"

    def test_session_timestamp_preserved(self):
        ts = "2026-06-13T10:00:00Z"
        builder = make_builder()
        profile = builder.build("P001", ts, make_parameters(), ANTHRO, CONFIDENCE)
        assert profile["session_timestamp"] == ts

    def test_schema_version_is_v1(self):
        builder = make_builder()
        profile = builder.build("P001", "2026-06-13T10:00:00Z", make_parameters(), ANTHRO, CONFIDENCE)
        assert profile["schema_version"] == "profile/v1"

    def test_anthropometrics_passed_through(self):
        builder = make_builder()
        profile = builder.build("P001", "2026-06-13T10:00:00Z", make_parameters(), ANTHRO, CONFIDENCE)
        assert profile["anthropometrics"] == ANTHRO

    def test_confidence_scores_passed_through(self):
        builder = make_builder()
        profile = builder.build("P001", "2026-06-13T10:00:00Z", make_parameters(), ANTHRO, CONFIDENCE)
        assert profile["confidence_scores"] == CONFIDENCE

    def test_spatiotemporal_has_lr_stance_pct(self):
        builder = make_builder()
        profile = builder.build("P001", "2026-06-13T10:00:00Z", make_parameters(), ANTHRO, CONFIDENCE)
        st = profile["spatiotemporal"]
        assert "L" in st["stance_pct"]
        assert "R" in st["stance_pct"]

    def test_cadence_is_mean_of_l_and_r(self):
        builder = make_builder()
        params = make_parameters(
            make_agg_params("L", cadence=100.0),
            make_agg_params("R", cadence=120.0),
        )
        profile = builder.build("P001", "2026-06-13T10:00:00Z", params, ANTHRO, CONFIDENCE)
        assert profile["spatiotemporal"]["cadence_spm"] == pytest.approx(110.0)

    def test_foot_strike_pattern_has_l_and_r(self):
        builder = make_builder()
        profile = builder.build("P001", "2026-06-13T10:00:00Z", make_parameters(), ANTHRO, CONFIDENCE)
        pattern = profile["foot_strike"]["pattern"]
        assert set(pattern.keys()) == {"L", "R"}

    def test_foot_strike_angle_has_l_and_r(self):
        builder = make_builder()
        profile = builder.build("P001", "2026-06-13T10:00:00Z", make_parameters(), ANTHRO, CONFIDENCE)
        fsa = profile["foot_strike"]["foot_strike_angle_deg"]
        assert "L" in fsa and "R" in fsa

    def test_pronation_classification_has_l_and_r(self):
        builder = make_builder()
        profile = builder.build("P001", "2026-06-13T10:00:00Z", make_parameters(), ANTHRO, CONFIDENCE)
        classification = profile["pronation"]["classification"]
        assert "L" in classification and "R" in classification

    def test_arch_type_has_l_and_r(self):
        builder = make_builder()
        profile = builder.build("P001", "2026-06-13T10:00:00Z", make_parameters(), ANTHRO, CONFIDENCE)
        arch_type = profile["arch"]["type"]
        assert "L" in arch_type and "R" in arch_type

    def test_health_assessment_present(self):
        builder = make_builder()
        profile = builder.build("P001", "2026-06-13T10:00:00Z", make_parameters(), ANTHRO, CONFIDENCE)
        assessment = profile["health_assessment"]
        for key in ("what_went_right", "defects_found", "improvement_plan"):
            assert key in assessment, f"Missing key: {key}"
        assert isinstance(assessment["what_went_right"], list)
        assert isinstance(assessment["defects_found"], list)
        assert isinstance(assessment["improvement_plan"], list)

    def test_symmetry_flags_is_list(self):
        builder = make_builder()
        profile = builder.build("P001", "2026-06-13T10:00:00Z", make_parameters(), ANTHRO, CONFIDENCE)
        assert isinstance(profile["symmetry_flags"], list)

    def test_quality_metrics_present(self):
        builder = make_builder()
        profile = builder.build("P001", "2026-06-13T10:00:00Z", make_parameters(), ANTHRO, CONFIDENCE)
        qm = profile["quality_metrics"]
        assert "quality_flag_L" in qm
        assert "quality_flag_R" in qm
        assert "cycle_count_L" in qm
        assert "cycle_count_R" in qm

    def test_quality_metrics_cycle_count_correct(self):
        builder = make_builder()
        params = make_parameters(
            make_agg_params("L", cycle_count=8),
            make_agg_params("R", cycle_count=6),
        )
        profile = builder.build("P001", "2026-06-13T10:00:00Z", params, ANTHRO, CONFIDENCE)
        assert profile["quality_metrics"]["cycle_count_L"] == 8
        assert profile["quality_metrics"]["cycle_count_R"] == 6

    def test_no_asymmetry_no_high_asymmetry_flag(self):
        builder = make_builder()
        params = make_parameters(
            make_agg_params("L", cadence=120.0, stance_pct=61.0),
            make_agg_params("R", cadence=120.0, stance_pct=61.0),
        )
        profile = builder.build("P001", "2026-06-13T10:00:00Z", params, ANTHRO, CONFIDENCE)
        assert "high_asymmetry" not in profile["symmetry_flags"]

    def test_high_asymmetry_flag_when_cadence_differs_much(self):
        builder = make_builder()
        params = make_parameters(
            make_agg_params("L", cadence=100.0),
            make_agg_params("R", cadence=160.0),
        )
        profile = builder.build("P001", "2026-06-13T10:00:00Z", params, ANTHRO, CONFIDENCE)
        assert "high_asymmetry" in profile["symmetry_flags"]

    def test_needs_human_review_false_when_all_ok(self):
        builder = make_builder()
        profile = builder.build(
            "P001",
            "2026-06-13T10:00:00Z",
            make_parameters(
                make_agg_params("L", quality_flag="PROCEED_OK"),
                make_agg_params("R", quality_flag="PROCEED_OK"),
            ),
            ANTHRO,
            CONFIDENCE,
        )
        # With empty rules engine and no asymmetry, should not need review
        assert profile["needs_human_review"] is False

    def test_needs_human_review_true_when_rerecord(self):
        builder = make_builder()
        params = make_parameters(
            make_agg_params("L", quality_flag="RERECORD", cycle_count=2),
            make_agg_params("R", quality_flag="PROCEED_OK"),
        )
        profile = builder.build("P001", "2026-06-13T10:00:00Z", params, ANTHRO, CONFIDENCE)
        assert profile["needs_human_review"] is True

    def test_speed_mps_from_parameters(self):
        builder = make_builder()
        params = make_parameters(speed_mps=1.3)
        profile = builder.build("P001", "2026-06-13T10:00:00Z", params, ANTHRO, CONFIDENCE)
        assert profile["spatiotemporal"]["speed_mps"] == pytest.approx(1.3)

    def test_speed_mps_defaults_to_zero(self):
        builder = make_builder()
        profile = builder.build("P001", "2026-06-13T10:00:00Z", make_parameters(), ANTHRO, CONFIDENCE)
        assert profile["spatiotemporal"]["speed_mps"] == pytest.approx(0.0)

    def test_extra_flags_passed_to_rules_engine(self):
        """External flags (e.g. pathological_gait) must reach the rules engine."""
        from gait.pipeline.config import RecommendationRule

        engine = RuleBasedRecommendationEngine(
            RecommendationRulesConfig(
                version=1,
                rules=[
                    RecommendationRule(
                        id="pathological",
                        when={"flag": "pathological_gait"},
                        then={"needs_human_review": True},
                        priority=90,
                    )
                ],
            )
        )
        builder = StandardProfileBuilder(engine, default_cfg())
        params = make_parameters(flags=["pathological_gait"])
        profile = builder.build("P001", "2026-06-13T10:00:00Z", params, ANTHRO, CONFIDENCE)
        assert profile["needs_human_review"] is True

    def test_pronation_values_from_aggregated_params(self):
        builder = make_builder()
        params = make_parameters(
            make_agg_params("L", pronation="overpronation", rearfoot_angle=10.0),
            make_agg_params("R", pronation="neutral", rearfoot_angle=2.0),
        )
        profile = builder.build("P001", "2026-06-13T10:00:00Z", params, ANTHRO, CONFIDENCE)
        assert profile["pronation"]["classification"]["L"] == "overpronation"
        assert profile["pronation"]["classification"]["R"] == "neutral"
        assert profile["pronation"]["rearfoot_angle_at_midstance_deg"]["L"] == pytest.approx(10.0)
        assert profile["pronation"]["rearfoot_angle_at_midstance_deg"]["R"] == pytest.approx(2.0)

    def test_empty_l_params_uses_defaults(self):
        builder = make_builder()
        params = {"L": {}, "R": make_agg_params("R")}
        profile = builder.build("P001", "2026-06-13T10:00:00Z", params, ANTHRO, CONFIDENCE)
        # Should not raise; pronation defaults to "neutral"
        assert profile["pronation"]["classification"]["L"] == "neutral"


# â”€â”€ StandardProfileBuilder.validate() â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestValidate:
    def _valid_profile(self) -> Dict[str, Any]:
        builder = make_builder()
        return builder.build(
            "P001", "2026-06-13T10:00:00Z", make_parameters(), ANTHRO, CONFIDENCE
        )

    def test_valid_profile_returns_true(self):
        builder = make_builder()
        profile = self._valid_profile()
        ok, errors = builder.validate(profile)
        assert ok is True
        assert errors == []

    def test_invalid_profile_missing_patient_id(self):
        builder = make_builder()
        profile = self._valid_profile()
        del profile["patient_id"]
        ok, errors = builder.validate(profile)
        assert ok is False
        assert errors

    def test_invalid_confidence_score_out_of_range(self):
        builder = make_builder()
        profile = self._valid_profile()
        profile["confidence_scores"]["bad_key"] = 1.5  # > 1.0
        ok, errors = builder.validate(profile)
        assert ok is False
        assert errors

    def test_errors_are_strings(self):
        builder = make_builder()
        profile = self._valid_profile()
        del profile["patient_id"]
        ok, errors = builder.validate(profile)
        assert all(isinstance(e, str) for e in errors)


# â”€â”€ StandardGatingEngine â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestStandardGatingEngine:
    def test_proceed_ok_at_target(self):
        engine = StandardGatingEngine(default_cfg(target_clean_cycles_per_foot=8))
        cycles = [make_gait_cycle(cycle_id=i) for i in range(8)]
        ok, reason = engine.check_gait_quality(cycles)
        assert ok is True
        assert reason == "PROCEED_OK"

    def test_proceed_ok_above_target(self):
        engine = StandardGatingEngine(default_cfg(target_clean_cycles_per_foot=8))
        cycles = [make_gait_cycle(cycle_id=i) for i in range(10)]
        ok, reason = engine.check_gait_quality(cycles)
        assert ok is True
        assert reason == "PROCEED_OK"

    def test_proceed_with_warning_at_min(self):
        engine = StandardGatingEngine(
            default_cfg(target_clean_cycles_per_foot=8, min_clean_cycles_per_foot=4)
        )
        cycles = [make_gait_cycle(cycle_id=i) for i in range(4)]
        ok, reason = engine.check_gait_quality(cycles)
        assert ok is True
        assert reason == "PROCEED_WITH_WARNING"

    def test_proceed_with_warning_between_min_and_target(self):
        engine = StandardGatingEngine(
            default_cfg(target_clean_cycles_per_foot=8, min_clean_cycles_per_foot=4)
        )
        cycles = [make_gait_cycle(cycle_id=i) for i in range(6)]
        ok, reason = engine.check_gait_quality(cycles)
        assert ok is True
        assert reason == "PROCEED_WITH_WARNING"

    def test_rerecord_below_min(self):
        engine = StandardGatingEngine(
            default_cfg(target_clean_cycles_per_foot=8, min_clean_cycles_per_foot=4)
        )
        cycles = [make_gait_cycle(cycle_id=i) for i in range(3)]
        ok, reason = engine.check_gait_quality(cycles)
        assert ok is False
        assert reason == "RERECORD"

    def test_rerecord_no_cycles(self):
        engine = StandardGatingEngine(default_cfg())
        ok, reason = engine.check_gait_quality([])
        assert ok is False
        assert reason == "RERECORD"

    def test_is_acceptable_true_for_ok(self):
        engine = StandardGatingEngine(default_cfg(target_clean_cycles_per_foot=4))
        cycles = [make_gait_cycle(cycle_id=i) for i in range(5)]
        ok, _ = engine.check_gait_quality(cycles)
        assert ok is True

    def test_is_acceptable_false_for_rerecord(self):
        engine = StandardGatingEngine(default_cfg(min_clean_cycles_per_foot=4))
        ok, _ = engine.check_gait_quality([make_gait_cycle()])
        assert ok is False


# â”€â”€ factory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestFactory:
    def test_create_gating_engine_returns_correct_type(self):
        engine = create_gating_engine(default_cfg())
        assert isinstance(engine, StandardGatingEngine)

    def test_create_profile_builder_returns_correct_type(self):
        from gait.pipeline.config import load_recommendation_rules

        cfg = load_recommendation_rules()
        builder = create_profile_builder(cfg, default_cfg())
        assert isinstance(builder, StandardProfileBuilder)

    def test_create_profile_builder_with_empty_rules(self):
        builder = create_profile_builder(
            RecommendationRulesConfig(version=1, rules=[]),
            default_cfg(),
        )
        assert isinstance(builder, StandardProfileBuilder)

