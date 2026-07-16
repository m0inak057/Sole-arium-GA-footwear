"""Multi-camera frame alignment — produces time-synchronized SyncedFrameSet objects.

Two sync modes are supported (controlled by IngestionConfig.sync_mode):

  "timestamp"   — (production / hardware-sync) Pairs frames from all cameras by
                  wall-clock timestamp within sync_tolerance_ms.  Requires all
                  cameras to share a common clock (PTP/NTP or hardware trigger).

  "frame_index" — (file-upload / dev / consumer cameras) Pairs frames by position:
                  frame N of camera A is synced with frame N of camera B and C.
                  All timestamps in the output are taken from the anchor camera;
                  this mode never raises FrameSyncError due to timing differences.

  "auto"        — Tries timestamp mode first.  If < 50% of the first 100 anchor
                  frames pass the tolerance check, it falls back to frame_index
                  mode and logs a WARNING.  Safest default for mixed environments.

align_frames() expects exactly three cameras: "anterior", "sagittal", "posterior".
"""

from __future__ import annotations

from typing import Dict, Generator, Iterable, Iterator, List

from gait.common.interfaces import Frame
from gait.common.logging_utils import get_logger
from gait.common.types import FrameSyncError, SyncedFrameSet
from gait.pipeline.config import IngestionConfig

logger = get_logger(__name__)

_REQUIRED_CAMERAS = {"anterior", "sagittal", "posterior"}


# ── public entry-point ────────────────────────────────────────────────────────


def align_frames(
    frame_streams: Dict[str, Iterable[Frame]],
    config: IngestionConfig,
) -> Generator[SyncedFrameSet, None, None]:
    """Yield time-aligned SyncedFrameSet objects from three camera streams.

    Routing:
      sync_mode="timestamp"   → _align_by_timestamp()
      sync_mode="frame_index" → _align_by_frame_index()
      sync_mode="auto"        → timestamp first; falls back to frame_index
    """
    if not frame_streams:
        raise FrameSyncError("frame_streams cannot be empty")

    provided = set(frame_streams.keys())
    if provided != _REQUIRED_CAMERAS:
        missing = _REQUIRED_CAMERAS - provided
        extra = provided - _REQUIRED_CAMERAS
        msg = f"Expected cameras {_REQUIRED_CAMERAS}, got {provided}"
        if missing:
            msg += f"; missing: {missing}"
        if extra:
            msg += f"; unexpected: {extra}"
        raise FrameSyncError(msg)

    sync_mode: str = getattr(config, "sync_mode", "auto")

    if sync_mode == "frame_index":
        logger.info("frame_sync.mode", extra={"mode": "frame_index"})
        yield from _align_by_frame_index(frame_streams)
    elif sync_mode == "timestamp":
        logger.info("frame_sync.mode", extra={"mode": "timestamp"})
        yield from _align_by_timestamp(frame_streams, config)
    else:  # "auto" or any unrecognised value
        logger.info("frame_sync.mode", extra={"mode": "auto"})
        yield from _align_auto(frame_streams, config)


# ── sync implementations ──────────────────────────────────────────────────────


def _align_by_frame_index(
    frame_streams: Dict[str, Iterable[Frame]],
) -> Generator[SyncedFrameSet, None, None]:
    """Pair cameras by frame position (frame N <-> frame N <-> frame N).

    Stops when the shortest stream is exhausted.  All frames in a set
    share the anchor camera's timestamp in the SyncedFrameSet.
    Ignores wall-clock timestamps entirely — safe for consumer cameras and
    file uploads where cameras were not hardware-synchronized.
    """
    camera_names = sorted(frame_streams.keys())
    anchor_cam = camera_names[0]

    iterators: Dict[str, Iterator[Frame]] = {
        cam: iter(frames) for cam, frames in frame_streams.items()
    }

    frame_count = 0
    while True:
        synced: Dict[str, Frame] = {}
        for cam in camera_names:
            frame = next(iterators[cam], None)
            if frame is None:
                # Shortest stream exhausted — stop.
                logger.info(
                    "frame_index_sync.exhausted",
                    extra={"cam": cam, "frames_yielded": frame_count},
                )
                return
            synced[cam] = frame

        anchor_ts = synced[anchor_cam].timestamp_ms
        frame_count += 1
        yield SyncedFrameSet(anchor_timestamp_ms=anchor_ts, frames=synced)


