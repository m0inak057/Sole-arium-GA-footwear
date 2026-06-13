"""Gold standard comparison and validation against reference measurements."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from src.gait.common.logging_utils import get_logger
from src.gait.validation.metrics import PerformanceValidator, ErrorMetrics

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """Result of gold standard comparison."""
    parameter_name: str
    mean_predicted: float
    mean_reference: float
    mean_absolute_error: float
    percentage_error: float
    correlation: float
    passes_validation: bool  # Within acceptable tolerance
    confidence_level: float  # 0-1


@dataclass
class GoldStandardReport:
    """Complete gold standard validation report."""
    total_parameters: int
    parameters_validated: int
    validation_pass_rate: float
    results: list[ValidationResult]
    overall_confidence: float


class GoldStandardComparator:
    """Compares system measurements against gold standard references."""

    def __init__(self):
        """Initialize comparator."""
        # Acceptable error tolerances for each parameter
        self.tolerances = {
            "cadence_spm": 5.0,  # ±5 SPM
            "speed_ms": 0.1,  # ±0.1 m/s
            "stride_length_m": 0.05,  # ±5 cm
            "pronation_angle_deg": 3.0,  # ±3 degrees
            "stance_time_pct": 5.0,  # ±5 percentage points
        }
        self.validator = PerformanceValidator()

    def compare_cadence(
        self,
        predicted_cadence: np.ndarray,
        reference_cadence: np.ndarray,
    ) -> ValidationResult:
        """Compare cadence against gold standard.

        Args:
            predicted_cadence: Predicted cadence values
            reference_cadence: Reference (gold standard) values

        Returns:
            ValidationResult with comparison metrics
        """
        return self._compare_parameter(
            predicted_cadence,
            reference_cadence,
            "cadence_spm",
        )

    def compare_speed(
        self,
        predicted_speed: np.ndarray,
        reference_speed: np.ndarray,
    ) -> ValidationResult:
        """Compare walking speed against gold standard."""
        return self._compare_parameter(
            predicted_speed,
            reference_speed,
            "speed_ms",
        )

    def compare_stride_length(
        self,
        predicted_stride: np.ndarray,
        reference_stride: np.ndarray,
    ) -> ValidationResult:
        """Compare stride length against gold standard."""
        return self._compare_parameter(
            predicted_stride,
            reference_stride,
            "stride_length_m",
        )

    def compare_all_parameters(
        self,
        predicted: dict[str, np.ndarray],
        reference: dict[str, np.ndarray],
    ) -> GoldStandardReport:
        """Compare all available parameters.

        Args:
            predicted: Dictionary of predicted measurements
            reference: Dictionary of reference measurements

        Returns:
            GoldStandardReport with all comparisons
        """
        try:
            results = []

            for param_name in predicted.keys():
                if param_name not in reference:
                    logger.warning(
                        "validation.missing_reference",
                        extra={"parameter": param_name},
                    )
                    continue

                result = self._compare_parameter(
                    predicted[param_name],
                    reference[param_name],
                    param_name,
                )
                results.append(result)

            # Calculate aggregate statistics
            total = len(results)
            passed = sum(1 for r in results if r.passes_validation)
            pass_rate = passed / total if total > 0 else 0.0
            mean_confidence = np.mean([r.confidence_level for r in results]) if results else 0.0

            logger.info(
                "validation.gold_standard_report",
                extra={
                    "total_parameters": total,
                    "passed": passed,
                    "pass_rate": round(pass_rate, 3),
                    "overall_confidence": round(mean_confidence, 3),
                },
            )

            return GoldStandardReport(
                total_parameters=total,
                parameters_validated=total,
                validation_pass_rate=pass_rate,
                results=results,
                overall_confidence=mean_confidence,
            )

        except Exception as e:
            logger.error("validation.gold_standard_failed", extra={"error": str(e)})
            return GoldStandardReport(
                total_parameters=0,
                parameters_validated=0,
                validation_pass_rate=0.0,
                results=[],
                overall_confidence=0.0,
            )

    def _compare_parameter(
        self,
        predicted: np.ndarray,
        reference: np.ndarray,
        parameter_name: str,
    ) -> ValidationResult:
        """Compare single parameter against gold standard."""
        try:
            if len(predicted) != len(reference):
                logger.error("validation.length_mismatch", extra={"parameter": parameter_name})
                return ValidationResult(
                    parameter_name=parameter_name,
                    mean_predicted=0.0,
                    mean_reference=0.0,
                    mean_absolute_error=0.0,
                    percentage_error=0.0,
                    correlation=0.0,
                    passes_validation=False,
                    confidence_level=0.0,
                )

            # Compute error metrics
            error_metrics = self.validator.compute_error_metrics(predicted, reference)

            # Check against tolerance
            tolerance = self.tolerances.get(parameter_name, float("inf"))
            passes = error_metrics.mae <= tolerance

            # Confidence = inverse of error relative to tolerance
            confidence = max(0.0, 1.0 - (error_metrics.mae / tolerance))

            logger.info(
                "validation.parameter_comparison",
                extra={
                    "parameter": parameter_name,
                    "mae": round(error_metrics.mae, 3),
                    "tolerance": tolerance,
                    "passes": passes,
                    "confidence": round(confidence, 3),
                },
            )

            return ValidationResult(
                parameter_name=parameter_name,
                mean_predicted=float(np.mean(predicted)),
                mean_reference=float(np.mean(reference)),
                mean_absolute_error=error_metrics.mae,
                percentage_error=error_metrics.mape,
                correlation=error_metrics.correlation,
                passes_validation=passes,
                confidence_level=float(np.clip(confidence, 0.0, 1.0)),
            )

        except Exception as e:
            logger.error(
                "validation.parameter_comparison_failed",
                extra={"parameter": parameter_name, "error": str(e)},
            )
            return ValidationResult(
                parameter_name=parameter_name,
                mean_predicted=0.0,
                mean_reference=0.0,
                mean_absolute_error=0.0,
                percentage_error=0.0,
                correlation=0.0,
                passes_validation=False,
                confidence_level=0.0,
            )
