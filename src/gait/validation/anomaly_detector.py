"""Anomaly detection for out-of-range and suspicious gait patterns."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from src.gait.common.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class AnomalyFlag:
    """Single anomaly detection flag."""
    severity: str  # "info", "warning", "critical"
    anomaly_type: str  # "outlier", "impossible", "suspicious", "device_failure"
    description: str
    affected_parameter: str
    value: float
    expected_range: tuple[float, float]


@dataclass
class AnomalyReport:
    """Report of detected anomalies."""
    total_samples: int
    anomalies_detected: int
    anomaly_rate: float
    flags: list[AnomalyFlag]
    data_quality_score: float  # 0-100


class AnomalyDetector:
    """Detects anomalies in gait measurements."""

    def __init__(self):
        """Initialize anomaly detector."""
        # Clinical reference ranges
        self.cadence_range = (60, 140)  # steps per minute
        self.speed_range = (0.5, 2.5)  # m/s
        self.stride_length_range = (0.3, 1.0)  # meters
        self.stability_min = 20.0  # minimum stability score
        self.symmetry_max = 30.0  # maximum acceptable asymmetry %

    def detect_anomalies(
        self,
        cadence_values: np.ndarray,
        speed_values: np.ndarray,
        stride_lengths: np.ndarray,
        stability_scores: np.ndarray,
        symmetry_indices: np.ndarray,
    ) -> AnomalyReport:
        """Detect anomalies across all gait parameters.

        Args:
            cadence_values: Array of cadence measurements
            speed_values: Array of speed measurements
            stride_lengths: Array of stride lengths
            stability_scores: Array of stability scores
            symmetry_indices: Array of asymmetry percentages

        Returns:
            AnomalyReport with all detected flags
        """
        try:
            flags = []

            # Check cadence
            cadence_flags = self._check_range(
                cadence_values,
                self.cadence_range,
                "cadence_spm",
                severity_factor=1.5,
            )
            flags.extend(cadence_flags)

            # Check speed
            speed_flags = self._check_range(
                speed_values,
                self.speed_range,
                "speed_ms",
                severity_factor=1.5,
            )
            flags.extend(speed_flags)

            # Check stride length
            stride_flags = self._check_range(
                stride_lengths,
                self.stride_length_range,
                "stride_length_m",
                severity_factor=1.5,
            )
            flags.extend(stride_flags)

            # Check stability
            stability_flags = self._check_minimum(
                stability_scores,
                self.stability_min,
                "stability_score",
            )
            flags.extend(stability_flags)

            # Check symmetry
            symmetry_flags = self._check_maximum(
                symmetry_indices,
                self.symmetry_max,
                "symmetry_index",
            )
            flags.extend(symmetry_flags)

            # Compute statistics
            total_samples = len(cadence_values)
            anomaly_count = len(flags)
            anomaly_rate = anomaly_count / total_samples if total_samples > 0 else 0.0

            # Quality score (inverse of anomaly rate)
            quality_score = max(0.0, 100.0 - (anomaly_rate * 100))

            logger.info(
                "validation.anomalies_detected",
                extra={
                    "total": total_samples,
                    "anomalies": anomaly_count,
                    "rate": round(anomaly_rate, 3),
                    "quality_score": round(quality_score, 1),
                },
            )

            return AnomalyReport(
                total_samples=total_samples,
                anomalies_detected=anomaly_count,
                anomaly_rate=anomaly_rate,
                flags=flags,
                data_quality_score=quality_score,
            )

        except Exception as e:
            logger.error("validation.anomaly_detection_failed", extra={"error": str(e)})
            return AnomalyReport(
                total_samples=0,
                anomalies_detected=0,
                anomaly_rate=0.0,
                flags=[],
                data_quality_score=0.0,
            )

    def detect_pattern_anomalies(
        self,
        heel_positions: np.ndarray,
        ankle_positions: np.ndarray,
    ) -> list[AnomalyFlag]:
        """Detect anomalies in movement patterns.

        Args:
            heel_positions: Time series of heel positions
            ankle_positions: Time series of ankle positions

        Returns:
            List of detected pattern anomalies
        """
        try:
            flags = []

            # Check for impossible movements (sudden jumps)
            heel_diffs = np.abs(np.diff(heel_positions))
            ankle_diffs = np.abs(np.diff(ankle_positions))

            # Threshold: 20% position change per frame is suspicious
            heel_jumps = np.where(heel_diffs > 0.2)[0]
            ankle_jumps = np.where(ankle_diffs > 0.2)[0]

            for idx in heel_jumps:
                flags.append(AnomalyFlag(
                    severity="critical",
                    anomaly_type="impossible",
                    description=f"Sudden heel position jump at frame {idx}",
                    affected_parameter="heel_position",
                    value=float(heel_diffs[idx]),
                    expected_range=(0.0, 0.2),
                ))

            for idx in ankle_jumps:
                flags.append(AnomalyFlag(
                    severity="critical",
                    anomaly_type="impossible",
                    description=f"Sudden ankle position jump at frame {idx}",
                    affected_parameter="ankle_position",
                    value=float(ankle_diffs[idx]),
                    expected_range=(0.0, 0.2),
                ))

            # Check for zero movement (device failure)
            if np.std(heel_positions) < 0.01 or np.std(ankle_positions) < 0.01:
                flags.append(AnomalyFlag(
                    severity="critical",
                    anomaly_type="device_failure",
                    description="No movement detected (possible sensor failure)",
                    affected_parameter="movement",
                    value=0.0,
                    expected_range=(0.01, 1.0),
                ))

            return flags

        except Exception as e:
            logger.error("validation.pattern_anomaly_detection_failed", extra={"error": str(e)})
            return []

    def _check_range(
        self,
        values: np.ndarray,
        expected_range: tuple[float, float],
        parameter_name: str,
        severity_factor: float = 1.0,
    ) -> list[AnomalyFlag]:
        """Check if values fall within expected range."""
        try:
            flags = []
            min_val, max_val = expected_range

            # Find outliers
            out_of_range = (values < min_val) | (values > max_val)
            outlier_indices = np.where(out_of_range)[0]

            for idx in outlier_indices:
                value = float(values[idx])

                # Determine severity based on distance from range
                if value < min_val:
                    distance = min_val - value
                else:
                    distance = value - max_val

                distance_pct = distance / (max_val - min_val)
                severity = "info"
                if distance_pct > severity_factor:
                    severity = "critical"
                elif distance_pct > severity_factor * 0.5:
                    severity = "warning"

                flags.append(AnomalyFlag(
                    severity=severity,
                    anomaly_type="outlier",
                    description=f"{parameter_name} out of range: {value:.2f}",
                    affected_parameter=parameter_name,
                    value=value,
                    expected_range=expected_range,
                ))

            return flags

        except Exception:
            return []

    def _check_minimum(
        self,
        values: np.ndarray,
        minimum: float,
        parameter_name: str,
    ) -> list[AnomalyFlag]:
        """Check if values meet minimum threshold."""
        try:
            flags = []
            below_min = values < minimum

            for idx in np.where(below_min)[0]:
                value = float(values[idx])
                flags.append(AnomalyFlag(
                    severity="warning",
                    anomaly_type="outlier",
                    description=f"{parameter_name} below minimum: {value:.2f} < {minimum}",
                    affected_parameter=parameter_name,
                    value=value,
                    expected_range=(minimum, float("inf")),
                ))

            return flags

        except Exception:
            return []

    def _check_maximum(
        self,
        values: np.ndarray,
        maximum: float,
        parameter_name: str,
    ) -> list[AnomalyFlag]:
        """Check if values stay below maximum threshold."""
        try:
            flags = []
            above_max = values > maximum

            for idx in np.where(above_max)[0]:
                value = float(values[idx])
                flags.append(AnomalyFlag(
                    severity="warning",
                    anomaly_type="outlier",
                    description=f"{parameter_name} exceeds maximum: {value:.2f} > {maximum}",
                    affected_parameter=parameter_name,
                    value=value,
                    expected_range=(0.0, maximum),
                ))

            return flags

        except Exception:
            return []
