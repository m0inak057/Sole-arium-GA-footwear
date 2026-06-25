"""Gait patient profile schema — source of truth for output contract.

This module defines the Pydantic models that represent the patient-profile JSON.
Every profile emitted by the pipeline must validate against these models.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, validator, field_validator


class FootStrikePattern(str, Enum):
    """Foot strike classification."""

    REARFOOT = "rearfoot"
    MIDFOOT = "midfoot"
    FOREFOOT = "forefoot"


class PronationClassification(str, Enum):
    """Pronation classification based on rearfoot eversion angle."""

    OVERPRONATION = "overpronation"
    MILD_PRONATION = "mild_pronation"
    NEUTRAL = "neutral"
    MILD_SUPINATION = "mild_supination"
    OVERSUPINATION = "oversupination"


class ArchType(str, Enum):
    """Arch classification based on arch height index."""

    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class MedialPostType(str, Enum):
    """Medial post recommendation."""

    REQUIRED = "required"
    OPTIONAL = "optional"
    NONE = "none"


class PostDensityType(str, Enum):
    """Post density recommendation."""

    SOFT = "soft"
    MEDIUM = "medium"
    FIRM = "firm"


class ArchSupportType(str, Enum):
    """Arch support level recommendation."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class HeelCounterType(str, Enum):
    """Heel counter rigidity recommendation."""

    FLEXIBLE = "flexible"
    SEMI_RIGID = "semi_rigid"
    RIGID = "rigid"


class LastShapeType(str, Enum):
    """Last shape recommendation."""

    STRAIGHT = "straight"
    SEMI_CURVED = "semi_curved"
    CURVED = "curved"


class LRPair(BaseModel):
    """Left-right pair of values."""

    L: float = Field(..., description="Left foot value")
    R: float = Field(..., description="Right foot value")

    class Config:
        json_schema_extra = {
            "example": {"L": 1.5, "R": 1.4},
            "description": "Always use L/R notation for left/right foot data",
        }


class LRString(BaseModel):
    """Left-right pair of string values (for classifications)."""

    L: str = Field(..., description="Left foot classification")
    R: str = Field(..., description="Right foot classification")

    class Config:
        json_schema_extra = {"example": {"L": "neutral", "R": "mild_pronation"}}


class Anthropometrics(BaseModel):
    """Subject measurements."""

    height_cm: float = Field(..., description="Height in centimeters")
    mass_kg: float = Field(..., description="Body mass in kilograms")
    foot_length_mm: LRPair = Field(..., description="Foot length in millimeters")
    foot_width_mm: LRPair = Field(..., description="Foot width in millimeters")

    class Config:
        json_schema_extra = {
            "example": {
                "height_cm": 172,
                "mass_kg": 68,
                "foot_length_mm": {"L": 258, "R": 260},
                "foot_width_mm": {"L": 98, "R": 99},
            }
        }


class FootProgressionClassification(str, Enum):
    """Foot progression angle classification."""

    TOE_IN = "toe_in"
    NEUTRAL = "neutral"
    TOE_OUT = "toe_out"


class Spatiotemporal(BaseModel):
    """Spatiotemporal gait parameters."""

    cadence_spm: float = Field(..., description="Cadence in steps per minute")
    speed_mps: float = Field(..., description="Walking speed in meters per second")
    stride_length_m: float = Field(..., description="Stride length in meters")
    step_width_m: float = Field(..., description="Step width in meters")
    stance_pct: LRPair = Field(..., description="Stance phase as % of cycle per foot")
    double_support_pct: float = Field(
        ..., description="Double support phase as % of cycle"
    )
    swing_pct: Optional[LRPair] = Field(
        None, description="Swing phase as % of cycle per foot"
    )
    step_length_left_m: float = Field(
        ..., description="Step length for left foot in meters"
    )
    step_length_right_m: float = Field(
        ..., description="Step length for right foot in meters"
    )
    foot_progression_angle_left_deg: float = Field(
        ..., description="Foot progression angle (left foot) in degrees (positive = toe-out, negative = toe-in)"
    )
    foot_progression_angle_right_deg: float = Field(
        ..., description="Foot progression angle (right foot) in degrees (positive = toe-out, negative = toe-in)"
    )
    foot_progression_classification_left: FootProgressionClassification = Field(
        ..., description="Foot progression classification for left foot (toe-in/neutral/toe-out)"
    )
    foot_progression_classification_right: FootProgressionClassification = Field(
        ..., description="Foot progression classification for right foot (toe-in/neutral/toe-out)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "cadence_spm": 112,
                "speed_mps": 1.28,
                "stride_length_m": 1.37,
                "step_width_m": 0.09,
                "stance_pct": {"L": 61.2, "R": 60.4},
                "double_support_pct": 22.1,
                "swing_pct": {"L": 38.8, "R": 39.6},
                "step_length_left_m": 0.68,
                "step_length_right_m": 0.67,
                "foot_progression_angle_left_deg": 7.2,
                "foot_progression_angle_right_deg": 6.8,
                "foot_progression_classification_left": "toe_out",
                "foot_progression_classification_right": "toe_out",
            }
        }


