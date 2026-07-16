"""StandardProfileBuilder â€” assembles GaitPatientProfile from aggregated parameters.

The builder:
  1. Extracts L/R aggregated parameters from the parameters dict.
  2. Computes symmetry flags.
  3. Derives a combined classification for rule-engine condition matching.
  4. Runs the RuleBasedRecommendationEngine to produce health assessment.
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

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from gait.common.interfaces import ProfileBuilder, RecommendationEngine
from gait.common.logging_utils import get_logger
from gait.pipeline.config import AnalysisConfig, RecommendationRulesConfig
from gait.profile.rules_engine import RuleBasedRecommendationEngine, create_recommendation_engine

logger = get_logger(__name__)

# Population-average placeholders used when a foot has zero usable gait
# cycles. These let the pipeline still produce a profile instead of
# aborting; every metric filled from here is tagged low-confidence via
# quality_flag/is_placeholder so the frontend can warn the clinician.
_POPULATION_AVERAGE_DEFAULTS: Dict[str, Any] = {
    "cadence_steps_per_min_mean": 110.0,
    "stance_pct_mean": 60.0,
    "swing_pct_mean": 40.0,
    "foot_strike_angle_deg_mean": 0.0,
    "rearfoot_angle_deg_mean": 2.0,
    "frontal_plane_excursion_deg_mean": 6.0,
    "arch_height_index_mean": 0.25,
    "foot_strike_type": "rearfoot",
    "arch_type": "normal",
    "pronation_type": "neutral",
    "step_length_left_m": 0.6,
    "step_length_right_m": 0.6,
    "foot_progression_angle_left_deg": 5.0,
    "foot_progression_angle_right_deg": 5.0,
}

# â”€â”€ pronation severity (higher = more pronated; used to pick dominant foot) â”€â”€â”€

_PRONATION_RANK: Dict[str, int] = {
    "overpronation": 5,
    "mild_pronation": 4,
    "neutral": 3,
    "mild_supination": 2,
    "oversupination": 1,
}


# â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


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
        "rearfoot_alignment_classification": dominant.get("rearfoot_alignment_classification"),
    }
    combined.update(extra)
    return combined


# â”€â”€ builder â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class StandardProfileBuilder(ProfileBuilder):
    """Assembles a GaitPatientProfile dict from aggregated gait parameters."""

    def __init__(
        self,
        rules_engine: RecommendationEngine,
        analysis_config: AnalysisConfig,
        health_coach: Optional[Any] = None,
        rules_config: Optional[RecommendationRulesConfig] = None,
    ) -> None:
        self._rules_engine = rules_engine
        self._cfg = analysis_config
        self._health_coach = health_coach
        self._rules_config = rules_config

    # â”€â”€ agent integration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _generate_health_assessment(
        self,
        rule_params: Dict[str, Any],
        patient_id: str,
        params_l: Dict[str, Any],
        params_r: Dict[str, Any],
        parameters: Dict[str, Any],
    ) -> tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """Generate health assessment via agent (with fallback) and log the decision.

        Returns:
            (health_data_dict, agent_decisions_log)
        """
        agent_decisions = None

        if self._health_coach is None:
            # No agent configured; use static rules only
            health_data = self._rules_engine.generate_recommendations(rule_params, patient_id)
            return health_data, None

        # Build agent parameters from biomechanical metrics
        agent_params = self._build_agent_parameters(params_l, params_r, parameters)

        # Try the agent
        assessment, confidence, reasoning = self._health_coach.predict(agent_params)

        # Log decision
        timestamp = datetime.now(timezone.utc).isoformat()

        if assessment is None:
            # Agent failed validation; use static rules and log failure
            health_data = self._rules_engine.generate_recommendations(rule_params, patient_id)
            agent_decisions = {
                "timestamp": timestamp,
                "method_used": "static_rules",
                "fallback_reason": reasoning,
                "confidence_score": confidence,
                "raw_llm_response": agent_params.get("_raw_llm_response"),
            }
            logger.info(
                "health_assessment.agent_failed_fallback",
                extra={
                    "patient_id": patient_id,
                    "fallback_reason": reasoning,
                },
            )
        else:
            # Agent succeeded; use its output
            health_data = {
                "what_went_right": assessment.what_went_right,
                "defects_found": [d.dict() for d in assessment.defects_found],
                "improvements": [i.dict() for i in assessment.improvement_plan],
                "needs_human_review": False,
            }
            agent_decisions = {
                "timestamp": timestamp,
                "method_used": "agent",
                "confidence_score": confidence,
                "reasoning": reasoning,
            }
            logger.info(
                "health_assessment.agent_success",
                extra={
                    "patient_id": patient_id,
                    "confidence": confidence,
                    "n_defects": len(assessment.defects_found),
                },
            )

        return health_data, agent_decisions

    def _build_agent_parameters(
        self,
        params_l: Dict[str, Any],
        params_r: Dict[str, Any],
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build agent input parameters from biomechanical metrics."""
        return {
            # Spatiotemporal
            "step_length_left_m": params_l.get("step_length_left_m", 0.0),
            "step_length_right_m": params_l.get("step_length_right_m", 0.0),
            "foot_progression_angle_left_deg": params_l.get("foot_progression_angle_left_deg", 0.0),
            "foot_progression_angle_right_deg": params_l.get("foot_progression_angle_right_deg", 0.0),
            # Pronation (left)
            "rearfoot_angle_deg_mean_L": params_l.get("rearfoot_angle_deg_mean", 0.0),
            "frontal_plane_excursion_deg_mean_L": params_l.get("frontal_plane_excursion_deg_mean", 0.0),
            "pronation_type_L": params_l.get("pronation_type", "neutral"),
            # Pronation (right)
            "rearfoot_angle_deg_mean_R": params_r.get("rearfoot_angle_deg_mean", 0.0),
            "frontal_plane_excursion_deg_mean_R": params_r.get("frontal_plane_excursion_deg_mean", 0.0),
            "pronation_type_R": params_r.get("pronation_type", "neutral"),
            # Arch
            "arch_type_L": params_l.get("arch_type", "normal"),
            "arch_type_R": params_r.get("arch_type", "normal"),
            # Foot strike
            "foot_strike_type_L": params_l.get("foot_strike_type", "rearfoot"),
            "foot_strike_type_R": params_r.get("foot_strike_type", "rearfoot"),
            # Per-foot metrics for validation
            "left_metrics": {
                "pronation_type": params_l.get("pronation_type", "neutral"),
                "arch_type": params_l.get("arch_type", "normal"),
                "rearfoot_angle_deg_mean": params_l.get("rearfoot_angle_deg_mean", 0.0),
                "frontal_plane_excursion_deg_mean": params_l.get("frontal_plane_excursion_deg_mean", 0.0),
            },
            "right_metrics": {
                "pronation_type": params_r.get("pronation_type", "neutral"),
                "arch_type": params_r.get("arch_type", "normal"),
                "rearfoot_angle_deg_mean": params_r.get("rearfoot_angle_deg_mean", 0.0),
                "frontal_plane_excursion_deg_mean": params_r.get("frontal_plane_excursion_deg_mean", 0.0),
            },
        }

    # â”€â”€ ProfileBuilder ABC â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def build(
        self,
        patient_id: str,
        session_timestamp: str,
        parameters: Dict[str, Any],
        anthropometrics: Dict[str, Any],
        confidence_scores: Dict[str, float],
        face_blur_applied: bool = False,
    ) -> Dict[str, Any]:
        """Assemble and return a profile dict matching GaitPatientProfile schema.

        Missing spatiotemporal fields that require external video metadata
        (speed, stride length, step width, double support) default to 0.0 and
        are recorded in quality_metrics for downstream review.
        """
        params_l: Dict[str, Any] = parameters.get("L", {})
        params_r: Dict[str, Any] = parameters.get("R", {})

        # ── zero-cycle fallback ─────────────────────────────────────────────
        # aggregate_parameters() returns {cycle_count: 0, quality_flag: "RERECORD"}
        # when no *complete* cycle was formed for a foot. That used to always
        # mean "nothing was detected", but the event detector can now anchor
        # a PARTIAL_CYCLE on a single heel-strike + following toe-off, and a
        # foot can also have real toe-off (or heel-strike) events without
        # enough to form any cycle at all. Population-average placeholders
        # should only be used when there is truly nothing real to report —
        # zero heel strikes AND zero toe offs. When some real (if partial)
        # data exists, keep it as-is rather than overwriting it with fake
        # population numbers; flag it as PARTIAL_DATA_NO_CYCLE instead.
        low_confidence_feet: List[str] = []
        partial_data_feet: List[str] = []
        for foot_key, foot_params in (("L", params_l), ("R", params_r)):
            n = foot_params.get("cycle_count", 0)
            hs_count = foot_params.get("heel_strike_count", 0)
            to_count = foot_params.get("toe_off_count", 0)
            if n == 0 and hs_count == 0 and to_count == 0:
                logger.warning(
                    "builder.zero_cycle_placeholder",
                    extra={"foot": foot_key, "cycle_count": n, "patient_id": patient_id},
                )
                for key, default in _POPULATION_AVERAGE_DEFAULTS.items():
                    foot_params.setdefault(key, default)
                foot_params["quality_flag"] = "LOW_CONFIDENCE_PLACEHOLDER"
                foot_params["is_placeholder"] = True
                low_confidence_feet.append(foot_key)
            elif n == 0:
                # Real heel-strike and/or toe-off events exist, but not enough
                # to anchor even a partial cycle (e.g. toe-offs with no heel
                # strike to pair them to). Report what's real; don't fabricate
                # the rest.
                logger.warning(
                    "builder.partial_data_no_cycle",
                    extra={
                        "foot": foot_key,
                        "heel_strike_count": hs_count,
                        "toe_off_count": to_count,
                        "patient_id": patient_id,
                    },
                )
                foot_params["quality_flag"] = "PARTIAL_DATA_NO_CYCLE"
                foot_params["is_placeholder"] = False
                partial_data_feet.append(foot_key)

        has_partial_cycle = bool(
            params_l.get("has_partial_cycle") or params_r.get("has_partial_cycle")
        )

        # â”€â”€ symmetry flags â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        symmetry_flags = _compute_symmetry_flags(
            params_l, params_r, self._cfg.symmetry_flag_threshold_pct
        )

        # â”€â”€ combined parameters for rule-condition matching â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

        # â”€â”€ health assessment (agent â†’ fallback to rules) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        health_data, agent_decisions = self._generate_health_assessment(
            rule_params, patient_id, params_l, params_r, parameters
        )
        needs_human_review = bool(health_data.pop("needs_human_review", False))

        # â”€â”€ spatiotemporal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Cadence: prefer real per-cycle timing (mean of L/R cadence_steps_per_min_mean,
        # which is only populated for COMPLETE cycles â€” see compute_spatiotemporal).
        # If neither foot has that, fall back to the heel-strike-interval estimate
        # (needs >=2 heel strikes combined across both feet â€” see
        # GaitPipeline._compute_cadence_from_heel_strikes). If that's also
        # unavailable, leave cadence as None (null in the profile) rather than
        # a population-average guess â€” a missing value is honest; a fabricated
        # one is not.
        cadence_l = params_l.get("cadence_steps_per_min_mean")
        cadence_r = params_r.get("cadence_steps_per_min_mean")
        if cadence_l is not None or cadence_r is not None:
            cadence = _mean_of(cadence_l, cadence_r)
        else:
            cadence = parameters.get("cadence_from_heel_strikes_spm")
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
            "step_length_left_m": params_l.get("step_length_left_m", 0.0),
            "step_length_right_m": params_l.get("step_length_right_m", 0.0),
            "foot_progression_angle_left_deg": params_l.get("foot_progression_angle_left_deg", 0.0),
            "foot_progression_angle_right_deg": params_l.get("foot_progression_angle_right_deg", 0.0),
            "foot_progression_classification_left": parameters.get("foot_progression_classification_left", "neutral"),
            "foot_progression_classification_right": parameters.get("foot_progression_classification_right", "neutral"),
        }

        # â”€â”€ foot strike â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

        # â”€â”€ pronation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        fpe_l = params_l.get("frontal_plane_excursion_deg_mean", 0.0)
        fpe_r = params_r.get("frontal_plane_excursion_deg_mean", 0.0)
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
            "frontal_plane_excursion_left_deg": fpe_l,
            "frontal_plane_excursion_right_deg": fpe_r,
        }

        # â”€â”€ rearfoot alignment (posterior camera; feeds wedging_prescription) â”€â”€â”€â”€
        rearfoot_alignment = {
            "angle_deg": {
                "L": params_l.get("rearfoot_alignment_angle_deg_mean"),
                "R": params_r.get("rearfoot_alignment_angle_deg_mean"),
            },
            "classification": {
                "L": params_l.get("rearfoot_alignment_classification"),
                "R": params_r.get("rearfoot_alignment_classification"),
            },
            "frame_count": {
                "L": params_l.get("rearfoot_alignment_frame_count", 0),
                "R": params_r.get("rearfoot_alignment_frame_count", 0),
            },
        }

        # â”€â”€ arch â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

        # â”€â”€ quality metrics (internal; not for shoe-design) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        qf_l = params_l.get("quality_flag", "RERECORD")
        qf_r = params_r.get("quality_flag", "RERECORD")
        if qf_l in ("RERECORD", "LOW_CONFIDENCE_PLACEHOLDER", "PARTIAL_DATA_NO_CYCLE") or qf_r in (
            "RERECORD",
            "LOW_CONFIDENCE_PLACEHOLDER",
            "PARTIAL_DATA_NO_CYCLE",
        ):
            needs_human_review = True

        # partial_data: true whenever any biomechanical value in this profile
        # came from a PARTIAL_CYCLE (single HS + following TO, no closing HS)
        # or from a foot with real events but no cycle at all. The frontend's
        # low-quality banner is already driven by is_low_confidence, which
        # this also feeds into.
        partial_data = has_partial_cycle or bool(partial_data_feet)

        quality_metrics = {
            "quality_flag_L": qf_l,
            "quality_flag_R": qf_r,
            "cycle_count_L": params_l.get("cycle_count", 0),
            "cycle_count_R": params_r.get("cycle_count", 0),
            "is_low_confidence": bool(low_confidence_feet) or partial_data,
            "low_confidence_feet": low_confidence_feet,
            "partial_data": partial_data,
            "partial_data_feet": partial_data_feet,
            "phase1_placeholder_fields": [
                "time_to_peak_eversion_pct_stance",
            ],
        }

        # â”€â”€ health assessment â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        health_assessment = {
            "what_went_right": health_data.get("what_went_right", []),
            "defects_found": health_data.get("defects_found", []),
            "improvement_plan": health_data.get("improvements", []),
        }

        # â”€â”€ prescription spec â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        from gait.profile.prescription_engine import PrescriptionEngine, _compute_wedging_prescription
        from gait.pipeline.config import load_recommendation_rules

        prx_rules_config = (
            self._rules_config
            if self._rules_config is not None
            else load_recommendation_rules()
        )
        prx_engine = PrescriptionEngine(
            prescription_rules=[
                r.model_dump() for r in prx_rules_config.prescription_rules
            ]
        )
        body_mass_kg: float = float(anthropometrics.get("mass_kg", 70.0))
        step_len_l: float = float(params_l.get("step_length_left_m", 0.0))
        step_len_r: float = float(params_l.get("step_length_right_m", 0.0))
        prescription_spec = prx_engine.generate_prescription(
            rule_params=rule_params,
            body_mass_kg=body_mass_kg,
            step_length_left_m=step_len_l,
            step_length_right_m=step_len_r,
            patient_id=patient_id,
        )
        wedging_prescription = _compute_wedging_prescription(params_l, params_r, anthropometrics)

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
            "health_assessment": health_assessment,
            "confidence_scores": confidence_scores,
            "needs_human_review": needs_human_review,
            "quality_metrics": quality_metrics,
            "agent_decisions": agent_decisions,
            "face_blur_applied": face_blur_applied,
            "prescription_spec": prescription_spec.model_dump(),
            "wedging_prescription": wedging_prescription,
            "rearfoot_alignment": rearfoot_alignment,
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
        from gait.profile.schema import GaitPatientProfile

        try:
            GaitPatientProfile(**profile)
            return True, []
        except ValidationError as exc:
            errors = [f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in exc.errors()]
            return False, errors
        except Exception as exc:  # pragma: no cover
            return False, [str(exc)]


# â”€â”€ factory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def create_profile_builder(
    rules_config: RecommendationRulesConfig,
    analysis_config: AnalysisConfig,
) -> StandardProfileBuilder:
    """Factory: create a StandardProfileBuilder wired with a RuleBasedRecommendationEngine."""
    engine = create_recommendation_engine(rules_config)
    return StandardProfileBuilder(engine, analysis_config, rules_config=rules_config)

