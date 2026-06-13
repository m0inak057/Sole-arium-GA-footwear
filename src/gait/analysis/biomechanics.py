"""Biomechanical parameter computation from gait cycles."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np

from src.gait.common.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class BiomechanicalParams:
    """Computed biomechanical parameters."""
    cadence_spm: float  # steps per minute
    speed_ms: float  # m/s
    stride_length_m: float  # meters
    stance_time_pct: float  # % of cycle
    swing_time_pct: float  # % of cycle
    foot_strike_angle_deg: float  # degrees
    rearfoot_angle_deg: float  # degrees (pronation)
    arch_height_index: float  # normalized 0-1


class BiomechanicsAnalyzer:
    """Computes biomechanical parameters from keypoint data."""

    def __init__(self, fps: float = 120.0, height_m: float = 1.7):
        """Initialize analyzer.

        Args:
            fps: Frame rate
            height_m: Subject height in meters (for scaling)
        """
        self.fps = fps
        self.height_m = height_m

    def compute_spatiotemporal(
        self,
        heel_strikes: List[int],
        cycle_duration_frames: int,
        frame_width: int,
    ) -> BiomechanicalParams:
        """Compute spatiotemporal parameters.

        Args:
            heel_strikes: Frame indices of heel strikes
            cycle_duration_frames: Duration of one gait cycle in frames
            frame_width: Video frame width in pixels

        Returns:
            BiomechanicalParams with computed values
        """
        try:
            # Cadence = number of steps per minute
            if len(heel_strikes) < 2:
                cadence = 0.0
            else:
                step_interval_frames = np.mean(np.diff(heel_strikes))
                step_interval_s = step_interval_frames / self.fps
                cadence = 60.0 / (step_interval_s * 2)  # *2 for bilateral

            # Cycle time and speeds (use height for scaling)
            cycle_time_s = cycle_duration_frames / self.fps
            stride_length_m = self.height_m * 0.43  # Heuristic: ~43% of height

            # Speed approximation
            speed_ms = stride_length_m / cycle_time_s if cycle_time_s > 0 else 0.0

            logger.info(
                "biomechanics.spatiotemporal",
                extra={
                    "cadence_spm": cadence,
                    "speed_ms": speed_ms,
                    "stride_length_m": stride_length_m,
                },
            )

            return BiomechanicalParams(
                cadence_spm=cadence,
                speed_ms=speed_ms,
                stride_length_m=stride_length_m,
                stance_time_pct=60.0,  # Typical stance is ~60% of cycle
                swing_time_pct=40.0,
                foot_strike_angle_deg=0.0,  # Placeholder
                rearfoot_angle_deg=0.0,  # Placeholder
                arch_height_index=0.5,  # Placeholder
            )

        except Exception as e:
            logger.error("biomechanics.computation_failed", extra={"error": str(e)})
            return BiomechanicalParams(
                cadence_spm=0.0,
                speed_ms=0.0,
                stride_length_m=0.0,
                stance_time_pct=0.0,
                swing_time_pct=0.0,
                foot_strike_angle_deg=0.0,
                rearfoot_angle_deg=0.0,
                arch_height_index=0.0,
            )

    def compute_pronation(
        self,
        ankle_pos: np.ndarray,  # (n_frames, 2) in image coords
        heel_pos: np.ndarray,
        achilles_pos: np.ndarray,
    ) -> float:
        """Estimate rearfoot angle (pronation indicator).

        Args:
            ankle_pos: Ankle keypoint positions
            heel_pos: Heel keypoint positions
            achilles_pos: Achilles tendon position

        Returns:
            Rearfoot angle in degrees (-10 to +10 typical range)
        """
        try:
            if len(ankle_pos) < 2 or len(heel_pos) < 2:
                return 0.0

            # Vector from heel to ankle
            diff = ankle_pos - heel_pos
            angle_rad = np.arctan2(diff[:, 1], diff[:, 0])
            angle_deg = np.degrees(angle_rad).mean()

            # Normalize to [-10, 10] range
            angle_deg = np.clip(angle_deg, -10, 10)

            logger.debug(
                "biomechanics.pronation",
                extra={"rearfoot_angle_deg": angle_deg},
            )
            return angle_deg

        except Exception as e:
            logger.error("biomechanics.pronation_failed", extra={"error": str(e)})
            return 0.0