class FootStrike(BaseModel):
    """Foot strike classification."""

    pattern: Dict[str, FootStrikePattern] = Field(
        ..., description="Foot strike pattern (rearfoot/midfoot/forefoot)"
    )
    foot_strike_angle_deg: LRPair = Field(
        ..., description="Foot strike angle at heel-strike in degrees"
    )

    @validator("pattern")
    def validate_lr_pattern(cls, v):
        if not isinstance(v, dict) or set(v.keys()) != {"L", "R"}:
            raise ValueError("pattern must have L and R keys")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "pattern": {"L": "rearfoot", "R": "rearfoot"},
                "foot_strike_angle_deg": {"L": 18.2, "R": 16.7},
            }
        }


class Pronation(BaseModel):
    """Pronation analysis."""

    rearfoot_angle_at_midstance_deg: LRPair = Field(
        ..., description="Rearfoot angle at midstance in degrees"
    )
    classification: Dict[str, PronationClassification] = Field(
        ..., description="Pronation classification per foot"
    )
    time_to_peak_eversion_pct_stance: LRPair = Field(
        ..., description="Time to peak eversion as % of stance phase"
    )
    frontal_plane_excursion_left_deg: float = Field(
        ..., description="Total frontal-plane rearfoot excursion during stance (left foot) in degrees (mobility metric)"
    )
    frontal_plane_excursion_right_deg: float = Field(
        ..., description="Total frontal-plane rearfoot excursion during stance (right foot) in degrees (mobility metric)"
    )

    @validator("classification")
    def validate_lr_classification(cls, v):
        if not isinstance(v, dict) or set(v.keys()) != {"L", "R"}:
            raise ValueError("classification must have L and R keys")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "rearfoot_angle_at_midstance_deg": {"L": 11.4, "R": 9.8},
                "classification": {"L": "overpronation", "R": "overpronation"},
                "time_to_peak_eversion_pct_stance": {"L": 38, "R": 42},
                "frontal_plane_excursion_left_deg": 12.3,
                "frontal_plane_excursion_right_deg": 11.8,
            }
        }


class Arch(BaseModel):
    """Arch assessment."""

    type: Dict[str, ArchType] = Field(..., description="Arch type per foot")
    arch_height_index: LRPair = Field(..., description="Arch height index per foot")

    @validator("type")
    def validate_lr_type(cls, v):
        if not isinstance(v, dict) or set(v.keys()) != {"L", "R"}:
            raise ValueError("type must have L and R keys")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "type": {"L": "low", "R": "low"},
                "arch_height_index": {"L": 0.21, "R": 0.22},
            }
        }


class DefectDetail(BaseModel):
    """Details about a gait defect or biomechanical issue found in the patient."""

    name: str = Field(
        ..., description="Name of the defect (e.g. 'Severe Overpronation - Left Foot')"
    )
    severity: str = Field(
        ..., description="Severity level (mild / moderate / severe)"
    )
    affected_side: str = Field(
        ..., description="Affected side (left / right / bilateral)"
    )
    biomechanical_cause: str = Field(
        ..., description="Plain-English explanation of what the data shows"
    )
    gait_cycle_phase: str = Field(
        ..., description="Which phase this occurs in (e.g. 'Loading Response', 'Mid-Stance')"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Severe Overpronation - Left Foot",
                "severity": "severe",
                "affected_side": "left",
                "biomechanical_cause": "Rearfoot eversion angle of 11.4° at midstance exceeds normal range (0-4°), indicating excessive foot inversion and stress on medial structures",
                "gait_cycle_phase": "Loading Response to Mid-Stance",
            }
        }


