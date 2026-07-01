"""Real-time gait analysis with streaming frame processing."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from gait.common.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class RealtimeGaitMetrics:
    """Metrics computed in real-time during video playback."""
    frame_index: int
    timestamp_ms: float
    is_valid: bool
    current_cadence_spm: Optional[float] = None
    current_speed_ms: Optional[float] = None
    stability_score: Optional[float] = None  # 0-100
    balance_quality: Optional[float] = None  # 0-100


@dataclass
class StreamingBuffer:
    """Circular buffer for computing windowed metrics."""
    window_frames: int
    heel_positions: list[float] = field(default_factory=list)
    timestamps_ms: list[float] = field(default_factory=list)
    confidence_scores: list[float] = field(default_factory=list)

    def add_frame(
        self,
        heel_y: float,
        timestamp_ms: float,
        confidence: float,
    ) -> None:
        """Add frame to buffer."""
        self.heel_positions.append(heel_y)
        self.timestamps_ms.append(timestamp_ms)
        self.confidence_scores.append(confidence)

        # Maintain window size
        if len(self.heel_positions) > self.window_frames:
            self.heel_positions.pop(0)
            self.timestamps_ms.pop(0)
            self.confidence_scores.pop(0)

    def is_full(self) -> bool:
        """Check if buffer has reached window size."""
        return len(self.heel_positions) == self.window_frames

    def clear(self) -> None:
        """Clear buffer."""
        self.heel_positions.clear()
        self.timestamps_ms.clear()
        self.confidence_scores.clear()


class RealtimeProcessor:
    """Processes gait frames in real-time for live feedback."""

    def __init__(self, fps: float = 120.0, window_seconds: float = 2.0):
        """Initialize real-time processor.

        Args:
            fps: Frame rate
            window_seconds: Window size for windowed metrics
        """
        self.fps = fps
        self.window_frames = int(fps * window_seconds)
        self.buffer = StreamingBuffer(window_frames=self.window_frames)

    def process_frame(
        self,
        frame_index: int,
        timestamp_ms: float,
        heel_y: float,
        ankle_y: float,
        confidence: float,
    ) -> RealtimeGaitMetrics:
        """Process single frame for real-time metrics.

        Args:
            frame_index: Frame number
            timestamp_ms: Timestamp in milliseconds
            heel_y: Heel vertical position
            ankle_y: Ankle vertical position
            confidence: Keypoint detection confidence

        Returns:
            RealtimeGaitMetrics for current frame
        """
        try:
            self.buffer.add_frame(heel_y, timestamp_ms, confidence)

            # Only compute metrics once buffer is full
            if not self.buffer.is_full():
                logger.debug("realtime.buffer_filling", extra={"progress": len(self.buffer.heel_positions)})
                return RealtimeGaitMetrics(
                    frame_index=frame_index,
                    timestamp_ms=timestamp_ms,
                    is_valid=False,
                )

            # Compute windowed metrics
            cadence = self._estimate_cadence()
            speed = self._estimate_speed()
            stability = self._compute_stability()
            balance = self._compute_balance(ankle_y)

            logger.info(
                "realtime.frame_metrics",
                extra={
                    "frame": frame_index,
                    "cadence": cadence,
                    "stability": stability,
                },
            )

            return RealtimeGaitMetrics(
                frame_index=frame_index,
                timestamp_ms=timestamp_ms,
                is_valid=True,
                current_cadence_spm=cadence,
                current_speed_ms=speed,
                stability_score=stability,
                balance_quality=balance,
            )

        except Exception as e:
            logger.error("realtime.processing_failed", extra={"error": str(e)})
            return RealtimeGaitMetrics(
                frame_index=frame_index,
                timestamp_ms=timestamp_ms,
                is_valid=False,
            )

    def reset(self) -> None:
        """Reset processor state."""
        self.buffer.clear()
        logger.debug("realtime.reset")

    def _estimate_cadence(self) -> float:
        """Estimate cadence from buffered heel strikes."""
        try:
            if len(self.buffer.heel_positions) < 3:
                return 0.0

            # Find local minima (heel contacts)
            heel_array = np.array(self.buffer.heel_positions)
            minima = self._find_local_minima(heel_array)

            if len(minima) < 2:
                return 0.0

            # Average interval between heel strikes
            intervals = np.diff(minima)
            avg_interval_frames = np.mean(intervals)
            avg_interval_s = avg_interval_frames / self.fps

            # Convert to steps per minute (stride = 2 steps)
            cadence = 60.0 / (avg_interval_s * 2) if avg_interval_s > 0 else 0.0
            return float(cadence)

        except Exception as e:
            logger.error("realtime.cadence_failed", extra={"error": str(e)})
            return 0.0

    def _estimate_speed(self) -> float:
        """Estimate walking speed."""
        try:
            cadence = self._estimate_cadence()
            if cadence == 0:
                return 0.0

            # Heuristic: typical stride length is ~0.7m per 120-bpm cadence
            stride_length_m = 0.7 * (cadence / 120.0)
            speed_ms = (stride_length_m * cadence) / 60.0

            return float(speed_ms)

        except Exception:
            return 0.0

    def _compute_stability(self) -> float:
        """Compute gait stability (0-100) based on variability."""
        try:
            if len(self.buffer.heel_positions) < 2:
                return 0.0

            # Lower variance = higher stability
            heel_array = np.array(self.buffer.heel_positions)
            variance = np.var(heel_array)

            # Normalize: variance > 0.1 â†’ 0, variance == 0 â†’ 100
            stability = max(0.0, 100.0 - (variance * 1000))
            return float(min(100.0, stability))

        except Exception:
            return 0.0

    def _compute_balance(self, ankle_y: float) -> float:
        """Compute balance quality (0-100)."""
        try:
            if len(self.buffer.heel_positions) == 0:
                return 0.0

            # Balance score based on ankle stability (low variance in ankle position)
            # This is a placeholder; real implementation would track ankle over time
            balance_score = 75.0  # Default to good balance

            return float(balance_score)

        except Exception:
            return 0.0

    def _find_local_minima(self, data: np.ndarray) -> list[int]:
        """Find indices of local minima in array."""
        try:
            if len(data) < 3:
                return []

            minima = []
            for i in range(1, len(data) - 1):
                if data[i] < data[i - 1] and data[i] < data[i + 1]:
                    minima.append(i)

            return minima

        except Exception:
            return []

