"""Static calibration trial processing â€” extract personal anatomical offsets.

A calibration trial captures 3+ seconds of standing posture (or the first 3 seconds
of any uploaded video in rest state). Joint angles measured in this neutral standing
position become the baseline (offset) for that patient. All subsequent dynamic gait
angle measurements are then adjusted relative to this baseline, normalizing for
individual morphology rather than using an absolute reference frame.

Example usage:
    calibration = extract_calibration_offsets(frames, pose_keypoints)
    # Later, during gait analysis:
    ankle_flexion_dynamic = ankle_flexion_raw - calibration.ankle_dorsi_deg
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from gait.common.interfaces import Frame, Keypoint
from gait.common.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class CalibrationOffsets:
    """Baseline joint angles from a standing anatomical posture trial.

    All angles in degrees. These offsets are subtracted from dynamic measurements
    to normalize for individual anatomy.
    """
    ankle_dorsi_deg: float = 0.0  # dorsiflexion at rest
    knee_flexion_deg: float = 0.0  # knee flexion at rest
    hip_flexion_deg: float = 0.0  # hip flexion at rest
    pelvic_tilt_deg: float = 0.0  # anterior pelvic tilt at rest
    trunk_lean_deg: float = 0.0  # trunk forward lean at rest
    rearfoot_angle_left_deg: float = 0.0  # rearfoot varus/valgus L at rest
    rearfoot_angle_right_deg: float = 0.0  # rearfoot varus/valgus R at rest

    def to_dict(self) -> dict:
        """Export as dictionary for storage/serialization."""
        return {
            "ankle_dorsi_deg": self.ankle_dorsi_deg,
            "knee_flexion_deg": self.knee_flexion_deg,
            "hip_flexion_deg": self.hip_flexion_deg,
            "pelvic_tilt_deg": self.pelvic_tilt_deg,
            "trunk_lean_deg": self.trunk_lean_deg,
            "rearfoot_angle_left_deg": self.rearfoot_angle_left_deg,
            "rearfoot_angle_right_deg": self.rearfoot_angle_right_deg,
        }


def extract_calibration_offsets(
    frames: List[Frame],
    pose_keypoints: dict,
    duration_sec: float = 3.0,
) -> CalibrationOffsets:
    """Extract personal anatomical baseline from a standing trial.

    Takes the first 3 seconds (or full duration if shorter) of a standing posture
    video and computes mean joint angles to use as patient-specific baseline offsets.

    Args:
        frames: List of video frames (should be standing posture, no walking).
        pose_keypoints: Dictionary mapping frame index â†’ keypoint data.
                       Expected keys: left_knee, right_knee, left_hip, right_hip,
                       left_ankle, right_ankle, etc. (as Keypoint objects).
        duration_sec: Duration to sample for baseline (default 3.0 seconds).

    Returns:
        CalibrationOffsets object with mean angles from standing posture.
        Returns zeros if insufficient data.
    """
    if not frames or not pose_keypoints:
        logger.warning("calibration.empty_input")
        return CalibrationOffsets()

    fps = 120.0  # Assume standard 120 fps
    frames_to_sample = min(int(duration_sec * fps), len(frames))

    if frames_to_sample < 2:
        logger.warning(
            "calibration.insufficient_frames",
            extra={"available": len(frames), "required": frames_to_sample},
        )
        return CalibrationOffsets()

    ankle_dorsis = []
    knee_flexions = []
    hip_flexions = []
    pelvic_tilts = []
    trunk_leans = []
    rearfoot_angles_left = []
    rearfoot_angles_right = []

    for frame_idx in range(frames_to_sample):
        kp = pose_keypoints.get(frame_idx)
        if not kp:
            continue

        try:
            ankle_dorsi = _compute_ankle_dorsiflexion(kp)
            if ankle_dorsi is not None:
                ankle_dorsis.append(ankle_dorsi)

            knee_flex = _compute_knee_flexion(kp)
            if knee_flex is not None:
                knee_flexions.append(knee_flex)

            hip_flex = _compute_hip_flexion(kp)
            if hip_flex is not None:
                hip_flexions.append(hip_flex)

            pelvis_tilt = _compute_pelvic_tilt(kp)
            if pelvis_tilt is not None:
                pelvic_tilts.append(pelvis_tilt)

            trunk_lean = _compute_trunk_lean(kp)
            if trunk_lean is not None:
                trunk_leans.append(trunk_lean)

            rfa_l = _compute_rearfoot_angle(kp, side="left")
            if rfa_l is not None:
                rearfoot_angles_left.append(rfa_l)

            rfa_r = _compute_rearfoot_angle(kp, side="right")
            if rfa_r is not None:
                rearfoot_angles_right.append(rfa_r)

        except Exception as e:
            logger.debug("calibration.frame_error", extra={"frame": frame_idx, "error": str(e)})
            continue

    offsets = CalibrationOffsets(
        ankle_dorsi_deg=_mean_or_zero(ankle_dorsis),
        knee_flexion_deg=_mean_or_zero(knee_flexions),
        hip_flexion_deg=_mean_or_zero(hip_flexions),
        pelvic_tilt_deg=_mean_or_zero(pelvic_tilts),
        trunk_lean_deg=_mean_or_zero(trunk_leans),
        rearfoot_angle_left_deg=_mean_or_zero(rearfoot_angles_left),
        rearfoot_angle_right_deg=_mean_or_zero(rearfoot_angles_right),
    )

    logger.info(
        "calibration.offsets_extracted",
        extra={
            "frames_sampled": frames_to_sample,
            "ankle_dorsi_deg": offsets.ankle_dorsi_deg,
            "knee_flexion_deg": offsets.knee_flexion_deg,
            "hip_flexion_deg": offsets.hip_flexion_deg,
        },
    )
    return offsets


def _compute_ankle_dorsiflexion(kp: dict) -> Optional[float]:
    """Compute ankle dorsiflexion angle from keypoints.

    Dorsiflexion = angle between shin (kneeâ†’ankle) and foot (ankleâ†’toe/metatarsal).
    Positive = toe raised (dorsiflexion), negative = toe down (plantarflexion).
    """
    try:
        ankle_l = kp.get("left_ankle")
        foot_l = kp.get("left_foot_index")
        knee_l = kp.get("left_knee")

        if not all([ankle_l, foot_l, knee_l]):
            return None

        shin_vec = (ankle_l.x - knee_l.x, ankle_l.y - knee_l.y)
        foot_vec = (foot_l.x - ankle_l.x, foot_l.y - ankle_l.y)

        shin_angle = math.atan2(shin_vec[1], shin_vec[0])
        foot_angle = math.atan2(foot_vec[1], foot_vec[0])

        dorsi_rad = shin_angle - foot_angle
        return math.degrees(dorsi_rad)
    except Exception:
        return None


def _compute_knee_flexion(kp: dict) -> Optional[float]:
    """Compute knee flexion angle from hipâ†’kneeâ†’ankle."""
    try:
        hip = kp.get("left_hip")
        knee = kp.get("left_knee")
        ankle = kp.get("left_ankle")

        if not all([hip, knee, ankle]):
            return None

        thigh_vec = (knee.x - hip.x, knee.y - hip.y)
        shin_vec = (ankle.x - knee.x, ankle.y - knee.y)

        thigh_angle = math.atan2(thigh_vec[1], thigh_vec[0])
        shin_angle = math.atan2(shin_vec[1], shin_vec[0])

        flexion_rad = shin_angle - thigh_angle
        return math.degrees(flexion_rad)
    except Exception:
        return None


def _compute_hip_flexion(kp: dict) -> Optional[float]:
    """Compute hip flexion angle from pelvisâ†’hipâ†’knee."""
    try:
        pelvis_mid = kp.get("midpoint_hips")
        if not pelvis_mid:
            left_hip = kp.get("left_hip")
            right_hip = kp.get("right_hip")
            if left_hip and right_hip:
                pelvis_mid = Keypoint(
                    x=(left_hip.x + right_hip.x) / 2,
                    y=(left_hip.y + right_hip.y) / 2,
                    confidence=0.5,
                )

        hip = kp.get("left_hip")
        knee = kp.get("left_knee")

        if not all([pelvis_mid, hip, knee]):
            return None

        torso_vec = (hip.x - pelvis_mid.x, hip.y - pelvis_mid.y)
        thigh_vec = (knee.x - hip.x, knee.y - hip.y)

        torso_angle = math.atan2(torso_vec[1], torso_vec[0])
        thigh_angle = math.atan2(thigh_vec[1], thigh_vec[0])

        flexion_rad = torso_angle - thigh_angle
        return math.degrees(flexion_rad)
    except Exception:
        return None


def _compute_pelvic_tilt(kp: dict) -> Optional[float]:
    """Compute pelvic tilt (anterior/posterior) from hip and shoulder positions."""
    try:
        left_hip = kp.get("left_hip")
        right_hip = kp.get("right_hip")
        left_shoulder = kp.get("left_shoulder")
        right_shoulder = kp.get("right_shoulder")

        if not all([left_hip, right_hip, left_shoulder, right_shoulder]):
            return None

        hip_line = (right_hip.x - left_hip.x, right_hip.y - left_hip.y)
        shoulder_line = (right_shoulder.x - left_shoulder.x, right_shoulder.y - left_shoulder.y)

        hip_angle = math.atan2(hip_line[1], hip_line[0])
        shoulder_angle = math.atan2(shoulder_line[1], shoulder_line[0])

        tilt_rad = hip_angle - shoulder_angle
        return math.degrees(tilt_rad)
    except Exception:
        return None


def _compute_trunk_lean(kp: dict) -> Optional[float]:
    """Compute trunk forward lean from shoulderâ†’hip alignment vs. vertical."""
    try:
        left_hip = kp.get("left_hip")
        left_shoulder = kp.get("left_shoulder")

        if not all([left_hip, left_shoulder]):
            return None

        torso_vec = (left_hip.x - left_shoulder.x, left_hip.y - left_shoulder.y)
        vertical_vec = (0.0, 1.0)

        torso_angle = math.atan2(torso_vec[1], torso_vec[0])
        vertical_angle = math.atan2(vertical_vec[1], vertical_vec[0])

        lean_rad = torso_angle - vertical_angle
        return math.degrees(lean_rad)
    except Exception:
        return None


def _compute_rearfoot_angle(kp: dict, side: str = "left") -> Optional[float]:
    """Compute rearfoot angle (varus/valgus) from ankleâ†’heel alignment."""
    try:
        prefix = f"{side}_"
        ankle = kp.get(f"{prefix}ankle")
        heel = kp.get(f"{prefix}heel")

        if not all([ankle, heel]):
            return None

        heel_vec = (heel.x - ankle.x, heel.y - ankle.y)
        vertical = (0.0, 1.0)

        angle_rad = math.atan2(heel_vec[1], heel_vec[0]) - math.atan2(vertical[1], vertical[0])
        return math.degrees(angle_rad)
    except Exception:
        return None


def _mean_or_zero(values: List[float]) -> float:
    """Return mean of values, or 0.0 if empty."""
    if not values:
        return 0.0
    return sum(values) / len(values)

