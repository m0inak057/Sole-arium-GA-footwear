"""Advanced gait metrics: symmetry, efficiency, stability."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from gait.common.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class SymmetryMetrics:
    """Left-right symmetry metrics."""
    cadence_symmetry_pct: float  # 0-100%
    stride_length_symmetry_pct: float
    stance_time_symmetry_pct: float
    asymmetry_flags: list[str]  # List of flagged asymmetries (>10%)


@dataclass
class EfficiencyMetrics:
    """Gait efficiency indicators."""
    walking_efficiency_score: float  # 0-100
    energy_cost_estimate: float  # Arbitrary units
    smoothness_index: float  # 0-100 (higher = smoother)
    variability_index: float  # 0-100 (higher = more variable)


class AdvancedMetricsAnalyzer:
    """Computes advanced gait metrics."""

    def __init__(self, asymmetry_threshold_pct: float = 10.0):
        """Initialize analyzer.

        Args:
            asymmetry_threshold_pct: Threshold for flagging asymmetry
        """
        self.asymmetry_threshold = asymmetry_threshold_pct

    def compute_symmetry(
        self,
        left_params: dict,
        right_params: dict,
    ) -> SymmetryMetrics:
        """Compute left-right symmetry indices.

        Args:
            left_params: Left side gait parameters
            right_params: Right side gait parameters

        Returns:
            SymmetryMetrics with computed indices
        """
        try:
            flags = []

            # Cadence symmetry (should be identical)
            cadence_l = left_params.get("cadence_spm", 0)
            cadence_r = right_params.get("cadence_spm", 0)
            cadence_sym = self._symmetry_index(cadence_l, cadence_r)
            if cadence_sym > self.asymmetry_threshold:
                flags.append("cadence_asymmetry")

            # Stride length symmetry
            stride_l = left_params.get("stride_length_m", 0)
            stride_r = right_params.get("stride_length_m", 0)
            stride_sym = self._symmetry_index(stride_l, stride_r)
            if stride_sym > self.asymmetry_threshold:
                flags.append("stride_length_asymmetry")

            # Stance time symmetry
            stance_l = left_params.get("stance_time_pct", 0)
            stance_r = right_params.get("stance_time_pct", 0)
            stance_sym = self._symmetry_index(stance_l, stance_r)
            if stance_sym > self.asymmetry_threshold:
                flags.append("stance_time_asymmetry")

            logger.info(
                "metrics.symmetry",
                extra={
                    "cadence_symmetry": cadence_sym,
                    "stride_symmetry": stride_sym,
                    "asymmetry_flags": flags,
                },
            )

            return SymmetryMetrics(
                cadence_symmetry_pct=cadence_sym,
                stride_length_symmetry_pct=stride_sym,
                stance_time_symmetry_pct=stance_sym,
                asymmetry_flags=flags,
            )

        except Exception as e:
            logger.error("metrics.symmetry_failed", extra={"error": str(e)})
            return SymmetryMetrics(
                cadence_symmetry_pct=0.0,
                stride_length_symmetry_pct=0.0,
                stance_time_symmetry_pct=0.0,
                asymmetry_flags=[],
            )

    def compute_efficiency(
        self,
        cadence_spm: float,
        speed_ms: float,
        stride_length_m: float,
        smoothness_score: float,
        variability_score: float,
    ) -> EfficiencyMetrics:
        """Compute gait efficiency metrics.

        Args:
            cadence_spm: Steps per minute
            speed_ms: Walking speed in m/s
            stride_length_m: Stride length in meters
            smoothness_score: Keypoint trajectory smoothness (0-100)
            variability_score: Gait cycle-to-cycle variability (0-100)

        Returns:
            EfficiencyMetrics
        """
        try:
            # Efficiency score: balance of speed, smoothness, low variability
            speed_score = min(100.0, (speed_ms / 1.5) * 100)  # Normalize to typical speed
            efficiency = (speed_score * 0.4 + smoothness_score * 0.4 + (100 - variability_score) * 0.2)

            # Energy cost estimate (inverse of efficiency)
            energy_cost = 100.0 - efficiency

            logger.info(
                "metrics.efficiency",
                extra={
                    "efficiency_score": efficiency,
                    "energy_cost": energy_cost,
                    "smoothness": smoothness_score,
                    "variability": variability_score,
                },
            )

            return EfficiencyMetrics(
                walking_efficiency_score=efficiency,
                energy_cost_estimate=energy_cost,
                smoothness_index=smoothness_score,
                variability_index=variability_score,
            )

        except Exception as e:
            logger.error("metrics.efficiency_failed", extra={"error": str(e)})
            return EfficiencyMetrics(
                walking_efficiency_score=0.0,
                energy_cost_estimate=100.0,
                smoothness_index=0.0,
                variability_index=100.0,
            )

    def _symmetry_index(self, left_value: float, right_value: float) -> float:
        """Compute symmetry index (%).

        Formula: |L - R| / (0.5 * (L + R)) * 100

        Args:
            left_value: Left side value
            right_value: Right side value

        Returns:
            Symmetry index in percent (0-100)
        """
        if left_value == 0 and right_value == 0:
            return 0.0

        numerator = abs(left_value - right_value)
        denominator = 0.5 * (abs(left_value) + abs(right_value))

        if denominator == 0:
            return 0.0

        return (numerator / denominator) * 100.0

