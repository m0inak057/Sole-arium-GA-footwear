"""Clinical validation metrics and performance evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from src.gait.common.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationMetrics:
    """Comprehensive validation performance metrics."""
    accuracy: float  # 0-1
    sensitivity: float  # True positive rate
    specificity: float  # True negative rate
    precision: float  # Positive predictive value
    f1_score: float  # Harmonic mean of precision/recall
    auc_roc: float  # Area under ROC curve
    mcc: float  # Matthews correlation coefficient
    confidence_interval_95: tuple[float, float]


@dataclass
class ErrorMetrics:
    """Error analysis metrics."""
    mae: float  # Mean absolute error
    rmse: float  # Root mean square error
    mape: float  # Mean absolute percentage error
    bias: float  # Systematic error
    correlation: float  # Pearson correlation with gold standard


class PerformanceValidator:
    """Validates performance against gold standard measurements."""

    def __init__(self):
        """Initialize validator."""
        pass

    def compute_metrics(
        self,
        predicted: np.ndarray,
        actual: np.ndarray,
        threshold: float = 0.5,
    ) -> ValidationMetrics:
        """Compute validation metrics for binary classification.

        Args:
            predicted: Predicted values (probabilities or binary)
            actual: Ground truth labels
            threshold: Classification threshold (for probabilities)

        Returns:
            ValidationMetrics with all performance measures
        """
        try:
            # Convert to binary if needed
            pred_binary = (predicted >= threshold).astype(int)
            actual_binary = actual.astype(int)

            # Confusion matrix
            tp = np.sum((pred_binary == 1) & (actual_binary == 1))
            tn = np.sum((pred_binary == 0) & (actual_binary == 0))
            fp = np.sum((pred_binary == 1) & (actual_binary == 0))
            fn = np.sum((pred_binary == 0) & (actual_binary == 1))

            # Metrics
            accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0.0
            sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            f1 = (2 * precision * sensitivity) / (precision + sensitivity) if (precision + sensitivity) > 0 else 0.0

            # Matthews correlation coefficient
            denom = np.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
            mcc = ((tp * tn) - (fp * fn)) / denom if denom > 0 else 0.0

            # AUC-ROC (approximate using trapezoidal rule)
            auc = self._compute_auc_roc(predicted, actual)

            # 95% confidence interval for accuracy
            ci = self._compute_confidence_interval(accuracy, len(actual), confidence=0.95)

            logger.info(
                "validation.metrics",
                extra={
                    "accuracy": round(accuracy, 3),
                    "sensitivity": round(sensitivity, 3),
                    "specificity": round(specificity, 3),
                    "f1": round(f1, 3),
                },
            )

            return ValidationMetrics(
                accuracy=accuracy,
                sensitivity=sensitivity,
                specificity=specificity,
                precision=precision,
                f1_score=f1,
                auc_roc=auc,
                mcc=mcc,
                confidence_interval_95=ci,
            )

        except Exception as e:
            logger.error("validation.metrics_failed", extra={"error": str(e)})
            return ValidationMetrics(
                accuracy=0.0,
                sensitivity=0.0,
                specificity=0.0,
                precision=0.0,
                f1_score=0.0,
                auc_roc=0.0,
                mcc=0.0,
                confidence_interval_95=(0.0, 0.0),
            )

    def compute_error_metrics(
        self,
        predicted: np.ndarray,
        actual: np.ndarray,
    ) -> ErrorMetrics:
        """Compute error analysis metrics for regression.

        Args:
            predicted: Predicted values
            actual: Ground truth values

        Returns:
            ErrorMetrics with error measures
        """
        try:
            if len(predicted) != len(actual):
                logger.error("validation.length_mismatch")
                return ErrorMetrics(
                    mae=0.0,
                    rmse=0.0,
                    mape=0.0,
                    bias=0.0,
                    correlation=0.0,
                )

            # Error computations
            errors = predicted - actual
            mae = np.mean(np.abs(errors))
            rmse = np.sqrt(np.mean(errors**2))

            # MAPE (percentage error)
            nonzero_mask = actual != 0
            mape = 0.0
            if np.any(nonzero_mask):
                percentage_errors = np.abs(errors[nonzero_mask]) / np.abs(actual[nonzero_mask])
                mape = np.mean(percentage_errors) * 100

            # Bias (systematic error)
            bias = np.mean(errors)

            # Correlation
            correlation = np.corrcoef(predicted, actual)[0, 1] if len(predicted) > 1 else 0.0
            correlation = 0.0 if np.isnan(correlation) else correlation

            logger.info(
                "validation.error_metrics",
                extra={
                    "mae": round(mae, 3),
                    "rmse": round(rmse, 3),
                    "bias": round(bias, 3),
                },
            )

            return ErrorMetrics(
                mae=mae,
                rmse=rmse,
                mape=mape,
                bias=bias,
                correlation=correlation,
            )

        except Exception as e:
            logger.error("validation.error_metrics_failed", extra={"error": str(e)})
            return ErrorMetrics(
                mae=0.0,
                rmse=0.0,
                mape=0.0,
                bias=0.0,
                correlation=0.0,
            )

    def _compute_auc_roc(self, predicted: np.ndarray, actual: np.ndarray) -> float:
        """Compute area under ROC curve."""
        try:
            # Sort by predicted score
            sorted_indices = np.argsort(-predicted)
            actual_sorted = actual[sorted_indices]

            # Compute TPR and FPR at each threshold
            n_pos = np.sum(actual == 1)
            n_neg = np.sum(actual == 0)

            if n_pos == 0 or n_neg == 0:
                return 0.5

            tpr_list = [0]
            fpr_list = [0]

            for i in range(len(actual_sorted)):
                tp = np.sum(actual_sorted[:i + 1] == 1)
                fp = i + 1 - tp
                tpr = tp / n_pos
                fpr = fp / n_neg
                tpr_list.append(tpr)
                fpr_list.append(fpr)

            # Trapezoidal rule for AUC
            auc = 0.0
            for i in range(1, len(fpr_list)):
                auc += (fpr_list[i] - fpr_list[i - 1]) * (tpr_list[i] + tpr_list[i - 1]) / 2

            return float(np.clip(auc, 0.0, 1.0))

        except Exception:
            return 0.5

    def _compute_confidence_interval(
        self,
        proportion: float,
        n: int,
        confidence: float = 0.95,
    ) -> tuple[float, float]:
        """Compute Wilson confidence interval for proportion."""
        try:
            if n == 0:
                return (0.0, 0.0)

            # Z-score for confidence level
            z = 1.96 if confidence == 0.95 else 1.645

            center = (proportion + z**2 / (2 * n)) / (1 + z**2 / n)
            margin = z * np.sqrt(
                (proportion * (1 - proportion) / n) + (z**2 / (4 * n**2))
            ) / (1 + z**2 / n)

            lower = max(0.0, center - margin)
            upper = min(1.0, center + margin)

            return (lower, upper)

        except Exception:
            return (0.0, 1.0)
