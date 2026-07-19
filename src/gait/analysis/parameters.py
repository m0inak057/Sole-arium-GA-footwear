"""Pure biomechanical parameter functions â€" no I/O, no state.

All functions take keypoints / cycle data in and return numbers or strings out.
Classifiers rely exclusively on thresholds from AnalysisConfig; nothing is
hardcoded here.

Coordinate conventions (image space):
  x  increases left â†' right
  y  increases top  â†' bottom (so higher y = lower physical position)

Gait sign conventions:
  Foot-strike angle (FSA): positive = rearfoot (heel lower than toe in image)
  Rearfoot angle (RFA):    positive = eversion / pronation
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from gait.common.geometry import compute_midpoint, signed_angle_deg
from gait.common.interfaces import GaitCycle, GaitEvent, Keypoint, KeypointFrame
from gait.common.logging_utils import get_logger
from gait.pipeline.config import AnalysisConfig

logger = get_logger(__name__)

# Minimum measurements required before trusting a calibration estimate over
# the next fallback in the chain.
_MIN_SCALE_MEASUREMENTS = 3
_FALLBACK_SCALE_M_PER_PX = 0.01

# Minimum valid midstance frames required to trust a rearfoot alignment
# estimate — raised from 3 to 5: a result from only 3-4 high-variance frames
# is not clinically trustworthy (checked *after* outlier rejection below).
_MIN_REARFOOT_ALIGNMENT_FRAMES = 5
_REARFOOT_ALIGNMENT_MIN_CONFIDENCE = 0.1
# Fraction-of-stance window used to avoid heel-strike / toe-off artifacts.
_REARFOOT_ALIGNMENT_STANCE_WINDOW = (0.2, 0.8)
# Frames whose angle deviates more than this many degrees from the initial
# median are dropped as outliers (motion blur / tracking error) before the
# final median is computed.
_REARFOOT_ALIGNMENT_OUTLIER_THRESHOLD_DEG = 20.0
# Normal human rearfoot alignment from a posterior view is within ~±15 deg;
# anything past this is a computation problem, not a clinical finding —
# applies to both the walking-video and static-photo methods.
_REARFOOT_ALIGNMENT_MAX_PLAUSIBLE_DEG = 30.0


# â"€â"€ Camera scale calibration â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


def estimate_scale_m_per_px(
    keypoint_frames: List[KeypointFrame],
    hs_frame_indices_l: List[int],
    foot_length_mm: Optional[float],
    height_cm: Optional[float],
    foot_width_mm: Optional[float] = None,
) -> Tuple[float, str, int]:
    """Estimate the camera's pixel-to-metre scale for this session.

    Tries, in order:
      1. Foot length: mean pixel distance between left_heel and
         left_foot_index at left-foot heel-strike frames, calibrated against
         the patient's real foot_length_mm. Requires >= 3 measurements.
      2. Body height: mean pixel distance between nose and left_ankle across
         all frames, calibrated against the patient's real height_cm.
      3. A hardcoded last-resort default (0.01 m/px) if neither anthropometric
         value or enough keypoint data is available.

    Args:
        foot_width_mm: Patient's foot width (for logging only; not used in calibration).

    Returns (scale_m_per_px, method, n_measurements) where method is one of
    "foot_length", "body_height", "fallback_default".
    """
    kf_by_index: Dict[int, KeypointFrame] = {kf.frame_index: kf for kf in keypoint_frames}

    if foot_length_mm:
        foot_lengths_px: List[float] = []
        for idx in hs_frame_indices_l:
            kf = kf_by_index.get(idx)
            if kf is None:
                continue
            heel = kf.keypoints.get("left_heel")
            toe = kf.keypoints.get("left_foot_index")
            if heel is not None and toe is not None:
                foot_lengths_px.append(math.hypot(toe.x - heel.x, toe.y - heel.y))

        if len(foot_lengths_px) >= _MIN_SCALE_MEASUREMENTS:
            mean_px = sum(foot_lengths_px) / len(foot_lengths_px)
            if mean_px > 1e-6:
                return (foot_length_mm / 1000.0) / mean_px, "foot_length", len(foot_lengths_px)

    if height_cm:
        person_heights_px: List[float] = []
        for kf in keypoint_frames:
            nose = kf.keypoints.get("nose")
            ankle = kf.keypoints.get("left_ankle")
            if nose is not None and ankle is not None:
                person_heights_px.append(math.hypot(ankle.x - nose.x, ankle.y - nose.y))

        if len(person_heights_px) >= _MIN_SCALE_MEASUREMENTS:
            mean_px = sum(person_heights_px) / len(person_heights_px)
            if mean_px > 1e-6:
                return (height_cm / 100.0) / mean_px, "body_height", len(person_heights_px)

    return _FALLBACK_SCALE_M_PER_PX, "fallback_default", 0


# â"€â"€ Spatiotemporal â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


def compute_spatiotemporal(cycle: GaitCycle, fps: float) -> Dict[str, float]:
    """Compute timing parameters and cadence for one gait cycle.

    All durations come from GaitCycle.stance/swing_duration_ms (already in ms).
    fps is accepted for API consistency but not used for basic timing.

    Returns:
        stance_time_ms, swing_time_ms, gait_cycle_time_ms,
        stance_pct, swing_pct, and (for COMPLETE cycles only) cadence_steps_per_min
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
    else:
        result["stance_pct"] = 0.0
        result["swing_pct"] = 0.0

    # A PARTIAL_CYCLE has no closing heel strike (swing_duration_ms is None),
    # so total_ms above is stance-only. Deriving cadence from that would
    # treat the stance phase as if it were a full stride and badly
    # overestimate it; leave cadence out entirely rather than fabricate it.
    # The caller (StandardBiomechanicalAnalyzer/orchestrator) falls back to a
    # heel-strike-interval cadence estimate instead when this key is absent.
    # Note: swing_duration_ms == 0.0 is a real (if degenerate) COMPLETE cycle
    # and still gets a cadence value; only None (no closing HS at all) omits it.
    if cycle.swing_duration_ms is not None:
        if total_ms > 0:
            # One HSâ†'HS on same foot = 1 stride = 2 steps
            result["cadence_steps_per_min"] = 120_000.0 / total_ms
        else:
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


