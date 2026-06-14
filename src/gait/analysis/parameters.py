"""Pure biomechanical parameter functions — no I/O, no state.

All functions take keypoints / cycle data in and return numbers or strings out.
Classifiers rely exclusively on thresholds from AnalysisConfig; nothing is
hardcoded here.

Coordinate conventions (image space):
  x  increases left → right
  y  increases top  → bottom (so higher y = lower physical position)

Gait sign conventions:
  Foot-strike angle (FSA): positive = rearfoot (heel lower than toe in image)
  Rearfoot angle (RFA):    positive = eversion / pronation
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from src.gait.common.geometry import signed_angle_deg
from src.gait.common.interfaces import GaitCycle, Keypoint
from src.gait.pipeline.config import AnalysisConfig


# ── Spatiotemporal ─────────────────────────────────────────────────────────────


def compute_spatiotemporal(cycle: GaitCycle, fps: float) -> Dict[str, float]:
    """Compute timing parameters and cadence for one gait cycle.

    All durations come from GaitCycle.stance/swing_duration_ms (already in ms).
    fps is accepted for API consistency but not used for basic timing.

    Returns:
        stance_time_ms, swing_time_ms, gait_cycle_time_ms,
        stance_pct, swing_pct, cadence_steps_per_min
    """
    stance_ms = cycle.stance_duration_ms or 0.0
    swing_ms = cycle.swing_duration_ms or 0.0
    total_ms = stance_ms + swing_ms

    result: Dict[str, float] = {
        "stance_time_ms": stance_ms,
        "swing_time_ms": swing_ms,
        "gait_cycle_time_ms": total_ms,
    }

    if total_ms > 0:
        result["stance_pct"] = stance_ms / total_ms * 100.0
        result["swing_pct"] = swing_ms / total_ms * 100.0
        # One HS→HS on same foot = 1 stride = 2 steps
        result["cadence_steps_per_min"] = 120_000.0 / total_ms
    else:
        result["stance_pct"] = 0.0
        result["swing_pct"] = 0.0
        result["cadence_steps_per_min"] = 0.0

    return result


def compute_step_length(
    ipsilateral_heel_x_px: float,
    contralateral_heel_x_px: float,
    scale_m_per_px: float,
) -> float:
    """Step length = horizontal distance between consecutive contralateral heel strikes.

    Args:
        ipsilateral_heel_x_px: x-coordinate (px) of this foot's heel at initial contact.
        contralateral_heel_x_px: x-coordinate (px) of the opposite foot's heel at its
            preceding initial contact.
        scale_m_per_px: camera calibration factor (metres per pixel in the floor plane).

    Returns:
        Step length in metres (always non-negative).
    """
    return abs(ipsilateral_heel_x_px - contralateral_heel_x_px) * scale_m_per_px


# ── Foot-strike classification ─────────────────────────────────────────────────


def compute_foot_progression_angle(heel: Keypoint, foot_index: Keypoint) -> float:
    """Foot progression angle (FPA) at heel-strike.

    FPA = angle between the foot's long axis (heel→toe) and the direction of
    travel, assumed to be the image +x axis.  Image y is inverted relative to
    world y, so the world-space angle is atan2(-dy, dx).

    Positive FPA: toe points above the direction of travel (toe-out / external rotation).
    Negative FPA: toe points below the direction of travel (toe-in / internal rotation).
    """
    dx = foot_index.x - heel.x
    dy = foot_index.y - heel.y  # image space: positive = downward
    return math.degrees(math.atan2(-dy, dx if abs(dx) > 1e-9 else 1e-9))


def compute_foot_strike_angle(heel: Keypoint, foot_index: Keypoint) -> float:
    """Foot-strike angle (FSA) at initial contact.

    FSA = atan2(heel.y - foot_index.y, |foot_index.x - heel.x|)

    Positive FSA: heel is lower than toe in the image (= physically lower =
    heel-first contact = rearfoot).
    Negative FSA: toe lower than heel = forefoot contact.
    Zero: flat = midfoot.
    """
    dy = heel.y - foot_index.y
    dx = abs(foot_index.x - heel.x)
    return math.degrees(math.atan2(dy, max(dx, 1e-9)))


def classify_foot_strike(angle_deg: float, cfg: AnalysisConfig) -> str:
    """Classify foot-strike pattern from FSA."""
    if angle_deg > cfg.rearfoot_min_deg:
        return "rearfoot"
    if angle_deg < cfg.forefoot_max_deg:
        return "forefoot"
    return "midfoot"


# ── Pronation analysis ─────────────────────────────────────────────────────────


def compute_rearfoot_angle(knee: Keypoint, ankle: Keypoint, heel: Keypoint) -> float:
    """Signed angle from the downward vertical to the ankle→heel vector.

    Returns degrees.  Positive = heel tilts in the −x direction (left in image).

    Because signed_angle_deg((0,1), v) = atan2(−v.x, v.y):
        heel.x > ankle.x  (right tilt) → negative raw angle
        heel.x < ankle.x  (left tilt)  → positive raw angle

    Callers must apply a side correction before clinical classification:
        Left foot:  no correction  (pronation = heel tilts left = positive raw angle ✓)
        Right foot: negate         (pronation = heel tilts right = negative raw → negate to get +)
    """
    heel_vec = (heel.x - ankle.x, heel.y - ankle.y)
    return signed_angle_deg((0.0, 1.0), heel_vec)


def classify_pronation(angle_deg: float, cfg: AnalysisConfig) -> str:
    """Classify rearfoot eversion angle (positive = pronation/eversion)."""
    if angle_deg >= cfg.overpronation_min_deg:
        return "overpronation"
    if angle_deg >= cfg.mild_pronation_min_deg:
        return "mild_pronation"
    if angle_deg >= cfg.neutral_min_deg:
        return "neutral"
    if angle_deg >= cfg.mild_supination_min_deg:
        return "mild_supination"
    return "oversupination"


def compute_frontal_plane_excursion(rearfoot_angles_deg: List[float]) -> float:
    """Total frontal-plane rearfoot excursion during stance.

    Returns max - min of the rearfoot angle series (degrees), which represents
    the full range of calcaneal motion from initial contact through toe-off.
    Returns 0.0 when fewer than two samples are available.
    """
    if len(rearfoot_angles_deg) < 2:
        return 0.0
    return max(rearfoot_angles_deg) - min(rearfoot_angles_deg)


# ── Arch assessment ────────────────────────────────────────────────────────────


def compute_arch_height_index(
    heel: Keypoint,
    foot_index: Keypoint,
    ankle: Keypoint,
) -> Optional[float]:
    """Approximate arch height index (AHI).

    AHI = navicular_height_px / foot_length_px

    navicular ≈ midpoint(ankle, foot_index) — rough proxy for navicular
    navicular_height = heel.y - navicular.y  (pixels, positive = arch present)
    foot_length = Euclidean distance(heel, foot_index)

    Returns None when geometry is degenerate (flat or inverted arch proxy,
    zero-length foot).
    """
    nav_y = (ankle.y + foot_index.y) / 2.0
    nav_height = heel.y - nav_y  # positive when nav is above heel level

    if nav_height <= 0:
        return None

    foot_length = math.sqrt(
        (foot_index.x - heel.x) ** 2 + (foot_index.y - heel.y) ** 2
    )
    if foot_length < 1e-9:
        return None

    return nav_height / foot_length


def classify_arch(ahi: float, cfg: AnalysisConfig) -> str:
    """Classify arch type from AHI."""
    if ahi >= cfg.high_ahi_min:
        return "high"
    if ahi >= cfg.normal_ahi_min:
        return "normal"
    return "low"


# ── Symmetry ───────────────────────────────────────────────────────────────────


def compute_symmetry_index(left_val: float, right_val: float) -> float:
    """SI = |L - R| / mean(L, R) × 100.

    Returns 0.0 when mean is effectively zero (both sides are zero).
    """
    mean_val = (left_val + right_val) / 2.0
    if mean_val < 1e-12:
        return 0.0
    return abs(left_val - right_val) / mean_val * 100.0
