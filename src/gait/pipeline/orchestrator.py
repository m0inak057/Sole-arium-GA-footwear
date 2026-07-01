"""GaitPipeline â€” end-to-end pipeline orchestrator.

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

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from gait.analysis.analyzer import create_biomechanical_analyzer
from gait.common.interfaces import GaitCycle, KeypointFrame
from gait.common.logging_utils import get_logger
from gait.events.gait_event_detector import assign_pass_ids
from gait.events.velocity_detector import create_event_detector
from gait.pipeline.config import (
    PipelineConfig,
    load_pipeline_config,
    load_recommendation_rules,
)
from gait.profile.builder import create_profile_builder
from gait.profile.gating import discard_boundary_cycles

logger = get_logger(__name__)


def _make_health_coach() -> Any:
    """Return a GaitHealthCoach backed by Claude, or None if no API key is set."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        from gait.agents.health_coach import GaitHealthCoach

        return GaitHealthCoach(anthropic.Anthropic())
    except Exception as exc:
        logger.warning("orchestrator.health_coach_init_failed", extra={"reason": str(exc)})
        return None


def _make_prescription_agent() -> Any:
    """Return a PrescriptionAgent backed by Claude, or None if no API key is set."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        from gait.agents.prescription_agent import PrescriptionAgent

        return PrescriptionAgent(anthropic.Anthropic())
    except Exception as exc:
        logger.warning("orchestrator.prescription_agent_init_failed", extra={"reason": str(exc)})
        return None


class GaitPipeline:
    """End-to-end gait analysis pipeline.

    Construct once per analysis session; never reuse across sessions.
    Call ``process_static_trial()`` before ``run()`` to capture per-subject
    joint-angle offsets; if omitted, all offsets default to zero.
    """

    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self._cfg = config or load_pipeline_config()
        self._static_trial_offsets: Dict[str, float] = {}
        self._health_coach = _make_health_coach()
        self._prescription_agent = _make_prescription_agent()

    def run(
        self,
        video_paths: Dict[str, Path],
        anthropometrics: Dict[str, Any],
        patient_id: str,
        session_timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run all pipeline stages and return a GaitPatientProfile-shaped dict.

        Args:
            video_paths:       camera_name â†’ path mapping (e.g. {"sagittal": Path(...)}).
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

        # â”€â”€ Stage 1: Ingestion â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        keypoint_frames = self._run_ingestion_and_pose(video_paths)

        # â”€â”€ Stages 3â€“4: Events + Analysis â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        parameters = self._run_analysis(keypoint_frames)

        # â”€â”€ Stage 5: Profile â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        rules_config = load_recommendation_rules()
        builder = create_profile_builder(rules_config, self._cfg.analysis)

        # Wire the Claude health coach into the builder (None = rules-only fallback)
        builder._health_coach = self._health_coach

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

        # â”€â”€ Claude prescription refinement (post-build) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if self._prescription_agent is not None and profile.get("prescription_spec"):
            try:
                # Reconstruct rule_params for the prescription agent
                params_l = parameters["L"]
                params_r = parameters["R"]
                from gait.profile.builder import _derive_rule_parameters, _compute_symmetry_flags

                sym_flags = _compute_symmetry_flags(
                    params_l, params_r, self._cfg.analysis.symmetry_flag_threshold_pct
                )
                rule_params = _derive_rule_parameters(
                    params_l,
                    params_r,
                    {"flags": sym_flags},
                )
                refined_spec, rationale = self._prescription_agent.refine(
                    rule_based_spec=profile["prescription_spec"],
                    rule_params=rule_params,
                    anthropometrics=anthropometrics,
                )
                profile["prescription_spec"] = refined_spec
                # Merge rationale into agent_decisions log
                decisions = profile.get("agent_decisions") or {}
                decisions["prescription_rationale"] = rationale
                decisions["claude_enhanced"] = True
                decisions["model"] = "claude-opus-4-8"
                profile["agent_decisions"] = decisions
                logger.info(
                    "pipeline.prescription_agent_applied",
                    extra={"patient_id": patient_id, "rationale": rationale[:80]},
                )
            except Exception as exc:
                logger.warning(
                    "pipeline.prescription_agent_failed",
                    extra={"patient_id": patient_id, "reason": str(exc)},
                )

        logger.info("pipeline.complete", extra={"patient_id": patient_id})
        return profile

    # â”€â”€ static calibration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def process_static_trial(
        self,
        session_id: str,
        keypoint_frames: List[KeypointFrame],
    ) -> "StaticTrial":
        """Run the static calibration trial and store per-subject joint-angle offsets.

        Must be called before ``run()`` if anatomical offset correction is desired.
        The resulting offsets are automatically forwarded to the biomechanical
        analyzer so that dynamic joint angles are expressed relative to the
        subject's own neutral standing posture.

        Args:
            session_id:       Identifier for this session (stored on the result).
            keypoint_frames:  Pose-estimated frames from the quiet-standing
                              capture (~3 s at the configured fps).

        Returns:
            StaticTrial containing averaged keypoints and joint_angle_offsets.
        """
        from gait.common.types import StaticTrial  # noqa: F401 (type re-export)
        from gait.ingestion.static_trial import StaticTrialProcessor

        processor = StaticTrialProcessor(
            self._cfg.static_trial,
            fps=float(self._cfg.ingestion.fps),
        )
        trial = processor.process(session_id, keypoint_frames)
        self._static_trial_offsets = trial.joint_angle_offsets
        logger.info(
            "pipeline.static_trial_captured",
            extra={
                "session_id": session_id,
                "duration_frames": trial.duration_frames,
                "offsets": trial.joint_angle_offsets,
            },
        )
        return trial

    # â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _run_ingestion_and_pose(
        self, video_paths: Dict[str, Path]
    ) -> List[KeypointFrame]:
        """Stages 1â€“2: ingestion + pose â†’ keypoint frames."""
        from gait.ingestion.preprocessor import IngestionPreprocessor
        from gait.pose.estimator import PoseEstimator

        preprocessor = IngestionPreprocessor(self._cfg.ingestion)
        ingestion_result = preprocessor.run(video_paths)

        fps = float(self._cfg.ingestion.fps)
        estimator = PoseEstimator(self._cfg.pose, fps=fps)
        return estimator.run(ingestion_result.frames)

    def _run_analysis(
        self, keypoint_frames: List[KeypointFrame]
    ) -> Dict[str, Dict[str, Any]]:
        """Stages 3â€“4: event detection + analysis â†’ {L: agg_params, R: agg_params}."""
        from gait.analysis.parameters import compute_step_lengths_lr, compute_foot_progression_angle

        fps = float(self._cfg.ingestion.fps)
        detector = create_event_detector(
            self._cfg.events.heel_strike_model,
            self._cfg.events,
        )
        analyzer = create_biomechanical_analyzer(
            self._cfg.analysis,
            fps=fps,
            joint_angle_offsets=self._static_trial_offsets,
        )

        # Detect heel strikes for both feet to compute step lengths and foot progression
        hs_l = detector.detect_heel_strikes(keypoint_frames, "L")
        hs_r = detector.detect_heel_strikes(keypoint_frames, "R")

        # Extract heel x-coordinates from heel strike frame indices
        heel_x_l = self._extract_heel_x_coords(keypoint_frames, hs_l, "left_heel")
        heel_x_r = self._extract_heel_x_coords(keypoint_frames, hs_r, "right_heel")

        # Extract foot index positions for foot progression angles
        foot_index_l = self._extract_keypoint_positions(keypoint_frames, hs_l, "left_foot_index")
        foot_index_r = self._extract_keypoint_positions(keypoint_frames, hs_r, "right_foot_index")

        # Compute step lengths (L and R)
        scale_m_per_px = 0.01  # default calibration
        step_length_l, step_length_r = compute_step_lengths_lr(heel_x_l, heel_x_r, scale_m_per_px)

        # Compute foot progression angles (mean per foot)
        fpa_l = self._compute_mean_fpa(keypoint_frames, hs_l, "left")
        fpa_r = self._compute_mean_fpa(keypoint_frames, hs_r, "right")

        result: Dict[str, Dict[str, Any]] = {}
        for foot in ("L", "R"):
            to = detector.detect_toe_offs(keypoint_frames, foot)
            hs = hs_l if foot == "L" else hs_r
            cycles: List[GaitCycle] = detector.segment_gait_cycles(
                keypoint_frames, hs, to, foot
            )
            cycles = assign_pass_ids(cycles, self._cfg.events.pass_gap_multiplier)
            cycles = discard_boundary_cycles(cycles)
            agg_params = analyzer.aggregate_parameters(cycles, foot)

            # Add global step length and foot progression angle metrics (only to L branch to avoid duplication)
            if foot == "L":
                agg_params["step_length_left_m"] = step_length_l
                agg_params["step_length_right_m"] = step_length_r
                agg_params["foot_progression_angle_left_deg"] = fpa_l
                agg_params["foot_progression_angle_right_deg"] = fpa_r

            result[foot] = agg_params

        return result

    def _extract_heel_x_coords(
        self, keypoint_frames: List[KeypointFrame], heel_strikes: List, heel_name: str
    ) -> list[float]:
        """Extract heel x-coordinates from heel strike events."""
        coords = []
        for event in heel_strikes:
            if event.frame_index < len(keypoint_frames):
                frame = keypoint_frames[event.frame_index]
                heel_kp = frame.keypoints.get(heel_name)
                if heel_kp:
                    coords.append(heel_kp.x)
        return coords

    def _extract_keypoint_positions(
        self, keypoint_frames: List[KeypointFrame], events: List, kp_name: str
    ) -> list[tuple[float, float]]:
        """Extract keypoint (x, y) positions from frame events."""
        positions = []
        for event in events:
            if event.frame_index < len(keypoint_frames):
                frame = keypoint_frames[event.frame_index]
                kp = frame.keypoints.get(kp_name)
                if kp:
                    positions.append((kp.x, kp.y))
        return positions

    def _compute_mean_fpa(
        self, keypoint_frames: List[KeypointFrame], heel_strikes: List, foot: str
    ) -> float:
        """Compute mean foot progression angle across heel strikes."""
        from gait.analysis.parameters import compute_foot_progression_angle
        from gait.common.interfaces import Keypoint

        angles = []
        for event in heel_strikes:
            if event.frame_index < len(keypoint_frames):
                frame = keypoint_frames[event.frame_index]
                heel_kp = frame.keypoints.get(f"{foot}_heel")
                toe_kp = frame.keypoints.get(f"{foot}_foot_index")
                if heel_kp and toe_kp:
                    angle = compute_foot_progression_angle(heel_kp, toe_kp)
                    angles.append(angle)
        return sum(angles) / len(angles) if angles else 0.0


def create_pipeline(config: Optional[PipelineConfig] = None) -> GaitPipeline:
    """Factory: return a GaitPipeline instance."""
    return GaitPipeline(config)