def compute_step_lengths_lr(
    heel_strikes_l_x_px: List[float],
    heel_strikes_r_x_px: List[float],
    scale_m_per_px: float,
) -> tuple[float, float]:
    """Compute clinical step lengths for left and right feet.

    Clinical step length = distance from one foot's heel strike to the NEXT
    opposite foot's heel strike (requires chronological interleaving of L and R events).

    step_length_left_m: mean distance from right heel strike to following left heel strike
    step_length_right_m: mean distance from left heel strike to following right heel strike

    Args:
        heel_strikes_l_x_px: List of x-positions (px) for left foot heel strikes (in time order).
        heel_strikes_r_x_px: List of x-positions (px) for right foot heel strikes (in time order).
        scale_m_per_px: Camera calibration factor (metres per pixel).

    Returns:
        Tuple of (step_length_left_m, step_length_right_m).
        Returns (0.0, 0.0) if insufficient data.
    """
    if len(heel_strikes_l_x_px) < 1 or len(heel_strikes_r_x_px) < 1:
        return 0.0, 0.0

    # Compute step_length_left: distance from each R heel strike to next L heel strike
    steps_left = []
    for r_x in heel_strikes_r_x_px:
        # Find the first L heel strike that occurs after this R strike
        next_l_strikes = [l_x for l_x in heel_strikes_l_x_px if l_x > r_x]
        if next_l_strikes:
            step = abs(next_l_strikes[0] - r_x)
            steps_left.append(step)

    # Compute step_length_right: distance from each L heel strike to next R heel strike
    steps_right = []
    for l_x in heel_strikes_l_x_px:
        # Find the first R heel strike that occurs after this L strike
        next_r_strikes = [r_x for r_x in heel_strikes_r_x_px if r_x > l_x]
        if next_r_strikes:
            step = abs(next_r_strikes[0] - l_x)
            steps_right.append(step)

    # Return means, or 0.0 if no valid steps computed
    step_length_left_m = (sum(steps_left) / len(steps_left) if steps_left else 0.0) * scale_m_per_px
    step_length_right_m = (sum(steps_right) / len(steps_right) if steps_right else 0.0) * scale_m_per_px

    return step_length_left_m, step_length_right_m


# â"€â"€ Foot-strike classification â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


def compute_foot_progression_angle(heel: Keypoint, foot_index: Keypoint) -> float:
    """Foot progression angle (FPA) at heel-strike.

    FPA = angle between the foot's long axis (heelâ†'toe) and the direction of
    travel, assumed to be the image +x axis.  Image y is inverted relative to
    world y, so the world-space angle is atan2(-dy, dx).

    Positive FPA: toe points above the direction of travel (toe-out / external rotation).
    Negative FPA: toe points below the direction of travel (toe-in / internal rotation).

    Returns:
        Angle in degrees. Range typically -30 to +30.
    """
    dx = foot_index.x - heel.x
    dy = foot_index.y - heel.y  # image space: positive = downward
    return math.degrees(math.atan2(-dy, dx if abs(dx) > 1e-9 else 1e-9))


