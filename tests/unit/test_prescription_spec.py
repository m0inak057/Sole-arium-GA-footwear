"""Tests for the prescription_spec feature.

Covers:
1. Correct last_shape for overpronation (straight), oversupination (curved), neutral (semi_curved)
2. Shore-C modifier for 80 kg patient (+10 vs baseline 70 kg patient)
3. Heel lift: 3 mm for >10% step asymmetry on the shorter side, 0 mm when symmetric
4. builder.build() produces both health_assessment AND prescription_spec non-null
5. Rigid flat foot â†’ "Refer to podiatrist" note and medial_post=False
"""
from __future__ import annotations

import pytest

from gait.pipeline.config import load_recommendation_rules
from gait.profile.prescription_engine import (
    PrescriptionEngine,
    _compute_heel_lift,
    _shore_c_modifier,
)


# â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _make_engine() -> PrescriptionEngine:
    rules_config = load_recommendation_rules()
    return PrescriptionEngine(
        prescription_rules=[r.model_dump() for r in rules_config.prescription_rules]
    )


def _params(
    pronation: str = "neutral",
    arch: str = "normal",
    foot_strike: str = "rearfoot",
    flags: list[str] | None = None,
) -> dict:
    return {
        "pronation_type": pronation,
        "arch_type": arch,
        "foot_strike_type": foot_strike,
        "flags": flags or [],
    }


# â”€â”€ 1. last_shape per pronation type â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestLastShape:
    def test_overpronation_produces_straight_last(self) -> None:
        engine = _make_engine()
        spec = engine.generate_prescription(
            rule_params=_params(pronation="overpronation"),
            body_mass_kg=70.0,
        )
        assert spec.last_spec.shape == "straight"

    def test_oversupination_produces_curved_last(self) -> None:
        engine = _make_engine()
        spec = engine.generate_prescription(
            rule_params=_params(pronation="oversupination"),
            body_mass_kg=70.0,
        )
        assert spec.last_spec.shape == "curved"

    def test_neutral_produces_semi_curved_last(self) -> None:
        engine = _make_engine()
        spec = engine.generate_prescription(
            rule_params=_params(pronation="neutral"),
            body_mass_kg=70.0,
        )
        assert spec.last_spec.shape == "semi_curved"


# â”€â”€ 2. Shore-C body-mass modifier â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestShoreCModifier:
    def test_modifier_zero_at_70kg(self) -> None:
        assert _shore_c_modifier(70.0) == 0.0

    def test_modifier_minus5_below_60kg(self) -> None:
        assert _shore_c_modifier(55.0) == -5.0

    def test_modifier_plus10_at_80kg(self) -> None:
        assert _shore_c_modifier(80.0) == 10.0

    def test_modifier_plus10_at_99kg(self) -> None:
        assert _shore_c_modifier(99.0) == 10.0

    def test_modifier_plus15_above_100kg(self) -> None:
        assert _shore_c_modifier(101.0) == 15.0

    def test_80kg_patient_gets_higher_shore_c_than_70kg(self) -> None:
        """80 kg patient should have medial_shore_c 10 units higher than 70 kg baseline."""
        engine = _make_engine()
        params = _params(pronation="neutral")

        spec_70 = engine.generate_prescription(rule_params=params, body_mass_kg=70.0)
        spec_80 = engine.generate_prescription(rule_params=params, body_mass_kg=80.0)

        assert spec_80.midsole.medial_shore_c == pytest.approx(
            spec_70.midsole.medial_shore_c + 10.0, abs=0.01
        )
        assert spec_80.midsole.lateral_shore_c == pytest.approx(
            spec_70.midsole.lateral_shore_c + 10.0, abs=0.01
        )

    def test_heavy_patient_gets_pu_note(self) -> None:
        """Patients > 100 kg should receive the PU midsole durability note."""
        engine = _make_engine()
        spec = engine.generate_prescription(
            rule_params=_params(pronation="neutral"),
            body_mass_kg=105.0,
        )
        notes_text = " ".join(spec.clinician_referral_notes)
        assert "PU midsole" in notes_text


