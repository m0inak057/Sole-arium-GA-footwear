# Gait Analysis Module — Implementation Playbook
**Status:** Phase 0 & 1 Architecture Complete; Phase 1B (Ingestion) In Progress  
**Version:** 1.1  
**Last updated:** 2026-06-10 (Task 3: Ingestion & Preprocessing + AI Agents Integration)

---

## Executive Summary

This playbook translates the 10-document suite into a **sequential, task-driven build plan**. The project is a **7-stage linear pipeline** that transforms raw synchronized video into a structured patient profile JSON in ~60 seconds. The pipeline follows these key principles:

- **One contract out** — only `profile.json` matters to downstream consumers.
- **Config over code** — thresholds and recommendation rules are **YAML-editable**, not hardcoded.
- **Fail loudly** — if data is insufficient (< 4 clean cycles/foot), the system refuses to fabricate and requests re-record.
- **Privacy by design** — DPDP 2023 compliant; video faces are blurred post-pipeline; all data pseudonymized and encrypted.

---

## 1. Phase 0 — Setup (~2 weeks)

**Goal:** Build the hardware rig, calibrate cameras, scaffold the repo, get CI green.

### 1.1 Hardware & Walkway

**Deliverables:**
- Three-view camera setup: sagittal, posterior, and optional plantar.
- 6 m+ matte walkway, ~1 m wide, ≥ 500 lux diffuse lighting.
- Hardware sync rig (trigger) or PTP/NTP software sync (≤ 10 ms drift).
- Checkerboard + ChArUco boards for calibration.
- Scale reference object on the walkway.

**Checklist:**
- [ ] Sagittal camera: side view, lens at knee height, 3–4 m away, global shutter preferred.
- [ ] Posterior camera: behind walkway, lens at mid-calf height, global shutter preferred.
- [ ] All cameras: ≥ 1080p resolution, ≥ 60 fps (ideally 120 fps for accurate heel-strike timing).
- [ ] Lighting verified: ≥ 500 lux, diffuse, no harsh shadows on feet.
- [ ] Checkerboard printed and mounted for capture.
- [ ] Hardware trigger working or PTP/NTP sync verified.

### 1.2 Calibration Scripts

**Input:** Raw checkerboard + ChArUco captures from each camera.  
**Output:** `configs/cameras/{sagittal,posterior,plantar}.yaml` with intrinsic and extrinsic matrices.

**Code to scaffold:**
```
src/gait/ingestion/calibrate.py
├── intrinsic_calibration(images) → K, D
├── extrinsic_calibration(image_pairs, K1, K2) → R, t
├── undistort_frame(frame, K, D) → corrected_frame
└── verify_calibration(test_frame) → straight_lines_check
```

**Exit criteria:**
- [ ] Intrinsic calibration reprojection error < 0.5 px per camera.
- [ ] Extrinsic calibration triangulation error < 10 mm for known-distance object.
- [ ] Test frame undistortion: straight physical lines remain straight.

### 1.3 Repository Scaffolding

**Structure per [PROJECT_STRUCTURE.md](./docs/PROJECT_STRUCTURE.md):**

```
gait-analysis/
├── README.md
├── pyproject.toml              # deps, build
├── docker-compose.yml          # dev stack
├── Dockerfile
├── .env.example
├── Makefile                    # lint, test, run, format
├── docs/                       # all 10 docs (already provided)
├── configs/
│   ├── cameras/
│   │   ├── sagittal.yaml       # intrinsics/extrinsics (post-calibration)
│   │   ├── posterior.yaml
│   │   └── plantar.yaml
│   ├── thresholds.yaml         # ALL tunable parameters
│   ├── rules.yaml              # shoe-design recommendations
│   └── pipeline.yaml           # model choice, fps, smoothing
├── src/gait/
│   ├── capture/                # hardware recording / import
│   ├── ingestion/              # preprocessing
│   ├── pose/                   # keypoint estimation
│   ├── events/                 # HS/TO, segmentation
│   ├── analysis/               # spatiotemporal, etc.
│   ├── profile/                # JSON builder
│   ├── pipeline/               # orchestration
│   ├── common/                 # shared utils
│   └── api/                    # FastAPI
├── models/                     # model cards (weights external)
├── data_pipeline/              # annotation tooling
├── frontend/                   # React UI (minimal MVP)
├── migrations/                 # Alembic DB schemas
├── tests/                      # unit, integration, e2e
├── scripts/                    # one-off ops
└── infra/                      # IaC, deployment
```

