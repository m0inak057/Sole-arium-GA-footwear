"""Test GaitHealthCoach with comprehensive fallback validation.

These tests verify:
1. Agent success path (happy path)
2. Malformed JSON rejection â†’ static rules fallback
3. Hallucinated defect rejection â†’ static rules fallback
4. LLM timeout/exception â†’ static rules fallback
5. agent_decisions log entries are written correctly
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gait.agents.health_coach import GaitHealthCoach
from gait.profile.builder import create_profile_builder
from gait.profile.schema import HealthAssessment
from gait.pipeline.config import load_pipeline_config, load_recommendation_rules


@pytest.mark.unit
class TestHealthCoachFallback:
    """Verify fallback mechanism triggers under failure conditions."""

    def test_malformed_json_fallback_to_static_rules(self):
        """Test that malformed LLM JSON response triggers fallback to static rules.

        Verifies that the final profile's health_assessment EXACTLY MATCHES
        what the static rules engine alone would have produced.
        """
        # Mock LLM that returns malformed JSON
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text='{"incomplete": "json without closing brace')]
        )

        coach = GaitHealthCoach(mock_client)

        # Build agent parameters
        agent_params = {
            "step_length_left_m": 0.72,
            "step_length_right_m": 0.68,
            "foot_progression_angle_left_deg": 8.5,
            "foot_progression_angle_right_deg": -3.2,
            "rearfoot_angle_deg_mean_L": 11.4,
            "rearfoot_angle_deg_mean_R": 9.8,
            "frontal_plane_excursion_deg_mean_L": 12.3,
            "frontal_plane_excursion_deg_mean_R": 11.8,
            "pronation_type_L": "overpronation",
            "pronation_type_R": "overpronation",
            "arch_type_L": "low",
            "arch_type_R": "low",
            "foot_strike_type_L": "rearfoot",
            "foot_strike_type_R": "rearfoot",
            "left_metrics": {
                "pronation_type": "overpronation",
                "arch_type": "low",
                "rearfoot_angle_deg_mean": 11.4,
                "frontal_plane_excursion_deg_mean": 12.3,
            },
            "right_metrics": {
                "pronation_type": "overpronation",
                "arch_type": "low",
                "rearfoot_angle_deg_mean": 9.8,
                "frontal_plane_excursion_deg_mean": 11.8,
            },
        }

        # Predict with malformed JSON
        assessment, confidence, reasoning = coach.predict(agent_params)

        # Verify fallback
        assert assessment is None, "Malformed JSON should return None"
        assert confidence == 0.0, "Confidence should be 0 on failure"
        assert "malformed json" in reasoning.lower(), f"Reasoning should mention malformed JSON: {reasoning}"

        # Now run full pipeline with static rules as fallback
        parameters = {
            "L": {
                "foot": "L",
                "cycle_count": 4,
                "cadence_steps_per_min_mean": 112.0,
                "cadence_steps_per_min_std": 2.0,
                "foot_strike_type": "rearfoot",
                "arch_type": "low",
                "pronation_type": "overpronation",
                "frontal_plane_excursion_deg_mean": 12.3,
                "frontal_plane_excursion_deg_std": 0.8,
                "foot_strike_angle_deg_mean": 5.2,
                "foot_strike_angle_deg_std": 1.1,
                "rearfoot_angle_deg_mean": 11.4,
                "rearfoot_angle_deg_std": 0.9,
                "stance_pct_mean": 61.2,
                "stance_pct_std": 1.5,
                "swing_pct_mean": 38.8,
                "swing_pct_std": 1.5,
                "quality_flag": "PROCEED_OK",
                "step_length_left_m": 0.72,
                "step_length_right_m": 0.68,
                "foot_progression_angle_left_deg": 8.5,
                "foot_progression_angle_right_deg": -3.2,
            },
            "R": {
                "foot": "R",
                "cycle_count": 4,
                "cadence_steps_per_min_mean": 112.0,
                "cadence_steps_per_min_std": 2.0,
                "foot_strike_type": "rearfoot",
                "arch_type": "low",
                "pronation_type": "overpronation",
                "frontal_plane_excursion_deg_mean": 11.8,
                "frontal_plane_excursion_deg_std": 0.7,
                "foot_strike_angle_deg_mean": 4.9,
                "foot_strike_angle_deg_std": 1.0,
                "rearfoot_angle_deg_mean": 9.8,
                "rearfoot_angle_deg_std": 0.8,
                "stance_pct_mean": 60.4,
                "stance_pct_std": 1.4,
                "swing_pct_mean": 39.6,
                "swing_pct_std": 1.4,
                "quality_flag": "PROCEED_OK",
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

        # First, get static-rules-only profile (no agent)
        rules_config = load_recommendation_rules()
        analysis_config = load_pipeline_config().analysis
        builder_static = create_profile_builder(rules_config, analysis_config)

        profile_static = builder_static.build(
            patient_id="P_STATIC",
            session_timestamp="2026-06-18T12:00:00Z",
            parameters=parameters,
            anthropometrics=anthropometrics,
            confidence_scores={"pipeline": 0.92},
        )

        # Now get profile with agent (will fallback due to malformed JSON)
        builder_with_agent = create_profile_builder(rules_config, analysis_config)
        builder_with_agent._health_coach = coach

        profile_with_fallback = builder_with_agent.build(
            patient_id="P_FALLBACK",
            session_timestamp="2026-06-18T12:00:00Z",
            parameters=parameters,
            anthropometrics=anthropometrics,
            confidence_scores={"pipeline": 0.92},
        )

        # Compare health_assessment
        health_static = profile_static["health_assessment"]
        health_fallback = profile_with_fallback["health_assessment"]

        # They should be identical (same defects, same improvements)
        assert health_fallback["defects_found"] == health_static["defects_found"], \
            "Fallback health_assessment defects should match static-rules-only output"
        assert health_fallback["what_went_right"] == health_static["what_went_right"], \
            "Fallback health_assessment what_went_right should match static-rules-only output"

        # Verify agent_decisions log
        assert profile_with_fallback["agent_decisions"] is not None
        assert profile_with_fallback["agent_decisions"]["method_used"] == "static_rules"
        assert "malformed json" in profile_with_fallback["agent_decisions"]["fallback_reason"].lower()
        assert profile_with_fallback["agent_decisions"]["confidence_score"] == 0.0

    def test_hallucinated_defect_fallback_to_static_rules(self):
        """Test that hallucinated defect (not grounded in input) is rejected.

        LLM claims "Severe Overpronation" but input metrics show "neutral" pronation.
        This should fail validation and trigger fallback.
        """
        # Mock LLM that returns hallucinated defect (overpronation when input is neutral)
        valid_response = {
            "what_went_right": ["Good symmetry"],
            "defects_found": [
                {
                    "name": "Severe Overpronation - Left Foot",
                    "severity": "severe",
                    "affected_side": "left",
                    "biomechanical_cause": "Your left foot is severely overpronated",
                    "gait_cycle_phase": "Mid-Stance",
                }
            ],
            "improvement_plan": [],
        }

        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=str(valid_response))]
        )

        import json
        mock_client.messages.create.return_value.content[0].text = json.dumps(valid_response)

        coach = GaitHealthCoach(mock_client)

        # Agent parameters with NEUTRAL pronation on left (contradicts LLM claim)
        agent_params = {
            "step_length_left_m": 0.70,
            "step_length_right_m": 0.68,
            "foot_progression_angle_left_deg": 5.0,
            "foot_progression_angle_right_deg": 5.0,
            "rearfoot_angle_deg_mean_L": 2.0,  # NEUTRAL (0-4Â°)
            "rearfoot_angle_deg_mean_R": 2.5,
            "frontal_plane_excursion_deg_mean_L": 5.0,
            "frontal_plane_excursion_deg_mean_R": 5.5,
            "pronation_type_L": "neutral",  # NOT overpronation!
            "pronation_type_R": "neutral",
            "arch_type_L": "normal",
            "arch_type_R": "normal",
            "foot_strike_type_L": "rearfoot",
            "foot_strike_type_R": "rearfoot",
            "left_metrics": {
                "pronation_type": "neutral",  # Contradicts LLM claim
                "arch_type": "normal",
                "rearfoot_angle_deg_mean": 2.0,
                "frontal_plane_excursion_deg_mean": 5.0,
            },
            "right_metrics": {
                "pronation_type": "neutral",
                "arch_type": "normal",
                "rearfoot_angle_deg_mean": 2.5,
                "frontal_plane_excursion_deg_mean": 5.5,
            },
        }

        # Predict should return None due to validation failure
        assessment, confidence, reasoning = coach.predict(agent_params)

        assert assessment is None, "Hallucinated defect should fail validation"
        assert confidence == 0.0
        assert "overpronation" in reasoning.lower() or "validation" in reasoning.lower(), \
            f"Reasoning should explain defect validation failure: {reasoning}"

        # Verify full pipeline falls back
        parameters = {
            "L": {
                "foot": "L",
                "cycle_count": 4,
                "cadence_steps_per_min_mean": 110.0,
                "cadence_steps_per_min_std": 2.0,
                "foot_strike_type": "rearfoot",
                "arch_type": "normal",
                "pronation_type": "neutral",  # NOT overpronation
                "frontal_plane_excursion_deg_mean": 5.0,
                "frontal_plane_excursion_deg_std": 0.8,
                "foot_strike_angle_deg_mean": 5.2,
                "foot_strike_angle_deg_std": 1.1,
                "rearfoot_angle_deg_mean": 2.0,  # Neutral
                "rearfoot_angle_deg_std": 0.9,
                "stance_pct_mean": 61.0,
                "stance_pct_std": 1.5,
                "swing_pct_mean": 39.0,
                "swing_pct_std": 1.5,
                "quality_flag": "PROCEED_OK",
                "step_length_left_m": 0.70,
                "step_length_right_m": 0.68,
                "foot_progression_angle_left_deg": 5.0,
                "foot_progression_angle_right_deg": 5.0,
            },
            "R": {
                "foot": "R",
                "cycle_count": 4,
                "cadence_steps_per_min_mean": 110.0,
                "cadence_steps_per_min_std": 2.0,
                "foot_strike_type": "rearfoot",
                "arch_type": "normal",
                "pronation_type": "neutral",
                "frontal_plane_excursion_deg_mean": 5.5,
                "frontal_plane_excursion_deg_std": 0.7,
                "foot_strike_angle_deg_mean": 4.9,
                "foot_strike_angle_deg_std": 1.0,
                "rearfoot_angle_deg_mean": 2.5,
                "rearfoot_angle_deg_std": 0.8,
                "stance_pct_mean": 60.5,
                "stance_pct_std": 1.4,
                "swing_pct_mean": 39.5,
                "swing_pct_std": 1.4,
                "quality_flag": "PROCEED_OK",
                "step_length_left_m": 0.70,
                "step_length_right_m": 0.68,
                "foot_progression_angle_left_deg": 5.0,
                "foot_progression_angle_right_deg": 5.0,
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
        builder_with_agent = create_profile_builder(rules_config, analysis_config)
        builder_with_agent._health_coach = coach

        profile = builder_with_agent.build(
            patient_id="P_HALLUCINATION",
            session_timestamp="2026-06-18T12:00:00Z",
            parameters=parameters,
            anthropometrics=anthropometrics,
            confidence_scores={"pipeline": 0.92},
        )

        # Verify fallback occurred
        assert profile["agent_decisions"]["method_used"] == "static_rules"
        assert "validation" in profile["agent_decisions"]["fallback_reason"].lower() or \
               "overpronation" in profile["agent_decisions"]["fallback_reason"].lower(), \
            f"Fallback reason should explain validation failure: {profile['agent_decisions']['fallback_reason']}"

    def test_llm_timeout_exception_fallback(self):
        """Test that LLM timeout/exception triggers clean fallback."""
        # Mock LLM that raises an exception
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = TimeoutError("LLM request timed out")

        coach = GaitHealthCoach(mock_client)

        agent_params = {
            "step_length_left_m": 0.70,
            "step_length_right_m": 0.68,
            "foot_progression_angle_left_deg": 5.0,
            "foot_progression_angle_right_deg": 5.0,
            "rearfoot_angle_deg_mean_L": 2.0,
            "rearfoot_angle_deg_mean_R": 2.5,
            "frontal_plane_excursion_deg_mean_L": 5.0,
            "frontal_plane_excursion_deg_mean_R": 5.5,
            "pronation_type_L": "neutral",
            "pronation_type_R": "neutral",
            "arch_type_L": "normal",
            "arch_type_R": "normal",
            "foot_strike_type_L": "rearfoot",
            "foot_strike_type_R": "rearfoot",
            "left_metrics": {"pronation_type": "neutral", "arch_type": "normal", "rearfoot_angle_deg_mean": 2.0, "frontal_plane_excursion_deg_mean": 5.0},
            "right_metrics": {"pronation_type": "neutral", "arch_type": "normal", "rearfoot_angle_deg_mean": 2.5, "frontal_plane_excursion_deg_mean": 5.5},
        }

        # Predict should handle exception gracefully
        assessment, confidence, reasoning = coach.predict(agent_params)

        assert assessment is None
        assert confidence == 0.0
        assert "TimeoutError" in reasoning or "timeout" in reasoning.lower(), \
            f"Reasoning should mention timeout: {reasoning}"

        # Verify pipeline doesn't crash and falls back
        parameters = {
            "L": {
                "foot": "L",
                "cycle_count": 4,
                "cadence_steps_per_min_mean": 110.0,
                "cadence_steps_per_min_std": 2.0,
                "foot_strike_type": "rearfoot",
                "arch_type": "normal",
                "pronation_type": "neutral",
                "frontal_plane_excursion_deg_mean": 5.0,
                "frontal_plane_excursion_deg_std": 0.8,
                "foot_strike_angle_deg_mean": 5.2,
                "foot_strike_angle_deg_std": 1.1,
                "rearfoot_angle_deg_mean": 2.0,
                "rearfoot_angle_deg_std": 0.9,
                "stance_pct_mean": 61.0,
                "stance_pct_std": 1.5,
                "swing_pct_mean": 39.0,
                "swing_pct_std": 1.5,
                "quality_flag": "PROCEED_OK",
                "step_length_left_m": 0.70,
                "step_length_right_m": 0.68,
                "foot_progression_angle_left_deg": 5.0,
                "foot_progression_angle_right_deg": 5.0,
            },
            "R": {
                "foot": "R",
                "cycle_count": 4,
                "cadence_steps_per_min_mean": 110.0,
                "cadence_steps_per_min_std": 2.0,
                "foot_strike_type": "rearfoot",
                "arch_type": "normal",
                "pronation_type": "neutral",
                "frontal_plane_excursion_deg_mean": 5.5,
                "frontal_plane_excursion_deg_std": 0.7,
                "foot_strike_angle_deg_mean": 4.9,
                "foot_strike_angle_deg_std": 1.0,
                "rearfoot_angle_deg_mean": 2.5,
                "rearfoot_angle_deg_std": 0.8,
                "stance_pct_mean": 60.5,
                "stance_pct_std": 1.4,
                "swing_pct_mean": 39.5,
                "swing_pct_std": 1.4,
                "quality_flag": "PROCEED_OK",
                "step_length_left_m": 0.70,
                "step_length_right_m": 0.68,
                "foot_progression_angle_left_deg": 5.0,
                "foot_progression_angle_right_deg": 5.0,
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
        builder_with_agent = create_profile_builder(rules_config, analysis_config)
        builder_with_agent._health_coach = coach

        # This should not crash
        profile = builder_with_agent.build(
            patient_id="P_TIMEOUT",
            session_timestamp="2026-06-18T12:00:00Z",
            parameters=parameters,
            anthropometrics=anthropometrics,
            confidence_scores={"pipeline": 0.92},
        )

        # Verify fallback occurred
        assert profile["agent_decisions"]["method_used"] == "static_rules"
        assert "TimeoutError" in profile["agent_decisions"]["fallback_reason"] or \
               "timeout" in profile["agent_decisions"]["fallback_reason"].lower()

    def test_hallucinated_arch_type_fallback(self):
        """Test that hallucinated arch defect (low arch when input is normal) is rejected."""
        valid_response = {
            "what_went_right": ["Good gait"],
            "defects_found": [
                {
                    "name": "Flat Foot (Pes Planus) - Left Foot",
                    "severity": "moderate",
                    "affected_side": "left",
                    "biomechanical_cause": "Your left arch is collapsed",
                    "gait_cycle_phase": "Stance",
                }
            ],
            "improvement_plan": [],
        }

        import json
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps(valid_response))]
        )

        coach = GaitHealthCoach(mock_client)

        # Input: normal arch on left, but LLM claims flat arch
        agent_params = {
            "step_length_left_m": 0.70,
            "step_length_right_m": 0.68,
            "foot_progression_angle_left_deg": 5.0,
            "foot_progression_angle_right_deg": 5.0,
            "rearfoot_angle_deg_mean_L": 2.0,
            "rearfoot_angle_deg_mean_R": 2.5,
            "frontal_plane_excursion_deg_mean_L": 5.0,
            "frontal_plane_excursion_deg_mean_R": 5.5,
            "pronation_type_L": "neutral",
            "pronation_type_R": "neutral",
            "arch_type_L": "normal",  # NOT low!
            "arch_type_R": "normal",
            "foot_strike_type_L": "rearfoot",
            "foot_strike_type_R": "rearfoot",
            "left_metrics": {
                "pronation_type": "neutral",
                "arch_type": "normal",  # NOT low!
                "rearfoot_angle_deg_mean": 2.0,
                "frontal_plane_excursion_deg_mean": 5.0,
            },
            "right_metrics": {
                "pronation_type": "neutral",
                "arch_type": "normal",
                "rearfoot_angle_deg_mean": 2.5,
                "frontal_plane_excursion_deg_mean": 5.5,
            },
        }

        assessment, confidence, reasoning = coach.predict(agent_params)
        assert assessment is None, "Hallucinated arch defect should be rejected"
        assert "not grounded" in reasoning.lower(), f"Reason should mention grounding: {reasoning}"

    def test_hallucinated_forefoot_strike_fallback(self):
        """Test that hallucinated foot strike defect (forefoot when input is rearfoot) is rejected."""
        valid_response = {
            "what_went_right": [],
            "defects_found": [
                {
                    "name": "Forefoot Strike Pattern",
                    "severity": "mild",
                    "affected_side": "bilateral",
                    "biomechanical_cause": "You strike with your forefoot",
                    "gait_cycle_phase": "Initial Contact",
                }
            ],
            "improvement_plan": [],
        }

        import json
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps(valid_response))]
        )

        coach = GaitHealthCoach(mock_client)

        agent_params = {
            "step_length_left_m": 0.70,
            "step_length_right_m": 0.68,
            "foot_progression_angle_left_deg": 5.0,
            "foot_progression_angle_right_deg": 5.0,
            "rearfoot_angle_deg_mean_L": 2.0,
            "rearfoot_angle_deg_mean_R": 2.5,
            "frontal_plane_excursion_deg_mean_L": 5.0,
            "frontal_plane_excursion_deg_mean_R": 5.5,
            "pronation_type_L": "neutral",
            "pronation_type_R": "neutral",
            "arch_type_L": "normal",
            "arch_type_R": "normal",
            "foot_strike_type_L": "rearfoot",  # NOT forefoot!
            "foot_strike_type_R": "rearfoot",
            "left_metrics": {
                "pronation_type": "neutral",
                "arch_type": "normal",
                "foot_strike_type": "rearfoot",  # NOT forefoot!
                "rearfoot_angle_deg_mean": 2.0,
                "frontal_plane_excursion_deg_mean": 5.0,
            },
            "right_metrics": {
                "pronation_type": "neutral",
                "arch_type": "normal",
                "foot_strike_type": "rearfoot",
                "rearfoot_angle_deg_mean": 2.5,
                "frontal_plane_excursion_deg_mean": 5.5,
            },
        }

        assessment, confidence, reasoning = coach.predict(agent_params)
        assert assessment is None
        assert "not grounded" in reasoning.lower()

    def test_hallucinated_step_asymmetry_fallback(self):
        """Test that hallucinated asymmetry defect is rejected when steps are actually symmetric."""
        valid_response = {
            "what_went_right": [],
            "defects_found": [
                {
                    "name": "High Step Length Asymmetry",
                    "severity": "moderate",
                    "affected_side": "bilateral",
                    "biomechanical_cause": "Your step lengths are very different",
                    "gait_cycle_phase": "Throughout gait cycle",
                }
            ],
            "improvement_plan": [],
        }

        import json
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps(valid_response))]
        )

        coach = GaitHealthCoach(mock_client)

        agent_params = {
            "step_length_left_m": 0.70,  # Nearly identical steps
            "step_length_right_m": 0.71,  # <2% difference, well below 10% threshold
            "foot_progression_angle_left_deg": 5.0,
            "foot_progression_angle_right_deg": 5.0,
            "rearfoot_angle_deg_mean_L": 2.0,
            "rearfoot_angle_deg_mean_R": 2.5,
            "frontal_plane_excursion_deg_mean_L": 5.0,
            "frontal_plane_excursion_deg_mean_R": 5.5,
            "pronation_type_L": "neutral",
            "pronation_type_R": "neutral",
            "arch_type_L": "normal",
            "arch_type_R": "normal",
            "foot_strike_type_L": "rearfoot",
            "foot_strike_type_R": "rearfoot",
            "left_metrics": {"pronation_type": "neutral", "arch_type": "normal"},
            "right_metrics": {"pronation_type": "neutral", "arch_type": "normal"},
        }

        assessment, confidence, reasoning = coach.predict(agent_params)
        assert assessment is None
        assert "not grounded" in reasoning.lower()

    def test_hallucinated_toe_in_fallback(self):
        """Test that hallucinated toe-in defect is rejected when foot progression is neutral."""
        valid_response = {
            "what_went_right": [],
            "defects_found": [
                {
                    "name": "Toe-In Foot Progression",
                    "severity": "mild",
                    "affected_side": "left",
                    "biomechanical_cause": "Your left foot points inward during walking",
                    "gait_cycle_phase": "Initial Contact",
                }
            ],
            "improvement_plan": [],
        }

        import json
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps(valid_response))]
        )

        coach = GaitHealthCoach(mock_client)

        agent_params = {
            "step_length_left_m": 0.70,
            "step_length_right_m": 0.68,
            "foot_progression_angle_left_deg": 5.0,  # Neutral/toe-out, NOT toe-in!
            "foot_progression_angle_right_deg": 5.0,
            "rearfoot_angle_deg_mean_L": 2.0,
            "rearfoot_angle_deg_mean_R": 2.5,
            "frontal_plane_excursion_deg_mean_L": 5.0,
            "frontal_plane_excursion_deg_mean_R": 5.5,
            "pronation_type_L": "neutral",
            "pronation_type_R": "neutral",
            "arch_type_L": "normal",
            "arch_type_R": "normal",
            "foot_strike_type_L": "rearfoot",
            "foot_strike_type_R": "rearfoot",
            "left_metrics": {"pronation_type": "neutral", "arch_type": "normal"},
            "right_metrics": {"pronation_type": "neutral", "arch_type": "normal"},
        }

        assessment, confidence, reasoning = coach.predict(agent_params)
        assert assessment is None
        assert "not grounded" in reasoning.lower()

    def test_hallucinated_frontal_excursion_fallback(self):
        """Test that hallucinated high excursion defect is rejected when excursion is low."""
        valid_response = {
            "what_went_right": [],
            "defects_found": [
                {
                    "name": "High Frontal-Plane Excursion",
                    "severity": "moderate",
                    "affected_side": "bilateral",
                    "biomechanical_cause": "Your rearfoot motion is excessive during stance",
                    "gait_cycle_phase": "Loading Response to Mid-Stance",
                }
            ],
            "improvement_plan": [],
        }

        import json
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps(valid_response))]
        )

        coach = GaitHealthCoach(mock_client)

        agent_params = {
            "step_length_left_m": 0.70,
            "step_length_right_m": 0.68,
            "foot_progression_angle_left_deg": 5.0,
            "foot_progression_angle_right_deg": 5.0,
            "rearfoot_angle_deg_mean_L": 2.0,
            "rearfoot_angle_deg_mean_R": 2.5,
            "frontal_plane_excursion_deg_mean_L": 4.0,  # LOW excursion, NOT high!
            "frontal_plane_excursion_deg_mean_R": 4.5,  # Below 8Â° threshold
            "pronation_type_L": "neutral",
            "pronation_type_R": "neutral",
            "arch_type_L": "normal",
            "arch_type_R": "normal",
            "foot_strike_type_L": "rearfoot",
            "foot_strike_type_R": "rearfoot",
            "left_metrics": {"pronation_type": "neutral", "arch_type": "normal"},
            "right_metrics": {"pronation_type": "neutral", "arch_type": "normal"},
        }

        assessment, confidence, reasoning = coach.predict(agent_params)
        assert assessment is None
        assert "not grounded" in reasoning.lower()

    def test_agent_decisions_logged_correctly(self):
        """Test that agent_decisions log entries are correctly formatted and inspectable."""
        # Mock successful LLM response
        valid_response = {
            "what_went_right": ["Good symmetry in cadence"],
            "defects_found": [],
            "improvement_plan": [],
        }

        import json
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=json.dumps(valid_response))]
        )

        coach = GaitHealthCoach(mock_client)

        agent_params = {
            "step_length_left_m": 0.70,
            "step_length_right_m": 0.68,
            "foot_progression_angle_left_deg": 5.0,
            "foot_progression_angle_right_deg": 5.0,
            "rearfoot_angle_deg_mean_L": 2.0,
            "rearfoot_angle_deg_mean_R": 2.5,
            "frontal_plane_excursion_deg_mean_L": 5.0,
            "frontal_plane_excursion_deg_mean_R": 5.5,
            "pronation_type_L": "neutral",
            "pronation_type_R": "neutral",
            "arch_type_L": "normal",
            "arch_type_R": "normal",
            "foot_strike_type_L": "rearfoot",
            "foot_strike_type_R": "rearfoot",
            "left_metrics": {"pronation_type": "neutral", "arch_type": "normal", "rearfoot_angle_deg_mean": 2.0, "frontal_plane_excursion_deg_mean": 5.0},
            "right_metrics": {"pronation_type": "neutral", "arch_type": "normal", "rearfoot_angle_deg_mean": 2.5, "frontal_plane_excursion_deg_mean": 5.5},
        }

        parameters = {
            "L": {
                "foot": "L",
                "cycle_count": 4,
                "cadence_steps_per_min_mean": 110.0,
                "cadence_steps_per_min_std": 2.0,
                "foot_strike_type": "rearfoot",
                "arch_type": "normal",
                "pronation_type": "neutral",
                "frontal_plane_excursion_deg_mean": 5.0,
                "frontal_plane_excursion_deg_std": 0.8,
                "foot_strike_angle_deg_mean": 5.2,
                "foot_strike_angle_deg_std": 1.1,
                "rearfoot_angle_deg_mean": 2.0,
                "rearfoot_angle_deg_std": 0.9,
                "stance_pct_mean": 61.0,
                "stance_pct_std": 1.5,
                "swing_pct_mean": 39.0,
                "swing_pct_std": 1.5,
                "quality_flag": "PROCEED_OK",
                "step_length_left_m": 0.70,
                "step_length_right_m": 0.68,
                "foot_progression_angle_left_deg": 5.0,
                "foot_progression_angle_right_deg": 5.0,
            },
            "R": {
                "foot": "R",
                "cycle_count": 4,
                "cadence_steps_per_min_mean": 110.0,
                "cadence_steps_per_min_std": 2.0,
                "foot_strike_type": "rearfoot",
                "arch_type": "normal",
                "pronation_type": "neutral",
                "frontal_plane_excursion_deg_mean": 5.5,
                "frontal_plane_excursion_deg_std": 0.7,
                "foot_strike_angle_deg_mean": 4.9,
                "foot_strike_angle_deg_std": 1.0,
                "rearfoot_angle_deg_mean": 2.5,
                "rearfoot_angle_deg_std": 0.8,
                "stance_pct_mean": 60.5,
                "stance_pct_std": 1.4,
                "swing_pct_mean": 39.5,
                "swing_pct_std": 1.4,
                "quality_flag": "PROCEED_OK",
                "step_length_left_m": 0.70,
                "step_length_right_m": 0.68,
                "foot_progression_angle_left_deg": 5.0,
                "foot_progression_angle_right_deg": 5.0,
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
        builder._health_coach = coach

        profile = builder.build(
            patient_id="P_LOGGED",
            session_timestamp="2026-06-18T12:00:00Z",
            parameters=parameters,
            anthropometrics=anthropometrics,
            confidence_scores={"pipeline": 0.92},
        )

        # Verify agent_decisions structure
        assert profile["agent_decisions"] is not None
        assert "timestamp" in profile["agent_decisions"]
        assert "method_used" in profile["agent_decisions"]
        assert profile["agent_decisions"]["method_used"] == "agent"
        assert "confidence_score" in profile["agent_decisions"]
        assert profile["agent_decisions"]["confidence_score"] > 0.9
        assert "reasoning" in profile["agent_decisions"]

