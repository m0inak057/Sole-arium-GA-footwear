"""Unit tests for gait patient profile schema.

Tests that:
1. Schema validates correct profiles
2. Schema rejects invalid profiles
3. All field types and enums are correct
4. Required fields are enforced
"""

import pytest
from datetime import datetime

from src.gait.profile.schema import (
    GaitPatientProfile,
    Anthropometrics,
    Spatiotemporal,
    FootStrike,
    Pronation,
    Arch,
    ShoeDesignRecommendations,
    FootStrikePattern,
    PronationClassification,
    ArchType,
    MedialPostType,
    ArchSupportType,
    HeelCounterType,
    LastShapeType,
    LRPair,
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
            )
            assert p.classification["L"] == cls

    def test_pronation_overpronation(self):
        """Pronation correctly classifies overpronation."""
        p = Pronation(
            rearfoot_angle_at_midstance_deg=LRPair(L=11.4, R=9.8),
            classification={"L": PronationClassification.OVERPRONATION, "R": PronationClassification.OVERPRONATION},
            time_to_peak_eversion_pct_stance=LRPair(L=38.0, R=42.0),
        )
        assert p.rearfoot_angle_at_midstance_deg.L > 8.0  # Over 8° is overpronation


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
class TestShoeDesignRecommendations:
    """Test shoe design recommendation schema."""

    def test_recommendations_valid(self):
        """Recommendations accepts valid values."""
        recs = ShoeDesignRecommendations(
            medial_post=MedialPostType.REQUIRED,
            post_density="firm",
            arch_support=ArchSupportType.HIGH,
            heel_counter=HeelCounterType.RIGID,
            heel_drop_mm=10.0,
            last_shape=LastShapeType.STRAIGHT,
        )
        assert recs.medial_post == MedialPostType.REQUIRED
        assert recs.arch_support == ArchSupportType.HIGH

    def test_recommendations_all_values(self):
        """Recommendations accepts all enum values."""
        posts = [MedialPostType.REQUIRED, MedialPostType.OPTIONAL, MedialPostType.NONE]
        for post in posts:
            recs = ShoeDesignRecommendations(
                medial_post=post,
                arch_support=ArchSupportType.MEDIUM,
                heel_counter=HeelCounterType.SEMI_RIGID,
                heel_drop_mm=8.0,
                last_shape=LastShapeType.SEMI_CURVED,
            )
            assert recs.medial_post == post


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
            ),
            foot_strike=FootStrike(
                pattern={"L": FootStrikePattern.REARFOOT, "R": FootStrikePattern.REARFOOT},
                foot_strike_angle_deg=LRPair(L=18.2, R=16.7),
            ),
            pronation=Pronation(
                rearfoot_angle_at_midstance_deg=LRPair(L=11.4, R=9.8),
                classification={"L": PronationClassification.OVERPRONATION, "R": PronationClassification.OVERPRONATION},
                time_to_peak_eversion_pct_stance=LRPair(L=38.0, R=42.0),
            ),
            arch=Arch(
                type={"L": ArchType.LOW, "R": ArchType.LOW},
                arch_height_index=LRPair(L=0.21, "R": 0.22),
            ),
            shoe_design_recommendations=ShoeDesignRecommendations(
                medial_post=MedialPostType.REQUIRED,
                post_density="firm",
                arch_support=ArchSupportType.HIGH,
                heel_counter=HeelCounterType.RIGID,
                heel_drop_mm=10.0,
                last_shape=LastShapeType.STRAIGHT,
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
                ),
                foot_strike=FootStrike(
                    pattern={"L": FootStrikePattern.REARFOOT, "R": FootStrikePattern.REARFOOT},
                    foot_strike_angle_deg=LRPair(L=18.2, R=16.7),
                ),
                pronation=Pronation(
                    rearfoot_angle_at_midstance_deg=LRPair(L=2.5, R=2.5),
                    classification={"L": PronationClassification.NEUTRAL, "R": PronationClassification.NEUTRAL},
                    time_to_peak_eversion_pct_stance=LRPair(L=38.0, R=42.0),
                ),
                arch=Arch(
                    type={"L": ArchType.NORMAL, "R": ArchType.NORMAL},
                    arch_height_index=LRPair(L=0.25, R=0.25),
                ),
                shoe_design_recommendations=ShoeDesignRecommendations(
                    medial_post=MedialPostType.OPTIONAL,
                    arch_support=ArchSupportType.MEDIUM,
                    heel_counter=HeelCounterType.FLEXIBLE,
                    heel_drop_mm=8.0,
                    last_shape=LastShapeType.SEMI_CURVED,
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
            ),
            foot_strike=FootStrike(
                pattern={"L": FootStrikePattern.REARFOOT, "R": FootStrikePattern.REARFOOT},
                foot_strike_angle_deg=LRPair(L=18.2, R=16.7),
            ),
            pronation=Pronation(
                rearfoot_angle_at_midstance_deg=LRPair(L=2.5, R=2.5),
                classification={"L": PronationClassification.NEUTRAL, "R": PronationClassification.NEUTRAL},
                time_to_peak_eversion_pct_stance=LRPair(L=38.0, R=42.0),
            ),
            arch=Arch(
                type={"L": ArchType.NORMAL, "R": ArchType.NORMAL},
                arch_height_index=LRPair(L=0.25, R=0.25),
            ),
            shoe_design_recommendations=ShoeDesignRecommendations(
                medial_post=MedialPostType.OPTIONAL,
                arch_support=ArchSupportType.MEDIUM,
                heel_counter=HeelCounterType.FLEXIBLE,
                heel_drop_mm=8.0,
                last_shape=LastShapeType.SEMI_CURVED,
            ),
            confidence_scores={
                "pronation_classification": 0.91,
                "foot_strike_classification": 0.95,
            },
        )

        json_str = profile.model_dump_json()
        assert '"patient_id": "P0042"' in json_str
        assert '"schema_version": "profile/v1"' in json_str