**Key files to initialize:**
- [ ] `pyproject.toml` with core deps: `opencv-python`, `mediaipe`, `numpy`, `scipy`, `pydantic`, `fastapi`, `celery`, `pytest`.
- [ ] `Makefile` with targets: `lint`, `format`, `test`, `test-e2e`, `run-api`, `run-worker`.
- [ ] `.pre-commit-config.yaml` with black, ruff, mypy hooks.
- [ ] `.github/workflows/ci.yml` (if using GitHub) to run lint → type → tests on every PR.

### 1.4 Empty Pipeline Scaffold

**Code structure (minimal stubs):**

```python
# src/gait/__init__.py
__version__ = "0.1.0"

# src/gait/pipeline/run.py
def process_session(session_dir: Path) -> profile.GaitPatientProfile:
    """Orchestrate full pipeline: session_dir → profile.json"""
    raise NotImplementedError

# src/gait/profile/schema.py (pydantic source of truth)
from pydantic import BaseModel

class GaitPatientProfile(BaseModel):
    patient_id: str
    session_timestamp: str
    anthropometrics: dict
    spatiotemporal: dict
    foot_strike: dict
    pronation: dict
    arch: dict
    symmetry_flags: list[str]
    shoe_design_recommendations: dict
    confidence_scores: dict

    class Config:
        json_schema_extra = {"$schema": "..."}

# tests/schema/test_profile_schema.py
def test_profile_validates_against_json_schema():
    """Every emitted profile must pass JSON schema validation"""
    assert validate_schema(profile_json) is True
```

**Exit criteria:**
- [ ] Repo structure scaffolded per PROJECT_STRUCTURE.md.
- [ ] CI pipeline green on empty code (lint passes, mypy passes, test suite runs).
- [ ] `pyproject.toml` locks core deps.
- [ ] A `.env.example` template exists.
- [ ] `README.md` points to the docs folder and explains the dev setup.

---

## 2. Phase 1 — MVP Pipeline (~6–8 weeks)

**Goal:** End-to-end pipeline with off-the-shelf MediaPipe pose, producing schema-valid `profile.json`.

### 2.1 Ingestion & Preprocessing (Week 1–2) — **[TASK 3: IN PROGRESS]**

**Input:** Raw multi-camera synchronized video files.  
**Output:** Typed `IngestionResult` with list of clean, undistorted, ROI-cropped `Frame` objects.

**Six-stage streaming pipeline (never loads full video into RAM):**
1. **Decode & demux** — `VideoFileSource(VideoSource)` yields `Frame` objects from video files.
2. **Timestamp align** — `align_frames()` syncs frames across cameras within `sync_tolerance_ms`.
3. **Undistort & calibrate** — `CameraCalibrator.apply()` (graceful degradation if uncalibrated).
4. **Background subtraction** — `MOG2BackgroundSubtractor` isolates subject (config-driven).
5. **Person tracking** — `SimpleIoUTracker` (MVP; ByteTrack pluggable for future).
6. **ROI crop** — `crop_roi()` pure function, returns new Frame with cropped image.

**Architecture highlights:**
- **Config-over-code:** All params (fps, resolution, sync_tolerance_ms, mog2_history, iou_threshold, etc.) from `pipeline.yaml`
- **Graceful degradation:** Missing calibration YAML → WARNING + passthrough (software-only mode)
- **Hardware-flexible:** `VideoSource` ABC allows `LiveCameraSource` swap-in later
- **Memory-efficient:** Streaming generator; `np.copy()` prevents memory sharing
- **Typed exceptions:** `VideoDecodeError`, `FrameSyncError`, `CalibrationLoadError`, `TrackingLostError`

**Task 3 Implementation Structure:**

*Phase A — Common Foundations:*
```
src/gait/common/types.py          # DTOs: CameraCalibration, SyncedFrameSet, PersonTrack, IngestionResult
src/gait/common/geometry.py       # Pure math: compute_iou, expand_bbox, compute_angle_deg, normalize_vector
src/gait/common/logging_utils.py  # JSON logger setup, log_stage_timing()
```