def classify_foot_progression_angle(angle_deg: float) -> str:
    """Classify foot progression angle into toe-in, neutral, or toe-out.

    Args:
        angle_deg: Foot progression angle in degrees.

    Returns:
        Classification: "toe_in", "neutral", or "toe_out".
    """
    if angle_deg < -5.0:
        return "toe_in"
    if angle_deg > 10.0:
        return "toe_out"
    return "neutral"


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


# â"€â"€ Pronation analysis â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


def compute_rearfoot_angle(knee: Keypoint, ankle: Keypoint, heel: Keypoint) -> float:
    """Signed angle from the downward vertical to the ankleâ†'heel vector.

    Returns degrees.  Positive = heel tilts in the âˆ'x direction (left in image).

    Because signed_angle_deg((0,1), v) = atan2(âˆ'v.x, v.y):
        heel.x > ankle.x  (right tilt) â†' negative raw angle
        heel.x < ankle.x  (left tilt)  â†' positive raw angle

    Callers must apply a side correction before clinical classification:
        Left foot:  no correction  (pronation = heel tilts left = positive raw angle âœ")
        Right foot: negate         (pronation = heel tilts right = negative raw â†' negate to get +)
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
    """Total frontal-plane rearfoot excursion during stance phase.

    Excursion = (maximum rearfoot eversion angle) - (rearfoot angle at initial contact).

    In typical gait, at heel strike (initial contact), the foot is relatively
    inverted (negative angle), and then everts (positive angle) during loading
    response and mid-stance. Excursion measures the total range of eversion motion.

    Args:
        rearfoot_angles_deg: Time series of rearfoot angles (degrees) during stance,
                             ordered chronologically from initial contact to toe-off.

    Returns:
        Excursion in degrees (max minus initial). Returns 0.0 if fewer than 2 samples.
    """
    if len(rearfoot_angles_deg) < 2:
        return 0.0
    initial_angle = rearfoot_angles_deg[0]
    max_angle = max(rearfoot_angles_deg)
    return max_angle - initial_angle


def classify_rearfoot_alignment(angle_deg: float) -> str:
    """Classify a rearfoot alignment angle (posterior camera) into a clinical bucket.

    Positive = eversion (overpronation), negative = inversion (supination).
    Boundaries follow the clinical thresholds: normal 0-4 deg, mild 4-8 deg
    (or 0 to -4 deg), severe beyond that.
    """
    if angle_deg >= 8.0:
        return "severe_overpronation"
    if angle_deg >= 4.0:
        return "mild_overpronation"
    if angle_deg >= 0.0:
        return "normal"
    if angle_deg >= -4.0:
        return "mild_supination"
    return "severe_supination"


def compute_rearfoot_alignment_angle(
    keypoint_frames: List[KeypointFrame],
    foot: str,
    cycles: List[GaitCycle],
) -> Dict[str, Optional[Any]]:
    """Clinical rearfoot alignment angle from the posterior camera view.

    Measures the signed angle between the lower-leg bisection (upper calf
    center -> Achilles tendon center) and the heel bisection (upper
    calcaneus center -> lower calcaneus center), for midstance frames only
    (20%-80% of each stance phase, to avoid heel-strike/toe-off artifacts).

    Args:
        keypoint_frames: All keypoint frames for the session (any camera);
            frames from cameras other than "posterior" are ignored.
        foot: "L" or "R" — which foot's cycles/landmarks to use.
        cycles: Gait cycles (any foot) providing each stance phase's frame
            range; only cycles matching `foot` are used.

    Returns:
        Dict with keys mean_deg, std_deg, frame_count, classification.
        mean_deg/std_deg/classification are None when fewer than
        `_MIN_REARFOOT_ALIGNMENT_FRAMES` valid frames are found.
    """
    side = "left" if foot == "L" else "right"
    posterior_by_index: Dict[int, KeypointFrame] = {
        kf.frame_index: kf for kf in keypoint_frames if kf.camera_view == "posterior"
    }

    lo_frac, hi_frac = _REARFOOT_ALIGNMENT_STANCE_WINDOW
    angles_deg: List[float] = []

    for cycle in cycles:
        if cycle.foot != foot or not cycle.stance_frames:
            continue
        stance = sorted(cycle.stance_frames)
        n = len(stance)
        lo = int(n * lo_frac)
        hi = int(n * hi_frac)
        for frame_index in stance[lo:hi]:
            kf = posterior_by_index.get(frame_index)
            if kf is None:
                continue
            kps = kf.keypoints
            knee = kps.get(f"{side}_knee")
            ankle = kps.get(f"{side}_ankle")
            heel = kps.get(f"{side}_heel")
            toe = kps.get(f"{side}_foot_index")
            required = (knee, ankle, heel, toe)
            if any(
                kp is None or kp.confidence < _REARFOOT_ALIGNMENT_MIN_CONFIDENCE
                for kp in required
            ):
                continue

            calf_mid = compute_midpoint((knee.x, knee.y), (ankle.x, ankle.y))
            calf_vector = (ankle.x - calf_mid[0], ankle.y - calf_mid[1])

            # Heel bisection axis, posterior view: approximately vertical
            # (pointing down, y always positive) with a lateral tilt equal to
            # how far the heel center sits from the ankle center. Using
            # heel.y - toe.y here (as a previous version did) is wrong: from
            # directly behind, heel and toe project to nearly the same
            # vertical position, so that difference is a few pixels of
            # landmark jitter whose *sign* can flip, reversing heel_vector by
            # 180 deg and producing clinically impossible angles. abs() on
            # the y component guarantees heel_vector always points down, so
            # only the real lateral-deviation signal (x) can move the angle.
            lateral_tilt_x = heel.x - ankle.x
            heel_vector = (lateral_tilt_x, abs(ankle.y - heel.y))

            angle = signed_angle_deg(calf_vector, heel_vector)
            # Same left/right sign convention as compute_rearfoot_angle:
            # positive = eversion for the left foot; negate for the right.
            if foot == "R":
                angle = -angle
            angles_deg.append(angle)

    if not angles_deg:
        logger.warning(
            "rearfoot_alignment_insufficient_data",
            extra={"foot": foot, "valid_frame_count": 0},
        )
        return {
            "mean_deg": None,
            "std_deg": None,
            "frame_count": 0,
            "classification": None,
        }

    # Outlier rejection: with only a handful of midstance frames, one or two
    # frames with motion blur / tracking error during dynamic gait loading
    # can dominate a mean. Reject anything far from the initial median, then
    # take the median of the survivors — median is far more robust to
    # outliers than mean for small, noisy samples like this.
    initial_median = float(np.median(angles_deg))
    surviving_angles = [
        a for a in angles_deg
        if abs(a - initial_median) <= _REARFOOT_ALIGNMENT_OUTLIER_THRESHOLD_DEG
    ]
    n_rejected = len(angles_deg) - len(surviving_angles)
    if n_rejected:
        logger.debug(
            "rearfoot_alignment_outliers_rejected",
            extra={
                "foot": foot,
                "n_rejected": n_rejected,
                "n_total": len(angles_deg),
                "initial_median_deg": initial_median,
            },
        )

    if len(surviving_angles) < _MIN_REARFOOT_ALIGNMENT_FRAMES:
        logger.warning(
            "rearfoot_alignment_insufficient_data",
            extra={"foot": foot, "valid_frame_count": len(surviving_angles)},
        )
        return {
            "mean_deg": None,
            "std_deg": None,
            "frame_count": len(surviving_angles),
            "classification": None,
        }

    # NOTE: "mean_deg" key name kept for backward compatibility with callers
    # (analyzer.py, orchestrator.py, builder.py) — the value is now a median.
    median_deg = float(np.median(surviving_angles))
    std_deg = float(np.std(surviving_angles))

    if abs(median_deg) > _REARFOOT_ALIGNMENT_MAX_PLAUSIBLE_DEG:
        logger.warning(
            "rearfoot_alignment_unreliable",
            extra={
                "foot": foot,
                "median_deg": median_deg,
                "frame_count": len(surviving_angles),
            },
        )
        return {
            "mean_deg": None,
            "std_deg": None,
            "frame_count": len(surviving_angles),
            "classification": None,
        }

    return {
        "mean_deg": median_deg,
        "std_deg": std_deg,
        "frame_count": len(surviving_angles),
        "classification": classify_rearfoot_alignment(median_deg),
    }


# Minimum per-landmark confidence to trust a static-photo rearfoot alignment
# measurement (single frame, no temporal averaging to smooth out a bad detection).
_STATIC_REARFOOT_MIN_CONFIDENCE = 0.3

# Only the BlazePose landmark indices this measurement actually needs.
_STATIC_REARFOOT_LANDMARK_INDICES: Dict[str, int] = {
    "left_knee": 25,
    "right_knee": 26,
    "left_ankle": 27,
    "right_ankle": 28,
    "left_heel": 29,
    "right_heel": 30,
    "left_foot_index": 31,
    "right_foot_index": 32,
}


def compute_rearfoot_alignment_from_image(
    image_path: str,
    model_path: str = "data/models/pose_landmarker_lite.task",
) -> Optional[Dict[str, Optional[Dict[str, Any]]]]:
    """Clinical rearfoot alignment angle (both feet) from a single static
    posterior-view standing photo.

    Uses MediaPipe's IMAGE running mode rather than VIDEO mode: a single
    photo has no temporal sequence for the landmarker to track across, so
    VIDEO mode's inter-frame tracking state would be meaningless (and its
    monotonic-timestamp requirement doesn't apply to a lone frame anyway).

    Computes the same calf-bisection-to-heel-bisection angle as
    `compute_rearfoot_alignment_angle`, but from one frame instead of an
    average over midstance frames.

    Args:
        image_path: Path to the static posterior standing photo.
        model_path: Path to the pose_landmarker_lite.task model file.

    Returns:
        {"L": {mean_deg, classification, confidence} | None,
         "R": {mean_deg, classification, confidence} | None}
        A foot's entry is None when its required landmarks are missing or
        below `_STATIC_REARFOOT_MIN_CONFIDENCE`. Returns None outright when
        MediaPipe detects no pose at all in the image.
    """
    import cv2
    import mediapipe as mp
    from mediapipe.tasks import python as mp_tasks
    from mediapipe.tasks.python import vision as mp_vision

    image = cv2.imread(str(image_path))
    if image is None:
        logger.warning(
            "static_rearfoot_alignment_failed",
            extra={"reason": "image_load_failed", "image_path": str(image_path)},
        )
        return None

    h, w = image.shape[:2]
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    options = mp_vision.PoseLandmarkerOptions(
        base_options=mp_tasks.BaseOptions(model_asset_path=str(model_path)),
        running_mode=mp_vision.RunningMode.IMAGE,
    )
    landmarker = mp_vision.PoseLandmarker.create_from_options(options)
    try:
        results = landmarker.detect(mp_image)
    finally:
        landmarker.close()

    if not results.pose_landmarks:
        # MediaPipe pose detection needs a visible head/torso to initialize;
        # a knee-to-floor crop reliably fails here. Give the user a specific,
        # actionable warning instead of a generic "no pose" message when the
        # image's shape suggests that's what happened.
        is_possibly_cropped = (h > 2 * w) or (h < 400)
        if is_possibly_cropped:
            logger.warning(
                "static_rearfoot_possibly_cropped_image",
                extra={
                    "reason": "possibly_cropped_lower_body_photo",
                    "image_path": str(image_path),
                    "image_size_wh": (w, h),
                    "detail": (
                        "Image may be a lower-body crop. MediaPipe requires the "
                        "full body to be visible including head and torso. "
                        "Re-upload a full-body posterior standing photo."
                    ),
                },
            )
        else:
            logger.warning(
                "static_rearfoot_alignment_failed",
                extra={"reason": "no_pose_detected", "image_path": str(image_path)},
            )
        return None

    pose = results.pose_landmarks[0]
    keypoints: Dict[str, Keypoint] = {}
    for name, idx in _STATIC_REARFOOT_LANDMARK_INDICES.items():
        lm = pose[idx]
        keypoints[name] = Keypoint(
            x=float(lm.x * w),
            y=float(lm.y * h),
            z=None,
            confidence=float(lm.presence),
            name=name,
        )

    result: Dict[str, Optional[Dict[str, Any]]] = {}
    for foot, side in (("L", "left"), ("R", "right")):
        knee = keypoints[f"{side}_knee"]
        ankle = keypoints[f"{side}_ankle"]
        heel = keypoints[f"{side}_heel"]
        toe = keypoints[f"{side}_foot_index"]
        required = (knee, ankle, heel, toe)
        min_confidence = min(kp.confidence for kp in required)
        if min_confidence < _STATIC_REARFOOT_MIN_CONFIDENCE:
            logger.warning(
                "static_rearfoot_alignment_failed",
                extra={
                    "reason": "low_confidence_landmarks",
                    "foot": foot,
                    "image_path": str(image_path),
                    "min_confidence": min_confidence,
                },
            )
            result[foot] = None
            continue

        calf_mid = compute_midpoint((knee.x, knee.y), (ankle.x, ankle.y))
        calf_vector = (ankle.x - calf_mid[0], ankle.y - calf_mid[1])

        # See compute_rearfoot_alignment_angle for why abs() on the y
        # component is required: it guarantees heel_vector always points
        # down, so a sign flip from heel/toe landmark jitter can never
        # reverse the vector by 180 deg. The lateral tilt (heel.x - ankle.x)
        # is the real clinical signal — how far the heel center deviates
        # sideways from the ankle/calf axis.
        lateral_tilt_x = heel.x - ankle.x
        heel_vector = (lateral_tilt_x, abs(ankle.y - heel.y))

        angle = signed_angle_deg(calf_vector, heel_vector)
        # Same left/right sign convention as compute_rearfoot_angle: positive
        # = eversion for the left foot; negate for the right.
        if foot == "R":
            angle = -angle

        if abs(angle) > _REARFOOT_ALIGNMENT_MAX_PLAUSIBLE_DEG:
            logger.warning(
                "rearfoot_alignment_unreliable",
                extra={
                    "foot": foot,
                    "angle_deg": angle,
                    "image_path": str(image_path),
                    "method": "static_image",
                },
            )
            result[foot] = None
            continue

        result[foot] = {
            "mean_deg": angle,
            "classification": classify_rearfoot_alignment(angle),
            "confidence": min_confidence,
        }

    if result["L"] is None and result["R"] is None:
        return None

    return result


# â"€â"€ Arch assessment â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


def compute_arch_height_index(
    heel: Keypoint,
    foot_index: Keypoint,
    ankle: Keypoint,
) -> Optional[float]:
    """Approximate arch height index (AHI).

    AHI = navicular_height_px / foot_length_px

    navicular â‰ˆ midpoint(ankle, foot_index) â€" rough proxy for navicular
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


