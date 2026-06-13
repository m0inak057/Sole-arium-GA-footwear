"""StandardBiomechanicalAnalyzer — orchestrates per-cycle parameter computation."""
from __future__ import annotations

import statistics
from typing import Any, Dict, List

import numpy as np

from src.gait.analysis.parameters import (
    classify_arch,
    classify_foot_strike,
    classify_pronation,
    compute_arch_height_index,
    compute_foot_strike_angle,
    compute_rearfoot_angle,
    compute_spatiotemporal,
    compute_symmetry_index,
)
from src.gait.common.interfaces import BiomechanicalAnalyzer, GaitCycle
from src.gait.common.logging_utils import get_logger
from src.gait.pipeline.config import AnalysisConfig

logger = get_logger(__name__)


class StandardBiomechanicalAnalyzer(BiomechanicalAnalyzer):
    """Computes all biomechanical parameters for gait cycles from keypoint data.

    `compute_parameters(cycle)` — one cycle at a time, returns a flat dict.
    `aggregate_parameters(cycles, foot)` — mean/std over a session, + quality flag.
    """

    def __init__(self, config: AnalysisConfig, fps: float = 120.0) -> None:
        self._cfg = config
        self._fps = fps

    # ── BiomechanicalAnalyzer ABC ──────────────────────────────────────────

    def compute_parameters(self, cycle: GaitCycle) -> Dict[str, Any]:
        """Compute spatiotemporal, foot-strike, pronation, and arch parameters.

        Optional parameters (those requiring specific keypoints) are omitted
        from the returned dict when keypoints are absent, rather than
        returning None values.
        """
        side = "left" if cycle.foot == "L" else "right"
        params: Dict[str, Any] = {}

        # ── Metadata ──────────────────────────────────────────────────────
        params["foot"] = cycle.foot
        params["cycle_id"] = cycle.cycle_id
        params["cycle_confidence"] = cycle.confidence

        # ── Spatiotemporal ─────────────────────────────────────────────────
        params.update(compute_spatiotemporal(cycle, self._fps))

        # ── Keypoints at heel-strike frame ─────────────────────────────────
        hs_kps = cycle.keypoints.get(cycle.frame_start, {})
        heel_hs = hs_kps.get(f"{side}_heel")
        toe_hs = hs_kps.get(f"{side}_foot_index")
        ankle_hs = hs_kps.get(f"{side}_ankle")

        if heel_hs and toe_hs:
            fsa = compute_foot_strike_angle(heel_hs, toe_hs)
            params["foot_strike_angle_deg"] = fsa
            params["foot_strike_type"] = classify_foot_strike(fsa, self._cfg)

        if heel_hs and toe_hs and ankle_hs:
            ahi = compute_arch_height_index(heel_hs, toe_hs, ankle_hs)
            if ahi is not None:
                params["arch_height_index"] = ahi
                params["arch_type"] = classify_arch(ahi, self._cfg)

        # ── Keypoints at midstance ─────────────────────────────────────────
        mid_frame = (cycle.frame_start + cycle.frame_end) // 2
        mid_kps = self._nearest_keypoints(cycle, mid_frame)
        knee_mid = mid_kps.get(f"{side}_knee")
        ankle_mid = mid_kps.get(f"{side}_ankle")
        heel_mid = mid_kps.get(f"{side}_heel")

        if knee_mid and ankle_mid and heel_mid:
            rfa = compute_rearfoot_angle(knee_mid, ankle_mid, heel_mid)
            # Clinical sign convention: positive = eversion/pronation.
            # Right foot eversion = heel tilts left (−x) → raw angle is negative → negate.
            if cycle.foot == "R":
                rfa = -rfa
            params["rearfoot_angle_deg"] = rfa
            params["pronation_type"] = classify_pronation(rfa, self._cfg)

        return params

    def aggregate_parameters(
        self, cycles: List[GaitCycle], foot: str
    ) -> Dict[str, Any]:
        """Aggregate per-cycle parameters across all cycles for one foot.

        Numeric parameters → mean and std.
        Classification parameters → statistical mode.
        Includes cycle_count and quality_flag.
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

        agg["quality_flag"] = _quality_flag(len(cycles), self._cfg)
        return agg

    # ── helpers ────────────────────────────────────────────────────────────

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
    config: AnalysisConfig, fps: float = 120.0
) -> StandardBiomechanicalAnalyzer:
    """Factory: return the standard biomechanical analyzer."""
    return StandardBiomechanicalAnalyzer(config, fps=fps)
