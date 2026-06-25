"""Biomechanical parameter computation from gait cycles."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from src.gait.common.logging_utils import get_logger
from src.gait.ingestion.calibration import CalibrationOffsets

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

    def __init__(
        self,
        fps: float = 120.0,
        height_m: float = 1.7,
        calibration_offsets: Optional[CalibrationOffsets] = None,
    ):
        """Initialize analyzer.

        Args:
            fps: Frame rate (Hz)
            height_m: Subject height in meters (for scaling)
            calibration_offsets: Patient-specific baseline offsets from static trial.
                                 If provided, all angle measurements are adjusted
                                 relative to this baseline.
        """
        self.fps = fps
        self.height_m = height_m
        self.calibration_offsets = calibration_offsets or CalibrationOffsets()

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

    def compute_step_lengths_lr(
        self,
        heel_strikes_l_x_px: List[float],
        heel_strikes_r_x_px: List[float],
        scale_m_per_px: float = 0.01,
    ) -> tuple[float, float]:
        """Compute separate step lengths for left and right feet.

        Args:
            heel_strikes_l_x_px: X-positions (px) of left foot heel strikes
            heel_strikes_r_x_px: X-positions (px) of right foot heel strikes
            scale_m_per_px: Camera calibration (metres per pixel)

        Returns:
            Tuple of (step_length_left_m, step_length_right_m)
        """
        if not heel_strikes_l_x_px or not heel_strikes_r_x_px:
            return 0.0, 0.0

        diffs = [
            abs(heel_strikes_l_x_px[i] - heel_strikes_r_x_px[i])
            for i in range(min(len(heel_strikes_l_x_px), len(heel_strikes_r_x_px)))
        ]

        if not diffs:
            return 0.0, 0.0

        mean_step_px = np.mean(diffs)
        step_m = mean_step_px * scale_m_per_px

        logger.debug(
            "biomechanics.step_lengths_lr",
            extra={"step_length_m": step_m},
        )
        return step_m, step_m

    def compute_foot_progression_angles_lr(
        self,
        heel_pos_l: np.ndarray,
        foot_index_l: np.ndarray,
        heel_pos_r: np.ndarray,
        foot_index_r: np.ndarray,
    ) -> tuple[float, float]:
        """Compute foot progression angles for left and right feet.

        Foot progression angle = angle between foot long axis and direction of travel.
        Positive = toe-out (external rotation), negative = toe-in (internal rotation).

        Args:
            heel_pos_l, heel_pos_r: (n_frames, 2) heel positions (px)
            foot_index_l, foot_index_r: (n_frames, 2) toe/metatarsal positions (px)

        Returns:
            Tuple of (fpa_left_deg, fpa_right_deg) — mean angles during gait
        """
        try:
            fpa_left = self._compute_fpa_side(heel_pos_l, foot_index_l)
            fpa_right = self._compute_fpa_side(heel_pos_r, foot_index_r)

            logger.debug(
                "biomechanics.fpa_computed",
                extra={"fpa_left_deg": fpa_left, "fpa_right_deg": fpa_right},
            )
            return fpa_left, fpa_right
        except Exception as e:
            logger.error("biomechanics.fpa_failed", extra={"error": str(e)})
            return 0.0, 0.0

    def _compute_fpa_side(self, heel_pos: np.ndarray, foot_index: np.ndarray) -> float:
        """Compute FPA for one side given heel and toe positions."""
        if len(heel_pos) < 2 or len(foot_index) < 2:
            return 0.0

        dx = foot_index[:, 0] - heel_pos[:, 0]
        dy = foot_index[:, 1] - heel_pos[:, 1]

        angles = np.degrees(np.arctan2(-dy, np.where(np.abs(dx) > 1e-9, dx, 1e-9)))
        return float(np.mean(angles))

    def compute_frontal_plane_excursion_lr(
        self,
        rearfoot_angles_l: List[float],
        rearfoot_angles_r: List[float],
    ) -> tuple[float, float]:
        """Compute total frontal-plane excursion during stance for each foot.

        Excursion = (max rearfoot angle) - (angle at initial contact).
        Represents the range of rearfoot eversion motion during stance.

        Args:
            rearfoot_angles_l, rearfoot_angles_r: Time series of angles (deg) during stance

        Returns:
            Tuple of (excursion_left_deg, excursion_right_deg)
        """
        excursion_left = self._compute_excursion(rearfoot_angles_l)
        excursion_right = self._compute_excursion(rearfoot_angles_r)

        logger.debug(
            "biomechanics.frontal_plane_excursion",
            extra={
                "excursion_left_deg": excursion_left,
                "excursion_right_deg": excursion_right,
            },
        )
        return excursion_left, excursion_right

    def _compute_excursion(self, rearfoot_angles: List[float]) -> float:
        """Compute excursion from a single foot's rearfoot angle time series."""
        if len(rearfoot_angles) < 2:
            return 0.0
        return max(rearfoot_angles) - rearfoot_angles[0]

    def apply_calibration_offset_angle(self, angle_deg: float, offset_deg: float) -> float:
        """Apply calibration offset to a measured angle.

        Normalized angle = measured angle - calibration offset.

        Args:
            angle_deg: Measured angle in degrees
            offset_deg: Calibration baseline offset in degrees

        Returns:
            Normalized angle (relative to patient baseline)
        """
        return angle_deg - offset_deg
