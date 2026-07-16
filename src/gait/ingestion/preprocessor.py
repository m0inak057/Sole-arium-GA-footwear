"""IngestionPreprocessor â€” orchestrates the full 4-step ingestion pipeline.

Pipeline per frame (for each camera in each SyncedFrameSet):
  1. Undistort       â€” CameraCalibrator.apply()
  2. Background mask â€” BackgroundSubtractor.apply()  â†’ fg_mask for tracker
  3. Track person    â€” PersonTracker.update()         â†’ PersonTrack | None
  4. Crop ROI        â€” crop_roi()                     â†’ final Frame

One CameraCalibrator, one BackgroundSubtractor, and one PersonTracker are
created **per camera** at construction time. They are never shared across
cameras â€” sagittal and posterior have different backgrounds and coordinate
spaces.

Warmup window: MOG2 returns an unreliable (often all-foreground) mask for
    its first mog2_history frames while it builds a background model. During
    this window we feed every frame to the background subtractor so it learns,
    but we skip calling tracker.update() entirely — the tracker never sees the
    noisy mask and therefore never accumulates lost_frames. The tracker's own
    warmup guard (SimpleIoUTracker.warmup_frames) provides a second layer of
    defence for any edge cases where the two thresholds differ.

Streaming guarantee: the video is read frame-by-frame and processed
immediately; the full decoded video is never held in RAM. The only object
that grows with time is the output `IngestionResult.frames` list.

VideoCapture resources are always released via try/finally, even on exception.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Optional

from gait.common.interfaces import Frame
from gait.common.logging_utils import get_logger, log_stage_timing
from gait.common.types import IngestionResult
from gait.ingestion.calibrate import CameraCalibrator, load_camera_calibration
from gait.ingestion.decode import VideoFileSource
from gait.ingestion.roi import crop_roi
from gait.ingestion.segment_bg import BackgroundSubtractor, create_background_subtractor
from gait.ingestion.sync import align_frames
from gait.ingestion.track import PersonTracker, create_person_tracker
from gait.pipeline.config import IngestionConfig

logger = get_logger(__name__)


class IngestionPreprocessor:
    """Orchestrates the full ingestion preprocessing pipeline.

    Construction is cheap â€” config is validated, no files are opened.
    All I/O and computation happen inside run().

    Usage:
        config = load_pipeline_config().ingestion
        pp = IngestionPreprocessor(config, cameras_config_dir=Path("configs/cameras"))
        result = pp.run({"sagittal": Path("sagittal.mp4"), "posterior": Path("posterior.mp4")})
    """

    def __init__(
        self,
        config: IngestionConfig,
        cameras_config_dir: Optional[Path] = None,
    ) -> None:
        self._config = config
        self._cameras_config_dir = (
            Path(cameras_config_dir) if cameras_config_dir else Path("configs/cameras")
        )
        # Recomputed per-run in run() based on actual video length; this
        # default only applies if _process_frame is ever called without run().
        self._effective_warmup = config.mog2_history

    def run(self, video_paths: Dict[str, Path]) -> IngestionResult:
        """Preprocess all camera videos and return an IngestionResult.

        Args:
            video_paths: Mapping of camera_name â†’ Path to video file.
                         Must contain at least one entry.

        Returns:
            IngestionResult with preprocessed Frame objects ready for pose estimation.
            Every Frame.image is a new ndarray â€” safe to mutate downstream.

        Raises:
            ValueError:           video_paths is empty.
            VideoDecodeError:     A video cannot be opened or has excessive decode failures.
            FrameSyncError:       Multi-camera timestamp alignment repeatedly fails.
            CalibrationLoadError: A calibration YAML exists but is malformed.

        Note: subject tracking no longer raises TrackingLostError — it falls
        back to a low-confidence full-frame track so short/noisy videos still
        produce output instead of aborting the session.
        """
        if not video_paths:
            raise ValueError("video_paths must contain at least one camera entry.")

        camera_names = sorted(video_paths.keys())
        t0 = time.perf_counter()

        # â”€â”€ Adaptive warmup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # config.mog2_history frames are normally skipped while MOG2 learns the
        # background. For a short clip that would consume the entire video and
        # leave nothing to analyse, so cap the warmup at a third of the
        # shortest camera's frame count (never below 0).
        probe_sources = {
            cam: VideoFileSource(video_paths[cam], cam, self._config) for cam in camera_names
        }
        try:
            for src in probe_sources.values():
                src.open()
            frame_counts = [src.get_frame_count() for src in probe_sources.values()]
        finally:
            for src in probe_sources.values():
                src.close()

        min_frames = min([c for c in frame_counts if c > 0], default=self._config.mog2_history)
        self._effective_warmup = max(0, min(self._config.mog2_history, min_frames // 3))
        if self._effective_warmup < self._config.mog2_history:
            logger.info(
                "ingestion.adaptive_warmup",
                extra={
                    "configured_mog2_history": self._config.mog2_history,
                    "effective_warmup": self._effective_warmup,
                    "min_frames_across_cameras": min_frames,
                },
            )

        # â”€â”€ Build per-camera components â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        calibrators: Dict[str, CameraCalibrator] = {}
        subtractors: Dict[str, BackgroundSubtractor] = {}
        trackers: Dict[str, PersonTracker] = {}

        for cam in camera_names:
            calibration = load_camera_calibration(cam, self._cameras_config_dir)
            calibrators[cam] = CameraCalibrator(calibration)
            subtractors[cam] = create_background_subtractor(
                self._config.background_subtraction_model, self._config
            )
            trackers[cam] = create_person_tracker(
                self._config.person_tracking_model,
                self._config,
                warmup_frames=self._effective_warmup,
            )

        logger.info(
            "ingestion_start",
            extra={
                "camera_names": camera_names,
                "bg_model": self._config.background_subtraction_model,
                "tracking_model": self._config.person_tracking_model,
            },
        )

        # â”€â”€ Open all video sources â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        sources: Dict[str, VideoFileSource] = {
            cam: VideoFileSource(video_paths[cam], cam, self._config)
            for cam in camera_names
        }

        output_frames: List[Frame] = []
        total_input_frames = 0
        dropped_frames = 0

        try:
            for cam, src in sources.items():
                src.open()

            frame_streams = {cam: sources[cam].get_frames() for cam in camera_names}

            for synced_set in align_frames(frame_streams, self._config):
                total_input_frames += len(synced_set.frames)

                for cam, raw_frame in synced_set.frames.items():
                    processed = self._process_frame(
                        cam,
                        raw_frame,
                        calibrators[cam],
                        subtractors[cam],
                        trackers[cam],
                    )
                    if processed is None:
                        dropped_frames += 1
                    else:
                        output_frames.append(processed)

        finally:
            for src in sources.values():
                src.close()

        processing_time_sec = time.perf_counter() - t0
        log_stage_timing(
            logger,
            "ingestion",
            duration_sec=processing_time_sec,
            frame_count=len(output_frames),
            dropped_frames=dropped_frames,
        )

        return IngestionResult(
            frames=output_frames,
            total_input_frames=total_input_frames,
            dropped_frames=dropped_frames,
            processing_time_sec=processing_time_sec,
            camera_views=camera_names,
        )

    # â”€â”€ Private â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _process_frame(
        self,
        cam: str,
        raw_frame: Frame,
        calibrator: CameraCalibrator,
        subtractor: BackgroundSubtractor,
        tracker: PersonTracker,
    ) -> Optional[Frame]:
        """Run the 4-step pipeline on one frame. Returns None for dropped frames."""

        # Step 1 â€” Undistort (passthrough when calibration file is missing)
        calibrated = calibrator.apply(raw_frame)

        # Step 2 â€” Feed frame to the background model so it keeps learning.
        # Discard the bg-zeroed image; we use the calibrated frame for ROI crop
        # so pose estimation sees full colour in the region of interest.
        _, fg_mask = subtractor.apply(calibrated)

        # During MOG2 warmup the fg_mask is unreliable (often full-frame
        # foreground on the very first call, then noisy until the model
        # stabilises).  Feed the frame to the subtractor above so the model
        # keeps learning, but do NOT pass the mask to the tracker — this
        # prevents spurious lost_frames accumulation before tracking even starts.
        # self._effective_warmup adapts this window down for short clips so
        # warmup never consumes the entire video (see run()).
        if raw_frame.frame_index < self._effective_warmup:
            logger.debug(
                "tracker_bg_warmup_skip",
                extra={"camera_view": cam, "frame_index": raw_frame.frame_index},
            )
            return None

        # Step 3 â€” Track person (only called after bg model has stabilised).
        # tracker.update() never raises and never returns None post-warmup —
        # it falls back to a low-confidence full-frame track when blob
        # detection fails, so every post-warmup frame reaches Step 4.
        track = tracker.update(calibrated, fg_mask)

        if track is None:
            logger.debug(
                "tracker_no_detection",
                extra={"camera_view": cam, "frame_index": raw_frame.frame_index},
            )
            return None

        # Step 4 â€” ROI crop. When the tracker is using a stale bbox
        # (frames_since_update > 0 â€” subject temporarily lost / extrapolated
        # position), widen the margin so a slightly-wrong bbox still keeps
        # the person inside the crop. If the computed ROI has zero area
        # (degenerate bbox from a noisy mask), fall back to the full
        # uncropped frame instead of dropping it — pose estimation can still
        # run on the whole frame even without a tight crop.
        margin_px = self._config.roi_margin_px
        if track.frames_since_update > 0:
            margin_px += 80

        try:
            return crop_roi(calibrated, track, margin_px)
        except ValueError:
            logger.warning(
                "roi_zero_area_full_frame_fallback",
                extra={"camera_view": cam, "frame_index": raw_frame.frame_index},
            )
            return calibrated

