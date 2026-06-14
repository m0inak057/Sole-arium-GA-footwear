"""Pipeline configuration loader — loads YAML configs at runtime.

Implements the config-over-code philosophy: all tunable parameters
(thresholds, rules, processing settings) are loaded from YAML, not hardcoded.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field


class FootStrikeThresholds(BaseModel):
    """Foot strike angle thresholds."""

    rearfoot_min_deg: float = Field(
        5.0, description="FSA > this → rearfoot strike"
    )
    forefoot_max_deg: float = Field(
        -5.0, description="FSA < this → forefoot strike; between → midfoot"
    )


class PronationThresholds(BaseModel):
    """Pronation angle thresholds (rearfoot eversion at midstance)."""

    overpronation_min_deg: float = Field(8.0, description="> this → overpronation")
    mild_pronation_min_deg: float = Field(4.0, description=">= this → mild pronation")
    neutral_min_deg: float = Field(0.0, description=">= this → neutral")
    mild_supination_min_deg: float = Field(-4.0, description=">= this → mild supination")


class SymmetryThresholds(BaseModel):
    """Symmetry detection thresholds."""

    flag_threshold_pct: float = Field(
        10.0, description="Flag asymmetry if |L-R| / mean > this %"
    )


class QualityGatingThresholds(BaseModel):
    """Quality gating thresholds."""

    min_keypoint_confidence: float = Field(
        0.5, description="Drop frames where keypoint confidence < this"
    )
    min_clean_cycles_per_foot: int = Field(
        4, description="RERECORD if < this many clean cycles"
    )
    target_clean_cycles_per_foot: int = Field(
        8, description="Target clean cycles for PROCEED_OK"
    )


class ThresholdsConfig(BaseModel):
    """All tunable parameters for classifiers and gating."""

    foot_strike: FootStrikeThresholds = Field(default_factory=FootStrikeThresholds)
    pronation: PronationThresholds = Field(default_factory=PronationThresholds)
    symmetry: SymmetryThresholds = Field(default_factory=SymmetryThresholds)
    quality_gating: QualityGatingThresholds = Field(
        default_factory=QualityGatingThresholds
    )

    class Config:
        extra = "allow"  # Allow additional thresholds without validation error


class IngestionConfig(BaseModel):
    """Video ingestion parameters."""

    fps: int = Field(120, description="Frames per second")
    resolution: list[int] = Field(
        [1920, 1080], description="Target resolution [width, height]"
    )
    sync_tolerance_ms: int = Field(10, description="Sync tolerance between cameras")
    background_subtraction_model: str = Field("mog2", description="'mog2' only in MVP")
    person_tracking_model: str = Field("simple_iou", description="'simple_iou' or 'bytetrack'")
    roi_margin_px: int = Field(50, description="Margin around detected person in pixels")
    # Decode error tolerance
    max_consecutive_decode_failure_pct: int = Field(
        10, description="Raise VideoDecodeError when this % of frames fail consecutively"
    )
    # Sync error tolerance
    max_unsync_frames_before_error: int = Field(
        30, description="Raise FrameSyncError after this many consecutive unsync windows"
    )
    # MOG2 background subtraction
    mog2_history: int = Field(500, description="MOG2 history length (warmup frames)")
    mog2_var_threshold: float = Field(16.0, description="MOG2 variance threshold")
    mog2_detect_shadows: bool = Field(True, description="MOG2 shadow detection flag")
    mog2_morph_kernel_size_px: int = Field(5, description="Morphological cleanup kernel size")
    # Person tracking
    iou_threshold: float = Field(0.3, description="Min IoU to accept blob as same person")
    max_lost_frames: int = Field(15, description="Raise TrackingLostError after this many misses")
    min_blob_area_px2: int = Field(5000, description="Ignore foreground blobs smaller than this")


class PoseConfig(BaseModel):
    """Pose estimation parameters."""

    model: str = Field("mediapipe", description="Pose model to use")
    confidence_threshold: float = Field(
        0.5, description="Drop keypoints with confidence < this"
    )
    smoothing_window: int = Field(5, description="1-Euro filter window size")
    use_3d_lifting: bool = Field(True, description="Store MediaPipe z coordinate")
    use_multiview_triangulation: bool = Field(False, description="Multi-view 3D (Phase 3+)")
    batch_size: int = Field(32, description="Frames per batch for pose inference")


class EventDetectionConfig(BaseModel):
    """Event detection parameters."""

    heel_strike_model: str = Field("velocity_based", description="Detection algorithm")
    heel_strike_threshold: float = Field(0.3, description="HS peak prominence (fraction of y range)")
    toe_off_threshold: float = Field(0.2, description="TO peak prominence (fraction of y range)")
    event_confidence_min: float = Field(0.5, description="Drop events whose keypoint confidence < this")
    min_frames_between_events: int = Field(15, description="Minimum frames between two HS (or two TO) events")
    smoothing_window_frames: int = Field(5, description="Moving-average window before peak detection")
    pass_gap_multiplier: float = Field(
        3.0,
        description=(
            "A gap between consecutive cycles larger than this multiple of the median "
            "cycle duration is treated as a between-pass turnaround"
        ),
    )


class StaticTrialConfig(BaseModel):
    """Parameters for the static calibration trial."""

    duration_sec: float = Field(
        3.0, description="Duration of quiet-standing capture used for calibration (seconds)"
    )
    required_keypoint_confidence: float = Field(
        0.7, description="Minimum per-keypoint confidence to include a frame in the standing average"
    )


class AnalysisConfig(BaseModel):
    """Biomechanical analysis thresholds and feature flags."""

    compute_kinematics_peaks: bool = Field(True, description="Compute knee/hip angle peaks")
    compute_symmetry_indices: bool = Field(True, description="Compute L/R symmetry indices")
    symmetry_flag_threshold_pct: float = Field(10.0, description="Flag asymmetry above this %")

    # Foot-strike classification (positive FSA = rearfoot)
    rearfoot_min_deg: float = Field(5.0, description="FSA > this → rearfoot")
    forefoot_max_deg: float = Field(-5.0, description="FSA < this → forefoot")

    # Pronation classification (positive angle = eversion/pronation)
    overpronation_min_deg: float = Field(8.0)
    mild_pronation_min_deg: float = Field(4.0)
    neutral_min_deg: float = Field(0.0)
    mild_supination_min_deg: float = Field(-4.0)

    # Arch height index
    high_ahi_min: float = Field(0.30, description="AHI >= this → high arch")
    normal_ahi_min: float = Field(0.20, description="AHI >= this → normal arch")

    # Gating
    min_clean_cycles_per_foot: int = Field(4)
    target_clean_cycles_per_foot: int = Field(8)


class PipelineConfig(BaseModel):
    """Overall pipeline processing configuration."""

    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    pose: PoseConfig = Field(default_factory=PoseConfig)
    events: EventDetectionConfig = Field(default_factory=EventDetectionConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    static_trial: StaticTrialConfig = Field(default_factory=StaticTrialConfig)

    class Config:
        extra = "allow"  # Allow additional configs


class RecommendationRule(BaseModel):
    """A single recommendation rule."""

    id: str = Field(..., description="Unique rule identifier")
    when: Dict[str, Any] = Field(..., description="Condition dict")
    then: Dict[str, Any] = Field(..., description="Recommendation patch dict")
    priority: Optional[int] = Field(0, description="Rule priority (higher = evaluated first)")


class RecommendationRulesConfig(BaseModel):
    """All recommendation rules."""

    version: int = Field(1, description="Rules version")
    rules: list[RecommendationRule] = Field(
        default_factory=list, description="List of rules"
    )

    class Config:
        extra = "allow"


def load_thresholds(config_path: Optional[str] = None) -> ThresholdsConfig:
    """Load thresholds from YAML config.

    Args:
        config_path: Path to thresholds.yaml. If None, uses CONFIGS_DIR env var.

    Returns:
        ThresholdsConfig object with all thresholds.

    Raises:
        FileNotFoundError: If config file not found.
        yaml.YAMLError: If config file is invalid YAML.
    """
    if config_path is None:
        config_path = os.getenv(
            "CONFIGS_DIR", "configs"
        ) + "/thresholds.yaml"

    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Thresholds config not found: {config_path}")

    with open(config_file, "r") as f:
        data = yaml.safe_load(f) or {}

    return ThresholdsConfig(**data)


def load_pipeline_config(config_path: Optional[str] = None) -> PipelineConfig:
    """Load pipeline config from YAML.

    Args:
        config_path: Path to pipeline.yaml. If None, uses CONFIGS_DIR env var.

    Returns:
        PipelineConfig object.
    """
    if config_path is None:
        config_path = os.getenv(
            "CONFIGS_DIR", "configs"
        ) + "/pipeline.yaml"

    config_file = Path(config_path)
    if not config_file.exists():
        return PipelineConfig()  # Return defaults if file doesn't exist

    with open(config_file, "r") as f:
        data = yaml.safe_load(f) or {}

    return PipelineConfig(**data)


def load_recommendation_rules(config_path: Optional[str] = None) -> RecommendationRulesConfig:
    """Load recommendation rules from YAML.

    Args:
        config_path: Path to rules.yaml. If None, uses CONFIGS_DIR env var.

    Returns:
        RecommendationRulesConfig object.
    """
    if config_path is None:
        config_path = os.getenv(
            "CONFIGS_DIR", "configs"
        ) + "/rules.yaml"

    config_file = Path(config_path)
    if not config_file.exists():
        return RecommendationRulesConfig()  # Return empty rules if file doesn't exist

    with open(config_file, "r") as f:
        data = yaml.safe_load(f) or {}

    return RecommendationRulesConfig(**data)


def load_camera_config(camera_name: str, config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load camera calibration config.

    Args:
        camera_name: Camera name (e.g. 'sagittal', 'posterior').
        config_path: Path to camera config directory. If None, uses CONFIGS_DIR env var.

    Returns:
        Camera calibration dict (intrinsics, extrinsics, etc.).

    Raises:
        FileNotFoundError: If camera config not found.
    """
    if config_path is None:
        config_path = os.getenv(
            "CONFIGS_DIR", "configs"
        ) + "/cameras"

    camera_file = Path(config_path) / f"{camera_name}.yaml"
    if not camera_file.exists():
        raise FileNotFoundError(f"Camera config not found: {camera_file}")

    with open(camera_file, "r") as f:
        return yaml.safe_load(f) or {}
