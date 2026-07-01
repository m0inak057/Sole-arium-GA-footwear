"""StaticTrialProcessor â€” calibrates per-subject joint-angle offsets.

The processor accepts ~3 seconds of quiet-standing frames, averages keypoint
positions across those frames (discarding low-confidence detections), and
computes baseline joint angles at ankle, knee, and hip.  These angles become
the anatomical zero references that the biomechanical analyzer subtracts from
dynamic measurements, making all reported joint angles subject-relative rather
than camera-relative.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from gait.common.interfaces import Keypoint, KeypointFrame
from gait.common.logging_utils import get_logger
from gait.common.types import StaticTrial
from gait.pipeline.config import StaticTrialConfig

logger = get_logger(__name__)


class StaticTrialProcessor:
    """Processes a quiet-standing capture into per-subject joint-angle offsets."""

    def __init__(self, config: StaticTrialConfig, fps: float = 120.0) -> None:
        self._cfg = config
        self._fps = fps

    def process(self, session_id: str, keypoint_frames: List[KeypointFrame]) -> StaticTrial:
        """Average standing-posture keypoints and compute anatomical zero offsets.

        Args:
            session_id:       Session identifier for the resulting StaticTrial.
            keypoint_frames:  Frames from the quiet-standing capture.  The
                              processor uses at most ``duration_sec * fps`` frames
                              from the start of the list.

        Returns:
            StaticTrial with averaged keypoints and joint_angle_offsets.
        """
        required = int(self._cfg.duration_sec * self._fps)
        frames = keypoint_frames[:required]

        avg_kps = self._average_keypoints(frames)
        offsets = self._compute_offsets(avg_kps)

        logger.info(
            "static_trial.processed",
            extra={
                "session_id": session_id,
                "frames_used": len(frames),
                "frames_available": len(keypoint_frames),
                "n_avg_keypoints": len(avg_kps),
                "offsets": offsets,
            },
        )
        return StaticTrial(
            session_id=session_id,
            duration_frames=len(frames),
            keypoints=avg_kps,
            joint_angle_offsets=offsets,
        )

    # â”€â”€ private helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _average_keypoints(self, frames: List[KeypointFrame]) -> Dict[str, Keypoint]:
        """Return one Keypoint per name, averaged over all frames that meet the
        confidence threshold."""
        accumulator: Dict[str, List[Tuple[float, float]]] = {}
        for frame in frames:
            for name, kp in frame.keypoints.items():
                if kp.confidence >= self._cfg.required_keypoint_confidence:
                    accumulator.setdefault(name, []).append((kp.x, kp.y))

        result: Dict[str, Keypoint] = {}
        for name, coords in accumulator.items():
            mean_x = sum(c[0] for c in coords) / len(coords)
            mean_y = sum(c[1] for c in coords) / len(coords)
            result[name] = Keypoint(x=mean_x, y=mean_y, confidence=1.0, name=name)
        return result

    def _compute_offsets(self, keypoints: Dict[str, Keypoint]) -> Dict[str, float]:
        """Compute baseline joint angles from the averaged standing posture.

        Returns a flat dict with keys like ``"left_ankle_deg"``.  Missing
        keypoints silently produce no entry rather than a zero placeholder so
        callers can distinguish measured-zero from absent-data.
        """
        offsets: Dict[str, float] = {}
        for side in ("left", "right"):
            hip = keypoints.get(f"{side}_hip")
            knee = keypoints.get(f"{side}_knee")
            ankle = keypoints.get(f"{side}_ankle")
            heel = keypoints.get(f"{side}_heel")

            # Ankle: rearfoot angle in standing (same convention as dynamic analysis)
            if knee and ankle and heel:
                rfa = _rearfoot_angle(knee, ankle, heel)
                if side == "right":
                    rfa = -rfa  # clinical sign: positive = eversion/pronation
                offsets[f"{side}_ankle_deg"] = rfa

            # Knee: interior angle at the joint (hip â†’ knee â† ankle)
            if hip and knee and ankle:
                offsets[f"{side}_knee_deg"] = _joint_angle(hip, knee, ankle)

            # Hip: angle of the thigh segment from the downward vertical
            if hip and knee:
                offsets[f"{side}_hip_deg"] = _segment_from_vertical(hip, knee)

        return offsets


# â”€â”€ geometry helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _rearfoot_angle(knee: Keypoint, ankle: Keypoint, heel: Keypoint) -> float:
    """Signed angle from the downward vertical to the ankleâ†’heel vector.

    Matches ``compute_rearfoot_angle`` in parameters.py without importing it
    here to keep ingestion free of an analysis-layer dependency.
    """
    heel_vec = (heel.x - ankle.x, heel.y - ankle.y)
    # signed_angle_deg((0,1), v) = atan2(-v.x, v.y)
    return math.degrees(math.atan2(-heel_vec[0], heel_vec[1] if abs(heel_vec[1]) > 1e-9 else 1e-9))


def _joint_angle(a: Keypoint, b: Keypoint, c: Keypoint) -> float:
    """Interior angle at vertex b between segments aâ†’b and bâ†’c (degrees)."""
    v1 = (a.x - b.x, a.y - b.y)
    v2 = (c.x - b.x, c.y - b.y)
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    mag = math.sqrt((v1[0]**2 + v1[1]**2) * (v2[0]**2 + v2[1]**2))
    if mag < 1e-9:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / mag))))


def _segment_from_vertical(top: Keypoint, bottom: Keypoint) -> float:
    """Angle of the topâ†’bottom segment from the downward vertical (degrees).

    In image space y increases downward, so a perfectly vertical segment has
    dx=0 and dy>0 â†’ angle=0Â°.  A segment tilted right has dx>0 â†’ positive angle.
    """
    dx = bottom.x - top.x
    dy = bottom.y - top.y
    return math.degrees(math.atan2(dx, dy if abs(dy) > 1e-9 else 1e-9))

