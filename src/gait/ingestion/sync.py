"""Multi-camera frame alignment — produces time-synchronized SyncedFrameSet objects.

align_frames() expects exactly three cameras: "anterior", "sagittal", "posterior".
Pairs frames from all cameras by timestamp within a configurable tolerance.
The first camera (alphabetically: "anterior") is the anchor;
frames from other cameras are advanced to match it.
"""

from __future__ import annotations

from typing import Dict, Generator, Iterable, Iterator, List

from src.gait.common.interfaces import Frame
from src.gait.common.logging_utils import get_logger
from src.gait.common.types import FrameSyncError, SyncedFrameSet
from src.gait.pipeline.config import IngestionConfig

logger = get_logger(__name__)


def align_frames(
    frame_streams: Dict[str, Iterable[Frame]],
    config: IngestionConfig,
) -> Generator[SyncedFrameSet, None, None]:
    """Align frames from three cameras (anterior, sagittal, posterior) into time-synchronized sets.

    Validates that exactly three cameras are present: "anterior", "sagittal", "posterior".
    For each anchor frame (anterior), finds the closest frame from sagittal and posterior
    within sync_tolerance_ms. Frames that cannot be aligned are dropped with a WARNING.

    Raises FrameSyncError after max_unsync_frames_before_error consecutive
    windows where at least one camera is out of sync.
    """
    required_cameras = {"anterior", "sagittal", "posterior"}
    if not frame_streams:
        raise FrameSyncError("frame_streams cannot be empty")

    provided_cameras = set(frame_streams.keys())
    if provided_cameras != required_cameras:
        missing = required_cameras - provided_cameras
        extra = provided_cameras - required_cameras
        error_msg = f"Expected cameras {required_cameras}, got {provided_cameras}"
        if missing:
            error_msg += f"; missing: {missing}"
        if extra:
            error_msg += f"; unexpected: {extra}"
        raise FrameSyncError(error_msg)

    camera_names = sorted(frame_streams.keys())
    anchor_cam = camera_names[0]
    other_cams = camera_names[1:]

    iterators: Dict[str, Iterator[Frame]] = {
        cam: iter(frames) for cam, frames in frame_streams.items()
    }

    # One buffered frame per non-anchor camera (pre-fetched)
    buffers: Dict[str, Frame | None] = {}
    for cam in other_cams:
        buffers[cam] = next(iterators[cam], None)

    consecutive_unsync = 0
    tolerance_ms = config.sync_tolerance_ms

    for anchor_frame in iterators[anchor_cam]:
        anchor_ts = anchor_frame.timestamp_ms
        synced: Dict[str, Frame] = {anchor_cam: anchor_frame}

        for cam in other_cams:
            # Advance this camera until its frame is within tolerance or past anchor
            while buffers[cam] is not None:
                delta = buffers[cam].timestamp_ms - anchor_ts
                if abs(delta) <= tolerance_ms:
                    break
                if delta < -tolerance_ms:
                    # Camera is behind anchor — advance it
                    buffers[cam] = next(iterators[cam], None)
                else:
                    # Camera is ahead of anchor — anchor frame has no match
                    break

            if buffers[cam] is not None:
                if abs(buffers[cam].timestamp_ms - anchor_ts) <= tolerance_ms:
                    synced[cam] = buffers[cam]
                    buffers[cam] = next(iterators[cam], None)

        if len(synced) == len(camera_names):
            consecutive_unsync = 0
            yield SyncedFrameSet(
                anchor_timestamp_ms=anchor_ts,
                frames=synced,
            )
        else:
            consecutive_unsync += 1
            missing = sorted(set(camera_names) - set(synced))
            logger.warning(
                "frame_sync_miss",
                extra={
                    "anchor_ts_ms": anchor_ts,
                    "missing_cameras": missing,
                    "consecutive": consecutive_unsync,
                },
            )
            if consecutive_unsync >= config.max_unsync_frames_before_error:
                raise FrameSyncError(
                    f"{consecutive_unsync} consecutive frames could not be synced "
                    f"(tolerance={tolerance_ms} ms). Check that all camera clocks "
                    f"are synchronized."
                )


def flatten_synced_frames(synced_sets: Iterable[SyncedFrameSet]) -> List[Frame]:
    """Flatten an iterable of SyncedFrameSet into a flat Frame list.

    Ordering: all cameras for set N, then all cameras for set N+1.
    Useful for feeding a batch pose inference call.
    """
    result: List[Frame] = []
    for synced in synced_sets:
        result.extend(synced.frames.values())
    return result
