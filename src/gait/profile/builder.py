"""StandardProfileBuilder — assembles GaitPatientProfile from aggregated parameters.

The builder:
  1. Extracts L/R aggregated parameters from the parameters dict.
  2. Computes symmetry flags.
  3. Derives a combined classification for rule-engine condition matching.
  4. Runs the RuleBasedRecommendationEngine to produce shoe recommendations.
  5. Assembles and validates the GaitPatientProfile dict.

Expected structure for `parameters` arg to `build()`:
    {
        "L": {<aggregated params from StandardBiomechanicalAnalyzer>},
        "R": {<aggregated params from StandardBiomechanicalAnalyzer>},
        # optional extra fields:
        "speed_mps": float,
        "stride_length_m": float,
        "step_width_m": float,
        "double_support_pct": float,
        "time_to_peak_eversion_pct_L": float,
        "time_to_peak_eversion_pct_R": float,
        "age_years": float,
        "flags": list[str],          # additional rule flags (pathological_gait, etc.)
        "eversion_peak_early": bool,
    }
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from src.gait.common.interfaces import ProfileBuilder, RecommendationEngine
from src.gait.common.logging_utils import get_logger
from src.gait.pipeline.config import AnalysisConfig, RecommendationRulesConfig
from src.gait.profile.rules_engine import RuleBasedRecommendationEngine, create_recommendation_engine

logger = get_logger(__name__)

# ── pronation severity (higher = more pronated; used to pick dominant foot) ───

_PRONATION_RANK: Dict[str, int] = {
    "overpronation": 5,
    "mild_pronation": 4,
    "neutral": 3,
    "mild_supination": 2,
    "oversupination": 1,
}


# ── helpers ───────────────────────────────────────────────────────────────────


def _mean_of(a: Optional[float], b: Optional[float]) -> float:
    """Mean of two optional floats; falls back to whichever is not None."""
    if a is None and b is None:
        return 0.0
    if a is None:
        return float(b)  # type: ignore[arg-type]
    if b is None:
        return float(a)
    return (a + b) / 2.0


def _compute_symmetry_flags(
    params_l: Dict[str, Any],
    params_r: Dict[str, Any],
    threshold_pct: float,
) -> List[str]:
    """Compute per-parameter symmetry indices; flag those above threshold_pct.

    Appends "high_asymmetry" once (at most) when any parameter asymmetry fires.
    This flag is recognised by Rule 7 in rules.yaml.
    """
    pairs = [
        ("cadence_steps_per_min_mean", "cadence"),
        ("stance_pct_mean", "stance_pct"),
        ("foot_strike_angle_deg_mean", "foot_strike_angle"),
        ("rearfoot_angle_deg_mean", "rearfoot_angle"),
    ]
    flags: List[str] = []
    has_high_asymmetry = False

    for key, label in pairs:
        l_val = params_l.get(key)
        r_val = params_r.get(key)
        if l_val is None or r_val is None:
            continue
        mean = abs((l_val + r_val) / 2.0)
        if mean < 1e-9:
            continue
        si = abs(l_val - r_val) / mean * 100.0
        if si > threshold_pct:
            flags.append(f"{label}_asymmetric_{si:.0f}pct")
            has_high_asymmetry = True

    if has_high_asymmetry:
        flags.append("high_asymmetry")

    return flags


def _derive_rule_parameters(
    params_l: Dict[str, Any],
    params_r: Dict[str, Any],
    extra: Dict[str, Any],
) -> Dict[str, Any]:
    """Return a flat dict for rule-condition matching.

    The dominant foot (more pronated) provides pronation/arch/foot-strike
    classifications.  Extra flags from the caller are merged in.
    """
    pron_l = params_l.get("pronation_type", "neutral")
    pron_r = params_r.get("pronation_type", "neutral")

    if _PRONATION_RANK.get(pron_l, 3) >= _PRONATION_RANK.get(pron_r, 3):
        dominant = params_l
    else:
        dominant = params_r

    combined: Dict[str, Any] = {
        "pronation_type": dominant.get("pronation_type", "neutral"),
        "arch_type": dominant.get("arch_type", "normal"),
        "foot_strike_type": dominant.get("foot_strike_type", "rearfoot"),
    }
    combined.update(extra)
    return combined


# ── builder ───────────────────────────────────────────────────────────────────


class StandardProfileBuilder(ProfileBuilder):
    """Assembles a GaitPatientProfile dict from aggregated gait parameters."""

    def __init__(
        self,
        rules_engine: RecommendationEngine,
        analysis_config: AnalysisConfig,
    ) -> None:
        self._rules_engine = rules_engine
        self._cfg = analysis_config

    # ── ProfileBuilder ABC ─────────────────────────────────────────────────

    def build(
        self,
        patient_id: str,
        session_timestamp: str,
        parameters: Dict[str, Any],
        anthropometrics: Dict[str, Any],
        confidence_scores: Dict[str, float],
    ) -> Dict[str, Any]:
        """Assemble and return a profile dict matching GaitPatientProfile schema.

        Missing spatiotemporal fields that require external video metadata
        (speed, stride length, step width, double support) default to 0.0 and
        are recorded in quality_metrics for downstream review.
        """
        params_l: Dict[str, Any] = parameters.get("L", {})
        params_r: Dict[str, Any] = parameters.get("R", {})

        # ── symmetry flags ─────────────────────────────────────────────────
        symmetry_flags = _compute_symmetry_flags(
            params_l, params_r, self._cfg.symmetry_flag_threshold_pct
        )

        # ── combined parameters for rule-condition matching ────────────────
        extra_flags = list(symmetry_flags) + list(parameters.get("flags", []))
        rule_params = _derive_rule_parameters(
            params_l,
            params_r,
            {
                "flags": extra_flags,
                "age_years": parameters.get("age_years"),
                "eversion_peak_early": parameters.get("eversion_peak_early", False),
            },
        )

        # ── shoe recommendations (rules engine) ────────────────────────────
        recs = self._rules_engine.generate_recommendations(rule_params, patient_id)
        needs_human_review = bool(recs.pop("needs_human_review", False))

        # ── spatiotemporal ─────────────────────────────────────────────────
        cadence = _mean_of(
            params_l.get("cadence_steps_per_min_mean"),
            params_r.get("cadence_steps_per_min_mean"),
        )
        spatiotemporal = {
            "cadence_spm": cadence,
            "speed_mps": parameters.get("speed_mps", 0.0),
            "stride_length_m": parameters.get("stride_length_m", 0.0),
            "step_width_m": parameters.get("step_width_m", 0.0),
            "stance_pct": {
                "L": params_l.get("stance_pct_mean", 60.0),
                "R": params_r.get("stance_pct_mean", 60.0),
            },
            "double_support_pct": parameters.get("double_support_pct", 0.0),
            "swing_pct": {
                "L": params_l.get("swing_pct_mean", 40.0),
                "R": params_r.get("swing_pct_mean", 40.0),
            },
        }

        # ── foot strike ────────────────────────────────────────────────────
        foot_strike = {
            "pattern": {
                "L": params_l.get("foot_strike_type", "rearfoot"),
                "R": params_r.get("foot_strike_type", "rearfoot"),
            },
            "foot_strike_angle_deg": {
                "L": params_l.get("foot_strike_angle_deg_mean", 0.0),
                "R": params_r.get("foot_strike_angle_deg_mean", 0.0),
            },
        }

        # ── pronation ──────────────────────────────────────────────────────
        pronation = {
            "rearfoot_angle_at_midstance_deg": {
                "L": params_l.get("rearfoot_angle_deg_mean", 0.0),
                "R": params_r.get("rearfoot_angle_deg_mean", 0.0),
            },
            "classification": {
                "L": params_l.get("pronation_type", "neutral"),
                "R": params_r.get("pronation_type", "neutral"),
            },
            # time_to_peak_eversion not computed in Phase 1; placeholder
            "time_to_peak_eversion_pct_stance": {
                "L": parameters.get("time_to_peak_eversion_pct_L", 40.0),
                "R": parameters.get("time_to_peak_eversion_pct_R", 40.0),
            },
        }

        # ── arch ───────────────────────────────────────────────────────────
        arch = {
            "type": {
                "L": params_l.get("arch_type", "normal"),
                "R": params_r.get("arch_type", "normal"),
            },
            "arch_height_index": {
                "L": params_l.get("arch_height_index_mean", 0.25),
                "R": params_r.get("arch_height_index_mean", 0.25),
            },
        }

        # ── quality metrics (internal; not for shoe-design) ────────────────
        qf_l = params_l.get("quality_flag", "RERECORD")
        qf_r = params_r.get("quality_flag", "RERECORD")
        if qf_l == "RERECORD" or qf_r == "RERECORD":
            needs_human_review = True

        quality_metrics = {
            "quality_flag_L": qf_l,
            "quality_flag_R": qf_r,
            "cycle_count_L": params_l.get("cycle_count", 0),
            "cycle_count_R": params_r.get("cycle_count", 0),
            "phase1_placeholder_fields": [
                "speed_mps",
                "stride_length_m",
                "step_width_m",
                "double_support_pct",
                "time_to_peak_eversion_pct_stance",
            ],
        }

        # ── shoe recommendations ───────────────────────────────────────────
        shoe_design = {
            "medial_post": recs.get("medial_post", "none"),
            "post_density": recs.get("post_density"),
            "arch_support": recs.get("arch_support", "medium"),
            "heel_counter": recs.get("heel_counter", "semi_rigid"),
            "heel_drop_mm": recs.get("heel_drop_mm", 8.0),
            "last_shape": recs.get("last_shape", "semi_curved"),
            "cushioning_zone_priority": recs.get("cushioning_zone_priority"),
            "notes": recs.get("notes"),
        }

        profile: Dict[str, Any] = {
            "schema_version": "profile/v1",
            "patient_id": patient_id,
            "session_timestamp": session_timestamp,
            "anthropometrics": anthropometrics,
            "spatiotemporal": spatiotemporal,
            "foot_strike": foot_strike,
            "pronation": pronation,
            "arch": arch,
            "symmetry_flags": symmetry_flags,
            "shoe_design_recommendations": shoe_design,
            "confidence_scores": confidence_scores,
            "needs_human_review": needs_human_review,
            "quality_metrics": quality_metrics,
        }

        logger.info(
            "profile.built",
            extra={
                "patient_id": patient_id,
                "quality_flag_L": qf_l,
                "quality_flag_R": qf_r,
                "needs_human_review": needs_human_review,
                "n_symmetry_flags": len(symmetry_flags),
            },
        )
        return profile

    def validate(self, profile: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate profile dict against GaitPatientProfile Pydantic schema.

        Returns (True, []) on success; (False, [error_str, ...]) on failure.
        """
        from src.gait.profile.schema import GaitPatientProfile

        try:
            GaitPatientProfile(**profile)
            return True, []
        except ValidationError as exc:
            errors = [f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in exc.errors()]
            return False, errors
        except Exception as exc:  # pragma: no cover
            return False, [str(exc)]


# ── factory ───────────────────────────────────────────────────────────────────


def create_profile_builder(
    rules_config: RecommendationRulesConfig,
    analysis_config: AnalysisConfig,
) -> StandardProfileBuilder:
    """Factory: create a StandardProfileBuilder wired with a RuleBasedRecommendationEngine."""
    engine = create_recommendation_engine(rules_config)
    return StandardProfileBuilder(engine, analysis_config)
