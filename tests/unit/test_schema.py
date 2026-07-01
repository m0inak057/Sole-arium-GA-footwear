"""Unit tests for gait patient profile schema.

Tests that:
1. Schema validates correct profiles
2. Schema rejects invalid profiles
3. All field types and enums are correct
4. Required fields are enforced
"""
from __future__ import annotations

from datetime import datetime

import pytest

from gait.profile.schema import (
    Anthropometrics,
    Arch,
    ArchType,
    DefectDetail,
    FootProgressionClassification,
    FootStrike,
    FootStrikePattern,
    GaitPatientProfile,
    HealthAssessment,
    ImprovementAction,
    LRPair,
    Pronation,
    PronationClassification,
    Spatiotemporal,
)


@pytest.mark.unit
class TestLRPair:
    """Test left-right pair validation."""

    def test_lr_pair_valid(self):
        """LRPair accepts valid L/R pairs."""
        pair = LRPair(L=1.5, R=1.4)
        assert pair.L == 1.5
        assert pair.R == 1.4

    def test_lr_pair_missing_left(self):
        """LRPair rejects missing L."""
        with pytest.raises(ValueError):
            LRPair(R=1.4)

    def test_lr_pair_missing_right(self):
        """LRPair rejects missing R."""
        with pytest.raises(ValueError):
            LRPair(L=1.5)


@pytest.mark.unit
class TestFootStrikeSchema:
    """Test foot strike classification schema."""

    def test_foot_strike_pattern_valid(self):
        """FootStrike accepts valid patterns."""
        fs = FootStrike(
            pattern={"L": FootStrikePattern.REARFOOT, "R": FootStrikePattern.REARFOOT},
            foot_strike_angle_deg=LRPair(L=18.2, R=16.7),
        )
        assert fs.pattern["L"] == FootStrikePattern.REARFOOT

    def test_foot_strike_all_patterns(self):
        """FootStrike accepts all pattern types."""
        patterns = [
            FootStrikePattern.REARFOOT,
            FootStrikePattern.MIDFOOT,
            FootStrikePattern.FOREFOOT,
        ]
        for pattern in patterns:
            fs = FootStrike(
                pattern={"L": pattern, "R": pattern},
                foot_strike_angle_deg=LRPair(L=0.0, R=0.0),
            )
            assert fs.pattern["L"] == pattern

    def test_foot_strike_missing_lr(self):
        """FootStrike rejects patterns without both L and R."""
        with pytest.raises(ValueError):
            FootStrike(
                pattern={"L": FootStrikePattern.REARFOOT},  # Missing R
                foot_strike_angle_deg=LRPair(L=18.2, R=16.7),
            )


@pytest.mark.unit
class TestPronationSchema:
    """Test pronation classification schema."""

    def test_pronation_neutral(self):
        """Pronation accepts neutral classification."""
        p = Pronation(
            rearfoot_angle_at_midstance_deg=LRPair(L=2.5, R=1.8),
            classification={"L": PronationClassification.NEUTRAL, "R": PronationClassification.NEUTRAL},
            time_to_peak_eversion_pct_stance=LRPair(L=38.0, R=42.0),
            frontal_plane_excursion_left_deg=3.2,
            frontal_plane_excursion_right_deg=2.8,
        )
        assert p.classification["L"] == PronationClassification.NEUTRAL

    def test_pronation_all_classifications(self):
        """Pronation accepts all classification types."""
        classifications = [
            PronationClassification.OVERPRONATION,
            PronationClassification.MILD_PRONATION,
            PronationClassification.NEUTRAL,
            PronationClassification.MILD_SUPINATION,
            PronationClassification.OVERSUPINATION,
        ]
        for cls in classifications:
            p = Pronation(
                rearfoot_angle_at_midstance_deg=LRPair(L=0.0, R=0.0),
                classification={"L": cls, "R": cls},
                time_to_peak_eversion_pct_stance=LRPair(L=40.0, R=40.0),
                frontal_plane_excursion_left_deg=5.0,
                frontal_plane_excursion_right_deg=5.0,
            )
            assert p.classification["L"] == cls

    def test_pronation_overpronation(self):
        """Pronation correctly classifies overpronation."""
        p = Pronation(
            rearfoot_angle_at_midstance_deg=LRPair(L=11.4, R=9.8),
            classification={"L": PronationClassification.OVERPRONATION, "R": PronationClassification.OVERPRONATION},
            time_to_peak_eversion_pct_stance=LRPair(L=38.0, R=42.0),
            frontal_plane_excursion_left_deg=12.3,
            frontal_plane_excursion_right_deg=11.8,
        )
        assert p.rearfoot_angle_at_midstance_deg.L > 8.0  # Over 8Â° is overpronation


