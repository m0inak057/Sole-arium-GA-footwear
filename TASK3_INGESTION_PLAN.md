# Task 3: Ingestion & Preprocessing Module

**Status:** Architecture & Planning Complete; Implementation In Progress  
**Date:** 2026-06-10  
**Duration:** ~15-22 hours (3-4 days of focused work)  

---

## Executive Summary

Task 3 implements the **Ingestion & Preprocessing stage** of the gait analysis pipeline: a 6-step streaming processor that transforms raw multi-camera video files into clean, undistorted, tracked, ROI-cropped Frame objects ready for pose estimation.

**Key characteristics:**
- ✅ **Zero hardcoding** — all 9+ tunable parameters from `pipeline.yaml`
- ✅ **Graceful degradation** — missing calibration files → warning + passthrough (software-only mode)
- ✅ **Hardware-flexible** — `VideoSource` ABC allows camera implementation swaps
- ✅ **Memory-efficient** — streaming loop; never loads full video into RAM
- ✅ **Type-safe** — dataclasses + pydantic for all boundaries; typed exceptions
- ✅ **Pure functions** — geometry/signal functions have no I/O or state
- ✅ **Agent-ready** — infrastructure for AI agents in Phase 2+

---

## Module Map

### Phase A: Common Foundations (3 files)
```
src/gait/common/types.py          ← DTOs + typed exceptions
src/gait/common/geometry.py       ← Pure 2D math (IoU, angle, vector)
src/gait/common/logging_utils.py  ← JSON logging setup
```

### Phase B: Ingestion Sub-steps (6 files)
```
src/gait/ingestion/decode.py      ← VideoFileSource (video reading)
src/gait/ingestion/sync.py        ← Multi-camera frame alignment
src/gait/ingestion/calibrate.py   ← Camera undistortion + graceful passthrough
src/gait/ingestion/segment_bg.py  ← Background subtraction (MOG2)
src/gait/ingestion/track.py       ← Person tracking (simple IoU MVP)
src/gait/ingestion/roi.py         ← ROI cropping
```

### Phase C: Orchestration (2 files)
```
src/gait/ingestion/preprocessor.py ← IngestionPreprocessor (streaming loop orchestrator)
src/gait/ingestion/__init__.py     ← Module exports
```

### Tests (8 files)
```
tests/unit/test_geometry.py
tests/unit/test_ingestion_decode.py
tests/unit/test_ingestion_calibrate.py
tests/unit/test_ingestion_segment_bg.py
tests/unit/test_ingestion_track.py
tests/unit/test_ingestion_roi.py
tests/unit/test_logging_utils.py
tests/integration/test_ingestion_pipeline.py
```

---

## The 6-Step Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 1: DECODE                                                      │
│ ───────────────────────────────────────────────────────────────────│
│ VideoFileSource(path, camera_view, config)                         │
│   ↓ reads MP4/AVI via OpenCV                                       │
│   → Frame(image, timestamp_ms, camera_view, frame_index, conf=1.0) │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 2: SYNC (multi-camera join)                                   │
│ ───────────────────────────────────────────────────────────────────│
│ align_frames(frame_streams: dict[camera→generator], config)        │
│   ↓ merges frames within sync_tolerance_ms                         │
│   → SyncedFrameSet(anchor_timestamp_ms, frames: dict[camera→Frame])│
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 3: UNDISTORT (per-camera, parallel)                           │
│ ───────────────────────────────────────────────────────────────────│
│ CameraCalibrator[camera].apply(frame)                              │
│   ↓ if is_calibrated: apply cv2.remap() with precomputed maps     │
│   ↓ else: return frame unchanged (graceful passthrough)             │
│   → Frame(undistorted_image, same_metadata)                        │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 4: SEGMENT BACKGROUND (per-camera, per-subtractor)            │
│ ───────────────────────────────────────────────────────────────────│
│ BackgroundSubtractor[camera].apply(frame)                          │
│   ↓ MOG2: learned background model → foreground mask               │
│   → Frame(image_with_bg_zeroed), foreground_mask                   │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 5: TRACK PERSON (shared tracker, all cameras)                 │
│ ───────────────────────────────────────────────────────────────────│
│ PersonTracker.update(frame, foreground_mask)                       │
│   ↓ IoU-based tracking: largest blob → PersonTrack bbox            │
│   → PersonTrack(track_id, bbox, confidence)                        │
│   if lost > max_lost_frames: raise TrackingLostError               │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 6: ROI CROP (per-camera)                                      │
│ ───────────────────────────────────────────────────────────────────│
│ crop_roi(frame, track, margin_px=50)                               │
│   ↓ expand_bbox(bbox, margin) → clamped to image bounds            │
│   ↓ slice image, np.copy() to prevent memory sharing               │
│   → Frame(cropped_image, same_metadata)                            │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
        ┌──────────────────────────────────────────┐
        │ IngestionResult                          │
        ├──────────────────────────────────────────┤
        │ frames: list[Frame]  (to pose stage)     │
        │ total_input_frames: int                  │
        │ dropped_frames: int                      │
        │ processing_time_sec: float               │
        └──────────────────────────────────────────┘
