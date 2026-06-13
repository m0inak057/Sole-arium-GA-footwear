"""RuleBasedRecommendationEngine — applies rules.yaml conditions in priority order.

Rules are sorted by priority ascending (lower first).  Higher-priority rules
come last and have the final say on any field they touch.  `needs_human_review`
is OR'd across all matching rules: once set to True it is never overridden back.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.gait.common.interfaces import RecommendationEngine
from src.gait.common.logging_utils import get_logger
from src.gait.pipeline.config import RecommendationRule, RecommendationRulesConfig

logger = get_logger(__name__)

# ── sensible defaults (applied before any rule fires) ─────────────────────────

_DEFAULTS: Dict[str, Any] = {
    "medial_post": "none",
    "post_density": None,
    "arch_support": "medium",
    "heel_counter": "semi_rigid",
    "heel_drop_mm": 8.0,
    "last_shape": "semi_curved",
    "cushioning_zone_priority": ["heel", "forefoot"],
    "notes": None,
    "needs_human_review": False,
}


# ── condition matching ────────────────────────────────────────────────────────


def _match_condition(condition: Dict[str, Any], parameters: Dict[str, Any]) -> bool:
    """Return True when ALL entries in condition match parameters (AND semantics).

    Supported condition keys:
      pronation: <str>        → parameters["pronation_type"] == value
      arch: <str>             → parameters["arch_type"] == value
      foot_strike: <str>      → parameters["foot_strike_type"] == value
      flag: <str>             → value in parameters.get("flags", [])
      eversion_peak_early: bool → parameters.get("eversion_peak_early", False) == value
      age_years_below: <num>  → parameters.get("age_years", ∞) < value
    """
    for key, value in condition.items():
        if key == "pronation":
            if parameters.get("pronation_type") != value:
                return False
        elif key == "arch":
            if parameters.get("arch_type") != value:
                return False
        elif key == "foot_strike":
            if parameters.get("foot_strike_type") != value:
                return False
        elif key == "flag":
            if value not in parameters.get("flags", []):
                return False
        elif key == "eversion_peak_early":
            if parameters.get("eversion_peak_early", False) != value:
                return False
        elif key == "age_years_below":
            age = parameters.get("age_years", float("inf"))
            if age is None or not (age < value):
                return False
        else:
            logger.warning(
                "rules.unknown_condition_key",
                extra={"key": key, "value": value},
            )
    return True


# ── engine ────────────────────────────────────────────────────────────────────


class RuleBasedRecommendationEngine(RecommendationEngine):
    """Evaluates recommendation rules and patches output in priority order.

    Lower-priority rules fire first and set the initial recommendation.
    Higher-priority rules fire last and override any fields they specify.
    """

    def __init__(self, rules_config: RecommendationRulesConfig) -> None:
        self._rules: List[RecommendationRule] = sorted(
            rules_config.rules, key=lambda r: (r.priority or 0)
        )

    def generate_recommendations(
        self, parameters: Dict[str, Any], patient_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Apply all matching rules and return the final recommendations dict."""
        recs: Dict[str, Any] = dict(_DEFAULTS)
        applied: List[str] = []

        for rule in self._rules:
            if _match_condition(rule.when, parameters):
                recs = self.apply_rule(rule.id, rule.when, rule.then, recs)
                applied.append(rule.id)

        logger.info(
            "rules.generation_complete",
            extra={
                "patient_id": patient_id,
                "n_applied": len(applied),
                "rules_applied": applied,
            },
        )
        return recs

    def apply_rule(
        self,
        rule_id: str,
        condition: Dict[str, Any],
        action: Dict[str, Any],
        current_recommendations: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Patch current_recommendations with the action dict.

        needs_human_review is OR'd: once True it stays True regardless of later rules.
        All other fields are overwritten by the action value.
        """
        updated = dict(current_recommendations)
        for key, value in action.items():
            if key == "needs_human_review":
                updated[key] = updated.get(key, False) or bool(value)
            else:
                updated[key] = value
        logger.debug("rules.rule_applied", extra={"rule_id": rule_id})
        return updated


def create_recommendation_engine(
    rules_config: RecommendationRulesConfig,
) -> RuleBasedRecommendationEngine:
    """Factory: return a RuleBasedRecommendationEngine."""
    return RuleBasedRecommendationEngine(rules_config)
