"""StandardProfileBuilder — assembles GaitPatientProfile from aggregated parameters.

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
        health_coach: Optional[Any] = None,
        rules_config: Optional[RecommendationRulesConfig] = None,
    ) -> None:
        self._rules_engine = rules_engine
        self._cfg = analysis_config
        self._health_coach = health_coach
        self._rules_config = rules_config

    # ── agent integration ──────────────────────────────────────────────────

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

    # ── ProfileBuilder ABC ─────────────────────────────────────────────────

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

        # ── health assessment (agent → fallback to rules) ─────────────────────
        health_data, agent_decisions = self._generate_health_assessment(
            rule_params, patient_id, params_l, params_r, parameters
        )
        needs_human_review = bool(health_data.pop("needs_human_review", False))

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
            "step_length_left_m": params_l.get("step_length_left_m", 0.0),
            "step_length_right_m": params_l.get("step_length_right_m", 0.0),
            "foot_progression_angle_left_deg": params_l.get("foot_progression_angle_left_deg", 0.0),
            "foot_progression_angle_right_deg": params_l.get("foot_progression_angle_right_deg", 0.0),
            "foot_progression_classification_left": parameters.get("foot_progression_classification_left", "neutral"),
            "foot_progression_classification_right": parameters.get("foot_progression_classification_right", "neutral"),
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

        # ── health assessment ─────────────────────────────────────────────────
        health_assessment = {
            "what_went_right": health_data.get("what_went_right", []),
            "defects_found": health_data.get("defects_found", []),
            "improvement_plan": health_data.get("improvements", []),
        }

        # ── prescription spec ─────────────────────────────────────────────────
        from src.gait.profile.prescription_engine import PrescriptionEngine
        from src.gait.pipeline.config import load_recommendation_rules

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
    return StandardProfileBuilder(engine, analysis_config, rules_config=rules_config)
