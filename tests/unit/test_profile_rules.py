"""Unit tests for RuleBasedRecommendationEngine (src.gait.profile.rules_engine)."""
from __future__ import annotations

from gait.pipeline.config import RecommendationRule, RecommendationRulesConfig
from gait.profile.rules_engine import (
    RuleBasedRecommendationEngine,
    _match_condition,
    create_recommendation_engine,
)

# â”€â”€ fixtures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def make_rules_config(*rules: RecommendationRule) -> RecommendationRulesConfig:
    return RecommendationRulesConfig(version=1, rules=list(rules))


def make_rule(
    rule_id: str,
    when: dict,
    then: dict,
    priority: int = 0,
) -> RecommendationRule:
    return RecommendationRule(id=rule_id, when=when, then=then, priority=priority)


def minimal_engine() -> RuleBasedRecommendationEngine:
    """Engine with no rules â€” always returns defaults."""
    return RuleBasedRecommendationEngine(RecommendationRulesConfig(version=1, rules=[]))


# â”€â”€ _match_condition â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestMatchCondition:
    def test_empty_condition_always_matches(self):
        assert _match_condition({}, {"pronation_type": "neutral"}) is True

    def test_pronation_match(self):
        assert _match_condition(
            {"pronation": "overpronation"},
            {"pronation_type": "overpronation"},
        ) is True

    def test_pronation_no_match(self):
        assert _match_condition(
            {"pronation": "overpronation"},
            {"pronation_type": "neutral"},
        ) is False

    def test_pronation_missing_from_params(self):
        assert _match_condition({"pronation": "overpronation"}, {}) is False

    def test_arch_match(self):
        assert _match_condition(
            {"arch": "low"},
            {"arch_type": "low"},
        ) is True

    def test_arch_no_match(self):
        assert _match_condition(
            {"arch": "low"},
            {"arch_type": "normal"},
        ) is False

    def test_foot_strike_match(self):
        assert _match_condition(
            {"foot_strike": "forefoot"},
            {"foot_strike_type": "forefoot"},
        ) is True

    def test_foot_strike_no_match(self):
        assert _match_condition(
            {"foot_strike": "forefoot"},
            {"foot_strike_type": "rearfoot"},
        ) is False

    def test_flag_match(self):
        assert _match_condition(
            {"flag": "high_asymmetry"},
            {"flags": ["high_asymmetry", "some_other_flag"]},
        ) is True

    def test_flag_no_match(self):
        assert _match_condition(
            {"flag": "high_asymmetry"},
            {"flags": ["other_flag"]},
        ) is False

    def test_flag_missing_flags_key(self):
        assert _match_condition({"flag": "high_asymmetry"}, {}) is False

    def test_eversion_peak_early_true_match(self):
        assert _match_condition(
            {"eversion_peak_early": True},
            {"eversion_peak_early": True},
        ) is True

    def test_eversion_peak_early_false_no_match(self):
        assert _match_condition(
            {"eversion_peak_early": True},
            {"eversion_peak_early": False},
        ) is False

    def test_eversion_peak_early_missing_defaults_false(self):
        assert _match_condition({"eversion_peak_early": True}, {}) is False

    def test_age_years_below_match(self):
        assert _match_condition(
            {"age_years_below": 18},
            {"age_years": 12},
        ) is True

    def test_age_years_below_equal_no_match(self):
        assert _match_condition(
            {"age_years_below": 18},
            {"age_years": 18},
        ) is False

    def test_age_years_below_adult_no_match(self):
        assert _match_condition(
            {"age_years_below": 18},
            {"age_years": 30},
        ) is False

    def test_age_years_below_missing_is_inf(self):
        # missing age â†’ treated as infinity â†’ not < 18
        assert _match_condition({"age_years_below": 18}, {}) is False

    def test_multiple_conditions_all_match(self):
        assert _match_condition(
            {"pronation": "overpronation", "arch": "low"},
            {"pronation_type": "overpronation", "arch_type": "low"},
        ) is True

    def test_multiple_conditions_one_fails(self):
        assert _match_condition(
            {"pronation": "overpronation", "arch": "low"},
            {"pronation_type": "overpronation", "arch_type": "normal"},
        ) is False


