"""Gait event detection (heel strike, toe off)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy import signal

from src.gait.common.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class GaitEvent:
    """Single gait event (heel strike or toe off)."""
    frame_index: int
    timestamp_ms: float
    event_type: str  # "heel_strike" or "toe_off"
    confidence: float


class GaitEventDetector:
    """Detects gait events from keypoint trajectories."""

    def __init__(
        self,
        fps: float = 120.0,
        filter_order: int = 4,
        heel_strike_threshold: float = -0.1,
    ):
        """Initialize gait event detector.

        Args:
            fps: Frame rate in Hz
            filter_order: Butterworth filter order
            heel_strike_threshold: Velocity threshold for heel strike detection
        """
        self.fps = fps
        self.filter_order = filter_order
        self.heel_strike_threshold = heel_strike_threshold

    def detect_heel_strikes(
        self,
        heel_y: np.ndarray,
        timestamps: np.ndarray,
        confidence_threshold: float = 0.5,
    ) -> list[GaitEvent]:
        """Detect heel strike events from heel vertical position.

        Args:
            heel_y: Heel Y-position over time (normalized 0-1)
            timestamps: Timestamps in milliseconds
            confidence_threshold: Min confidence to accept detection

        Returns:
            List of GaitEvent objects for heel strikes
        """
        if len(heel_y) < 10:
            logger.warning("gait_event.insufficient_frames")
            return []

        try:
            # Filter heel trajectory
            filtered_heel = self._bandpass_filter(heel_y)

            # Detect minima (heel strike = lowest point)
            peaks, properties = signal.find_peaks(
                -filtered_heel,  # Invert to find minima
                distance=int(self.fps * 0.3),  # Min 300ms between strikes
                prominence=0.05,
            )

            events = []
            for peak_idx in peaks:
                if peak_idx < len(timestamps):
                    events.append(GaitEvent(
                        frame_index=int(peak_idx),
                        timestamp_ms=float(timestamps[peak_idx]),
                        event_type="heel_strike",
                        confidence=min(1.0, properties["prominences"][list(peaks).index(peak_idx)] * 10),
                    ))

            logger.info(
                "gait_event.heel_strikes_detected",
                extra={"count": len(events)},
            )
            return events

        except Exception as e:
            logger.error("gait_event.detection_failed", extra={"error": str(e)})
            return []

    def detect_toe_offs(
        self,
        toe_y: np.ndarray,
        heel_y: np.ndarray,
        timestamps: np.ndarray,
    ) -> list[GaitEvent]:
        """Detect toe off events (rapid upward motion of toe).

        Args:
            toe_y: Toe Y-position over time
            heel_y: Heel Y-position over time
            timestamps: Timestamps in milliseconds

        Returns:
            List of GaitEvent objects for toe offs
        """
        if len(toe_y) < 10:
            logger.warning("gait_event.insufficient_frames")
            return []

        try:
            # Compute vertical velocity
            velocity = np.diff(toe_y, prepend=toe_y[0])

            # Toe off = rapid upward motion (negative velocity in image coords)
            peaks, _ = signal.find_peaks(
                -velocity,  # Invert for upward motion
                distance=int(self.fps * 0.2),  # Min 200ms between toe-offs
                height=-0.5,
            )

            events = []
            for peak_idx in peaks:
                if peak_idx < len(timestamps):
                    events.append(GaitEvent(
                        frame_index=int(peak_idx),
                        timestamp_ms=float(timestamps[peak_idx]),
                        event_type="toe_off",
                        confidence=0.7,  # Heuristic confidence
                    ))

            logger.info(
                "gait_event.toe_offs_detected",
                extra={"count": len(events)},
            )
            return events

        except Exception as e:
            logger.error("gait_event.toe_off_detection_failed", extra={"error": str(e)})
            return []

    def _bandpass_filter(self, signal_data: np.ndarray) -> np.ndarray:
        """Apply Butterworth bandpass filter to isolate gait frequency.

        Args:
            signal_data: Input signal

        Returns:
            Filtered signal
        """
        try:
            # Gait frequency ~1-3 Hz
            nyquist = self.fps / 2
            low = 0.5 / nyquist
            high = 3.0 / nyquist

            # Clamp to valid range
            low = max(0.001, min(low, 0.999))
            high = max(0.001, min(high, 0.999))

            if low >= high:
                return signal_data

            b, a = signal.butter(
                self.filter_order,
                [low, high],
                btype="band",
            )
            return signal.filtfilt(b, a, signal_data)

        except Exception as e:
            logger.warning("gait_event.filter_failed", extra={"error": str(e)})
            return signal_data
