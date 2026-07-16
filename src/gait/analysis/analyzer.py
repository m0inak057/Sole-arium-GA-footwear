"""StandardBiomechanicalAnalyzer â€” orchestrates per-cycle parameter computation."""
from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional

import numpy as np

from gait.analysis.parameters import (
    classify_arch,
    classify_foot_strike,
    classify_pronation,
    compute_arch_height_index,
    compute_foot_progression_angle,
    compute_foot_strike_angle,
    compute_frontal_plane_excursion,
    compute_rearfoot_alignment_angle,
    compute_rearfoot_angle,
    compute_spatiotemporal,
    compute_step_length,
    compute_symmetry_index,
)
from gait.common.interfaces import BiomechanicalAnalyzer, GaitCycle, KeypointFrame
from gait.common.logging_utils import get_logger
from gait.pipeline.config import AnalysisConfig

logger = get_logger(__name__)


class StandardBiomechanicalAnalyzer(BiomechanicalAnalyzer):
    """Computes all biomechanical parameters for gait cycles from keypoint data.

    `compute_parameters(cycle)` â€” one cycle at a time, returns a flat dict.
    `aggregate_parameters(cycles, foot)` â€” mean/std over a session, + quality flag.
    """

    def __init__(
        self,
        config: AnalysisConfig,
        fps: float = 120.0,
        joint_angle_offsets: Optional[Dict[str, float]] = None,
    ) -> None:
        self._cfg = config
        self._fps = fps
        self._offsets: Dict[str, float] = joint_angle_offsets or {}

    # â”€â”€ BiomechanicalAnalyzer ABC â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def compute_parameters(self, cycle: GaitCycle) -> Dict[str, Any]:
        """Compute spatiotemporal, foot-strike, pronation, and arch parameters.

        Optional parameters (those requiring specific keypoints) are omitted
        from the returned dict when keypoints are absent, rather than
        returning None values.
        """
        side = "left" if cycle.foot == "L" else "right"
        params: Dict[str, Any] = {}

        # â”€â”€ Metadata â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        params["foot"] = cycle.foot
        params["cycle_id"] = cycle.cycle_id
        params["cycle_confidence"] = cycle.confidence

        # â”€â”€ Spatiotemporal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        params.update(compute_spatiotemporal(cycle, self._fps))

        # â”€â”€ Keypoints at heel-strike frame â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        hs_kps = cycle.keypoints.get(cycle.frame_start, {})
        heel_hs = hs_kps.get(f"{side}_heel")
        toe_hs = hs_kps.get(f"{side}_foot_index")
        ankle_hs = hs_kps.get(f"{side}_ankle")

        if heel_hs:
            params["heel_strike_x_px"] = heel_hs.x

        if heel_hs and toe_hs:
            fsa = compute_foot_strike_angle(heel_hs, toe_hs)
            params["foot_strike_angle_deg"] = fsa
            params["foot_strike_type"] = classify_foot_strike(fsa, self._cfg)
            params["foot_progression_angle_deg"] = compute_foot_progression_angle(heel_hs, toe_hs)

        if heel_hs and toe_hs and ankle_hs:
            ahi = compute_arch_height_index(heel_hs, toe_hs, ankle_hs)
            if ahi is not None:
                params["arch_height_index"] = ahi
                params["arch_type"] = classify_arch(ahi, self._cfg)

        # â”€â”€ Keypoints at midstance â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        mid_frame = (cycle.frame_start + cycle.frame_end) // 2
        mid_kps = self._nearest_keypoints(cycle, mid_frame)
        knee_mid = mid_kps.get(f"{side}_knee")
        ankle_mid = mid_kps.get(f"{side}_ankle")
        heel_mid = mid_kps.get(f"{side}_heel")

        if knee_mid and ankle_mid and heel_mid:
            rfa = compute_rearfoot_angle(knee_mid, ankle_mid, heel_mid)
            # Clinical sign convention: positive = eversion/pronation.
            # Right foot eversion = heel tilts left (âˆ’x) â†’ raw angle is negative â†’ negate.
            if cycle.foot == "R":
                rfa = -rfa
            # Subtract anatomical zero from static calibration trial so the
            # dynamic angle is relative to the subject's own neutral posture.
            rfa -= self._offsets.get(f"{side}_ankle_deg", 0.0)
            params["rearfoot_angle_deg"] = rfa
            params["pronation_type"] = classify_pronation(rfa, self._cfg)

        # â”€â”€ Frontal-plane excursion across all stance frames â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        stance_angles: List[float] = []
        for frame, kps in cycle.keypoints.items():
            if not (cycle.frame_start <= frame <= cycle.frame_end):
                continue
            k = kps.get(f"{side}_knee")
            a = kps.get(f"{side}_ankle")
            h = kps.get(f"{side}_heel")
            if k and a and h:
                rfa_frame = compute_rearfoot_angle(k, a, h)
                if cycle.foot == "R":
                    rfa_frame = -rfa_frame
                stance_angles.append(rfa_frame)
        if stance_angles:
            params["frontal_plane_excursion_deg"] = compute_frontal_plane_excursion(stance_angles)

        return params

    def aggregate_parameters(
        self,
        cycles: List[GaitCycle],
        foot: str,
        posterior_frames: Optional[List[KeypointFrame]] = None,
    ) -> Dict[str, Any]:
        """Aggregate per-cycle parameters across all cycles for one foot.

        Numeric parameters â†’ mean and std.
        Classification parameters â†’ statistical mode.
        Includes cycle_count and quality_flag.

        `posterior_frames`, when supplied, are used to additionally compute
        the clinical rearfoot alignment angle (posterior-camera-only metric,
        independent of the sagittal-camera rearfoot_angle already above).
        """
        if not cycles:
            return {"foot": foot, "cycle_count": 0, "quality_flag": "RERECORD"}

        all_params = [self.compute_parameters(c) for c in cycles]
        agg: Dict[str, Any] = {"foot": foot, "cycle_count": len(cycles)}

        # Numeric aggregation (exclude non-metric metadata fields)
        _meta = {"foot", "cycle_id"}
        numeric_keys = sorted({
            k
            for p in all_params
            for k, v in p.items()
            if isinstance(v, (int, float)) and k not in _meta
        })
        for key in numeric_keys:
            values = [p[key] for p in all_params if key in p and isinstance(p[key], (int, float))]
            if values:
                agg[f"{key}_mean"] = float(np.mean(values))
                agg[f"{key}_std"] = float(np.std(values))

        # Classification mode
        for key in ("foot_strike_type", "arch_type", "pronation_type"):
            vals = [p[key] for p in all_params if key in p]
            if vals:
                agg[key] = statistics.mode(vals)

        if posterior_frames:
            alignment = compute_rearfoot_alignment_angle(posterior_frames, foot, cycles)
            agg["rearfoot_alignment_angle_deg_mean"] = alignment["mean_deg"]
            agg["rearfoot_alignment_angle_deg_std"] = alignment["std_deg"]
            agg["rearfoot_alignment_frame_count"] = alignment["frame_count"]
            agg["rearfoot_alignment_classification"] = alignment["classification"]

        agg["quality_flag"] = _quality_flag(len(cycles), self._cfg)
        return agg

    def compute_step_lengths(
        self,
        l_cycles: List[GaitCycle],
        r_cycles: List[GaitCycle],
        scale_m_per_px: float,
    ) -> Dict[str, float]:
        """Compute mean step length (metres) for each foot across a session.

        Step length = distance between this foot's heel-strike x and the
        contralateral foot's mean heel-strike x, scaled by camera calibration.

        Returns:
            {"L": <step_length_m>, "R": <step_length_m>}
            Missing values default to 0.0 when heel keypoints are unavailable.
        """
        def _mean_heel_x(cycles: List[GaitCycle]) -> Optional[float]:
            xs = []
            for c in cycles:
                side = "left" if c.foot == "L" else "right"
                hs_kps = c.keypoints.get(c.frame_start, {})
                heel = hs_kps.get(f"{side}_heel")
                if heel is not None:
                    xs.append(heel.x)
            return float(np.mean(xs)) if xs else None

        l_x = _mean_heel_x(l_cycles)
        r_x = _mean_heel_x(r_cycles)

        result: Dict[str, float] = {}
        if l_x is not None and r_x is not None:
            result["L"] = compute_step_length(l_x, r_x, scale_m_per_px)
            result["R"] = compute_step_length(r_x, l_x, scale_m_per_px)
        else:
            result["L"] = 0.0
            result["R"] = 0.0
        return result

    # â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _nearest_keypoints(self, cycle: GaitCycle, target_frame: int) -> Dict:
        """Return keypoints from the cycle frame nearest to target_frame."""
        if not cycle.keypoints:
            return {}
        best = min(cycle.keypoints.keys(), key=lambda f: abs(f - target_frame))
        return cycle.keypoints[best]


def _quality_flag(n_cycles: int, cfg: AnalysisConfig) -> str:
    if n_cycles >= cfg.target_clean_cycles_per_foot:
        return "PROCEED_OK"
    if n_cycles >= cfg.min_clean_cycles_per_foot:
        return "PROCEED_WITH_WARNING"
    return "RERECORD"


def create_biomechanical_analyzer(
    config: AnalysisConfig,
    fps: float = 120.0,
    joint_angle_offsets: Optional[Dict[str, float]] = None,
) -> StandardBiomechanicalAnalyzer:
    """Factory: return the standard biomechanical analyzer."""
    return StandardBiomechanicalAnalyzer(config, fps=fps, joint_angle_offsets=joint_angle_offsets)