# â”€â”€ apply_rule â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestApplyRule:
    def test_apply_overwrites_field(self):
        engine = minimal_engine()
        recs = {"medial_post": "none", "arch_support": "medium"}
        result = engine.apply_rule("r1", {}, {"arch_support": "high"}, recs)
        assert result["arch_support"] == "high"

    def test_apply_adds_new_field(self):
        engine = minimal_engine()
        result = engine.apply_rule("r1", {}, {"heel_drop_mm": 10}, {})
        assert result["heel_drop_mm"] == 10

    def test_needs_human_review_or_semantics_false_then_true(self):
        engine = minimal_engine()
        recs = {"needs_human_review": False}
        result = engine.apply_rule("r1", {}, {"needs_human_review": True}, recs)
        assert result["needs_human_review"] is True

    def test_needs_human_review_true_stays_true(self):
        engine = minimal_engine()
        recs = {"needs_human_review": True}
        result = engine.apply_rule("r1", {}, {"needs_human_review": False}, recs)
        assert result["needs_human_review"] is True

    def test_does_not_mutate_original(self):
        engine = minimal_engine()
        recs = {"medial_post": "none"}
        engine.apply_rule("r1", {}, {"medial_post": "required"}, recs)
        assert recs["medial_post"] == "none"

    def test_empty_action_returns_copy_unchanged(self):
        engine = minimal_engine()
        recs = {"medial_post": "none"}
        result = engine.apply_rule("r1", {}, {}, recs)
        assert result == recs
        assert result is not recs


# â”€â”€ generate_recommendations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestGenerateRecommendations:
    def test_no_rules_returns_defaults(self):
        engine = minimal_engine()
        result = engine.generate_recommendations({"pronation_type": "neutral"})
        assert result["defects_found"] == []
        assert result["improvements"] == []
        assert result["what_went_right"] == []
        assert result["needs_human_review"] is False

    def test_matching_rule_adds_defect(self):
        engine = RuleBasedRecommendationEngine(
            make_rules_config(
                make_rule(
                    "test_rule",
                    when={"pronation": "overpronation"},
                    then={
                        "defects_found": [{"name": "Test Defect", "severity": "moderate", "affected_side": "bilateral", "biomechanical_cause": "Test", "gait_cycle_phase": "Test"}],
                    },
                )
            )
        )
        result = engine.generate_recommendations({"pronation_type": "overpronation"})
        assert len(result["defects_found"]) == 1
        assert result["defects_found"][0]["name"] == "Test Defect"

    def test_non_matching_rule_leaves_defaults(self):
        engine = RuleBasedRecommendationEngine(
            make_rules_config(
                make_rule(
                    "test_rule",
                    when={"pronation": "overpronation"},
                    then={"defects_found": [{"name": "Test", "severity": "mild", "affected_side": "left", "biomechanical_cause": "test", "gait_cycle_phase": "test"}]},
                )
            )
        )
        result = engine.generate_recommendations({"pronation_type": "neutral"})
        assert result["defects_found"] == []

    def test_higher_priority_overrides_lower(self):
        engine = RuleBasedRecommendationEngine(
            make_rules_config(
                make_rule("low_p", when={}, then={"heel_drop_mm": 4}, priority=10),
                make_rule("high_p", when={}, then={"heel_drop_mm": 10}, priority=90),
            )
        )
        result = engine.generate_recommendations({})
        assert result["heel_drop_mm"] == 10

    def test_lower_priority_overridden_by_higher(self):
        engine = RuleBasedRecommendationEngine(
            make_rules_config(
                make_rule("high_p", when={}, then={"arch_support": "high"}, priority=90),
                make_rule("low_p", when={}, then={"arch_support": "low"}, priority=10),
            )
        )
        result = engine.generate_recommendations({})
        # priority 10 fires first, priority 90 fires last â†’ "high" wins
        assert result["arch_support"] == "high"

    def test_needs_human_review_set_by_flag(self):
        engine = RuleBasedRecommendationEngine(
            make_rules_config(
                make_rule(
                    "asymmetry",
                    when={"flag": "high_asymmetry"},
                    then={"needs_human_review": True},
                    priority=80,
                )
            )
        )
        result = engine.generate_recommendations({"flags": ["high_asymmetry"]})
        assert result["needs_human_review"] is True

    def test_needs_human_review_false_by_default(self):
        engine = minimal_engine()
        result = engine.generate_recommendations({})
        assert result["needs_human_review"] is False

    def test_needs_human_review_not_overridden_by_later_non_review_rule(self):
        engine = RuleBasedRecommendationEngine(
            make_rules_config(
                make_rule("review", when={}, then={"needs_human_review": True}, priority=10),
                make_rule("norec", when={}, then={"heel_drop_mm": 8}, priority=90),
            )
        )
        result = engine.generate_recommendations({})
        assert result["needs_human_review"] is True

    def test_multi_rule_cumulative_patch(self):
        """Two rules firing at different priorities each contribute different fields."""
        engine = RuleBasedRecommendationEngine(
            make_rules_config(
                make_rule("r1", when={}, then={"heel_counter": "rigid"}, priority=20),
                make_rule("r2", when={}, then={"arch_support": "high"}, priority=50),
            )
        )
        result = engine.generate_recommendations({})
        assert result["heel_counter"] == "rigid"
        assert result["arch_support"] == "high"

    def test_patient_id_does_not_affect_output(self):
        engine = minimal_engine()
        r1 = engine.generate_recommendations({}, patient_id="P001")
        r2 = engine.generate_recommendations({}, patient_id="P999")
        assert r1 == r2


