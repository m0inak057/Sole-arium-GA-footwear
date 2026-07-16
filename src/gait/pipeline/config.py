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
        1, description="RERECORD if < this many clean cycles"
    )
    target_clean_cycles_per_foot: int = Field(
        1, description="Target clean cycles for PROCEED_OK"
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
    sync_mode: str = Field(
        "frame_index",
        description=(
            "Camera sync strategy: "
            "'timestamp' = hardware-synced cameras (strict wall-clock matching); "
            "'frame_index' = pair by frame number, trimming all cameras to the "
            "shortest stream (file uploads / consumer cameras / mismatched lengths — "
            "default, since it never rejects a session on length or timing mismatch); "
            "'auto' = probe first 100 frames and choose automatically."
        ),
    )
    background_subtraction_model: str = Field("mog2", description="'mog2' only in MVP")
    person_tracking_model: str = Field("simple_iou", description="'simple_iou' or 'bytetrack'")
    roi_margin_px: int = Field(120, description="Margin around detected person in pixels â€” generous enough for arm swing and foot extension during walking")
    # Decode error tolerance
    max_consecutive_decode_failure_pct: int = Field(
        50, description="Raise VideoDecodeError when this % of frames fail consecutively"
    )
    # Sync error tolerance
    max_unsync_frames_before_error: int = Field(
        100000, description="Raise FrameSyncError after this many consecutive unsync windows (effectively disabled)"
    )
    # MOG2 background subtraction
    mog2_history: int = Field(3, description="MOG2 history length (warmup frames) — kept low so short clips aren't fully consumed by warmup")
    mog2_var_threshold: float = Field(16.0, description="MOG2 variance threshold")
    mog2_detect_shadows: bool = Field(False, description="MOG2 shadow detection flag â€” disabled: shadow pixels (127) pollute the mask and this codebase already thresholds hard to binary")
    mog2_morph_kernel_size_px: int = Field(5, description="Morphological cleanup kernel size")
    # Person tracking
    iou_threshold: float = Field(0.3, description="Min IoU to accept blob as same person")
    max_lost_frames: int = Field(100000, description="TrackingLostError is no longer raised by the tracker; kept as a nominal ceiling")
    min_blob_area_px2: int = Field(10, description="Ignore foreground blobs smaller than this")


class PoseConfig(BaseModel):
    """Pose estimation parameters."""

    model: str = Field("mediapipe", description="Pose model to use")
    model_path: str = Field("data/models/pose_landmarker_lite.task", description="Path to MediaPipe Pose Landmarker task model file (auto-downloaded if missing)")
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
    heel_strike_threshold: float = Field(0.05, description="HS peak prominence (fraction of y range) - low because posterior/anterior camera views have much smaller vertical bounce amplitude than sagittal")
    toe_off_threshold: float = Field(0.05, description="TO peak prominence (fraction of y range) - low for the same reason as heel_strike_threshold")
    event_confidence_min: float = Field(0.1, description="Drop events whose keypoint confidence < this â€” low because MediaPipe presence for lower-leg landmarks in side-view/ROI-cropped footage is typically 0.3-0.6, not 0.8+")
    min_frames_between_events: int = Field(3, description="Minimum frames between two HS (or two TO) events — low enough for short clips to still yield 1-2 cycles")
    smoothing_window_frames: int = Field(3, description="Moving-average window before peak detection - reduced from 5 so heavy smoothing doesn't flatten already-subtle peaks")
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

    # Gating — 0 complete cycles no longer forces RERECORD/placeholder mode:
    # a foot can still have a real PARTIAL_CYCLE or raw event data (see
    # segment_gait_cycles/profile/builder.py), which is more informative than
    # a profile built entirely from population averages.
    min_clean_cycles_per_foot: int = Field(0)
    target_clean_cycles_per_foot: int = Field(1)


class FeaturesConfig(BaseModel):
    """Feature flags (enable/disable by phase)."""

    multi_view_3d: bool = Field(False, description="Phase 3+")
    pressure_mat_validation: bool = Field(False, description="Phase 3+")
    custom_foot_model: bool = Field(False, description="Phase 2+")
    face_blur_pipeline: bool = Field(True, description="DPDP Act 2023 compliance — blur faces before storage")
    audit_logging: bool = Field(True, description="Privacy/compliance audit trail")

    class Config:
        extra = "allow"


class DevelopmentConfig(BaseModel):
    """Development/testing flags from pipeline.yaml's `development:` section.

    Only `verbose_logging` and `skip_gating_check` are wired to real behavior
    (see GaitPipeline.__init__ in gait.pipeline.orchestrator). The other three
    are documented here for discoverability but not implemented anywhere —
    setting them has no effect.
    """

    mock_video_enabled: bool = Field(
        False, description="NOT IMPLEMENTED — intended to substitute synthetic video for testing"
    )
    synthetic_data_mode: bool = Field(
        False, description="NOT IMPLEMENTED — intended to generate synthetic profiles instead of running the pipeline"
    )
    skip_calibration_check: bool = Field(
        False, description="NOT IMPLEMENTED — intended to allow uncalibrated cameras"
    )
    skip_gating_check: bool = Field(
        False,
        description=(
            "Bypass the minimum-clean-cycle-count gate in "
            "StandardBiomechanicalAnalyzer.aggregate_parameters: forces every "
            "foot's quality_flag to PROCEED_OK regardless of cycle_count."
        ),
    )
    verbose_logging: bool = Field(
        False, description="Set every gait.* logger to DEBUG level"
    )


class PipelineConfig(BaseModel):
    """Overall pipeline processing configuration."""

    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    pose: PoseConfig = Field(default_factory=PoseConfig)
    events: EventDetectionConfig = Field(default_factory=EventDetectionConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    static_trial: StaticTrialConfig = Field(default_factory=StaticTrialConfig)
    features: FeaturesConfig = Field(default_factory=FeaturesConfig)
    development: DevelopmentConfig = Field(default_factory=DevelopmentConfig)

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
        default_factory=list, description="List of health recommendation rules"
    )
    prescription_rules: list[RecommendationRule] = Field(
        default_factory=list, description="List of shoe prescription rules"
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
