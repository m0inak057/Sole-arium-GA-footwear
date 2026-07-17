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

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

# Keypoints considered when scoring a frame's usefulness for event detection
# (heel-strike / toe-off require reliable lower-body tracking).
_LOWER_BODY_KEYPOINTS = (
    "left_heel",
    "right_heel",
    "left_ankle",
    "right_ankle",
    "left_foot_index",
    "right_foot_index",
)

# Below this many usable frames on the best single camera, merge all cameras
# instead of restricting to one.
_MIN_USABLE_EVENT_FRAMES = 10

# Foot progression angle requires a lateral view where heel->toe pixel
# separation tracks direction of travel; posterior collapses that
# separation to noise (see _compute_mean_fpa).
_FPA_ALLOWED_CAMERAS = ("sagittal", "anterior")
# Normal human foot progression angle is roughly -20 to +20 deg; anything
# beyond this is a computation error, not a real gait finding.
_FPA_MAX_PLAUSIBLE_DEG = 45.0


def _lower_body_confidence(kf: KeypointFrame) -> float:
    """Max confidence among lower-body keypoints present in this frame (0.0 if none)."""
    confs = [
        kp.confidence
        for name in _LOWER_BODY_KEYPOINTS
        if (kp := kf.keypoints.get(name)) is not None
    ]
    return max(confs) if confs else 0.0


def _select_event_detection_frames(
    keypoint_frames: List[KeypointFrame],
) -> Tuple[List[KeypointFrame], str]:
    """Pick the camera with the most usable lower-body keypoint frames for
    event detection; merge all cameras if no single camera has enough.

    Returns (frames_to_use, camera_label) where camera_label is either the
    selected camera's name or "merged".
    """
    frames_by_camera: Dict[str, List[KeypointFrame]] = {}
    for kf in keypoint_frames:
        frames_by_camera.setdefault(kf.camera_view, []).append(kf)

    if not frames_by_camera:
        return keypoint_frames, "unknown"

    counts: Dict[str, int] = {
        cam: sum(1 for kf in frames if _lower_body_confidence(kf) > 0.0)
        for cam, frames in frames_by_camera.items()
    }

    best_camera = max(counts, key=counts.get)
    best_count = counts[best_camera]

    logger.info(
        "event_camera_selected",
        extra={"selected_camera": best_camera, "frame_counts": counts},
    )

    if best_count < _MIN_USABLE_EVENT_FRAMES:
        merged: Dict[int, KeypointFrame] = {}
        for kf in keypoint_frames:
            existing = merged.get(kf.frame_index)
            if existing is None or _lower_body_confidence(kf) > _lower_body_confidence(existing):
                merged[kf.frame_index] = kf
        merged_frames = sorted(merged.values(), key=lambda kf: kf.frame_index)

        logger.info(
            "event_camera_merged",
            extra={
                "reason": (
                    f"best camera '{best_camera}' had only {best_count} usable "
                    f"frames (< {_MIN_USABLE_EVENT_FRAMES})"
                ),
                "frame_counts": counts,
                "merged_frame_count": len(merged_frames),
            },
        )
        return merged_frames, "merged"

    return frames_by_camera[best_camera], best_camera