def compute_step_width(
    frontal_frames: List[KeypointFrame],
    scale_m_per_px: float,
) -> Optional[float]:
    """Mean step width (m): lateral (horizontal) distance between left_heel and
    right_heel, from a frontal camera view (anterior or posterior) where left/
    right separation is actually visible (sagittal view can't resolve this).

    Returns None if left_heel and right_heel are never simultaneously present.
    """
    distances_px: List[float] = []
    for kf in frontal_frames:
        left = kf.keypoints.get("left_heel")
        right = kf.keypoints.get("right_heel")
        if left is not None and right is not None:
            distances_px.append(abs(left.x - right.x))

    if not distances_px:
        return None

    return (sum(distances_px) / len(distances_px)) * scale_m_per_px


def compute_double_support_pct(
    heel_strikes_l: List[GaitEvent],
    heel_strikes_r: List[GaitEvent],
    stride_time_ms: Optional[float],
) -> Optional[float]:
    """Estimate double-support phase as a percentage of the gait cycle.

    Double support occurs twice per cycle (loading response + pre-swing), each
    lasting roughly the time offset between one foot's heel strike and the
    other foot's next heel strike. Estimated as
    (2 x mean_step_time_offset_ms / stride_time_ms) x 100.

    Returns None if there isn't at least one L->R or R->L heel-strike pair, or
    stride_time_ms is unavailable/non-positive (caller should fall back to
    `100 - swing_pct_L` in that case).
    """
    all_hs = sorted(list(heel_strikes_l) + list(heel_strikes_r), key=lambda e: e.timestamp_ms)
    step_time_diffs_ms = [
        b.timestamp_ms - a.timestamp_ms
        for a, b in zip(all_hs, all_hs[1:])
        if a.foot != b.foot and b.timestamp_ms > a.timestamp_ms
    ]

    if not step_time_diffs_ms or not stride_time_ms or stride_time_ms <= 0:
        return None

    mean_step_time_diff_ms = sum(step_time_diffs_ms) / len(step_time_diffs_ms)
    return (2.0 * mean_step_time_diff_ms / stride_time_ms) * 100.0


# â"€â"€ Symmetry â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


def compute_symmetry_index(left_val: float, right_val: float) -> float:
    """SI = |L - R| / mean(L, R) é— 100.

    Returns 0.0 when mean is effectively zero (both sides are zero).
    """
    mean_val = (left_val + right_val) / 2.0
    if mean_val < 1e-12:
        return 0.0
    return abs(left_val - right_val) / mean_val * 100.0