class ImprovementAction(BaseModel):
    """Specific exercise or intervention to address a gait defect."""

    exercise_name: str = Field(..., description="Name of the exercise")
    target_area: str = Field(..., description="Body area targeted (e.g. 'Intrinsic foot muscles')")
    frequency: str = Field(
        ..., description="Recommended frequency (e.g. '3 sets of 12 reps, daily')"
    )
    instructions: str = Field(..., description="Step-by-step exercise instructions")
    addresses_defect: str = Field(
        ..., description="Links back to DefectDetail.name — which defect this action addresses"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "exercise_name": "Short Foot Exercise",
                "target_area": "Intrinsic foot muscles",
                "frequency": "3 sets of 12 reps, daily",
                "instructions": "Sit or stand with feet flat. Without curling toes, shorten the foot by drawing the ball of the foot toward the heel, creating a dome under the arch.",
                "addresses_defect": "Severe Overpronation - Left Foot",
            }
        }


class HealthAssessment(BaseModel):
    """Patient-facing health assessment and personalized improvement plan."""

    what_went_right: list[str] = Field(
        default_factory=list,
        description="Positive findings (e.g. 'Good symmetry in step length')"
    )
    defects_found: list[DefectDetail] = Field(
        default_factory=list,
        description="Biomechanical defects or issues identified"
    )
    improvement_plan: list[ImprovementAction] = Field(
        default_factory=list,
        description="Targeted exercises and interventions to address defects"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "what_went_right": [
                    "Good symmetry in cadence (112 steps/min on both feet)",
                    "Healthy foot progression angle (neutral, 6-7°)",
                ],
                "defects_found": [
                    {
                        "name": "Severe Overpronation - Left Foot",
                        "severity": "severe",
                        "affected_side": "left",
                        "biomechanical_cause": "Rearfoot eversion angle of 11.4° at midstance exceeds normal range",
                        "gait_cycle_phase": "Loading Response to Mid-Stance",
                    }
                ],
                "improvement_plan": [
                    {
                        "exercise_name": "Short Foot Exercise",
                        "target_area": "Intrinsic foot muscles",
                        "frequency": "3 sets of 12 reps, daily",
                        "instructions": "Sit or stand with feet flat. Without curling toes, shorten the foot by drawing the ball of the foot toward the heel.",
                        "addresses_defect": "Severe Overpronation - Left Foot",
                    }
                ],
            }
        }


# ── Prescription spec (orthotist / shoe-designer facing) ─────────────────────


class MidsoleSpec(BaseModel):
    """Midsole material and geometry specification."""

    medial_shore_c: float = Field(..., description="Medial midsole firmness (Shore C, typical 45–75)")
    lateral_shore_c: float = Field(..., description="Lateral midsole firmness (Shore C, typical 45–65)")
    heel_drop_mm: float = Field(..., description="Height difference heel-to-forefoot in mm (0–12 mm)")
    cushioning_priority: str = Field(
        ..., description="Zone requiring primary cushioning: heel / forefoot / full_length / lateral"
    )


class ArchSupportSpec(BaseModel):
    """Arch support insert specification."""

    height_mm: float = Field(..., description="Arch support peak height in mm (typical 15–35 mm)")
    type: str = Field(..., description="Support geometry: contoured / flat / accommodative")
    medial_post: bool = Field(..., description="Whether a firmer medial density post is needed")
    medial_post_shore_c: Optional[float] = Field(
        None, description="Shore C of medial post — only populated when medial_post is True"
    )


class LastSpec(BaseModel):
    """Last shape and structural envelope specification."""

    shape: str = Field(..., description="Last shape: straight / semi_curved / curved")
    toe_box: str = Field(..., description="Toe-box width: standard / wide / extra_wide / deep")
    heel_counter: str = Field(..., description="Heel counter rigidity: rigid / semi_rigid / flexible")


class FootLiftSpec(BaseModel):
    """Heel-lift compensation for leg-length discrepancy or step asymmetry."""

    heel_lift_left_mm: float = Field(
        ..., description="Heel lift added to left shoe in mm (0 if symmetric)"
    )
    heel_lift_right_mm: float = Field(
        ..., description="Heel lift added to right shoe in mm (0 if symmetric)"
    )


class OutsoleSpec(BaseModel):
    """Outsole geometry and reinforcement specification."""

    base: str = Field(..., description="Outsole profile: standard / flared / rocker")
    rocker_apex_position: Optional[str] = Field(
        None, description="Rocker apex location (metatarsal / midfoot) — only if base is rocker"
    )
    lateral_reinforcement: bool = Field(
        ..., description="Whether extra rubber on the lateral wear zone is required"
    )