def _mean_ignore_none(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """Mean of two optional floats, ignoring whichever is None; None if both are."""
    vals = [v for v in (a, b) if v is not None]
    return sum(vals) / len(vals) if vals else None


def _select_frontal_view_frames(
    all_keypoint_frames: List[KeypointFrame],
) -> Tuple[List[KeypointFrame], str]:
    """Pick anterior or posterior camera frames for step-width measurement.

    Step width is a lateral (left/right) separation, which only a frontal
    (anterior or posterior) camera view can resolve â€” the sagittal/side view
    used for event detection can't. Picks whichever of the two frontal
    cameras has more frames with both left_heel and right_heel present.
    """
    best_frames: List[KeypointFrame] = []
    best_camera = "none"
    best_count = 0
    for cam in ("anterior", "posterior"):
        frames = [kf for kf in all_keypoint_frames if kf.camera_view == cam]
        count = sum(
            1
            for kf in frames
            if kf.keypoints.get("left_heel") is not None and kf.keypoints.get("right_heel") is not None
        )
        if count > best_count:
            best_frames, best_camera, best_count = frames, cam, count
    return best_frames, best_camera


def _compute_cadence_from_heel_strikes(hs_l: List, hs_r: List) -> Optional[float]:
    """Estimate cadence (steps/min) from heel-strike timing alone, without
    requiring a complete HS->TO->HS cycle on either foot.

    Combines both feet's heel-strike events (each strike = one step),
    orders them by timestamp, and averages the interval between consecutive
    strikes. Needs at least 2 heel strikes combined across both feet;
    returns None otherwise (left/right alone having 0-1 strikes each is not
    enough to estimate a rate).
    """
    all_hs = sorted(list(hs_l) + list(hs_r), key=lambda e: e.timestamp_ms)
    if len(all_hs) < 2:
        return None

    intervals_ms = [
        b.timestamp_ms - a.timestamp_ms
        for a, b in zip(all_hs, all_hs[1:])
        if b.timestamp_ms > a.timestamp_ms
    ]
    if not intervals_ms:
        return None

    mean_interval_ms = sum(intervals_ms) / len(intervals_ms)
    return 60_000.0 / mean_interval_ms


def _probe_video_quality(video_paths: Dict[str, Path], config: PipelineConfig) -> Dict[str, Any]:
    """Best-effort probe of raw upload duration/resolution for the results-page
    quality banner. Tries each camera in turn and never raises — a probe
    failure just means the banner has less information to work with, it must
    never block analysis.
    """
    from gait.ingestion.decode import VideoFileSource

    for cam, path in video_paths.items():
        src = VideoFileSource(path, cam, config.ingestion)
        try:
            src.open()
            frame_count = src.get_frame_count()
            fps = src.get_fps()
            width, height = src.get_resolution()
            duration_sec = (frame_count / fps) if fps and frame_count > 0 else None
            return {"duration_sec": duration_sec, "width": width, "height": height}
        except Exception as exc:
            logger.warning(
                "orchestrator.video_quality_probe_failed",
                extra={"camera": cam, "reason": str(exc)},
            )
            continue
        finally:
            src.close()
    return {"duration_sec": None, "width": None, "height": None}


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

        if self._cfg.development.verbose_logging:
            logging.getLogger("gait").setLevel(logging.DEBUG)
            for name in list(logging.root.manager.loggerDict.keys()):
                if name == "gait" or name.startswith("gait."):
                    logging.getLogger(name).setLevel(logging.DEBUG)
            logger.info("dev_flag.verbose_logging_enabled")

        if self._cfg.development.skip_gating_check:
            # Neutralise the cycle-count thresholds so
            # StandardBiomechanicalAnalyzer._quality_flag always sees
            # n_cycles >= target (0) and returns PROCEED_OK.
            logger.warning("dev_flag.skip_gating_check_enabled")
            self._cfg.analysis.min_clean_cycles_per_foot = 0
            self._cfg.analysis.target_clean_cycles_per_foot = 0

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

        # The static posterior photo isn't a walking video â€” it must not be
        # fed to ingestion/pose-per-frame processing (which expects a video
        # stream). Split it out here; it's routed separately to the rearfoot
        # alignment computation in _run_analysis.
        static_posterior_path = video_paths.get("static_posterior")
        walking_video_paths = {k: v for k, v in video_paths.items() if k != "static_posterior"}

        logger.info(
            "pipeline.start",
            extra={
                "patient_id": patient_id,
                "n_cameras": len(walking_video_paths),
                "has_static_posterior": static_posterior_path is not None,
            },
        )

        # â”€â”€ Stage 1: Ingestion â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        keypoint_frames = self._run_ingestion_and_pose(walking_video_paths)

        # â”€â”€ Stages 3â€“4: Events + Analysis â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        parameters, cadence_from_heel_strikes, session_params = self._run_analysis(
            keypoint_frames, anthropometrics, static_posterior_path=static_posterior_path
        )

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
                "cadence_from_heel_strikes_spm": cadence_from_heel_strikes,
                **session_params,
            },
            anthropometrics=anthropometrics,
            confidence_scores={"pipeline": 0.80},
        )

        # â”€â”€ Video quality metadata (for the results-page quality banner) â”€â”€â”€â”€â”€
        video_quality = _probe_video_quality(walking_video_paths, self._cfg)
        qm = profile.get("quality_metrics", {})
        cycle_counts = [qm.get("cycle_count_L", 0), qm.get("cycle_count_R", 0)]
        video_quality["is_low_quality"] = bool(
            (video_quality.get("duration_sec") is not None and video_quality["duration_sec"] < 5)
            or (
                video_quality.get("width") is not None
                and video_quality.get("height") is not None
                and min(video_quality["width"], video_quality["height"]) < 360
            )
            or any(c < 4 for c in cycle_counts)
        )
        profile["video_quality"] = video_quality

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
        self,
        keypoint_frames: List[KeypointFrame],
        anthropometrics: Dict[str, Any],
        static_posterior_path: Optional[Path] = None,
    ) -> Tuple[Dict[str, Dict[str, Any]], Optional[float], Dict[str, Any]]:
        """Stages 3â€“4: event detection + analysis.

        Returns ({L: agg_params, R: agg_params}, cadence_from_heel_strikes_spm,
        session_params). `session_params` holds the non-per-foot metrics
        (speed_mps, stride_length_m, step_width_m, double_support_pct) that
        builder.py reads directly off the top-level parameters dict.

        `static_posterior_path`, when given, routes rearfoot alignment through
        the static-photo method instead of the walking-video midstance
        estimate (falls back to the latter if the photo yields no usable
        pose).
        """
        from gait.analysis.parameters import (
            compute_double_support_pct,
            compute_step_lengths_lr,
            compute_step_width,
            estimate_scale_m_per_px,
        )

        # Event detection (heel-strike/toe-off via heel/toe y-trajectory peaks)
        # requires a single, geometrically consistent camera perspective â€”
        # mixing anterior/posterior/sagittal pixel coordinates into one
        # trajectory produces meaningless peaks. Rather than hardcoding
        # sagittal (which is often the worst camera for pose detection since
        # the subject is side-on and partially visible), pick whichever
        # camera actually produced the most usable lower-body keypoints; fall
        # back to a merged multi-camera set if none has enough data alone.
        # Keep the original multi-camera frame set too â€” step width needs the
        # anterior/posterior (frontal) view specifically, which the selected
        # event-detection camera may not be.
        all_keypoint_frames = keypoint_frames
        keypoint_frames, event_camera = _select_event_detection_frames(keypoint_frames)

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

        # â”€â”€ Camera scale calibration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        foot_length_mm_l = None
        raw_foot_length = anthropometrics.get("foot_length_mm")
        if isinstance(raw_foot_length, dict):
            foot_length_mm_l = raw_foot_length.get("L")
        elif isinstance(raw_foot_length, (int, float)):
            foot_length_mm_l = raw_foot_length
        height_cm = anthropometrics.get("height_cm")

        scale_m_per_px, scale_method, scale_n = estimate_scale_m_per_px(
            keypoint_frames,
            [e.frame_index for e in hs_l],
            foot_length_mm_l,
            height_cm,
        )
        if scale_method == "fallback_default":
            logger.warning(
                "scale_calibration_failed",
                extra={
                    "reason": "insufficient heel-strike or body-height keypoint data",
                    "fallback_scale_m_per_px": scale_m_per_px,
                },
            )
        logger.info(
            "scale_calibration_result",
            extra={
                "method": scale_method,
                "scale_m_per_px": scale_m_per_px,
                "n_measurements": scale_n,
            },
        )

        # Extract heel x-coordinates from heel strike frame indices
        heel_x_l = self._extract_heel_x_coords(keypoint_frames, hs_l, "left_heel")
        heel_x_r = self._extract_heel_x_coords(keypoint_frames, hs_r, "right_heel")

        # Compute step lengths (L and R) with the calibrated scale
        step_length_l, step_length_r = compute_step_lengths_lr(heel_x_l, heel_x_r, scale_m_per_px)
        stride_length_m: Optional[float] = None
        if step_length_l > 0.0 or step_length_r > 0.0:
            stride_length_m = (step_length_l + step_length_r) / 2.0

        # â”€â”€ Rearfoot alignment (posterior camera only) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        posterior_frames = [kf for kf in all_keypoint_frames if kf.camera_view == "posterior"]

        # â”€â”€ Rearfoot alignment method selection (static photo vs. walking video) â”€
        static_alignment_result: Optional[Dict[str, Optional[Dict[str, Any]]]] = None
        rearfoot_alignment_method = "walking_video_midstance"
        if static_posterior_path is not None:
            from gait.analysis.parameters import compute_rearfoot_alignment_from_image

            static_alignment_result = compute_rearfoot_alignment_from_image(
                str(static_posterior_path), model_path=self._cfg.pose.model_path
            )
            if static_alignment_result is not None:
                rearfoot_alignment_method = "static_image"

        logger.info(
            "rearfoot_alignment_method_selected",
            extra={
                "rearfoot_alignment_method": rearfoot_alignment_method,
                "static_posterior_provided": static_posterior_path is not None,
            },
        )

        # â”€â”€ Step width (needs the frontal/anterior-posterior view) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        frontal_frames, frontal_camera = _select_frontal_view_frames(all_keypoint_frames)
        step_width_m = compute_step_width(frontal_frames, scale_m_per_px)
        logger.info(
            "step_width_camera_selected",
            extra={
                "camera": frontal_camera,
                "n_frontal_frames": len(frontal_frames),
                "step_width_m": step_width_m,
            },
        )

        # Compute foot progression angles (mean per foot). Uses
        # all_keypoint_frames (every camera), not the possibly
        # event-detection-selected `keypoint_frames`, because FPA needs a
        # lateral view specifically and must not silently fall back to
        # whichever camera event detection happened to pick.
        fpa_l = self._compute_mean_fpa(all_keypoint_frames, hs_l, "left")
        fpa_r = self._compute_mean_fpa(all_keypoint_frames, hs_r, "right")

        result: Dict[str, Dict[str, Any]] = {}
        to_by_foot: Dict[str, List] = {}
        for foot in ("L", "R"):
            to = detector.detect_toe_offs(keypoint_frames, foot)
            to_by_foot[foot] = to
            hs = hs_l if foot == "L" else hs_r
            cycles: List[GaitCycle] = detector.segment_gait_cycles(
                keypoint_frames, hs, to, foot
            )
            cycles = assign_pass_ids(cycles, self._cfg.events.pass_gap_multiplier)
            cycles = discard_boundary_cycles(cycles)
            foot_static_alignment = (
                static_alignment_result.get(foot) if static_alignment_result is not None else None
            )
            agg_params = analyzer.aggregate_parameters(
                cycles,
                foot,
                posterior_frames=posterior_frames,
                static_alignment=foot_static_alignment,
            )

            # Raw event counts + partial-cycle flag, independent of whether a
            # cycle could be formed â€” lets the profile builder distinguish
            # "zero cycles because zero events were ever detected" from
            # "zero complete cycles but real partial data exists" (Fix D).
            agg_params["heel_strike_count"] = len(hs)
            agg_params["toe_off_count"] = len(to)
            agg_params["has_partial_cycle"] = any(
                c.quality_flag == "PARTIAL_CYCLE" for c in cycles
            )

            # Add global step length and foot progression angle metrics (only to L branch to avoid duplication)
            if foot == "L":
                agg_params["step_length_left_m"] = step_length_l
                agg_params["step_length_right_m"] = step_length_r
                agg_params["foot_progression_angle_left_deg"] = fpa_l
                agg_params["foot_progression_angle_right_deg"] = fpa_r

            result[foot] = agg_params

            logger.info(
                "rearfoot_alignment_result",
                extra={
                    "foot": foot,
                    "mean_deg": agg_params.get("rearfoot_alignment_angle_deg_mean"),
                    "std_deg": agg_params.get("rearfoot_alignment_angle_deg_std"),
                    "frame_count": agg_params.get("rearfoot_alignment_frame_count"),
                    "classification": agg_params.get("rearfoot_alignment_classification"),
                    "rearfoot_alignment_method": rearfoot_alignment_method,
                },
            )

        cadence_from_heel_strikes = _compute_cadence_from_heel_strikes(hs_l, hs_r)

        # â”€â”€ Speed: prefer real per-cycle cadence over the heel-strike estimate â”€â”€
        cadence_l = result["L"].get("cadence_steps_per_min_mean")
        cadence_r = result["R"].get("cadence_steps_per_min_mean")
        if cadence_l is not None or cadence_r is not None:
            cadence_for_speed = _mean_ignore_none(cadence_l, cadence_r)
        else:
            cadence_for_speed = cadence_from_heel_strikes

        speed_mps: Optional[float] = None
        if stride_length_m is not None and cadence_for_speed is not None:
            speed_mps = (stride_length_m * cadence_for_speed / 60.0) / 2.0

        # â”€â”€ Double support â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        stride_time_ms = result["L"].get("gait_cycle_time_ms_mean") or result["R"].get(
            "gait_cycle_time_ms_mean"
        )
        double_support_pct = compute_double_support_pct(hs_l, hs_r, stride_time_ms)
        if double_support_pct is None:
            swing_pct_l = result["L"].get("swing_pct_mean")
            if swing_pct_l is not None:
                double_support_pct = 100.0 - swing_pct_l

        session_params: Dict[str, Any] = {
            "speed_mps": speed_mps,
            "stride_length_m": stride_length_m,
            "step_width_m": step_width_m,
            "double_support_pct": double_support_pct,
            "rearfoot_alignment_method": rearfoot_alignment_method,
        }

        peak_debug = detector.get_peak_debug_summary()
        logger.info(
            "event_detection_summary",
            extra={
                "event_camera": event_camera,
                "trajectory_frame_count": len(keypoint_frames),
                "heel_strikes_L": len(hs_l),
                "heel_strikes_R": len(hs_r),
                "toe_offs_L": len(to_by_foot["L"]),
                "toe_offs_R": len(to_by_foot["R"]),
                "heel_strike_threshold": self._cfg.events.heel_strike_threshold,
                "toe_off_threshold": self._cfg.events.toe_off_threshold,
                "cadence_from_heel_strikes_spm": cadence_from_heel_strikes,
                "speed_mps": speed_mps,
                "stride_length_m": stride_length_m,
                "step_width_m": step_width_m,
                "double_support_pct": double_support_pct,
                "peak_debug": peak_debug,
            },
        )

        return result, cadence_from_heel_strikes, session_params

    def _extract_heel_x_coords(
        self, keypoint_frames: List[KeypointFrame], heel_strikes: List, heel_name: str
    ) -> list[float]:
        """Extract heel x-coordinates from heel strike events."""
        # frame_index is the original ingestion frame number, not this list's
        # position (frames are dropped whenever pose detection fails, and this
        # list may already be event-camera-filtered/merged) â€” look up by the
        # real index rather than treating it as a position.
        kf_by_index = {kf.frame_index: kf for kf in keypoint_frames}
        coords = []
        for event in heel_strikes:
            frame = kf_by_index.get(event.frame_index)
            if frame is not None:
                heel_kp = frame.keypoints.get(heel_name)
                if heel_kp:
                    coords.append(heel_kp.x)
        return coords

    def _extract_keypoint_positions(
        self, keypoint_frames: List[KeypointFrame], events: List, kp_name: str
    ) -> list[tuple[float, float]]:
        """Extract keypoint (x, y) positions from frame events."""
        kf_by_index = {kf.frame_index: kf for kf in keypoint_frames}
        positions = []
        for event in events:
            frame = kf_by_index.get(event.frame_index)
            if frame is not None:
                kp = frame.keypoints.get(kp_name)
                if kp:
                    positions.append((kp.x, kp.y))
        return positions

    def _compute_mean_fpa(
        self, keypoint_frames: List[KeypointFrame], heel_strikes: List, foot: str
    ) -> Optional[float]:
        """Compute mean foot progression angle across heel strikes.

        Foot progression angle needs a lateral view (sagittal or anterior),
        where heel->toe pixel separation actually tracks the direction of
        travel. A posterior camera (person walking directly away) collapses
        that separation to near-zero landmark noise and produces
        meaningless angles, so posterior-camera frames are excluded here
        regardless of which camera event detection used. Restricted to
        whichever of sagittal/anterior has the most usable frames, rather
        than merging both, to avoid mixing two different camera geometries
        into one average.

        Returns None (not 0.0) when no lateral-camera data is available, or
        when the resulting mean is outside the physiologically plausible
        range — a null result is safer than a fabricated placeholder.
        """
        from gait.analysis.parameters import compute_foot_progression_angle

        frames_by_camera: Dict[str, List[KeypointFrame]] = {}
        for kf in keypoint_frames:
            if kf.camera_view in _FPA_ALLOWED_CAMERAS:
                frames_by_camera.setdefault(kf.camera_view, []).append(kf)

        camera_used: Optional[str] = None
        kf_by_index: Dict[int, KeypointFrame] = {}
        if frames_by_camera:
            camera_used = max(frames_by_camera, key=lambda cam: len(frames_by_camera[cam]))
            kf_by_index = {kf.frame_index: kf for kf in frames_by_camera[camera_used]}

        angles = []
        for event in heel_strikes:
            frame = kf_by_index.get(event.frame_index)
            if frame is not None:
                heel_kp = frame.keypoints.get(f"{foot}_heel")
                toe_kp = frame.keypoints.get(f"{foot}_foot_index")
                if heel_kp and toe_kp:
                    angle = compute_foot_progression_angle(heel_kp, toe_kp)
                    angles.append(angle)

        logger.info(
            "foot_progression_angle_camera_used",
            extra={"foot": foot, "camera_used": camera_used, "n_frames_used": len(angles)},
        )

        if not angles:
            return None

        mean_angle = sum(angles) / len(angles)
        if abs(mean_angle) > _FPA_MAX_PLAUSIBLE_DEG:
            logger.warning(
                "foot_progression_angle_unreliable",
                extra={
                    "foot": foot,
                    "mean_angle_deg": mean_angle,
                    "camera_used": camera_used,
                    "n_frames_used": len(angles),
                },
            )
            return None

        return mean_angle


def create_pipeline(config: Optional[PipelineConfig] = None) -> GaitPipeline:
    """Factory: return a GaitPipeline instance."""
    return GaitPipeline(config)

