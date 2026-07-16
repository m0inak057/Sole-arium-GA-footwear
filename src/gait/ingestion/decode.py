"""Video decoding â€” converts a video file into a stream of Frame objects.

VideoFileSource implements the VideoSource ABC so hardware cameras can be
swapped in (by implementing LiveCameraSource) without touching any pipeline
code. The only public surface the pipeline uses is the context-manager form:

    with VideoFileSource(path, camera_view, config) as src:
        for frame in src.get_frames():
            ...
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator, Optional, Tuple

import cv2
import numpy as np

from gait.common.geometry import frame_index_to_timestamp_ms
from gait.common.interfaces import Frame, VideoSource
from gait.common.logging_utils import get_logger
from gait.common.types import VideoDecodeError
from gait.pipeline.config import IngestionConfig

logger = get_logger(__name__)

# cv2.CAP_PROP_ORIENTATION_META reports the container rotation tag in degrees.
_ROTATE_CODE_BY_ANGLE = {
    90: cv2.ROTATE_90_CLOCKWISE,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
    180: cv2.ROTATE_180,
}


class VideoFileSource(VideoSource):
    """Read a video file and yield Frame objects.

    Implements VideoSource ABC â€” hardware cameras need only provide a
    LiveCameraSource implementation; all pipeline code is unchanged.
    """

    def __init__(
        self,
        path: Path,
        camera_view: str,
        config: IngestionConfig,
    ) -> None:
        self._path = Path(path)
        self._camera_view = camera_view
        self._config = config
        self._cap: cv2.VideoCapture | None = None
        # cv2 rotate code (e.g. cv2.ROTATE_90_CLOCKWISE) to normalize a
        # portrait-recorded stream to landscape, or None if no rotation needed.
        self._rotate_code: Optional[int] = None

    # â”€â”€ Context manager â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def __enter__(self) -> "VideoFileSource":
        self.open()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # â”€â”€ VideoSource ABC â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def open(self) -> None:
        """Open the video file. Raises VideoDecodeError if not found or unreadable."""
        if not self._path.exists():
            raise VideoDecodeError(f"Video file not found: {self._path}")
        self._cap = cv2.VideoCapture(str(self._path))
        if not self._cap.isOpened():
            raise VideoDecodeError(f"cv2 could not open video: {self._path}")
        self._rotate_code = self._detect_rotation()
        self._warn_if_mismatch()

    def close(self) -> None:
        """Release the VideoCapture resource."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def get_frames(self) -> Generator[Frame, None, None]:
        """Yield Frame objects one at a time â€” never buffers the full video.

        Raises VideoDecodeError when consecutive decode failures exceed
        IngestionConfig.max_consecutive_decode_failure_pct of total frames.
        """
        if self._cap is None:
            raise RuntimeError("VideoFileSource.open() must be called before get_frames()")

        total = self.get_frame_count()
        fps = self.get_fps() or self._config.fps
        max_fail = (
            max(1, int(total * self._config.max_consecutive_decode_failure_pct / 100))
            if total > 0
            else 10
        )

        frame_index = 0
        consecutive_failures = 0

        while True:
            ret, bgr = self._cap.read()
            if not ret:
                break  # end of stream

            if bgr is None or bgr.size == 0:
                consecutive_failures += 1
                logger.warning(
                    "frame_decode_failure",
                    extra={
                        "camera_view": self._camera_view,
                        "frame_index": frame_index,
                        "consecutive": consecutive_failures,
                    },
                )
                if consecutive_failures >= max_fail:
                    raise VideoDecodeError(
                        f"{self._path}: {consecutive_failures} consecutive decode "
                        f"failures (limit {max_fail})"
                    )
                frame_index += 1
                continue

            consecutive_failures = 0
            timestamp_ms = frame_index_to_timestamp_ms(frame_index, int(fps))

            if self._rotate_code is not None:
                bgr = cv2.rotate(bgr, self._rotate_code)

            yield Frame(
                image=np.copy(bgr),  # copy â€” caller must not corrupt upstream buffer
                timestamp_ms=timestamp_ms,
                camera_view=self._camera_view,
                frame_index=frame_index,
                confidence=1.0,
            )
            frame_index += 1

    def get_frame_count(self) -> int:
        if self._cap is None:
            return -1
        return int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))

    def get_fps(self) -> float:
        if self._cap is None:
            return float(self._config.fps)
        actual = float(self._cap.get(cv2.CAP_PROP_FPS))
        return actual if actual > 0 else float(self._config.fps)

    def get_resolution(self) -> Tuple[int, int]:
        """Return (width, height) as frames are actually yielded â€” i.e. after
        rotation normalization, so a 90/270Â° rotated stream reports swapped
        dimensions matching what get_frames() produces."""
        if self._cap is None:
            return (self._config.resolution[0], self._config.resolution[1])
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if self._rotate_code in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE):
            return (h, w)
        return (w, h)

    # â”€â”€ Private â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _detect_rotation(self) -> Optional[int]:
        """Detect stream rotation and return the cv2.rotate() code to apply.

        Tries the container rotation tag (CAP_PROP_ORIENTATION_META) first.
        If that is unavailable or reports no rotation, falls back to
        inferring from the stream's reported dimensions: a frame taller than
        it is wide is almost certainly a portrait recording that needs
        rotating to landscape before pose estimation.
        """
        meta_angle = 0
        try:
            meta_angle = int(self._cap.get(cv2.CAP_PROP_ORIENTATION_META))
        except Exception:
            meta_angle = 0

        if meta_angle in _ROTATE_CODE_BY_ANGLE:
            logger.info(
                "rotation_metadata_detected",
                extra={"camera_view": self._camera_view, "angle": meta_angle},
            )
            return _ROTATE_CODE_BY_ANGLE[meta_angle]

        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if h > w:
            logger.info(
                "auto_portrait_correction",
                extra={
                    "camera_view": self._camera_view,
                    "reported_width": w,
                    "reported_height": h,
                },
            )
            return cv2.ROTATE_90_CLOCKWISE

        return None

    def _warn_if_mismatch(self) -> None:
        actual_fps = self.get_fps()
        if abs(actual_fps - self._config.fps) > 1.0:
            logger.warning(
                "fps_mismatch",
                extra={
                    "camera_view": self._camera_view,
                    "actual_fps": actual_fps,
                    "expected_fps": self._config.fps,
                },
            )

        actual_w, actual_h = self.get_resolution()
        exp_w, exp_h = self._config.resolution[0], self._config.resolution[1]
        if actual_w != exp_w or actual_h != exp_h:
            logger.warning(
                "resolution_mismatch",
                extra={
                    "camera_view": self._camera_view,
                    "actual": f"{actual_w}x{actual_h}",
                    "expected": f"{exp_w}x{exp_h}",
                },
            )