class UpperSpec(BaseModel):
    """Upper construction specification."""

    construction: str = Field(..., description="Upper build: standard / seamless / minimal_seam")
    material: str = Field(..., description="Primary upper material: leather / neoprene / mesh")
    closure: str = Field(..., description="Fastening method: lace / velcro / slip_on")
    extra_depth: bool = Field(..., description="Whether extra vertical depth is required")


class PrescriptionSpec(BaseModel):
    """Orthotist / shoe-designer-facing manufacturing specification.

    This block answers 'what kind of shoe should be manufactured for this patient'
    — not exercises, but physical design parameters derived from the same
    biomechanical data that feeds health_assessment.

    **Audience:** orthotists and shoe designers only.  Do NOT surface this block
    directly to patients — it contains technical manufacturing language.
    """

    last_spec: LastSpec = Field(..., description="Last shape and structural envelope")
    arch_support: ArchSupportSpec = Field(..., description="Arch support insert specification")
    midsole: MidsoleSpec = Field(..., description="Midsole material and geometry")
    outsole: OutsoleSpec = Field(..., description="Outsole profile and reinforcement")
    upper: UpperSpec = Field(..., description="Upper construction and material")
    foot_lift: FootLiftSpec = Field(..., description="Heel-lift compensation per side")
    primary_condition_addressed: str = Field(
        ...,
        description="Plain-English summary of the primary biomechanical condition driving the prescription",
    )
    clinician_referral_notes: list[str] = Field(
        default_factory=list,
        description="Flags requiring clinician or specialist review before fabrication",
    )
    confidence: str = Field(
        ..., description="How the prescription was generated: rule_based / agent_override"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "last_spec": {"shape": "straight", "toe_box": "standard", "heel_counter": "rigid"},
                "arch_support": {
                    "height_mm": 30.0,
                    "type": "contoured",
                    "medial_post": True,
                    "medial_post_shore_c": 75.0,
                },
                "midsole": {
                    "medial_shore_c": 75.0,
                    "lateral_shore_c": 45.0,
                    "heel_drop_mm": 10.0,
                    "cushioning_priority": "heel",
                },
                "outsole": {
                    "base": "standard",
                    "rocker_apex_position": None,
                    "lateral_reinforcement": False,
                },
                "upper": {
                    "construction": "standard",
                    "material": "leather",
                    "closure": "lace",
                    "extra_depth": False,
                },
                "foot_lift": {"heel_lift_left_mm": 0.0, "heel_lift_right_mm": 0.0},
                "primary_condition_addressed": "Severe bilateral overpronation with flat arch",
                "clinician_referral_notes": [],
                "confidence": "rule_based",
            }
        }