@pytest.mark.unit
class TestArchSchema:
    """Test arch type schema."""

    def test_arch_high(self):
        """Arch accepts high arch type."""
        arch = Arch(
            type={"L": ArchType.HIGH, "R": ArchType.HIGH},
            arch_height_index=LRPair(L=0.32, R=0.30),
        )
        assert arch.type["L"] == ArchType.HIGH

    def test_arch_all_types(self):
        """Arch accepts all arch types."""
        types = [ArchType.HIGH, ArchType.NORMAL, ArchType.LOW]
        for arch_type in types:
            arch = Arch(
                type={"L": arch_type, "R": arch_type},
                arch_height_index=LRPair(L=0.25, R=0.25),
            )
            assert arch.type["L"] == arch_type


@pytest.mark.unit
class TestHealthAssessment:
    """Test health assessment schema."""

    def test_health_assessment_with_defects(self):
        """HealthAssessment accepts defects and improvements."""
        assessment = HealthAssessment(
            what_went_right=["Good pronation control"],
            defects_found=[
                DefectDetail(
                    name="Overpronation",
                    severity="severe",
                    affected_side="bilateral",
                    biomechanical_cause="Excessive eversion angle",
                    gait_cycle_phase="Loading Response",
                )
            ],
            improvement_plan=[
                ImprovementAction(
                    exercise_name="Short Foot",
                    target_area="Intrinsic foot muscles",
                    frequency="3 sets daily",
                    instructions="Draw foot shorter without curling toes",
                    addresses_defect="Overpronation",
                )
            ],
        )
        assert len(assessment.defects_found) == 1
        assert assessment.defects_found[0].name == "Overpronation"
        assert len(assessment.improvement_plan) == 1

    def test_health_assessment_empty(self):
        """HealthAssessment accepts empty lists (normal gait)."""
        assessment = HealthAssessment(
            what_went_right=["Normal gait pattern"],
            defects_found=[],
            improvement_plan=[],
        )
        assert len(assessment.defects_found) == 0
        assert len(assessment.improvement_plan) == 0