```

---

## Critical Design Decisions

### 1. One BackgroundSubtractor per Camera
- **Not shared** — sagittal and posterior have different backgrounds
- Each camera has its own learned MOG2 model
- Prevents correctness bugs from mixing backgrounds

### 2. Precomputed Undistort Maps
- `cv2.initUndistortRectifyMap()` called **once** per camera at startup
- Stores (map1, map2) for fast `cv2.remap()` per frame
- Avoids per-frame coefficient lookup

### 3. Graceful Calibration Degradation
- Missing `configs/cameras/{name}.yaml` → WARNING + passthrough
- Malformed YAML (bad structure) → `CalibrationLoadError` (operator error, hard fail)
- Allows software-only development until hardware arrives

### 4. Streaming Loop, No Full-Video Buffering
- `preprocessor.run()` processes one `SyncedFrameSet` at a time
- Total RAM = max(frame_height × frame_width × 3 bytes) per camera at once
- Can handle 2+ hours of 1080p video on 4GB RAM

### 5. Stale Track Confidence Reduction
- If person tracker loses lock for a few frames but recovers: returns last-known bbox
- **But** reduces `PersonTrack.confidence` proportionally
- Never returns stale track with full 1.0 confidence

### 6. Integer Timestamp Arithmetic
- `timestamp_ms = (frame_index * 1000) // fps`  ← **correct**
- `int(frame_index / fps * 1000)` ← **wrong** (float precision loss)

---

## Configuration (No Magic Numbers!)

**New IngestionConfig fields** (in `src/gait/pipeline/config.py`):
```python
# Decode
max_consecutive_decode_failure_pct: int = 10  # % before VideoDecodeError

# Sync
max_unsync_frames_before_error: int = 30      # synced sets before FrameSyncError

# Calibration (intrinsic only; extrinsic deferred to Phase 3)
# (no new params; loads from YAML)

# MOG2 Background Subtraction
mog2_history: int = 500                       # frames to remember
mog2_var_threshold: float = 16.0              # variance threshold
mog2_detect_shadows: bool = True              # handle shadows
mog2_morph_kernel_size_px: int = 5            # morphology kernel

# Person Tracking (IoU)
iou_threshold: float = 0.3                    # IoU cutoff for track continuation
max_lost_frames: int = 15                     # before TrackingLostError
min_blob_area_px2: int = 5000                 # filter noise blobs

# ROI
roi_margin_px: int = 50                       # (already in pipeline.yaml)
```

**In `configs/pipeline.yaml`:**
```yaml
ingestion:
  fps: 120
  resolution: [1920, 1080]
  sync_tolerance_ms: 10
  background_subtraction_model: mog2
  person_tracking_model: bytetrack  # falls back to simple_iou with WARNING
  roi_margin_px: 50
  # ... all the above IngestionConfig fields
```

---

## Error Handling Strategy

**Fail-loudly with typed exceptions:**

| Exception | When | Action |
|-----------|------|--------|
| `VideoDecodeError` | File not found or too many consecutive decode failures | Raise; upstream catches and logs |
| `FrameSyncError` | Cameras persistently out of sync (> 30 synced sets missed) | Raise; operator must fix sync |
| `CalibrationLoadError` | YAML exists but is malformed (bad structure) | Raise; operator must fix YAML |
| `TrackingLostError` | Person lost for > 15 frames | Raise; operator must re-record |

