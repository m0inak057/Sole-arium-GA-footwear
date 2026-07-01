"""End-to-end test verifying step lengths flow through full pipeline to profile output."""
from __future__ import annotations

import numpy as np
import pytest

from gait.common.interfaces import Keypoint, KeypointFrame
from gait.profile.builder import create_profile_builder
from gait.pipeline.config import load_pipeline_config, load_recommendation_rules


@pytest.mark.unit
class TestPipelineEndToEndStepLengths:
    """Verify step_length_left_m and step_length_right_m reach final profile as non-zero values."""

    def test_builder_receives_and_outputs_step_lengths(self):
        """Test that profile builder correctly outputs step_length_left_m and step_length_right_m."""
        # Simulate parameters from analyzer with real step lengths
        parameters = {
            "L": {
                "foot": "L",
                "cycle_count": 4,
                "cadence_steps_per_min_mean": 112.0,
                "cadence_steps_per_min_std": 2.0,
                "foot_strike_type": "rearfoot",
                "arch_type": "normal",
                "pronation_type": "neutral",
                "frontal_plane_excursion_deg_mean": 6.5,
                "frontal_plane_excursion_deg_std": 0.8,
                "foot_strike_angle_deg_mean": 5.2,
                "foot_strike_angle_deg_std": 1.1,
                "rearfoot_angle_deg_mean": 2.1,
                "rearfoot_angle_deg_std": 0.9,
                "stance_pct_mean": 61.2,
                "stance_pct_std": 1.5,
                "swing_pct_mean": 38.8,
                "swing_pct_std": 1.5,
                "quality_flag": "PROCEED_OK",
                # NEW: Real computed step lengths (asymmetric)
                "step_length_left_m": 0.72,   # Left foot takes longer steps
                "step_length_right_m": 0.68,  # Right foot takes shorter steps
                # NEW: Real computed foot progression angles (asymmetric)
                "foot_progression_angle_left_deg": 8.5,
                "foot_progression_angle_right_deg": -3.2,
            },
            "R": {
                "foot": "R",
                "cycle_count": 4,
                "cadence_steps_per_min_mean": 112.0,
                "cadence_steps_per_min_std": 2.0,
                "foot_strike_type": "rearfoot",
                "arch_type": "normal",
                "pronation_type": "neutral",
                "frontal_plane_excursion_deg_mean": 5.8,
                "frontal_plane_excursion_deg_std": 0.7,
                "foot_strike_angle_deg_mean": 4.9,
                "foot_strike_angle_deg_std": 1.0,
                "rearfoot_angle_deg_mean": 1.8,
                "rearfoot_angle_deg_std": 0.8,
                "stance_pct_mean": 60.4,
                "stance_pct_std": 1.4,
                "swing_pct_mean": 39.6,
                "swing_pct_std": 1.4,
                "quality_flag": "PROCEED_OK",
                # NEW: Same step lengths and foot progression angles
                "step_length_left_m": 0.72,
                "step_length_right_m": 0.68,
                "foot_progression_angle_left_deg": 8.5,
                "foot_progression_angle_right_deg": -3.2,
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
            patient_id="P999",
            session_timestamp="2026-06-18T12:00:00Z",
            parameters=parameters,
            anthropometrics=anthropometrics,
            confidence_scores={"pipeline": 0.92},
        )

        # Verify step lengths are in the profile
        assert "spatiotemporal" in profile, "Profile should have spatiotemporal section"
        spatiotemporal = profile["spatiotemporal"]

        # CRITICAL: Verify non-zero real values
        assert spatiotemporal["step_length_left_m"] == 0.72, f"Expected 0.72m, got {spatiotemporal['step_length_left_m']}"
        assert spatiotemporal["step_length_right_m"] == 0.68, f"Expected 0.68m, got {spatiotemporal['step_length_right_m']}"

        # CRITICAL: Verify asymmetry (left â‰  right)
        assert spatiotemporal["step_length_left_m"] != spatiotemporal["step_length_right_m"], \
            "Step lengths should be asymmetric (left â‰  right)"
        assert spatiotemporal["step_length_left_m"] > spatiotemporal["step_length_right_m"], \
            "Left step length should be greater than right in this asymmetric gait"

        # CRITICAL: Verify foot progression angles are in profile and asymmetric
        assert spatiotemporal["foot_progression_angle_left_deg"] == 8.5, \
            f"Expected 8.5Â°, got {spatiotemporal['foot_progression_angle_left_deg']}"
        assert spatiotemporal["foot_progression_angle_right_deg"] == -3.2, \
            f"Expected -3.2Â°, got {spatiotemporal['foot_progression_angle_right_deg']}"

        # Verify asymmetry in foot progression angles
        assert spatiotemporal["foot_progression_angle_left_deg"] != spatiotemporal["foot_progression_angle_right_deg"], \
            "Foot progression angles should be different (left toe-out, right toe-in)"

    def test_builder_defaults_to_zero_without_step_length_data(self):
        """Verify that step_length defaults to 0.0 if not provided (backward compat)."""
        # Minimal parameters without step lengths
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
            patient_id="P998",
            session_timestamp="2026-06-18T12:01:00Z",
            parameters=parameters,
            anthropometrics=anthropometrics,
            confidence_scores={"pipeline": 0.85},
        )

        spatiotemporal = profile["spatiotemporal"]
        # Should default to 0.0 if not provided
        assert spatiotemporal["step_length_left_m"] == 0.0, \
            "Step length should default to 0.0 when not provided"
        assert spatiotemporal["step_length_right_m"] == 0.0, \
            "Step length should default to 0.0 when not provided"