def _align_by_timestamp(
    frame_streams: Dict[str, Iterable[Frame]],
    config: IngestionConfig,
) -> Generator[SyncedFrameSet, None, None]:
    """Original timestamp-based alignment (for hardware-synced cameras).

    The alphabetically-first camera ("anterior") is the anchor.  For each
    anchor frame, non-anchor camera buffers are advanced until a frame
    within sync_tolerance_ms is found.

    Raises FrameSyncError after config.max_unsync_frames_before_error
    consecutive windows where at least one camera is out of sync.
    """
    camera_names = sorted(frame_streams.keys())
    anchor_cam = camera_names[0]
    other_cams = camera_names[1:]

    iterators: Dict[str, Iterator[Frame]] = {
        cam: iter(frames) for cam, frames in frame_streams.items()
    }

    # One buffered frame per non-anchor camera (pre-fetched)
    buffers: Dict[str, Frame | None] = {
        cam: next(iterators[cam], None) for cam in other_cams
    }

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
                    f"are synchronized, or set sync_mode=frame_index in pipeline.yaml "
                    f"if uploading independently-recorded video files."
                )


def _align_auto(
    frame_streams: Dict[str, Iterable[Frame]],
    config: IngestionConfig,
) -> Generator[SyncedFrameSet, None, None]:
    """Auto-detect sync mode by probing the first PROBE frames.

    Buffers up to PROBE frames from every camera, evaluates timestamp
    alignment quality, then routes to the appropriate implementation.
    Falls back to frame_index if < 50% of probe frames pass the tolerance
    check (which is the normal case for uploaded consumer video files).
    """
    PROBE = 100

    camera_names = sorted(frame_streams.keys())
    anchor_cam = camera_names[0]
    other_cams = camera_names[1:]

    # Buffer the probe window in memory (at most PROBE frames per camera)
    probe_buffer: Dict[str, List[Frame]] = {cam: [] for cam in camera_names}
    iterators: Dict[str, Iterator[Frame]] = {
        cam: iter(frames) for cam, frames in frame_streams.items()
    }

    # Collect up to PROBE frames from each stream
    for _ in range(PROBE):
        for cam in camera_names:
            f = next(iterators[cam], None)
            if f is not None:
                probe_buffer[cam].append(f)

    # Evaluate timestamp sync quality on the probe window using same-index
    # comparison (fast O(N) estimate instead of full O(N²) nearest-neighbour)
    tolerance_ms = config.sync_tolerance_ms
    probe_anchor = probe_buffer[anchor_cam]
    probe_count = len(probe_anchor)
    sync_hits = 0

    if probe_count > 0:
        for i, a_frame in enumerate(probe_anchor):
            all_match = True
            for cam in other_cams:
                if i < len(probe_buffer[cam]):
                    delta = abs(probe_buffer[cam][i].timestamp_ms - a_frame.timestamp_ms)
                    if delta > tolerance_ms:
                        all_match = False
                        break
                else:
                    all_match = False
                    break
            if all_match:
                sync_hits += 1

        hit_rate = sync_hits / probe_count
    else:
        hit_rate = 0.0

    # Decision
    if hit_rate >= 0.5:
        logger.info(
            "frame_sync.auto_selected",
            extra={"mode": "timestamp", "probe_hit_rate": round(hit_rate, 3)},
        )
        use_frame_index = False
    else:
        logger.warning(
            "frame_sync.auto_fallback",
            extra={
                "mode": "frame_index",
                "probe_hit_rate": round(hit_rate, 3),
                "reason": (
                    f"Only {sync_hits}/{probe_count} probe frames synced within "
                    f"{tolerance_ms} ms. Falling back to frame-index alignment. "
                    "For hardware-synced cameras set sync_mode=timestamp in pipeline.yaml."
                ),
            },
        )
        use_frame_index = True

    # Build combined iterators: probe buffer first, then the live remainder
    def _chained(cam: str) -> Iterator[Frame]:
        yield from probe_buffer[cam]
        yield from iterators[cam]

    combined: Dict[str, Iterable[Frame]] = {cam: _chained(cam) for cam in camera_names}

    if use_frame_index:
        yield from _align_by_frame_index(combined)
    else:
        yield from _align_by_timestamp(combined, config)


# ── utilities ─────────────────────────────────────────────────────────────────


def flatten_synced_frames(synced_sets: Iterable[SyncedFrameSet]) -> List[Frame]:
    """Flatten an iterable of SyncedFrameSet into a flat Frame list.

    Ordering: all cameras for set N, then all cameras for set N+1.
    Useful for feeding a batch pose inference call.
    """
    result: List[Frame] = []
    for synced in synced_sets:
        result.extend(synced.frames.values())
    return result