**Never silent failures.** Every dropped frame/cycle is logged with context.

---

## Implementation Sequence

**Phase A (Foundations — 2-3 hours):**
1. `common/types.py` (DTOs + exceptions)
2. `common/geometry.py` (pure math)
3. `common/logging_utils.py` (JSON logging)

**Phase B (Sub-steps — 8-10 hours):**
4. `ingestion/decode.py` (video reading)
5. `ingestion/sync.py` (frame alignment)
6. `ingestion/calibrate.py` (undistortion)
7. `ingestion/segment_bg.py` (background subtraction)
8. `ingestion/track.py` (person tracking)
9. `ingestion/roi.py` (cropping)

**Phase C (Orchestration — 2-3 hours):**
10. `ingestion/preprocessor.py` (main loop)
11. `ingestion/__init__.py` (exports)

**Configuration (30 mins):**
12. Extend `PipelineConfig` in `config.py`
13. Update `pipeline.yaml` with new params

**Testing (4-6 hours):**
14. Unit tests for each sub-module (60+ tests)
15. Integration test with synthetic video

**Validation (30 mins):**
16. `make test-unit`, `make type-check`, `make lint`, `make ci`

---

## Testing Strategy

### Unit Tests (60+ tests)
- **`test_geometry.py`** — Pure math (IoU, angle, bbox, vector)
- **`test_ingestion_decode.py`** — Frame generation, fps/resolution warnings
- **`test_ingestion_calibrate.py`** — Graceful uncalibrated, undistort correctness
- **`test_ingestion_segment_bg.py`** — Mask correctness, shadow handling
- **`test_ingestion_track.py`** — Tracking state, lost-frame handling
- **`test_ingestion_roi.py`** — Bbox expansion, clamping, crop correctness
- **`test_logging_utils.py`** — Logger setup, JSON format

### Integration Test (8+ tests)
- **`test_ingestion_pipeline.py`**
  - Uses `cv2.VideoWriter` to create synthetic videos (no hardware needed)
  - Single-camera and dual-camera scenarios
  - Uncalibrated passthrough verification
  - `IngestionResult` type validation
  - Deterministic output (same input → same output)
  - Memory efficiency (never loads full video)

### Fixtures
- Synthetic video generation (moving white rectangle = "person walking")
- Minimal camera YAML for calibrated tests
- Empty camera YAML for uncalibrated tests

---

## Loopholes to Prevent

1. ⚠️ **Never import yaml inside ingestion/ modules** → Config injected at pipeline boundary
2. ⚠️ **Always `np.copy()` when returning Frame** → Prevents silent memory corruption
3. ⚠️ **Handle MOG2 warmup** → First frames produce noisy masks; don't error
4. ⚠️ **VideoFileSource must close on exception** → Use `try/finally` in preprocessor
5. ⚠️ **Single-camera sync must work** → Test explicitly
6. ⚠️ **No stale track with full confidence** → Reduce confidence if track is old

---

## Verification Checklist

```bash
# After implementation:
make test-unit                    # All 60+ tests pass
make test-integration             # Synthetic video tests pass
make type-check                   # mypy clean
make lint                         # ruff clean
make ci                           # Full pipeline green

# Spot-checks:
grep "import yaml" src/gait/ingestion/    # Should return nothing
grep -E "[0-9]{2,}" src/gait/ingestion/segment_bg.py src/gait/ingestion/track.py src/gait/ingestion/roi.py \
  | grep -v " [0,1,255] "        # Check for magic numbers (except 0/1/255)

# Memory-safety check:
pytest -k "shares_memory" tests/unit/      # Should all pass (np.copy verified)

# Type-safety check:
pytest -k "Frame.*type" tests/unit/        # Should all pass (uint8, ndim==3)
```

---

## Success Criteria

✅ 60+ unit tests pass  
✅ Integration test passes with synthetic video  
✅ mypy clean (no type errors)  
✅ ruff clean (no style errors)  
✅ No yaml imports in ingestion/  
✅ np.shares_memory checks pass  
✅ IngestionResult.frames are properly typed Frame objects  
✅ Uncalibrated camera gracefully passes through (software-only mode works)  
✅ make ci green end-to-end  

---

**Next:** Proceed to Phase A implementation (common foundations).
