"""Camera calibration â€” loads intrinsic parameters and undistorts frames.

Two distinct outcomes for a missing vs. malformed calibration file:
  - Missing file  â†’ WARNING + returns None â†’ pipeline runs in passthrough mode.
  - Malformed YAML â†’ CalibrationLoadError (operator must fix the file before proceeding).

CameraCalibrator precomputes cv2.remap maps once at construction so the
per-frame cost is a single cv2.remap call (not initUndistortRectifyMap every frame).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
import yaml

from gait.common.interfaces import Frame
from gait.common.logging_utils import get_logger
from gait.common.types import CalibrationLoadError, CameraCalibration

logger = get_logger(__name__)


def load_camera_calibration(
    camera_name: str,
    cameras_config_dir: Path,
) -> Optional[CameraCalibration]:
    """Load intrinsic calibration for one camera from its YAML file.

    Expected YAML structure:
        camera_matrix: [[fx, 0, cx], [0, fy, cy], [0, 0, 1]]
        dist_coeffs: [k1, k2, p1, p2, k3]
        image_size: [width, height]

    Returns:
        CameraCalibration if file exists and is valid, None if file is missing.

    Raises:
        CalibrationLoadError: File exists but is malformed or missing required keys.
    """
    config_file = cameras_config_dir / f"{camera_name}.yaml"

    if not config_file.exists():
        logger.warning(
            "calibration_file_missing",
            extra={
                "camera_name": camera_name,
                "path": str(config_file),
                "mode": "passthrough",
            },
        )
        return None

    try:
        with open(config_file, "r") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise CalibrationLoadError(
            f"Calibration YAML for {camera_name!r} is malformed: {config_file}"
        ) from exc

    if not isinstance(data, dict):
        raise CalibrationLoadError(
            f"Calibration YAML for {camera_name!r} must be a mapping: {config_file}"
        )

    required = ("camera_matrix", "dist_coeffs", "image_size")
    missing_keys = [k for k in required if k not in data]
    if missing_keys:
        raise CalibrationLoadError(
            f"Calibration YAML for {camera_name!r} missing keys {missing_keys}: {config_file}"
        )

    try:
        camera_matrix = np.array(data["camera_matrix"], dtype=np.float64).reshape(3, 3)
        dist_coeffs = np.array(data["dist_coeffs"], dtype=np.float64).reshape(1, -1)
        image_size: Tuple[int, int] = (
            int(data["image_size"][0]),
            int(data["image_size"][1]),
        )
    except Exception as exc:
        raise CalibrationLoadError(
            f"Calibration YAML for {camera_name!r} has invalid values: {config_file}"
        ) from exc

    return CameraCalibration(
        camera_name=camera_name,
        camera_matrix=camera_matrix,
        dist_coeffs=dist_coeffs,
        image_size=image_size,
    )


class CameraCalibrator:
    """Holds precomputed cv2.remap maps and applies undistortion per frame.

    Remap maps are computed once in __init__ via cv2.initUndistortRectifyMap â€”
    per-frame cost is a single cv2.remap call.

    When calibration is None, apply() is a passthrough that still returns a
    new Frame with np.copy(image) â€” callers always receive an independent array.
    """

    def __init__(self, calibration: Optional[CameraCalibration]) -> None:
        self._calibration = calibration

        if calibration is not None:
            w, h = calibration.image_size
            map1, map2 = cv2.initUndistortRectifyMap(
                calibration.camera_matrix,
                calibration.dist_coeffs,
                None,
                calibration.camera_matrix,
                (w, h),
                cv2.CV_32FC1,
            )
            calibration.map1 = map1
            calibration.map2 = map2
            logger.info(
                "calibration_maps_computed",
                extra={"camera_name": calibration.camera_name, "image_size": [w, h]},
            )

    @property
    def is_calibrated(self) -> bool:
        """True when remap maps are ready; False means passthrough mode."""
        return self._calibration is not None and self._calibration.is_calibrated

    def apply(self, frame: Frame) -> Frame:
        """Undistort a frame and return a new Frame.

        Always returns a new ndarray â€” never shares memory with the input.
        """
        if not self.is_calibrated:
            return Frame(
                image=np.copy(frame.image),
                timestamp_ms=frame.timestamp_ms,
                camera_view=frame.camera_view,
                frame_index=frame.frame_index,
                confidence=frame.confidence,
            )

        assert self._calibration is not None
        undistorted = cv2.remap(
            frame.image,
            self._calibration.map1,
            self._calibration.map2,
            interpolation=cv2.INTER_LINEAR,
        )
        return Frame(
            image=undistorted,  # cv2.remap always allocates a new array
            timestamp_ms=frame.timestamp_ms,
            camera_view=frame.camera_view,
            frame_index=frame.frame_index,
            confidence=frame.confidence,
        )