class GaitPatientProfile(BaseModel):
    """Complete gait analysis patient profile — source of truth for output contract.

    This is the single artifact emitted at the end of the pipeline.
    All downstream consumers (shoe-design module, clinician UI, etc.) depend on this schema.
    """

    schema_version: str = Field(default="profile/v1", description="Schema version")
    patient_id: str = Field(..., description="Pseudonymous patient identifier")
    session_timestamp: datetime = Field(..., description="Session capture timestamp (UTC)")
    trial_condition: Optional[str] = Field(
        None, description="Footwear condition: 'barefoot' or 'shod'"
    )
    linked_session_id: Optional[str] = Field(
        None, description="Session ID of the paired barefoot/shod trial for comparison"
    )
    anthropometrics: Anthropometrics = Field(..., description="Patient measurements")
    spatiotemporal: Spatiotemporal = Field(
        ..., description="Spatiotemporal gait parameters"
    )
    foot_strike: FootStrike = Field(..., description="Foot strike classification")
    pronation: Pronation = Field(..., description="Pronation analysis")
    arch: Arch = Field(..., description="Arch assessment")
    kinematics_peaks: Optional[Dict[str, LRPair]] = Field(
        None, description="Peak joint angles during stance (e.g. knee_flexion_deg, hip_adduction_deg)"
    )
    symmetry_flags: list[str] = Field(
        default_factory=list,
        description="List of asymmetries flagged (e.g. step_length_asymmetric_12pct)",
    )
    health_assessment: HealthAssessment = Field(
        ..., description="Patient-facing health assessment and personalized improvement plan"
    )
    confidence_scores: Dict[str, float] = Field(
        ..., description="Confidence scores (0-1) for each classification"
    )
    needs_human_review: Optional[bool] = Field(
        False, description="Flag: requires clinician/orthotist review"
    )
    quality_metrics: Optional[Dict[str, Any]] = Field(
        None, description="Pipeline quality metrics (internal; not for shoe-design)"
    )
    processing_metadata: Optional[Dict[str, Any]] = Field(
        None, description="Pipeline metadata (timestamps, model versions, etc.)"
    )
    agent_decisions: Optional[Dict[str, Any]] = Field(
        None, description="Agent decision log: timestamp, method_used (agent|static_rules), confidence_score or fallback_reason, raw_llm_response if rejected"
    )
    face_blur_applied: bool = Field(
        False,
        description="True if at least one face was detected and blurred across the session videos (DPDP Act 2023 compliance)"
    )
    prescription_spec: Optional[PrescriptionSpec] = Field(
        None,
        description=(
            "Orthotist/shoe-designer-facing manufacturing specification. "
            "Populated for every session with a valid health_assessment. "
            "Audience: orthotists and shoe designers only — do not surface directly to patients."
        ),
    )

    @validator("trial_condition")
    def validate_trial_condition(cls, v):
        if v is not None and v not in {"barefoot", "shod"}:
            raise ValueError("trial_condition must be 'barefoot' or 'shod'")
        return v

    @validator("confidence_scores")
    def validate_confidence_scores(cls, v):
        for key, score in v.items():
            if not 0.0 <= score <= 1.0:
                raise ValueError(
                    f"Confidence score for {key} must be between 0 and 1, got {score}"
                )
        return v

    class Config:
        json_schema_extra = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://example.org/schemas/gait/profile/v1.json",
            "title": "GaitPatientProfile",
            "description": "Complete gait analysis patient profile",
            "example": {
                "schema_version": "profile/v1",
                "patient_id": "P0042",
                "session_timestamp": "2026-05-15T11:23:00Z",
                "trial_condition": "barefoot",
                "linked_session_id": None,
                "anthropometrics": {
                    "height_cm": 172,
                    "mass_kg": 68,
                    "foot_length_mm": {"L": 258, "R": 260},
                    "foot_width_mm": {"L": 98, "R": 99},
                },
                "spatiotemporal": {
                    "cadence_spm": 112,
                    "speed_mps": 1.28,
                    "stride_length_m": 1.37,
                    "step_width_m": 0.09,
                    "stance_pct": {"L": 61.2, "R": 60.4},
                    "double_support_pct": 22.1,
                    "step_length_left_m": 0.68,
                    "step_length_right_m": 0.67,
                    "foot_progression_angle_left_deg": 7.2,
                    "foot_progression_angle_right_deg": 6.8,
                    "foot_progression_classification_left": "toe_out",
                    "foot_progression_classification_right": "toe_out",
                },
                "foot_strike": {
                    "pattern": {"L": "rearfoot", "R": "rearfoot"},
                    "foot_strike_angle_deg": {"L": 18.2, "R": 16.7},
                },
                "pronation": {
                    "rearfoot_angle_at_midstance_deg": {"L": 11.4, "R": 9.8},
                    "classification": {"L": "overpronation", "R": "overpronation"},
                    "time_to_peak_eversion_pct_stance": {"L": 38, "R": 42},
                    "frontal_plane_excursion_left_deg": 12.3,
                    "frontal_plane_excursion_right_deg": 11.8,
                },
                "arch": {
                    "type": {"L": "low", "R": "low"},
                    "arch_height_index": {"L": 0.21, "R": 0.22},
                },
                "symmetry_flags": ["step_length_asymmetric_12pct"],
                "health_assessment": {
                    "what_went_right": [
                        "Good symmetry in cadence (112 steps/min)",
                        "Healthy foot progression angle (neutral, 6-7°)"
                    ],
                    "defects_found": [
                        {
                            "name": "Severe Overpronation - Left Foot",
                            "severity": "severe",
                            "affected_side": "left",
                            "biomechanical_cause": "Rearfoot eversion angle of 11.4° at midstance exceeds normal range (0-4°), indicating excessive foot inversion",
                            "gait_cycle_phase": "Loading Response to Mid-Stance"
                        }
                    ],
                    "improvement_plan": [
                        {
                            "exercise_name": "Short Foot Exercise",
                            "target_area": "Intrinsic foot muscles",
                            "frequency": "3 sets of 12 reps, daily",
                            "instructions": "Sit or stand with feet flat. Without curling toes, shorten the foot by drawing the ball of the foot toward the heel.",
                            "addresses_defect": "Severe Overpronation - Left Foot"
                        }
                    ]
                },
                "confidence_scores": {
                    "pronation_classification": 0.91,
                    "foot_strike_classification": 0.95,
                },
                "needs_human_review": False,
            },
        }