*Phase B — Ingestion Sub-steps:*
```
src/gait/ingestion/decode.py      # VideoFileSource (implements VideoSource ABC)
src/gait/ingestion/sync.py        # align_frames() → SyncedFrameSet generator
src/gait/ingestion/calibrate.py   # CameraCalibrator, undistort_frame()
src/gait/ingestion/segment_bg.py  # BackgroundSubtractor ABC, MOG2BackgroundSubtractor
src/gait/ingestion/track.py       # PersonTracker ABC, SimpleIoUTracker
src/gait/ingestion/roi.py         # crop_roi() pure function
```

*Phase C — Orchestration:*
```
src/gait/ingestion/preprocessor.py  # IngestionPreprocessor: loads config once, runs 6-step loop
src/gait/ingestion/__init__.py      # Module exports
```

**Test fixtures:**
- [ ] `tests/unit/test_geometry.py` (30+ tests) — pure math validation
- [ ] `tests/unit/test_ingestion_decode.py` (10+ tests) — video reading
- [ ] `tests/unit/test_ingestion_calibrate.py` (10+ tests) — graceful uncalibrated mode
- [ ] `tests/unit/test_ingestion_segment_bg.py` (10+ tests) — background subtraction
- [ ] `tests/unit/test_ingestion_track.py` (12+ tests) — person tracking
- [ ] `tests/unit/test_ingestion_roi.py` (8+ tests) — ROI cropping
- [ ] `tests/integration/test_ingestion_pipeline.py` (8+ tests) — synthetic video end-to-end (no hardware needed)

**Exit criteria:**
- [ ] 60+ unit tests pass (all ingestion tests)
- [ ] Integration test passes with synthetic video
- [ ] mypy clean: `mypy src/gait/ingestion/ src/gait/common/`
- [ ] ruff clean: `ruff check src/gait/ingestion/`
- [ ] No YAML imports inside ingestion/ modules
- [ ] `IngestionResult.frames` contains only typed `Frame` objects
- [ ] Processing time for 60 s video ≤ 10 s (ingestion stage budget)
- [ ] Uncalibrated camera passthrough works (software-only mode)

### 2.2 Pose & Foot Keypoint Estimation (Week 2–3)

**Input:** Clean frames per camera.  
**Output:** Time-series of smoothed 2D (and optionally 3D) keypoints.

**Tier A — Whole-body 2D pose (MediaPipe MVP):**
- Use MediaPipe Pose (33 keypoints: joints + landmarks).
- Per-frame confidence; drop frames where critical points (ankle, hip, shoulder) < threshold.

**Tier B — Foot keypoints (TODO Phase 2):**
- For MVP: use MediaPipe's heel and toe landmarks (coarse).
- Phase 2: fine-tune a model on custom annotated dataset.

**3D reconstruction (MVP: monocular):**
- Monocular 2D→3D lifter (VideoPose3D / MotionBERT) for single camera.
- Phase 3: multi-view triangulation once cameras are extrinsically calibrated.