@pytest.mark.unit
class TestGaitPatientProfile:
    """Test complete patient profile schema."""

    def test_profile_valid(self):
        """Profile accepts valid, complete data."""
        profile = GaitPatientProfile(
            patient_id="P0042",
            session_timestamp=datetime.utcnow(),
            anthropometrics=Anthropometrics(
                height_cm=172.0,
                mass_kg=68.0,
                foot_length_mm=LRPair(L=258.0, R=260.0),
                foot_width_mm=LRPair(L=98.0, R=99.0),
            ),
            spatiotemporal=Spatiotemporal(
                cadence_spm=112.0,
                speed_mps=1.28,
                stride_length_m=1.37,
                step_width_m=0.09,
                stance_pct=LRPair(L=61.2, R=60.4),
                double_support_pct=22.1,
                step_length_left_m=0.68,
                step_length_right_m=0.67,
                foot_progression_angle_left_deg=8.5,
                foot_progression_angle_right_deg=7.2,
                foot_progression_classification_left=FootProgressionClassification.NEUTRAL,
                foot_progression_classification_right=FootProgressionClassification.NEUTRAL,
            ),
            foot_strike=FootStrike(
                pattern={"L": FootStrikePattern.REARFOOT, "R": FootStrikePattern.REARFOOT},
                foot_strike_angle_deg=LRPair(L=18.2, R=16.7),
            ),
            pronation=Pronation(
                rearfoot_angle_at_midstance_deg=LRPair(L=11.4, R=9.8),
                classification={"L": PronationClassification.OVERPRONATION, "R": PronationClassification.OVERPRONATION},
                time_to_peak_eversion_pct_stance=LRPair(L=38.0, R=42.0),
                frontal_plane_excursion_left_deg=12.3,
                frontal_plane_excursion_right_deg=11.8,
            ),
            arch=Arch(
                type={"L": ArchType.LOW, "R": ArchType.LOW},
                arch_height_index=LRPair(L=0.21, R=0.22),
            ),
            health_assessment=HealthAssessment(
                what_went_right=[],
                defects_found=[
                    DefectDetail(
                        name="Severe Overpronation with Low Arch",
                        severity="severe",
                        affected_side="bilateral",
                        biomechanical_cause="Rearfoot eversion exceeds normal range, indicating excessive foot inversion",
                        gait_cycle_phase="Loading Response to Mid-Stance",
                    )
                ],
                improvement_plan=[
                    ImprovementAction(
                        exercise_name="Short Foot Exercise",
                        target_area="Intrinsic foot muscles",
                        frequency="3 sets of 12 reps, daily",
                        instructions="Draw the ball of the foot toward the heel without curling toes",
                        addresses_defect="Severe Overpronation with Low Arch",
                    )
                ],
            ),
            confidence_scores={
                "pronation_classification": 0.91,
                "foot_strike_classification": 0.95,
            },
        )
        assert profile.patient_id == "P0042"
        assert profile.schema_version == "profile/v1"

    def test_profile_missing_required_field(self):
        """Profile rejects missing required fields."""
        with pytest.raises(ValueError):
            GaitPatientProfile(
                # Missing patient_id, session_timestamp, etc.
                anthropometrics=Anthropometrics(
                    height_cm=172.0,
                    mass_kg=68.0,
                    foot_length_mm=LRPair(L=258.0, R=260.0),
                    foot_width_mm=LRPair(L=98.0, R=99.0),
                ),
            )

    def test_profile_invalid_confidence_score(self):
        """Profile rejects invalid confidence scores (not 0-1)."""
        with pytest.raises(ValueError):
            GaitPatientProfile(
                patient_id="P0042",
                session_timestamp=datetime.utcnow(),
                anthropometrics=Anthropometrics(
                    height_cm=172.0,
                    mass_kg=68.0,
                    foot_length_mm=LRPair(L=258.0, R=260.0),
                    foot_width_mm=LRPair(L=98.0, R=99.0),
                ),
                spatiotemporal=Spatiotemporal(
                    cadence_spm=112.0,
                    speed_mps=1.28,
                    stride_length_m=1.37,
                    step_width_m=0.09,
                    stance_pct=LRPair(L=61.2, R=60.4),
                    double_support_pct=22.1,
                    step_length_left_m=0.68,
                    step_length_right_m=0.67,
                    foot_progression_angle_left_deg=8.5,
                    foot_progression_angle_right_deg=7.2,
                    foot_progression_classification_left=FootProgressionClassification.NEUTRAL,
                    foot_progression_classification_right=FootProgressionClassification.NEUTRAL,
                ),
                foot_strike=FootStrike(
                    pattern={"L": FootStrikePattern.REARFOOT, "R": FootStrikePattern.REARFOOT},
                    foot_strike_angle_deg=LRPair(L=18.2, R=16.7),
                ),
                pronation=Pronation(
                    rearfoot_angle_at_midstance_deg=LRPair(L=2.5, R=2.5),
                    classification={"L": PronationClassification.NEUTRAL, "R": PronationClassification.NEUTRAL},
                    time_to_peak_eversion_pct_stance=LRPair(L=38.0, R=42.0),
                    frontal_plane_excursion_left_deg=3.2,
                    frontal_plane_excursion_right_deg=2.8,
                ),
                arch=Arch(
                    type={"L": ArchType.NORMAL, "R": ArchType.NORMAL},
                    arch_height_index=LRPair(L=0.25, R=0.25),
                ),
                health_assessment=HealthAssessment(
                    what_went_right=["Neutral pronation pattern"],
                    defects_found=[],
                    improvement_plan=[],
                ),
                confidence_scores={
                    "pronation_classification": 1.5,  # Invalid: > 1.0
                },
            )

    def test_profile_json_serialization(self):
        """Profile can be serialized to JSON."""
        profile = GaitPatientProfile(
            patient_id="P0042",
            session_timestamp=datetime(2026, 5, 15, 11, 23, 0),
            anthropometrics=Anthropometrics(
                height_cm=172.0,
                mass_kg=68.0,
                foot_length_mm=LRPair(L=258.0, R=260.0),
                foot_width_mm=LRPair(L=98.0, R=99.0),
            ),
            spatiotemporal=Spatiotemporal(
                cadence_spm=112.0,
                speed_mps=1.28,
                stride_length_m=1.37,
                step_width_m=0.09,
                stance_pct=LRPair(L=61.2, R=60.4),
                double_support_pct=22.1,
                step_length_left_m=0.68,
                step_length_right_m=0.67,
                foot_progression_angle_left_deg=8.5,
                foot_progression_angle_right_deg=7.2,
                foot_progression_classification_left=FootProgressionClassification.NEUTRAL,
                foot_progression_classification_right=FootProgressionClassification.NEUTRAL,
            ),
            foot_strike=FootStrike(
                pattern={"L": FootStrikePattern.REARFOOT, "R": FootStrikePattern.REARFOOT},
                foot_strike_angle_deg=LRPair(L=18.2, R=16.7),
            ),
            pronation=Pronation(
                rearfoot_angle_at_midstance_deg=LRPair(L=2.5, R=2.5),
                classification={"L": PronationClassification.NEUTRAL, "R": PronationClassification.NEUTRAL},
                time_to_peak_eversion_pct_stance=LRPair(L=38.0, R=42.0),
                frontal_plane_excursion_left_deg=3.2,
                frontal_plane_excursion_right_deg=2.8,
            ),
            arch=Arch(
                type={"L": ArchType.NORMAL, "R": ArchType.NORMAL},
                arch_height_index=LRPair(L=0.25, R=0.25),
            ),
            health_assessment=HealthAssessment(
                what_went_right=[
                    "Neutral pronation pattern",
                    "Good arch structure",
                    "Healthy foot strike pattern",
                ],
                defects_found=[],
                improvement_plan=[],
            ),
            confidence_scores={
                "pronation_classification": 0.91,
                "foot_strike_classification": 0.95,
            },
        )

        json_str = profile.model_dump_json()
        assert '"patient_id":"P0042"' in json_str or '"patient_id": "P0042"' in json_str
        assert '"schema_version":"profile/v1"' in json_str or '"schema_version": "profile/v1"' in json_str

