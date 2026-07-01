"""Test that frontal_plane_excursion outputs real asymmetric values left vs right."""
from __future__ import annotations

import pytest

from gait.profile.builder import create_profile_builder
from gait.pipeline.config import load_pipeline_config, load_recommendation_rules


@pytest.mark.unit
class TestFrontalPlaneExcursionAsymmetry:
    """Verify frontal_plane_excursion_left_deg and _right_deg are computed separately and can be asymmetric."""

    def test_frontal_plane_excursion_outputs_real_asymmetric_values(self):
        """
        Test that profile builder outputs real, non-zero, DIFFERENT values for left and right FPE.

        FPE is computed per-foot during stance phase. Asymmetric gait means left and right
        feet have different pronation/supination patterns, thus different excursion values.
        """
        # Simulate parameters from analyzer: 4 gait cycles per foot with different FPE values
        parameters = {
            "L": {
                "foot": "L",
                "cycle_count": 4,
                # Left foot: higher frontal plane excursion (more pronation/eversion)
                "frontal_plane_excursion_deg_mean": 14.2,  # Real computed per-cycle mean
                "frontal_plane_excursion_deg_std": 1.1,
                "cadence_steps_per_min_mean": 112.0,
                "cadence_steps_per_min_std": 2.0,
                "foot_strike_type": "rearfoot",
                "arch_type": "low",
                "pronation_type": "overpronation",
                "rearfoot_angle_deg_mean": 8.4,
                "rearfoot_angle_deg_std": 0.9,
                "foot_strike_angle_deg_mean": 5.2,
                "foot_strike_angle_deg_std": 1.1,
                "stance_pct_mean": 61.2,
                "stance_pct_std": 1.5,
                "swing_pct_mean": 38.8,
                "swing_pct_std": 1.5,
                "quality_flag": "PROCEED_OK",
            },
            "R": {
                "foot": "R",
                "cycle_count": 4,
                # Right foot: lower frontal plane excursion (less pronation/eversion)
                "frontal_plane_excursion_deg_mean": 8.7,  # Real computed per-cycle mean
                "frontal_plane_excursion_deg_std": 0.8,
                "cadence_steps_per_min_mean": 112.0,
                "cadence_steps_per_min_std": 2.0,
                "foot_strike_type": "rearfoot",
                "arch_type": "normal",
                "pronation_type": "neutral",
                "rearfoot_angle_deg_mean": 2.1,
                "rearfoot_angle_deg_std": 0.8,
                "foot_strike_angle_deg_mean": 4.9,
                "foot_strike_angle_deg_std": 1.0,
                "stance_pct_mean": 60.4,
                "stance_pct_std": 1.4,
                "swing_pct_mean": 39.6,
                "swing_pct_std": 1.4,
                "quality_flag": "PROCEED_OK",
            },
        }

        anthropometrics = {
            "height_cm": 172.0,
            "mass_kg": 68.0,
            "foot_length_mm": {"L": 258.0, "R": 260.0},
            "foot_width_mm": {"L": 98.0, "R": 99.0},
        }

        # Build profile
        rules_config = load_recommendation_rules()
        analysis_config = load_pipeline_config().analysis
        builder = create_profile_builder(rules_config, analysis_config)

        profile = builder.build(
            patient_id="P123",
            session_timestamp="2026-06-18T12:00:00Z",
            parameters=parameters,
            anthropometrics=anthropometrics,
            confidence_scores={"pipeline": 0.92},
        )

        # Get the output values from the profile
        pronation = profile["pronation"]
        fpe_left = pronation["frontal_plane_excursion_left_deg"]
        fpe_right = pronation["frontal_plane_excursion_right_deg"]

        # ASSERTION 1: Both values are non-zero (real computed values, not defaults)
        assert fpe_left > 0, f"Left FPE should be non-zero, got {fpe_left}"
        assert fpe_right > 0, f"Right FPE should be non-zero, got {fpe_right}"

        # ASSERTION 2: Values are asymmetric (left â‰  right)
        assert fpe_left != fpe_right, \
            f"FPE should be asymmetric (left={fpe_left}, right={fpe_right})"

        # ASSERTION 3: Actual values match input (verify no transformation/aggregation error)
        assert abs(fpe_left - 14.2) < 0.01, \
            f"Left FPE should be 14.2 (left foot overpronation), got {fpe_left}"
        assert abs(fpe_right - 8.7) < 0.01, \
            f"Right FPE should be 8.7 (right foot neutral), got {fpe_right}"

        # ASSERTION 4: Left > Right (overpronating vs neutral foot)
        assert fpe_left > fpe_right, \
            f"Left (overpronated) should have higher FPE than right (neutral): {fpe_left} vs {fpe_right}"

    def test_frontal_plane_excursion_defaults_to_zero_when_missing(self):
        """Verify backward compatibility: FPE defaults to 0.0 if not provided."""
        # Minimal parameters without FPE values
        parameters = {
            "L": {
                "foot": "L",
                "cycle_count": 2,
                "cadence_steps_per_min_mean": 110.0,
                "cadence_steps_per_min_std": 1.0,
                "foot_strike_type": "rearfoot",
                "arch_type": "normal",
                "pronation_type": "neutral",
                "stance_pct_mean": 61.0,
                "stance_pct_std": 1.0,
                "swing_pct_mean": 39.0,
                "swing_pct_std": 1.0,
                "quality_flag": "RERECORD",
            },
            "R": {
                "foot": "R",
                "cycle_count": 2,
                "cadence_steps_per_min_mean": 110.0,
                "cadence_steps_per_min_std": 1.0,
                "foot_strike_type": "rearfoot",
                "arch_type": "normal",
                "pronation_type": "neutral",
                "stance_pct_mean": 60.0,
                "stance_pct_std": 1.0,
                "swing_pct_mean": 40.0,
                "swing_pct_std": 1.0,
                "quality_flag": "RERECORD",
            },
        }

        anthropometrics = {
            "height_cm": 172.0,
            "mass_kg": 68.0,
            "foot_length_mm": {"L": 258.0, "R": 260.0},
            "foot_width_mm": {"L": 98.0, "R": 99.0},
        }

        rules_config = load_recommendation_rules()
        analysis_config = load_pipeline_config().analysis
        builder = create_profile_builder(rules_config, analysis_config)

        profile = builder.build(
            patient_id="P124",
            session_timestamp="2026-06-18T12:01:00Z",
            parameters=parameters,
            anthropometrics=anthropometrics,
            confidence_scores={"pipeline": 0.85},
        )

        pronation = profile["pronation"]
        # Should default to 0.0 if not provided (line 223-224 of builder.py)
        assert pronation["frontal_plane_excursion_left_deg"] == 0.0, \
            "FPE should default to 0.0 when not provided"
        assert pronation["frontal_plane_excursion_right_deg"] == 0.0, \
            "FPE should default to 0.0 when not provided"

