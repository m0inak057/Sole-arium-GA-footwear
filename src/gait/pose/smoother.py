"""1-Euro filter for temporal smoothing of keypoint trajectories.

Reference: Casiez et al. (2012) "1€ Filter: A Simple Speed-based Low-pass Filter
for Noisy Input in Interactive Systems", CHI 2012.

smoothing_window maps to 1-Euro min_cutoff:
    min_cutoff = 1.0 / smoothing_window
Higher window → lower cutoff → more aggressive smoothing.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from src.gait.common.interfaces import Keypoint, KeypointFrame, KeypointSmoother


class _LowPassFilter:
    """Single-pole IIR low-pass filter."""

    def __init__(self, alpha: float) -> None:
        self._alpha = alpha
        self._y: Optional[float] = None

    def __call__(self, x: float, alpha: Optional[float] = None) -> float:
        a = alpha if alpha is not None else self._alpha
        self._y = x if self._y is None else a * x + (1.0 - a) * self._y
        return self._y  # type: ignore[return-value]


class _OneEuroFilter:
    """Single-axis 1-Euro adaptive low-pass filter.

    Args:
        freq:       Sampling frequency in Hz (frames per second).
        min_cutoff: Minimum cutoff frequency. Lower = more smoothing.
        beta:       Speed coefficient. Higher = less lag on fast motion.
        d_cutoff:   Cutoff for the derivative low-pass (Hz).
    """

    def __init__(
        self,
        freq: float,
        min_cutoff: float = 1.0,
        beta: float = 0.007,
        d_cutoff: float = 1.0,
    ) -> None:
        self._freq = freq
        self._min_cutoff = min_cutoff
        self._beta = beta
        self._x_filt = _LowPassFilter(self._alpha(min_cutoff))
        self._dx_filt = _LowPassFilter(self._alpha(d_cutoff))
        self._last_x: Optional[float] = None

    def _alpha(self, cutoff: float) -> float:
        r = 2.0 * math.pi * cutoff / self._freq
        return r / (r + 1.0)

    def __call__(self, x: float) -> float:
        dx = 0.0 if self._last_x is None else (x - self._last_x) * self._freq
        self._last_x = x
        dx_hat = self._dx_filt(dx)
        cutoff = self._min_cutoff + self._beta * abs(dx_hat)
        return self._x_filt(x, alpha=self._alpha(cutoff))


class OneEuroSmoother(KeypointSmoother):
    """Apply 1-Euro filtering to keypoint trajectories."""

    def __init__(self, fps: float, smoothing_window: int = 5) -> None:
        self._fps = max(1.0, float(fps))
        self._min_cutoff = 1.0 / max(1, smoothing_window)

    def smooth(self, trajectory: Dict[int, float]) -> Dict[int, float]:
        """Smooth a 1D trajectory (frame_index → value).

        Processes frame indices in ascending order; a fresh filter instance
        guarantees no cross-gap smearing.
        """
        if not trajectory:
            return {}
        f = _OneEuroFilter(self._fps, min_cutoff=self._min_cutoff)
        return {idx: f(trajectory[idx]) for idx in sorted(trajectory)}

    def smooth_frame(self, keypoint_frames: List[KeypointFrame]) -> List[KeypointFrame]:
        """Apply 1-Euro smoothing to every keypoint coordinate across all frames.

        Per-coordinate (x, y, z) trajectories are extracted, independently
        smoothed, then written back into new KeypointFrame objects.
        Keypoints absent from a frame remain absent after smoothing.
        """
        if not keypoint_frames:
            return []

        # Collect per-name, per-axis trajectories
        trajs: Dict[str, Dict[str, Dict[int, float]]] = {}
        for kf in keypoint_frames:
            for name, kp in kf.keypoints.items():
                if name not in trajs:
                    trajs[name] = {"x": {}, "y": {}, "z": {}}
                trajs[name]["x"][kf.frame_index] = kp.x
                trajs[name]["y"][kf.frame_index] = kp.y
                if kp.z is not None:
                    trajs[name]["z"][kf.frame_index] = kp.z

        # Smooth each axis trajectory
        smoothed: Dict[str, Dict[str, Dict[int, float]]] = {
            name: {
                "x": self.smooth(coords["x"]),
                "y": self.smooth(coords["y"]),
                "z": self.smooth(coords["z"]) if coords["z"] else {},
            }
            for name, coords in trajs.items()
        }

        # Rebuild KeypointFrames with smoothed coordinates
        result: List[KeypointFrame] = []
        for kf in keypoint_frames:
            new_kps: Dict[str, Keypoint] = {}
            for name, kp in kf.keypoints.items():
                s = smoothed.get(name)
                if s is None:
                    new_kps[name] = kp
                    continue
                new_kps[name] = Keypoint(
                    x=s["x"].get(kf.frame_index, kp.x),
                    y=s["y"].get(kf.frame_index, kp.y),
                    z=s["z"].get(kf.frame_index, kp.z) if s["z"] else kp.z,
                    confidence=kp.confidence,
                    name=kp.name,
                )
            result.append(
                KeypointFrame(
                    timestamp_ms=kf.timestamp_ms,
                    frame_index=kf.frame_index,
                    camera_view=kf.camera_view,
                    keypoints=new_kps,
                    confidence=kf.confidence,
                )
            )

        return result