# â”€â”€ 3. Heel lift from step asymmetry â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestHeelLift:
    def test_symmetric_steps_no_lift(self) -> None:
        left_mm, right_mm = _compute_heel_lift({}, 0.68, 0.68)
        assert left_mm == 0.0
        assert right_mm == 0.0

    def test_less_than_10pct_asymmetry_no_lift(self) -> None:
        # 0.68 vs 0.65 â†’ ~4.5% asymmetry
        left_mm, right_mm = _compute_heel_lift({}, 0.68, 0.65)
        assert left_mm == 0.0
        assert right_mm == 0.0

    def test_left_shorter_gets_3mm_lift(self) -> None:
        # 0.55 vs 0.70 â†’ ~24% asymmetry; left is shorter
        left_mm, right_mm = _compute_heel_lift({}, 0.55, 0.70)
        assert left_mm == pytest.approx(3.0)
        assert right_mm == pytest.approx(0.0)

    def test_right_shorter_gets_3mm_lift(self) -> None:
        # 0.70 vs 0.55 â†’ ~24% asymmetry; right is shorter
        left_mm, right_mm = _compute_heel_lift({}, 0.70, 0.55)
        assert left_mm == pytest.approx(0.0)
        assert right_mm == pytest.approx(3.0)

    def test_flag_alone_triggers_lift_defaults_to_left(self) -> None:
        """When the flag is set but no numeric lengths supplied, left gets lift."""
        rule_params = {"flags": ["step_length_asymmetric"]}
        left_mm, right_mm = _compute_heel_lift(rule_params, 0.0, 0.0)
        assert left_mm == pytest.approx(3.0)
        assert right_mm == pytest.approx(0.0)

    def test_engine_adds_3mm_for_asymmetric_flag(self) -> None:
        engine = _make_engine()
        params = _params(flags=["step_length_asymmetric"])
        spec = engine.generate_prescription(
            rule_params=params,
            body_mass_kg=70.0,
            step_length_left_m=0.55,
            step_length_right_m=0.70,
        )
        # right is longer â†’ left is shorter â†’ left gets lift
        assert spec.foot_lift.heel_lift_left_mm == pytest.approx(3.0)
        assert spec.foot_lift.heel_lift_right_mm == pytest.approx(0.0)


# â”€â”€ 4. builder.build() produces both health_assessment and prescription_spec â”€â”€


class TestBuilderIntegration:
    def _make_params(self, pronation: str = "neutral") -> dict:
        per_foot = {
            "cadence_steps_per_min_mean": 112.0,
            "stance_pct_mean": 61.0,
            "rearfoot_angle_deg_mean": 2.0,
            "frontal_plane_excursion_deg_mean": 4.0,
            "pronation_type": pronation,
            "arch_type": "normal",
            "foot_strike_type": "rearfoot",
            "foot_strike_angle_deg_mean": 12.0,
            "foot_length_mm": 260.0,
            "step_length_left_m": 0.68,
            "step_length_right_m": 0.67,
            "foot_progression_angle_left_deg": 7.0,
            "foot_progression_angle_right_deg": 6.5,
        }
        return {"L": per_foot.copy(), "R": per_foot.copy()}

    def test_both_blocks_present_and_non_null(self) -> None:
        from gait.profile.builder import create_profile_builder
        from gait.pipeline.config import AnalysisConfig, load_recommendation_rules

        rules_config = load_recommendation_rules()
        builder = create_profile_builder(rules_config, AnalysisConfig())
        profile = builder.build(
            patient_id="test_pt",
            session_timestamp="2026-06-20T10:00:00Z",
            parameters=self._make_params(),
            anthropometrics={"height_cm": 172.0, "mass_kg": 70.0},
            confidence_scores={"pipeline": 0.85},
        )

        assert profile["health_assessment"] is not None
        assert profile["prescription_spec"] is not None

    def test_prescription_spec_shape_matches_pronation(self) -> None:
        from gait.profile.builder import create_profile_builder
        from gait.pipeline.config import AnalysisConfig, load_recommendation_rules

        rules_config = load_recommendation_rules()
        builder = create_profile_builder(rules_config, AnalysisConfig())

        for pronation, expected_shape in [
            ("overpronation", "straight"),
            ("neutral", "semi_curved"),
            ("oversupination", "curved"),
        ]:
            per_foot = {
                "cadence_steps_per_min_mean": 112.0,
                "stance_pct_mean": 61.0,
                "rearfoot_angle_deg_mean": 2.0,
                "frontal_plane_excursion_deg_mean": 4.0,
                "pronation_type": pronation,
                "arch_type": "normal",
                "foot_strike_type": "rearfoot",
                "foot_strike_angle_deg_mean": 12.0,
                "foot_length_mm": 260.0,
                "step_length_left_m": 0.68,
                "step_length_right_m": 0.67,
            }
            profile = builder.build(
                patient_id="test_pt",
                session_timestamp="2026-06-20T10:00:00Z",
                parameters={"L": per_foot, "R": per_foot},
                anthropometrics={"height_cm": 172.0, "mass_kg": 70.0},
                confidence_scores={"pipeline": 0.85},
            )
            actual_shape = profile["prescription_spec"]["last_spec"]["shape"]
            assert actual_shape == expected_shape, (
                f"For pronation={pronation}, expected last_shape={expected_shape}, got {actual_shape}"
            )


