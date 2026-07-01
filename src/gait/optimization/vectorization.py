"""Vectorized operations for fast batch processing."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from gait.common.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class BatchMetrics:
    """Metrics for a batch of frames."""
    cadence_spm: np.ndarray  # (batch_size,)
    speed_ms: np.ndarray
    stability_scores: np.ndarray
    processing_time_ms: float


class VectorizedAnalyzer:
    """Vectorized gait analysis for batch processing."""

    def __init__(self, fps: float = 120.0):
        """Initialize vectorized analyzer.

        Args:
            fps: Frame rate
        """
        self.fps = fps

    def compute_cadence_batch(
        self,
        heel_strikes_batch: list[list[int]],
    ) -> np.ndarray:
        """Compute cadence for multiple sequences.

        Args:
            heel_strikes_batch: List of heel strike frame indices per sequence

        Returns:
            Array of cadence values (steps per minute)
        """
        try:
            cadences = []

            for heel_strikes in heel_strikes_batch:
                if len(heel_strikes) < 2:
                    cadences.append(0.0)
                    continue

                # Vectorized difference computation
                intervals = np.diff(heel_strikes)
                interval_s = intervals / self.fps
                cadence = 60.0 / (np.mean(interval_s) * 2) if np.mean(interval_s) > 0 else 0.0
                cadences.append(cadence)

            return np.array(cadences, dtype=np.float32)

        except Exception as e:
            logger.error("vectorization.cadence_failed", extra={"error": str(e)})
            return np.zeros(len(heel_strikes_batch), dtype=np.float32)

    def compute_speed_batch(
        self,
        cadence_spm: np.ndarray,
        stride_length_m: np.ndarray,
    ) -> np.ndarray:
        """Compute speed for batch.

        Args:
            cadence_spm: Array of cadence values
            stride_length_m: Array of stride lengths

        Returns:
            Array of speed values (m/s)
        """
        try:
            # Vectorized operation: speed = (stride * cadence) / 60
            speed = (stride_length_m * cadence_spm) / 60.0
            return np.clip(speed, 0.0, 5.0)  # Clip to reasonable range

        except Exception as e:
            logger.error("vectorization.speed_failed", extra={"error": str(e)})
            return np.zeros_like(cadence_spm)

    def compute_stability_batch(
        self,
        heel_positions_batch: list[np.ndarray],
    ) -> np.ndarray:
        """Compute stability for batch.

        Args:
            heel_positions_batch: List of heel Y-positions per sequence

        Returns:
            Array of stability scores (0-100)
        """
        try:
            stabilities = []

            for heel_pos in heel_positions_batch:
                if len(heel_pos) < 2:
                    stabilities.append(0.0)
                    continue

                # Vectorized variance computation
                variance = np.var(heel_pos)
                stability = max(0.0, 100.0 - (variance * 1000))
                stabilities.append(min(100.0, stability))

            return np.array(stabilities, dtype=np.float32)

        except Exception as e:
            logger.error("vectorization.stability_failed", extra={"error": str(e)})
            return np.zeros(len(heel_positions_batch), dtype=np.float32)

    def compute_symmetry_batch(
        self,
        left_params_batch: list[dict],
        right_params_batch: list[dict],
    ) -> np.ndarray:
        """Compute symmetry indices for batch.

        Args:
            left_params_batch: List of left side parameters
            right_params_batch: List of right side parameters

        Returns:
            Array of symmetry indices (percent)
        """
        try:
            symmetries = []

            for left_params, right_params in zip(left_params_batch, right_params_batch):
                left_val = left_params.get("stride_length_m", 0.0)
                right_val = right_params.get("stride_length_m", 0.0)

                if left_val == 0 and right_val == 0:
                    symmetries.append(0.0)
                    continue

                numerator = abs(left_val - right_val)
                denominator = 0.5 * (abs(left_val) + abs(right_val))

                if denominator == 0:
                    symmetries.append(0.0)
                else:
                    symmetries.append((numerator / denominator) * 100.0)

            return np.array(symmetries, dtype=np.float32)

        except Exception as e:
            logger.error("vectorization.symmetry_failed", extra={"error": str(e)})
            return np.zeros(len(left_params_batch), dtype=np.float32)

    def filter_outliers_batch(
        self,
        values: np.ndarray,
        std_threshold: float = 3.0,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Filter outliers using z-score method.

        Args:
            values: Array of values
            std_threshold: Number of standard deviations for outlier detection

        Returns:
            Tuple of (filtered_values, outlier_mask)
        """
        try:
            if len(values) == 0:
                return values, np.array([], dtype=bool)

            mean = np.mean(values)
            std = np.std(values)

            if std == 0:
                return values, np.zeros(len(values), dtype=bool)

            z_scores = np.abs((values - mean) / std)
            outlier_mask = z_scores > std_threshold

            filtered = values[~outlier_mask]

            logger.debug(
                "vectorization.outliers_filtered",
                extra={"total": len(values), "outliers": np.sum(outlier_mask)},
            )

            return filtered, outlier_mask

        except Exception as e:
            logger.error("vectorization.outlier_filtering_failed", extra={"error": str(e)})
            return values, np.zeros(len(values), dtype=bool)

    def normalize_batch(
        self,
        values: np.ndarray,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
    ) -> np.ndarray:
        """Normalize values to [0, 1] range.

        Args:
            values: Array of values
            min_val: Minimum value (uses data min if None)
            max_val: Maximum value (uses data max if None)

        Returns:
            Normalized array
        """
        try:
            if len(values) == 0:
                return values

            data_min = np.min(values) if min_val is None else min_val
            data_max = np.max(values) if max_val is None else max_val

            if data_min == data_max:
                return np.ones_like(values, dtype=np.float32) * 0.5

            normalized = (values - data_min) / (data_max - data_min)
            return np.clip(normalized, 0.0, 1.0).astype(np.float32)

        except Exception as e:
            logger.error("vectorization.normalization_failed", extra={"error": str(e)})
            return np.zeros_like(values, dtype=np.float32)

    def resample_batch(
        self,
        data_batch: list[np.ndarray],
        target_size: int,
    ) -> list[np.ndarray]:
        """Resample sequences to target size.

        Args:
            data_batch: List of arrays
            target_size: Target size for each array

        Returns:
            List of resampled arrays
        """
        try:
            resampled = []

            for data in data_batch:
                if len(data) == target_size:
                    resampled.append(data)
                    continue

                # Linear interpolation for resampling
                indices = np.linspace(0, len(data) - 1, target_size)
                resampled_data = np.interp(indices, np.arange(len(data)), data)
                resampled.append(resampled_data.astype(np.float32))

            return resampled

        except Exception as e:
            logger.error("vectorization.resampling_failed", extra={"error": str(e)})
            return data_batch