# â”€â”€ rules loaded from RecommendationRulesConfig â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestWithRealRulesConfig:
    """Integration tests using the full rules schema from config."""

    def _full_engine(self) -> RuleBasedRecommendationEngine:
        from gait.pipeline.config import load_recommendation_rules

        cfg = load_recommendation_rules()
        return create_recommendation_engine(cfg)

    def test_overpronation_low_arch_creates_defect(self):
        engine = self._full_engine()
        result = engine.generate_recommendations(
            {"pronation_type": "overpronation", "arch_type": "low"}
        )
        assert len(result["defects_found"]) > 0
        assert any("Overpronation" in d.get("name", "") for d in result["defects_found"])

    def test_overpronation_low_arch_has_improvement_plan(self):
        engine = self._full_engine()
        result = engine.generate_recommendations(
            {"pronation_type": "overpronation", "arch_type": "low"}
        )
        assert len(result["improvements"]) > 0

    def test_neutral_pronation_positive_finding(self):
        engine = self._full_engine()
        result = engine.generate_recommendations(
            {"pronation_type": "neutral", "arch_type": "normal"}
        )
        assert len(result["defects_found"]) == 0
        assert len(result["what_went_right"]) > 0

    def test_oversupination_high_arch_creates_defect(self):
        engine = self._full_engine()
        result = engine.generate_recommendations(
            {"pronation_type": "oversupination", "arch_type": "high"}
        )
        assert len(result["defects_found"]) > 0
        assert any("Oversupination" in d.get("name", "") or "Supination" in d.get("name", "") for d in result["defects_found"])

    def test_forefoot_striker_creates_defect(self):
        engine = self._full_engine()
        result = engine.generate_recommendations({"foot_strike_type": "forefoot"})
        assert len(result["defects_found"]) > 0
        assert any("Forefoot" in d.get("name", "") for d in result["defects_found"])

    def test_high_asymmetry_flag_triggers_review(self):
        engine = self._full_engine()
        result = engine.generate_recommendations({"flags": ["high_asymmetry"]})
        assert result["needs_human_review"] is True

    def test_pathological_gait_flag_triggers_review(self):
        engine = self._full_engine()
        result = engine.generate_recommendations({"flags": ["pathological_gait"]})
        assert result["needs_human_review"] is True

    def test_pediatric_adjustment_noted(self):
        engine = self._full_engine()
        result = engine.generate_recommendations(
            {
                "pronation_type": "neutral",
                "arch_type": "normal",
                "age_years": 10,
            }
        )
        # Pediatric rule should add positive finding about monitoring
        assert len(result["what_went_right"]) > 0


# â”€â”€ factory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestFactory:
    def test_create_returns_correct_type(self):
        cfg = RecommendationRulesConfig(version=1, rules=[])
        engine = create_recommendation_engine(cfg)
        assert isinstance(engine, RuleBasedRecommendationEngine)

    def test_rules_sorted_ascending_by_priority(self):
        cfg = make_rules_config(
            make_rule("high", when={}, then={}, priority=90),
            make_rule("low", when={}, then={}, priority=10),
            make_rule("mid", when={}, then={}, priority=50),
        )
        engine = create_recommendation_engine(cfg)
        priorities = [r.priority for r in engine._rules]
        assert priorities == sorted(priorities)

    def test_empty_rules_config_works(self):
        engine = create_recommendation_engine(RecommendationRulesConfig(version=1, rules=[]))
        result = engine.generate_recommendations({"pronation_type": "neutral"})
        assert isinstance(result, dict)