# â”€â”€ 5. Rigid flat foot â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestRigidFlatFoot:
    def test_refer_to_podiatrist_note_present(self) -> None:
        """Low arch without overpronation â†’ rigid flat foot â†’ podiatrist referral note."""
        engine = _make_engine()
        spec = engine.generate_prescription(
            rule_params=_params(pronation="neutral", arch="low"),
            body_mass_kg=70.0,
        )
        notes_text = " ".join(spec.clinician_referral_notes)
        assert "podiatrist" in notes_text.lower()

    def test_rigid_flat_foot_no_medial_post(self) -> None:
        """Rigid flat foot must NOT have a medial post (no control post â€” accommodative only)."""
        engine = _make_engine()
        spec = engine.generate_prescription(
            rule_params=_params(pronation="neutral", arch="low"),
            body_mass_kg=70.0,
        )
        assert spec.arch_support.medial_post is False

    def test_flexible_flat_foot_has_medial_post(self) -> None:
        """Flexible flat foot (low arch + overpronation) should have a medial post."""
        engine = _make_engine()
        spec = engine.generate_prescription(
            rule_params=_params(pronation="overpronation", arch="low"),
            body_mass_kg=70.0,
        )
        assert spec.arch_support.medial_post is True

    def test_flexible_flat_foot_midfoot_shank_note(self) -> None:
        """Flexible flat foot should include rigid midfoot shank note."""
        engine = _make_engine()
        spec = engine.generate_prescription(
            rule_params=_params(pronation="overpronation", arch="low"),
            body_mass_kg=70.0,
        )
        notes_text = " ".join(spec.clinician_referral_notes)
        assert "shank" in notes_text.lower()


# â”€â”€ 6. Schema validation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestPrescriptionSpecSchema:
    def test_prescription_spec_validates_against_pydantic_schema(self) -> None:
        """PrescriptionSpec returned by the engine must pass GaitPatientProfile validation."""
        from gait.profile.schema import PrescriptionSpec

        engine = _make_engine()
        spec = engine.generate_prescription(
            rule_params=_params(pronation="mild_pronation"),
            body_mass_kg=75.0,
        )
        assert isinstance(spec, PrescriptionSpec)
        # Re-parse from dict (round-trip) to confirm it's fully serialisable
        spec2 = PrescriptionSpec(**spec.model_dump())
        assert spec2.last_spec.shape == spec.last_spec.shape

    def test_confidence_is_rule_based(self) -> None:
        engine = _make_engine()
        spec = engine.generate_prescription(
            rule_params=_params(),
            body_mass_kg=70.0,
        )
        assert spec.confidence == "rule_based"

    def test_medial_post_shore_c_null_when_no_post(self) -> None:
        """medial_post_shore_c must be None when medial_post is False."""
        engine = _make_engine()
        spec = engine.generate_prescription(
            rule_params=_params(pronation="neutral"),
            body_mass_kg=70.0,
        )
        assert spec.arch_support.medial_post is False
        assert spec.arch_support.medial_post_shore_c is None

