"""Multi-view 3D keypoint reconstruction from synchronized cameras."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from gait.common.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class CameraIntrinsics:
    """Camera intrinsic parameters."""
    focal_x: float
    focal_y: float
    center_x: float
    center_y: float
    distortion: np.ndarray  # [k1, k2, p1, p2, k3]


@dataclass
class CameraExtrinsics:
    """Camera extrinsic parameters (pose)."""
    rotation: np.ndarray  # 3x3 rotation matrix
    translation: np.ndarray  # 3x1 translation vector


@dataclass
class Keypoint3D:
    """3D keypoint with confidence."""
    x: float
    y: float
    z: float
    confidence: float


class TriangulationEngine:
    """Triangulates 2D keypoints from multiple views into 3D."""

    def __init__(self):
        """Initialize triangulation engine."""
        self.min_confidence_threshold = 0.5

    def triangulate(
        self,
        keypoint_2d_view1: tuple[float, float],
        keypoint_2d_view2: tuple[float, float],
        confidence1: float,
        confidence2: float,
        intrinsics1: CameraIntrinsics,
        intrinsics2: CameraIntrinsics,
        extrinsics1: CameraExtrinsics,
        extrinsics2: CameraExtrinsics,
    ) -> Optional[Keypoint3D]:
        """Triangulate 2D points from two camera views into 3D.

        Uses linear triangulation method (DLT).

        Args:
            keypoint_2d_view1: (x, y) in view 1
            keypoint_2d_view2: (x, y) in view 2
            confidence1: Confidence in view 1 detection
            confidence2: Confidence in view 2 detection
            intrinsics1: Camera 1 intrinsics
            intrinsics2: Camera 2 intrinsics
            extrinsics1: Camera 1 extrinsics (world pose)
            extrinsics2: Camera 2 extrinsics (world pose)

        Returns:
            Keypoint3D with triangulated position, or None if failed
        """
        try:
            # Check minimum confidence
            if confidence1 < self.min_confidence_threshold or confidence2 < self.min_confidence_threshold:
                logger.debug("triangulation.low_confidence")
                return None

            # Build projection matrices
            K1 = self._build_K_matrix(intrinsics1)
            K2 = self._build_K_matrix(intrinsics2)

            P1 = K1 @ np.hstack([extrinsics1.rotation, extrinsics1.translation])
            P2 = K2 @ np.hstack([extrinsics2.rotation, extrinsics2.translation])

            # Linear triangulation
            x1, y1 = keypoint_2d_view1
            x2, y2 = keypoint_2d_view2

            # Build system of equations
            A = np.array([
                x1 * P1[2, :] - P1[0, :],
                y1 * P1[2, :] - P1[1, :],
                x2 * P2[2, :] - P2[0, :],
                y2 * P2[2, :] - P2[1, :],
            ])

            # SVD to solve
            _, _, Vt = np.linalg.svd(A)
            X = Vt[-1, :]
            X = X / X[3]  # Normalize by homogeneous coordinate

            # Compute reprojection error as confidence
            error1 = self._reprojection_error(X, P1, keypoint_2d_view1)
            error2 = self._reprojection_error(X, P2, keypoint_2d_view2)
            mean_error = (error1 + error2) / 2.0

            # Confidence inversely proportional to error
            confidence = max(0.0, 1.0 - min(mean_error, 1.0))
            confidence = confidence * min(confidence1, confidence2)

            logger.debug(
                "triangulation.success",
                extra={
                    "position": [float(X[0]), float(X[1]), float(X[2])],
                    "confidence": float(confidence),
                },
            )

            return Keypoint3D(
                x=float(X[0]),
                y=float(X[1]),
                z=float(X[2]),
                confidence=float(confidence),
            )

        except Exception as e:
            logger.error("triangulation.failed", extra={"error": str(e)})
            return None

    def _build_K_matrix(self, intrinsics: CameraIntrinsics) -> np.ndarray:
        """Build intrinsic matrix K."""
        return np.array([
            [intrinsics.focal_x, 0, intrinsics.center_x],
            [0, intrinsics.focal_y, intrinsics.center_y],
            [0, 0, 1],
        ])

    def _reprojection_error(
        self,
        point_3d: np.ndarray,
        P: np.ndarray,
        point_2d: tuple[float, float],
    ) -> float:
        """Compute reprojection error (L2 distance in pixels)."""
        try:
            # Project 3D point to 2D
            projected = P @ point_3d
            projected = projected / projected[2]  # Normalize

            x_proj = projected[0]
            y_proj = projected[1]
            x_obs, y_obs = point_2d

            error = np.sqrt((x_proj - x_obs) ** 2 + (y_proj - y_obs) ** 2)
            return float(error)
        except Exception:
            return float("inf")

