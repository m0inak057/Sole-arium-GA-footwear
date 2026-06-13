"""Gait patient profile schema — source of truth for output contract.

This module defines the Pydantic models that represent the patient-profile JSON.
Every profile emitted by the pipeline must validate against these models.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, validator


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


class ShoeDesignRecommendations(BaseModel):
    """Shoe design recommendations (rule-derived)."""

    medial_post: MedialPostType = Field(..., description="Medial post recommendation")
    post_density: Optional[PostDensityType] = Field(
        None, description="Post density if post is required"
    )
    arch_support: ArchSupportType = Field(..., description="Arch support level")
    heel_counter: HeelCounterType = Field(..., description="Heel counter rigidity")
    heel_drop_mm: float = Field(..., description="Heel drop in millimeters")
    last_shape: LastShapeType = Field(..., description="Last shape recommendation")
    cushioning_zone_priority: Optional[list[str]] = Field(
        None, description="Priority zones for cushioning (e.g. heel, midfoot, forefoot)"
    )
    notes: Optional[str] = Field(None, description="Orthotist notes on recommendations")

    class Config:
        json_schema_extra = {
            "example": {
                "medial_post": "required",
                "post_density": "firm",
                "arch_support": "high",
                "heel_counter": "rigid",
                "heel_drop_mm": 10,
                "last_shape": "straight",
                "cushioning_zone_priority": ["heel", "medial_forefoot"],
                "notes": "High overpronation with low arch; prioritize medial support",
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
    shoe_design_recommendations: ShoeDesignRecommendations = Field(
        ..., description="Rule-derived shoe design recommendations"
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
                },
                "foot_strike": {
                    "pattern": {"L": "rearfoot", "R": "rearfoot"},
                    "foot_strike_angle_deg": {"L": 18.2, "R": 16.7},
                },
                "pronation": {
                    "rearfoot_angle_at_midstance_deg": {"L": 11.4, "R": 9.8},
                    "classification": {"L": "overpronation", "R": "overpronation"},
                    "time_to_peak_eversion_pct_stance": {"L": 38, "R": 42},
                },
                "arch": {
                    "type": {"L": "low", "R": "low"},
                    "arch_height_index": {"L": 0.21, "R": 0.22},
                },
                "symmetry_flags": ["step_length_asymmetric_12pct"],
                "shoe_design_recommendations": {
                    "medial_post": "required",
                    "post_density": "firm",
                    "arch_support": "high",
                    "heel_counter": "rigid",
                    "heel_drop_mm": 10,
                    "last_shape": "straight",
                    "cushioning_zone_priority": ["heel", "medial_forefoot"],
                },
                "confidence_scores": {
                    "pronation_classification": 0.91,
                    "foot_strike_classification": 0.95,
                },
                "needs_human_review": False,
            },
        }
