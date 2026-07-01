"""Fast execution paths for common operations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from gait.common.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class FastPathConfig:
    """Configuration for fast path optimizations."""
    enable_caching: bool = True
    enable_vectorization: bool = True
    batch_size: int = 32
    use_approximations: bool = False  # Use fast approximations instead of exact


class FastPathOptimizer:
    """Applies optimization strategies to critical paths."""

    def __init__(self, config: Optional[FastPathConfig] = None):
        """Initialize optimizer.

        Args:
            config: Fast path configuration
        """
        self.config = config or FastPathConfig()
        self.operation_count = 0
        self.skipped_operations = 0

    def fast_cadence_estimation(
        self,
        heel_strikes: np.ndarray,
    ) -> float:
        """Fast cadence estimation using approximation.

        Args:
            heel_strikes: Array of heel strike frame indices

        Returns:
            Estimated cadence (SPM)
        """
        try:
            if len(heel_strikes) < 2:
                return 0.0

            # Fast path: use median interval instead of mean
            intervals = np.diff(heel_strikes)

            if self.config.use_approximations:
                # Use median for faster computation (less sensitive to outliers)
                median_interval = np.median(intervals)
                cadence = 60.0 / ((median_interval / 120.0) * 2)
                self.operation_count += 1
            else:
                # Exact computation
                mean_interval = np.mean(intervals)
                cadence = 60.0 / ((mean_interval / 120.0) * 2)
                self.operation_count += 1

            return float(np.clip(cadence, 0, 300))

        except Exception as e:
            logger.error("fast_path.cadence_failed", extra={"error": str(e)})
            return 0.0

    def fast_distance_computation(
        self,
        points1: np.ndarray,
        points2: np.ndarray,
    ) -> np.ndarray:
        """Fast pairwise distance computation.

        Args:
            points1: Array of shape (n, 2)
            points2: Array of shape (m, 2)

        Returns:
            Distance matrix of shape (n, m)
        """
        try:
            # Vectorized Euclidean distance
            # ||a-b||^2 = ||a||^2 + ||b||^2 - 2*aÂ·b
            sq1 = np.sum(points1**2, axis=1, keepdims=True)  # (n, 1)
            sq2 = np.sum(points2**2, axis=1, keepdims=True)  # (m, 1)
            dot_product = points1 @ points2.T  # (n, m)

            distances_sq = sq1 + sq2.T - 2 * dot_product
            distances = np.sqrt(np.maximum(distances_sq, 0))  # Avoid negative due to FP error

            self.operation_count += 1
            return distances.astype(np.float32)

        except Exception as e:
            logger.error("fast_path.distance_failed", extra={"error": str(e)})
            return np.array([])

    def fast_filtering(
        self,
        signal: np.ndarray,
        window_size: int = 5,
    ) -> np.ndarray:
        """Fast moving average filtering.

        Args:
            signal: 1D signal array
            window_size: Averaging window size

        Returns:
            Filtered signal
        """
        try:
            if len(signal) < window_size:
                return signal

            # Use numpy convolve for fast moving average
            window = np.ones(window_size) / window_size
            filtered = np.convolve(signal, window, mode="same")

            self.operation_count += 1
            return filtered.astype(np.float32)

        except Exception as e:
            logger.error("fast_path.filtering_failed", extra={"error": str(e)})
            return signal

    def fast_peak_detection(
        self,
        signal: np.ndarray,
        min_distance: int = 10,
    ) -> np.ndarray:
        """Fast peak detection without scipy dependency.

        Args:
            signal: 1D signal array
            min_distance: Minimum distance between peaks

        Returns:
            Array of peak indices
        """
        try:
            if len(signal) < 3:
                return np.array([])

            # Find local maxima: signal[i] > signal[i-1] and signal[i] > signal[i+1]
            maxima = (signal[1:-1] > signal[:-2]) & (signal[1:-1] > signal[2:])
            peak_indices = np.where(maxima)[0] + 1

            # Apply minimum distance constraint
            if len(peak_indices) > 1:
                filtered_peaks = [peak_indices[0]]
                for peak in peak_indices[1:]:
                    if peak - filtered_peaks[-1] >= min_distance:
                        filtered_peaks.append(peak)
                peak_indices = np.array(filtered_peaks)

            self.operation_count += 1
            return peak_indices.astype(np.int32)

        except Exception as e:
            logger.error("fast_path.peak_detection_failed", extra={"error": str(e)})
            return np.array([])

    def fast_correlation(
        self,
        signal1: np.ndarray,
        signal2: np.ndarray,
    ) -> float:
        """Fast Pearson correlation coefficient.

        Args:
            signal1: First signal
            signal2: Second signal

        Returns:
            Correlation coefficient (-1 to 1)
        """
        try:
            if len(signal1) != len(signal2) or len(signal1) < 2:
                return 0.0

            # Vectorized correlation: cov / (std1 * std2)
            mean1 = np.mean(signal1)
            mean2 = np.mean(signal2)

            cov = np.mean((signal1 - mean1) * (signal2 - mean2))
            std1 = np.std(signal1)
            std2 = np.std(signal2)

            if std1 == 0 or std2 == 0:
                return 0.0

            correlation = cov / (std1 * std2)
            self.operation_count += 1

            return float(np.clip(correlation, -1.0, 1.0))

        except Exception as e:
            logger.error("fast_path.correlation_failed", extra={"error": str(e)})
            return 0.0

    def get_performance_summary(self) -> dict:
        """Get fast path performance summary.

        Returns:
            Summary dictionary
        """
        return {
            "total_operations": self.operation_count,
            "skipped_operations": self.skipped_operations,
            "caching_enabled": self.config.enable_caching,
            "vectorization_enabled": self.config.enable_vectorization,
            "using_approximations": self.config.use_approximations,
        }