**Smoothing:**
- 1-Euro filter on each keypoint trajectory **before** event detection.
- Do NOT filter the heel-strike frame itself (it's an event signal).

**Code structure:**
```python
# src/gait/pose/body_2d.py
def estimate_body_pose_2d(frame) → KeypointFrame:
    """MediaPipe Pose wrapper; returns 33 keypoints + confidence"""

# src/gait/pose/lift_3d.py
def lift_2d_to_3d(keypoint_series_2d, model='videpose3d') → keypoint_series_3d:
    """Monocular 2D→3D"""

# src/gait/pose/smooth.py
def smooth_keypoints_1euro(trajectory) → smoothed_trajectory:
    """1-Euro filter; preserve event timing"""

# src/gait/common/types.py
class KeypointFrame(BaseModel):
    timestamp_ms: int
    keypoints: dict  # {keypoint_id: (x, y, z?, confidence)}
    camera_view: str  # 'sagittal' or 'posterior'
```

**Test fixtures:**
- [ ] Synthetic keypoint series (sine wave, step function).
- [ ] Unit tests: smoothing preserves event timing (heel-strike frame index ± tolerance).
- [ ] Integration test: frame → keypoints.

**Exit criteria:**
- [ ] MediaPipe runs on sample video; confidence scores populate.
- [ ] 1-Euro filter does not shift event frames beyond tolerance (e.g., ± 1 frame @ 120 fps).
- [ ] Processing time ≤ 15 s for 60 s video.

### 2.3 Gait Event Detection & Cycle Segmentation (Week 3–4)

**Input:** Time-series of keypoints.  
**Output:** Segmented gait cycles with labeled sub-phases.

**Heel-strike (HS) detection:**
- Bandpass filter the heel trajectory (vertical position).
- Detect local minimum + velocity zero-crossing.
- Cross-check with sagittal foot angle (foot flat after HS).

**Toe-off (TO) detection:**
- Peak of toe vertical velocity transitioning positive.
- Often coincides with rapid hip-flexion increase.

**Cycle segmentation:**
- HS→TO = Stance (~60% of cycle).
- TO→next HS = Swing (~40%).
- Sub-phases per gait-cycle state machine (see [DATA_FLOW.md](./docs/DATA_FLOW.md)).

**Code structure:**
```python
# src/gait/events/detect.py
def detect_heel_strikes(kp_trajectory) → timestamps:
    """Return list of HS frame indices"""

def detect_toe_offs(kp_trajectory) → timestamps:
    """Return list of TO frame indices"""

# src/gait/events/segment_cycles.py
def segment_gait_cycles(hs_list, to_list, kp_trajectory) → list[GaitCycle]:
    """Yield GaitCycle(frames, stance_frames, swing_frames, sub_phases)"""

# src/gait/common/types.py
class GaitCycle(BaseModel):
    cycle_id: int
    frame_start: int
    frame_end: int
    stance_frames: list[int]
    swing_frames: list[int]
    keypoints: dict  # trimmed to this cycle
    confidence: float  # min confidence of critical keypoints in cycle
```

**Confidence gating:**
- If any critical frame in a cycle has confidence < threshold, drop the cycle.
- Track count of dropped cycles per session.

**Test fixtures:**
- [ ] Synthetic keypoint series with known HS/TO timings.
- [ ] Unit tests: HS/TO detection on synthetic data (known correct answers).
- [ ] Integration test: video → cycles (count ≈ expected).

**Exit criteria:**
- [ ] Event detection produces expected HS/TO counts on test video.
- [ ] Cycles are correctly segmented.
- [ ] Processing time ≤ 10 s for 60 s video.

### 2.4 Biomechanical Analysis Engine (Week 4–5)

**Input:** Segmented gait cycles.  
**Output:** Parameters per cycle, then aggregated (mean ± SD).

**Spatiotemporal parameters:**
- Cadence (steps/min), walking speed (m/s), stride length (m), step length L/R (m), step width (m).
- Stance time (s, %), swing time (s, %), double-support time (%, overall).
- Foot progression angle (toe-in/out).

**Foot-strike classification (sagittal view):**
- Foot strike angle (FSA) at heel-strike = angle of plantar foot to ground.
- **Rearfoot** if FSA > +5°, **midfoot** if −5° ≤ FSA ≤ +5°, **forefoot** if FSA < −5°.

**Pronation/supination (posterior view, **headline metric**):**
- Three points: mid-Achilles, mid-calf (mid-shank), mid-heel (calcaneus).
- **Rearfoot angle** = angle in frontal plane, tracked across stance phase.
- Most diagnostic instant: **mid-stance** (peak eversion).

| Peak rearfoot eversion | Classification |
|---|---|
| > +8° | **Overpronation** |
| +4° to +8° | Mild pronation |
| 0° to +4° | **Neutral** |
| −4° to 0° | Mild supination |
| < −4° | **Oversupination** |

- Also compute: time-to-peak eversion (early peak = poor shock absorption).

**Arch type (sagittal view):**
- Arch height index (AHI) = navicular height ÷ truncated foot length.
- Classify: high (pes cavus) / normal / low (pes planus).

**Symmetry indices (L vs. R):**
```
Symmetry Index (%) = |X_L − X_R| / (0.5 · (X_L + X_R)) · 100
```
Flag if > 10%.

**Code structure:**
```python
# src/gait/analysis/spatiotemporal.py
def compute_spatiotemporal(cycle: GaitCycle) → SpatiotemporalParams:
    """cadence, speed, stride_length, etc."""

# src/gait/analysis/foot_strike.py
def classify_foot_strike(cycle: GaitCycle) → FootStrikeClass:
    """FSA → rearfoot / midfoot / forefoot"""

# src/gait/analysis/pronation.py
def compute_pronation(cycle: GaitCycle) → PronationResult:
    """rearfoot_angle → classification + confidence"""

# src/gait/analysis/arch.py
def estimate_arch_type(cycle: GaitCycle) → ArchType:
    """arch_height_index → high / normal / low"""

# src/gait/analysis/symmetry.py
def compute_symmetry_indices(cycles_l, cycles_r) → SymmetryFlags:
    """List of asymmetry > 10%"""

# src/gait/common/geometry.py
def compute_rearfoot_angle(mid_achilles, mid_calf, mid_heel) → angle_deg:
    """Frontal-plane angle; return deg"""
```

**Confidence scoring:**
- Each classification carries a confidence score (0–1).
- Low confidence ↔ uncertain keypoint positions or edge-case parameters.

**Test fixtures:**
- [ ] Golden cycle data (known spatiotemporal values).
- [ ] Unit tests: geometry (rearfoot angle), classification boundaries (both sides of FSA, rearfoot-angle cutoffs).
- [ ] Integration test: cycles → parameters.

**Exit criteria:**
- [ ] Spatiotemporal parameters compute correctly.
- [ ] Pronation classification produces expected classes on synthetic/test data.
- [ ] Confidence scores populate.
- [ ] Processing time ≤ 15 s for 60 s video.

### 2.5 Patient Profile Generator (Week 5–6)

**Input:** Aggregated parameters + classifications.  
**Output:** Schema-valid `profile.json`.

**Assembly:**
1. Aggregate parameters across cycles: mean ± SD.
2. Apply confidence thresholds; drop low-confidence cycles.
3. Check re-record gate: if < 4 clean cycles/foot, fail loudly.
4. Generate `shoe_design_recommendations` by applying `configs/rules.yaml`.
5. Emit `profile.json`.

**Rule-based recommendations (YAML-driven):**

Example `configs/rules.yaml`:
```yaml
recommendations:
  - condition:
      pronation_classification: overpronation
      arch_type: low
    action:
      medial_post: required
      post_density: firm
      arch_support: high
      heel_counter: rigid
      last_shape: straight
  
  - condition:
      pronation_classification: oversupination
      arch_type: high
    action:
      medial_post: "no"
      arch_support: minimal
      last_shape: curved
      cushioning_zone_priority: [heel, lateral_forefoot]
```

**Code structure:**
```python
# src/gait/profile/builder.py
def build_patient_profile(
    cycles: list[GaitCycle],
    parameters: dict,
    subject_metadata: dict,
    confidence_scores: dict,
) → GaitPatientProfile:
    """Assemble all fields into profile"""

# src/gait/profile/recommend.py
def generate_recommendations(
    parameters: dict,
    rules_config: dict,
) → ShoeDesignRecommendations:
    """Apply rules.yaml logic"""

# src/gait/profile/confidence.py
def gating_and_confidence(
    cycles: list[GaitCycle],
    threshold_config: dict,
) → (cleaned_cycles, GatingDecision):
    """Drop low-confidence cycles; return decision"""

# src/gait/profile/schema.py
class GaitPatientProfile(BaseModel):
    # All fields per API_AND_SCHEMA.md
    ...
```

**Quality gates (in `gating.py`):**
```python
def apply_confidence_gates(cycles, thresholds):
    """
    - If keypoint_confidence < threshold → drop cycle
    - If clean_cycles < 4 per foot → GatingDecision.RERECORD
    - If clean_cycles < 8 per foot → GatingDecision.PROCEED_WITH_WARNING
    - If clean_cycles ≥ 8 per foot → GatingDecision.PROCEED_OK
    """
```

**JSON schema validation:**
```python
def validate_profile_schema(profile: dict) → bool:
    """Validate against profile/v1 JSON schema"""
    return jsonschema.validate(profile, schema)
```

**Test fixtures:**
- [ ] Golden parameter vectors.
- [ ] Unit tests: rule application (all condition combinations), schema validation.
- [ ] Integration test: parameters → profile.json (valid).

**Exit criteria:**
- [ ] Profile JSON schema-valid 100% of test runs.
- [ ] Gating logic correctly triggers re-record when < 4 cycles.
- [ ] Recommendations populate correctly per rules.yaml.

### 2.6 API & Simple Viewer (Week 6–8)

**API (FastAPI):**

```python
# src/gait/api/main.py
app = FastAPI()

# src/gait/api/routes/sessions.py
@app.post("/api/v1/sessions")
async def create_session(subject_metadata: SubjectMetadata) → SessionID:
    """Register subject, return session_id"""

@app.post("/api/v1/sessions/{session_id}/uploads")
async def upload_video(session_id: str, files: UploadFile) → None:
    """Store synchronized video"""

@app.post("/api/v1/sessions/{session_id}/process")
async def process_session(session_id: str) → TaskID:
    """Enqueue Celery job; return task_id"""

@app.get("/api/v1/sessions/{session_id}")
async def get_session_status(session_id: str) → SessionStatus:
    """created | uploaded | processing | complete | needs_rerecord | failed"""

@app.get("/api/v1/sessions/{session_id}/profile")
async def get_profile(session_id: str) → GaitPatientProfile:
    """Return profile.json if complete"""
```

**Celery worker:**
```python
# src/gait/api/tasks.py
@celery.task
def process_session_task(session_id: str):
    """
    Load video, run pipeline, save profile.json to DB.
    On gating failure, set status to needs_rerecord.
    """
```

**Simple viewer (Streamlit MVP):**
```python
# frontend/app.py (MVP: no React yet)
import streamlit as st

st.title("Gait Analysis Results")
session_id = st.text_input("Session ID")

if session_id:
    profile = fetch_profile(session_id)
    st.json(profile)
    
    # Plot gait curves
    cycles = fetch_timeseries(session_id)
    st.line_chart(cycles["cadence_over_cycles"])
    st.line_chart(cycles["rearfoot_angle_over_cycle"])
```

**Test fixtures:**
- [ ] Mock FastAPI app with test client.
- [ ] Unit tests: endpoints return correct status, error handling.
- [ ] Integration test: upload → process → retrieve profile.

**Exit criteria:**
- [ ] All endpoints functional and tested.
- [ ] Viewer renders profile JSON + basic plots.
- [ ] Full e2e: upload 6-pass session → process → retrieve valid profile.json within ~60 s.

### 2.7 Phase 1 Exit Criteria

- [ ] End-to-end pipeline functional: 6-pass video → profile.json in ≤ ~60 s.
- [ ] Profile JSON schema-valid 100%.
- [ ] Pronation classification + spatiotemporal parameters populate.
- [ ] Gating logic works: < 4 cycles/foot → no profile.
- [ ] API endpoints tested.
- [ ] Viewer renders results.
- [ ] CI/CD green (lint, type, tests).

---

## 3. Phase 2 — Custom Foot Model (~6 weeks)

**Goal:** Replace weak off-the-shelf foot points with a fine-tuned, fair detector.

### 3.1 Dataset Curation

**Target:** ~3000 annotated images covering:
- Diverse Indian foot morphology (arch types, toe shapes).
- Multiple skin tones.
- Varying lighting conditions.
- Barefoot + shod conditions.

**Annotation format:** keypoints on 5 foot landmarks (calcaneus, malleoli, MTP heads, hallux, mid-Achilles).

### 3.2 Fine-tuning Pipeline

**Base model:** RTMPose, HRNet, or ViTPose (lighter than MediaPipe for foot-only).

**Code structure:**
```python
# data_pipeline/annotation/guidelines.md
# data_pipeline/ingest.py → load annotated dataset
# data_pipeline/augment.py → data augmentation
# src/gait/pose/foot_kp.py → fine-tuned model wrapper
```

### 3.3 Validation

- Localization error (L2 pixel distance) on held-out test set.
- No systematic drop across skin-tone subgroups (fairness check).
- Rearfoot-angle accuracy improvement vs. Phase 1.

---

## 4. Phase 3 — 3D & Clinical Validation (~6–8 weeks)

**Goal:** Multi-view 3D reconstruction + pressure-mat validation study.

### 4.1 Multi-view Triangulation

Replace monocular lifter with proper triangulation:
```python
def triangulate_keypoints(
    keypoint_2d_sagittal,
    keypoint_2d_posterior,
    K_sag, R_sag, t_sag,
    K_post, R_post, t_post,
) → keypoint_3d:
    """Linear triangulation"""
```

### 4.2 Validation Study (n ≈ 30)

- Simultaneous capture: video + pressure mat (Tekscan / RSScan).
- Barefoot + shod conditions.
- ICC > 0.85 vs. pressure mat on event timing, foot strike, rearfoot angle.
- Repeatability: re-scan within 30 min; SD thresholds.

### 4.3 Threshold & Rules Re-tuning

Update `configs/thresholds.yaml` and `configs/rules.yaml` based on study data.

---

## 5. Phase 4 — Productionization (ongoing)

### 5.1 Hardening & Compliance

- Authentication + RBAC (role-scoped access).
- Encryption at rest (S3, DB), TLS in transit.
- Signed URLs for video retrieval.
- Audit logging on every profile read.
- Face-blur pipeline post-analysis.
- Data retention + auto-purge jobs.

### 5.2 Monitoring

- Per-stage timings, confidence distributions.
- Dropped-cycle and re-record rates.
- Clinician override frequency.

### 5.3 K8s Orchestration

- When throughput grows, move from Compose → Kubernetes.
- Helm charts for API, worker, DB, Redis.

---

## 6. Development Workflow

### Directory Setup
```bash
# Clone repo
cd gait-analysis

# Create virtual env
python3.11 -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install deps
pip install -e .
pip install -r requirements-dev.txt

# Pre-commit hooks
pre-commit install
```

### Local Development (Docker Compose)
```bash
# All services: API, Celery worker, Redis, Postgres, MinIO
docker-compose up -d

# Run tests
make test
make test-e2e

# Lint + format
make lint
make format

# Run API locally
make run-api

# Run Celery worker locally
make run-worker
```

### Git & PR Workflow
1. Create feature branch: `feature/<short-desc>` (e.g., `feature/rearfoot-angle`).
2. Commit with Conventional Commits: `feat(analysis): add time-to-peak-eversion`.
3. Push → PR.
4. CI must pass: lint, type check, tests.
5. Update docs **in same PR** if behavior or schema changes.
6. Reviewer checklist: no magic numbers, units in names, schema sync, tests, privacy checks.

---

## 7. Key Invariants (Never Break These)

1. **`src/gait/profile/schema.py` is the single source of truth** for the patient-profile schema.
2. **All thresholds come from `configs/thresholds.yaml`** — no magic numbers in code.
3. **All recommendation logic lives in `configs/rules.yaml`** — orthotist-editable, not hardcoded.
4. **Every numeric field carries a unit in its name:** `stride_length_m`, `rearfoot_angle_deg`, `mass_kg`.
5. **Always use `{"L": ..., "R": ...}` for left/right data** — never mix `left`/`right` with `L`/`R`.
6. **Fail loudly on bad data:** if < 4 clean cycles/foot, refuse to emit a profile and request re-record.
7. **Confidence gates are respected:** low-confidence cycles are dropped, never silently trusted.
8. **Privacy non-negotiable:** faces are blurred post-pipeline, data is encrypted at rest, all access is audit-logged.
9. **Schema-breaking changes require a version bump** (`profile/v1` → `profile/v2`) and a migration note.

---

## 8. Success Metrics (How to Know You're Done)

### Phase 1 exit (MVP)
- Profile JSON schema-valid 100%.
- Pronation classification + spatiotemporal params working.
- Processing time ≤ ~60 s per session.
- Gating logic: < 4 cycles/foot → no profile.

### Phase 3 exit (validation)
- ICC > 0.85 vs. ground truth.
- Rearfoot-angle repeatability SD < 2°.
- Stance-time repeatability SD < 5%.
- Thresholds and rules tuned from study.

### Phase 4 (production ready)
- Compliance checklist fully satisfied.
- Monitoring dashboards live.
- Quarterly model re-training cadence established.
- Runnable on Kubernetes.

---

## 9. Quick Reference: Who Owns What

| Component | Owner | Priority |
|---|---|---|
| `src/gait/pipeline/` | Engineer | Core orchestration |
| `src/gait/pose/` | ML Engineer | Accuracy + speed |
| `src/gait/events/` | Engineer | Robustness of HS/TO |
| `src/gait/analysis/` | Biomech expert | Clinical validity |
| `src/gait/profile/` | Engineer | Schema consistency |
| `configs/thresholds.yaml` | Clinician + Engineer | Tuning |
| `configs/rules.yaml` | Orthotist | Shoe recommendations |
| `src/gait/api/` | Backend engineer | Reliability |
| `frontend/` | Frontend engineer | UX |
| Docs | Everyone | Sync with code |

---

## 10. Common Pitfalls (Avoid These)

❌ **Hardcoding a threshold in an `if` statement.**  
✅ Load thresholds from `configs/thresholds.yaml`.

❌ **Silently filtering out low-confidence cycles without logging.**  
✅ Log dropped cycles; surface re-record condition to the operator.

❌ **Forgetting to update the schema doc when changing `schema.py`.**  
✅ Always update `API_AND_SCHEMA.md` in the same PR.

❌ **Storing un-blurred subject video indefinitely.**  
✅ Blur faces post-pipeline; delete beyond retention window.

❌ **Mixing L/R naming conventions** (sometimes `left`, sometimes `L`).  
✅ Always use `{"L": ..., "R": ...}` throughout.

❌ **Running a heavy model inference in the API thread.**  
✅ Offload to Celery worker; API stays light and async.

---

## 11. AI Agents Integration Roadmap

This project is designed for **progressive integration of AI agents** to reduce hardcoding and enable adaptive, learning-driven decision-making. Agents are **optional** for MVP but lay the groundwork for intelligent automation.

### Why Agents?

Instead of static rules and thresholds:
- **Adaptive thresholds** — agents learn optimal foot-strike/pronation angles from validation data
- **Smart recommendations** — agents learn shoe designs that work best for each gait type
- **Quality assessment** — agents learn to flag edge cases instead of binary gates
- **Model selection** — agents choose best pose model/tracking strategy per input

### Integration Timeline

**Phase 1B (Current):** Infrastructure-ready but agents disabled
- All config parameters externalized (ready for agent tuning)
- Placeholder `src/gait/agents/` directory structure
- `pipeline.yaml` has `agents: {enabled: false}`

**Phase 2:** First agent
- **Data Quality Agent** — learns to score gait data quality
- Reduces need for manual QA

**Phase 3 (Validation Study):** Core learning agents
- **Threshold-Tuning Agent** — learns from clinical validation data
- **Recommendation Agent** — learns from clinician feedback
- **Anomaly Agent** — learns pathological gait patterns

**Phase 4 (Production):** Online learning
- Agents adapt continuously from production feedback
- Per-demographic personalization
- Automatic model retraining

### How Agents Change the Architecture

**Agent Decision Points:**

| Decision | Current (Static) | With Agent (Phase 3+) |
|----------|-----------------|----------------------|
| Is data good? | `< 4 cycles = reject` | Agent scores confidence |
| Which model? | `pipeline.yaml: mediapipe` | Agent selects pose model |
| Shoe design? | Static rules in `rules.yaml` | Agent learns from outcomes |
| Thresholds? | `thresholds.yaml` hardcoded | Agent learns from validation data |

**Key invariant:** Agents never break the schema. Output is always `profile.json` matching `schema.py`.

### For Implementers

- **Task 3 (Ingestion):** Build without worrying about agents — architecture is flexible
- **Task 4+ (Pose, Analysis, Profile):** Design components to be agent-pluggable:
  - Expose tunable parameters in config
  - Emit confidence scores
  - Log decisions (so agents can learn from them)
- **Phase 2+:** Agents plug into these decision points without rewriting core logic

See `AI_AGENTS_INTEGRATION.md` for detailed agent architecture and learning loops.

---

## Appendix: Useful Commands

```bash
# Lint + format
make format
make lint

# Run tests
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/e2e/ -v

# Type check
mypy src/gait/

# Start dev stack
docker-compose up -d

# View logs
docker-compose logs -f api
docker-compose logs -f worker

# Stop
docker-compose down

# Generate JSON schema from Pydantic model
python -c "from src.gait.profile.schema import GaitPatientProfile; print(GaitPatientProfile.model_json_schema())"
```

---

**Next Step:** Review this playbook with the team. Assign Phase 0 tasks (hardware + calibration) to get hardware/rig ready in parallel with code scaffolding. Then kick off Phase 1 (MVP) in week 3 of Phase 0.
