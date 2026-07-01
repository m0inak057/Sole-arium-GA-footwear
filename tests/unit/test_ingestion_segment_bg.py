"""Unit tests for background subtraction (src.gait.ingestion.segment_bg)."""

import numpy as np
import pytest

from gait.common.interfaces import Frame
from gait.ingestion.segment_bg import (
    MOG2BackgroundSubtractor,
    create_background_subtractor,
)
from gait.pipeline.config import IngestionConfig

# â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

IMG_H, IMG_W = 240, 320


def make_cfg(**overrides):
    return IngestionConfig(
        mog2_history=10,
        mog2_var_threshold=16.0,
        mog2_detect_shadows=True,
        mog2_morph_kernel_size_px=3,
        **overrides,
    )


def make_frame(image: np.ndarray, idx: int = 0) -> Frame:
    return Frame(
        image=image,
        timestamp_ms=idx * 33,
        camera_view="sagittal",
        frame_index=idx,
        confidence=1.0,
    )


def bg_frame(idx: int = 0) -> Frame:
    return make_frame(np.zeros((IMG_H, IMG_W, 3), dtype=np.uint8), idx)


def fg_frame(idx: int = 0) -> Frame:
    img = np.zeros((IMG_H, IMG_W, 3), dtype=np.uint8)
    img[60:180, 80:240] = 200
    return make_frame(img, idx)


def warmup(sub: MOG2BackgroundSubtractor, n: int | None = None) -> None:
    """Feed the subtractor enough background frames to pass the warmup window."""
    n = n or sub._config.mog2_history + 2
    for i in range(n):
        sub.apply(bg_frame(i))


# â”€â”€ mask dtype and values â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestMaskProperties:
    def test_mask_dtype_is_uint8(self):
        sub = MOG2BackgroundSubtractor(make_cfg())
        _, mask = sub.apply(bg_frame())
        assert mask.dtype == np.uint8

    def test_mask_values_only_0_and_255(self):
        sub = MOG2BackgroundSubtractor(make_cfg())
        warmup(sub)
        _, mask = sub.apply(fg_frame(20))
        unique = set(np.unique(mask))
        assert unique.issubset({0, 255}), f"shadow value leaked: {unique}"

    def test_mask_shape_matches_image(self):
        sub = MOG2BackgroundSubtractor(make_cfg())
        _, mask = sub.apply(bg_frame())
        assert mask.shape == (IMG_H, IMG_W)


# â”€â”€ output frame properties â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestOutputFrame:
    def test_output_image_is_new_ndarray(self):
        sub = MOG2BackgroundSubtractor(make_cfg())
        frame = bg_frame()
        out_frame, _ = sub.apply(frame)
        assert not np.shares_memory(frame.image, out_frame.image)

    def test_output_frame_preserves_timestamp(self):
        sub = MOG2BackgroundSubtractor(make_cfg())
        frame = make_frame(np.zeros((IMG_H, IMG_W, 3), dtype=np.uint8), idx=5)
        out_frame, _ = sub.apply(frame)
        assert out_frame.timestamp_ms == frame.timestamp_ms

    def test_output_frame_preserves_camera_view(self):
        sub = MOG2BackgroundSubtractor(make_cfg())
        frame = bg_frame()
        out_frame, _ = sub.apply(frame)
        assert out_frame.camera_view == frame.camera_view

    def test_output_frame_preserves_frame_index(self):
        sub = MOG2BackgroundSubtractor(make_cfg())
        frame = make_frame(np.zeros((IMG_H, IMG_W, 3), dtype=np.uint8), idx=9)
        out_frame, _ = sub.apply(frame)
        assert out_frame.frame_index == frame.frame_index


# â”€â”€ warmup tracking â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestWarmup:
    def test_is_warmed_up_false_initially(self):
        sub = MOG2BackgroundSubtractor(make_cfg())
        assert not sub.is_warmed_up

    def test_is_warmed_up_true_after_history_frames(self):
        sub = MOG2BackgroundSubtractor(make_cfg())
        warmup(sub)
        assert sub.is_warmed_up

    def test_first_frame_returns_full_foreground(self):
        sub = MOG2BackgroundSubtractor(make_cfg())
        # On the very first call, MOG2 has no model â†’ all pixels are "new" â†’ all 255
        _, mask = sub.apply(bg_frame(0))
        assert mask.max() == 255


# â”€â”€ reset â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestReset:
    def test_reset_clears_frame_count(self):
        sub = MOG2BackgroundSubtractor(make_cfg())
        warmup(sub)
        sub.reset()
        assert sub._frames_processed == 0

    def test_reset_clears_background_model(self):
        sub = MOG2BackgroundSubtractor(make_cfg())
        warmup(sub)
        sub.reset()
        # After reset the first frame should again be all-foreground
        _, mask = sub.apply(bg_frame(0))
        assert mask.max() == 255

    def test_is_warmed_up_false_after_reset(self):
        sub = MOG2BackgroundSubtractor(make_cfg())
        warmup(sub)
        sub.reset()
        assert not sub.is_warmed_up


# â”€â”€ factory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestCreateBackgroundSubtractor:
    def test_mog2_returns_correct_type(self):
        sub = create_background_subtractor("mog2", make_cfg())
        assert isinstance(sub, MOG2BackgroundSubtractor)

    def test_mog2_case_insensitive(self):
        sub = create_background_subtractor("MOG2", make_cfg())
        assert isinstance(sub, MOG2BackgroundSubtractor)

    def test_unknown_model_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown background_subtraction_model"):
            create_background_subtractor("learned", make_cfg())

