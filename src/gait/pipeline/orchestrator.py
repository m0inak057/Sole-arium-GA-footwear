"""GaitPipeline — end-to-end pipeline orchestrator.

Stitches together the five pipeline stages:
  1. Ingestion & preprocessing  (IngestionPreprocessor)
  2. Pose estimation            (PoseEstimator)
  3. Gait event detection       (VelocityBasedEventDetector)
  4. Biomechanical analysis     (StandardBiomechanicalAnalyzer)
  5. Profile generation         (StandardProfileBuilder)

All dependencies are constructed internally from config; nothing is shared
across `GaitPipeline` instances, so it is safe to instantiate per-task.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.gait.analysis.analyzer import create_biomechanical_analyzer
from src.gait.common.interfaces import GaitCycle, KeypointFrame
from src.gait.common.logging_utils import get_logger
from src.gait.events.velocity_detector import create_event_detector
from src.gait.pipeline.config import (
    PipelineConfig,
    load_pipeline_config,
    load_recommendation_rules,
)
from src.gait.profile.builder import create_profile_builder

logger = get_logger(__name__)


class GaitPipeline:
    """End-to-end gait analysis pipeline.

    Construct once per analysis session; never reuse across sessions.
    """

    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self._cfg = config or load_pipeline_config()

    def run(
        self,
        video_paths: Dict[str, Path],
        anthropometrics: Dict[str, Any],
        patient_id: str,
        session_timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run all pipeline stages and return a GaitPatientProfile-shaped dict.

        Args:
            video_paths:       camera_name → path mapping (e.g. {"sagittal": Path(...)}).
            anthropometrics:   Patient measurements (height_cm, mass_kg, foot_length_mm, ...).
            patient_id:        Pseudonymous patient identifier.
            session_timestamp: ISO 8601 string; defaults to current UTC time.

        Returns:
            Profile dict matching GaitPatientProfile schema.
        """
        if session_timestamp is None:
            session_timestamp = datetime.now(timezone.utc).isoformat()

        logger.info(
            "pipeline.start",
            extra={"patient_id": patient_id, "n_cameras": len(video_paths)},
        )

        # ── Stage 1: Ingestion ─────────────────────────────────────────────────
        keypoint_frames = self._run_ingestion_and_pose(video_paths)

        # ── Stages 3–4: Events + Analysis ─────────────────────────────────────
        parameters = self._run_analysis(keypoint_frames)

        # ── Stage 5: Profile ───────────────────────────────────────────────────
        rules_config = load_recommendation_rules()
        builder = create_profile_builder(rules_config, self._cfg.analysis)

        profile = builder.build(
            patient_id=patient_id,
            session_timestamp=session_timestamp,
            parameters={
                "L": parameters["L"],
                "R": parameters["R"],
            },
            anthropometrics=anthropometrics,
            confidence_scores={"pipeline": 0.80},
        )

        logger.info("pipeline.complete", extra={"patient_id": patient_id})
        return profile

    # ── helpers ────────────────────────────────────────────────────────────────

    def _run_ingestion_and_pose(
        self, video_paths: Dict[str, Path]
    ) -> List[KeypointFrame]:
        """Stages 1–2: ingestion + pose → keypoint frames."""
        from src.gait.ingestion.preprocessor import IngestionPreprocessor
        from src.gait.pose.estimator import PoseEstimator

        preprocessor = IngestionPreprocessor(self._cfg.ingestion)
        ingestion_result = preprocessor.run(video_paths)

        fps = float(self._cfg.ingestion.fps)
        estimator = PoseEstimator(self._cfg.pose, fps=fps)
        return estimator.run(ingestion_result.frames)

    def _run_analysis(
        self, keypoint_frames: List[KeypointFrame]
    ) -> Dict[str, Dict[str, Any]]:
        """Stages 3–4: event detection + analysis → {L: agg_params, R: agg_params}."""
        fps = float(self._cfg.ingestion.fps)
        detector = create_event_detector(
            self._cfg.events.heel_strike_model,
            self._cfg.events,
        )
        analyzer = create_biomechanical_analyzer(self._cfg.analysis, fps=fps)

        result: Dict[str, Dict[str, Any]] = {}
        for foot in ("L", "R"):
            hs = detector.detect_heel_strikes(keypoint_frames, foot)
            to = detector.detect_toe_offs(keypoint_frames, foot)
            cycles: List[GaitCycle] = detector.segment_gait_cycles(
                keypoint_frames, hs, to, foot
            )
            result[foot] = analyzer.aggregate_parameters(cycles, foot)

        return result


def create_pipeline(config: Optional[PipelineConfig] = None) -> GaitPipeline:
    """Factory: return a GaitPipeline instance."""
    return GaitPipeline(config)
