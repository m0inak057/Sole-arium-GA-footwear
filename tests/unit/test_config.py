"""Unit tests for pipeline configuration loaders.

Tests that:
1. Configs load from YAML
2. Configs validate with pydantic
3. Defaults are applied correctly
4. Missing files raise appropriate errors
"""

import os
import pytest
import tempfile
from pathlib import Path

from src.gait.pipeline.config import (
    load_thresholds,
    load_pipeline_config,
    load_recommendation_rules,
    ThresholdsConfig,
    PipelineConfig,
    RecommendationRulesConfig,
)


@pytest.mark.unit
class TestThresholdsLoading:
    """Test loading and validating thresholds config."""

    def test_load_thresholds_from_default_path(self):
        """Load thresholds from configs/thresholds.yaml."""
        # The actual file should exist in the repo
        try:
            thresholds = load_thresholds()
            assert isinstance(thresholds, ThresholdsConfig)
            assert thresholds.quality_gating.min_clean_cycles_per_foot == 4
        except FileNotFoundError:
            pytest.skip("thresholds.yaml not found (expected in full repo)")

    def test_load_thresholds_custom_path(self):
        """Load thresholds from custom path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
foot_strike:
  rearfoot_min_deg: 5.0
  forefoot_max_deg: -5.0
pronation:
  overpronation_min_deg: 8.0
  mild_pronation_min_deg: 4.0
  neutral_min_deg: 0.0
  mild_supination_min_deg: -4.0
symmetry:
  flag_threshold_pct: 10.0
quality_gating:
  min_keypoint_confidence: 0.5
  min_clean_cycles_per_foot: 4
  target_clean_cycles_per_foot: 8
""")
            f.flush()

            try:
                thresholds = load_thresholds(f.name)
                assert thresholds.foot_strike.rearfoot_min_deg == 5.0
                assert thresholds.pronation.overpronation_min_deg == 8.0
                assert thresholds.symmetry.flag_threshold_pct == 10.0
            finally:
                os.unlink(f.name)

    def test_load_thresholds_missing_file(self):
        """Raise FileNotFoundError for missing config."""
        with pytest.raises(FileNotFoundError):
            load_thresholds("/nonexistent/path/thresholds.yaml")


@pytest.mark.unit
class TestPipelineConfigLoading:
    """Test loading and validating pipeline config."""

    def test_load_pipeline_config_defaults(self):
        """Pipeline config returns defaults if file doesn't exist."""
        config = load_pipeline_config("/nonexistent/path/pipeline.yaml")
        assert isinstance(config, PipelineConfig)
        assert config.ingestion.fps == 120
        assert config.pose.model == "mediapipe"

    def test_load_pipeline_config_custom(self):
        """Load pipeline config from custom path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
ingestion:
  fps: 60
  resolution: [1280, 720]
  sync_tolerance_ms: 20
pose:
  model: openpose
  confidence_threshold: 0.6
""")
            f.flush()

            try:
                config = load_pipeline_config(f.name)
                assert config.ingestion.fps == 60
                assert config.ingestion.resolution == [1280, 720]
                assert config.pose.model == "openpose"
            finally:
                os.unlink(f.name)

    def test_pipeline_config_partial_override(self):
        """Pipeline config merges defaults with custom values."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
ingestion:
  fps: 60
""")
            f.flush()

            try:
                config = load_pipeline_config(f.name)
                # Custom value
                assert config.ingestion.fps == 60
                # Default value (not overridden)
                assert config.pose.model == "mediapipe"
            finally:
                os.unlink(f.name)


@pytest.mark.unit
class TestRecommendationRulesLoading:
    """Test loading and validating recommendation rules."""

    def test_load_rules_defaults(self):
        """Rules config returns empty rules if file doesn't exist."""
        rules = load_recommendation_rules("/nonexistent/path/rules.yaml")
        assert isinstance(rules, RecommendationRulesConfig)
        assert rules.version == 1
        assert len(rules.rules) == 0

    def test_load_rules_custom(self):
        """Load rules from custom path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
version: 1
rules:
  - id: test_rule_1
    when:
      pronation: overpronation
      arch: low
    then:
      medial_post: required
      arch_support: high
      heel_counter: rigid
  - id: test_rule_2
    when:
      foot_strike: forefoot
    then:
      heel_drop_mm: 6
""")
            f.flush()

            try:
                rules = load_recommendation_rules(f.name)
                assert rules.version == 1
                assert len(rules.rules) == 2
                assert rules.rules[0].id == "test_rule_1"
                assert rules.rules[0].then["medial_post"] == "required"
                assert rules.rules[1].id == "test_rule_2"
            finally:
                os.unlink(f.name)

    def test_load_rules_empty_file(self):
        """Load rules from empty YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            f.flush()

            try:
                rules = load_recommendation_rules(f.name)
                assert isinstance(rules, RecommendationRulesConfig)
                assert len(rules.rules) == 0
            finally:
                os.unlink(f.name)


@pytest.mark.unit
class TestConfigValidation:
    """Test that configs validate correctly."""

    def test_thresholds_config_validation(self):
        """ThresholdsConfig validates pydantic constraints."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
foot_strike:
  rearfoot_min_deg: 5.0
  forefoot_max_deg: -5.0
pronation:
  overpronation_min_deg: 8.0
  mild_pronation_min_deg: 4.0
  neutral_min_deg: 0.0
  mild_supination_min_deg: -4.0
symmetry:
  flag_threshold_pct: 10.0
quality_gating:
  min_keypoint_confidence: 0.5
  min_clean_cycles_per_foot: 4
  target_clean_cycles_per_foot: 8
""")
            f.flush()

            try:
                thresholds = load_thresholds(f.name)
                # Verify loaded values
                assert 0 <= thresholds.quality_gating.min_keypoint_confidence <= 1
                assert thresholds.quality_gating.min_clean_cycles_per_foot > 0
            finally:
                os.unlink(f.name)

    def test_pipeline_config_extra_fields_allowed(self):
        """PipelineConfig allows extra fields (flexible for future additions)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
ingestion:
  fps: 60
future_feature:
  some_param: value
""")
            f.flush()

            try:
                config = load_pipeline_config(f.name)
                # Should not raise, extra fields are allowed
                assert config.ingestion.fps == 60
            finally:
                os.unlink(f.name)
