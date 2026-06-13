"""Background subtraction — isolates the subject from a static background.

Each camera must have its own BackgroundSubtractor instance — sagittal and
posterior cameras see different backgrounds and sharing one MOG2 model across
cameras causes correctness bugs.

During warmup (first mog2_history frames) the model produces noisy masks.
Callers should treat frames from this period with lower confidence.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Tuple

import cv2
import numpy as np

from src.gait.common.interfaces import Frame
from src.gait.common.logging_utils import get_logger
from src.gait.pipeline.config import IngestionConfig

logger = get_logger(__name__)


class BackgroundSubtractor(ABC):
    """Abstract base for background subtraction strategies."""

    @abstractmethod
    def apply(self, frame: Frame) -> Tuple[Frame, np.ndarray]:
        """Apply background subtraction to one frame.

        Returns:
            (processed_frame, foreground_mask)
            - processed_frame: Frame with background pixels zeroed; always a new ndarray.
            - foreground_mask: uint8 ndarray shape (H, W); 255 = foreground, 0 = background.
        """

    @abstractmethod
    def reset(self) -> None:
        """Discard the learned background model (e.g., for a new session)."""


class MOG2BackgroundSubtractor(BackgroundSubtractor):
    """OpenCV MOG2 background subtractor.

    All tuning parameters come from IngestionConfig — no hardcoded values.
    Shadows (marked 127 by MOG2 when detectShadows=True) are treated as
    background to avoid misclassifying shadow blobs as person pixels.
    """

    def __init__(self, config: IngestionConfig) -> None:
        self._config = config
        self._subtractor = self._create_subtractor()
        kernel_size = config.mog2_morph_kernel_size_px
        self._kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (kernel_size, kernel_size)
        )
        self._frames_processed = 0

    @property
    def is_warmed_up(self) -> bool:
        """True once the background model has seen enough frames to be reliable."""
        return self._frames_processed >= self._config.mog2_history

    def apply(self, frame: Frame) -> Tuple[Frame, np.ndarray]:
        """Apply MOG2 + morphological cleanup and zero out the background."""
        raw_mask = self._subtractor.apply(frame.image)

        # Shadow pixels are 127 — treat as background
        binary_mask = np.where(raw_mask == 255, np.uint8(255), np.uint8(0))

        # Close small holes, then remove small isolated blobs
        clean_mask = cv2.morphologyEx(binary_mask, cv2.MORPH_CLOSE, self._kernel)
        clean_mask = cv2.morphologyEx(clean_mask, cv2.MORPH_OPEN, self._kernel)

        fg_image = np.copy(frame.image)
        fg_image[clean_mask == 0] = 0

        self._frames_processed += 1

        return (
            Frame(
                image=fg_image,
                timestamp_ms=frame.timestamp_ms,
                camera_view=frame.camera_view,
                frame_index=frame.frame_index,
                confidence=frame.confidence,
            ),
            clean_mask,
        )

    def reset(self) -> None:
        self._subtractor = self._create_subtractor()
        self._frames_processed = 0
        logger.info("background_subtractor_reset")

    def _create_subtractor(self) -> cv2.BackgroundSubtractorMOG2:
        return cv2.createBackgroundSubtractorMOG2(
            history=self._config.mog2_history,
            varThreshold=self._config.mog2_var_threshold,
            detectShadows=self._config.mog2_detect_shadows,
        )


def create_background_subtractor(
    model_name: str,
    config: IngestionConfig,
) -> BackgroundSubtractor:
    """Factory — return the requested BackgroundSubtractor.

    Supported: 'mog2'
    Raises ValueError for unknown model names.
    """
    if model_name.lower() == "mog2":
        return MOG2BackgroundSubtractor(config)
    raise ValueError(
        f"Unknown background_subtraction_model {model_name!r}. Supported: 'mog2'"
    )
