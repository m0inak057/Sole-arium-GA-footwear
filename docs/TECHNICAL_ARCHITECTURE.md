# Gait Analysis Module — Technical Architecture Reference

**A compact, visual guide to the system's structure, dependencies, and interfaces.**

---

## 1. Component Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            CLINICIAN / OPERATOR                          │
│                         (Web Browser / Desktop UI)                       │
└────────────┬─────────────────────────────────────────────────────────────┘
             │ HTTPS (TLS)
             ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                    FRONTEND LAYER (React / Streamlit MVP)               │
│                                                                           │
│  Routes:                                                                  │
│  ├─ /sessions → create session, upload video                            │
│  ├─ /sessions/{id}/profile → view results (curves, classifications)     │
│  ├─ /sessions/{id}/timeseries → plot per-cycle parameters              │
│  └─ /rules → (admin) edit recommendation rules                          │
└────────────┬─────────────────────────────────────────────────────────────┘
             │ HTTP (async)
             ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                    API LAYER (FastAPI)                                   │
│                                                                           │
│  /api/v1/sessions           → POST create, GET list                     │
│  /api/v1/sessions/{id}      → GET status (created|processing|complete)  │
│  /api/v1/sessions/{id}/uploads    → POST multipart video               │
│  /api/v1/sessions/{id}/process    → POST enqueue pipeline              │
│  /api/v1/sessions/{id}/profile    → GET profile.json                   │
│  /api/v1/sessions/{id}/timeseries → GET Parquet timeseries             │
│  /api/v1/profiles/schema          → GET JSON schema v1                 │
│  /api/v1/rules                    → GET/PUT rules.yaml                 │
│  /api/v1/health                   → GET liveness                        │
│                                                                           │
│  Authentication: Bearer token + RBAC                                    │
│  Roles: clinician, shoe_designer, admin                                 │
└────────────┬──────────────┬──────────────┬──────────────────────────────┘
             │              │              │
      HTTP ↓        enqueue ↓              │   read/write
    session db      task → queue    metadata   ↓
             │        │              db     ┌───────────┐
┌────────────▼────────▼──────────────────────────┐        │
│            BROKER & WORKER LAYER               │        │
│                                                  │        │
│  Redis: task broker + cache                   │        │
│  ├─ Celery task queue                         │        │
│  └─ Cache hotspot data (config, models)       │        │
│                                                  │        │
│  Celery Worker (GPU-enabled):                 │        │
│  ├─ Run pipeline: ingestion → pose →          │        │
│  │  events → analysis → profile               │        │
│  ├─ Save profile.json to DB                   │        │
│  ├─ Write Parquet timeseries                  │        │
│  └─ Update session status                     │        │
└────────────┬─────────────────────────────────────┘        │
             │                                         │    │
       read/write                                     │    │
             ↓                                         │    │
┌────────────────────────────────────────────────────▼────▼─┐
│            DATA LAYER (Storage & Metadata)                 │
│                                                             │
│  PostgreSQL:                                              │
│  ├─ Sessions (id, subject_id, status, timestamps)         │
│  ├─ Profiles (session_id, profile_json, created_at)       │
│  ├─ Audit logs (who, what, when, profile_id)              │
│  └─ Rules versions (rules_yaml, version, updated_at)      │
│                                                             │
│  S3-compatible (MinIO / AWS S3):                          │
│  ├─ Raw video (encrypted, auto-purged)                    │
│  ├─ Face-blurred video (encrypted)                        │
│  └─ Parquet timeseries (encrypted)                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Processing Pipeline (7 Stages)

```
         INPUT: Raw video (3-camera rig)
              ↓

   ┌──────────────────────────────┐
   │  1. INGESTION (10s budget)   │
   │  decode → demux → sync →     │
   │  undistort → calibrate →     │
   │  bg_subtract → track → roi   │
   └──────────┬───────────────────┘
              ↓
   ┌──────────────────────────────┐
   │ 2. POSE ESTIMATION (15s)     │
   │ MediaPipe 2D →               │
   │ Custom foot model (Phase 2) →│
   │ 3D lift/triangulation →      │
   │ 1-Euro smoothing             │
   └──────────┬───────────────────┘
              ↓
   ┌──────────────────────────────┐
   │ 3. GAIT EVENTS (10s)         │
   │ HS/TO detection →            │
   │ Stance/swing segmentation →  │
   │ Cycle normalization          │
   └──────────┬───────────────────┘
              ↓
   ┌──────────────────────────────┐
   │ 4. BIOMECHANICS (15s)        │
   │ Spatiotemporal →             │
   │ Kinematics →                 │
   │ Pronation → Foot-strike →    │
   │ Arch type → Symmetry         │
   └──────────┬───────────────────┘
              ↓
   ┌──────────────────────────────┐
   │ 5. PROFILE BUILDER (5s)      │
   │ Aggregate cycles →           │
   │ Confidence gates →           │
   │ Apply rules.yaml →           │
   │ Emit profile.json            │
   └──────────┬───────────────────┘
              ↓
       OUTPUT: profile.json
       (schema-valid, ≤ 60 s total)
```

---

## 3. Data Models & Type Hierarchy

```python
# Common types (src/gait/common/types.py)
class Frame(BaseModel):
    timestamp_ms: int
    image: np.ndarray
    camera_view: str  # 'sagittal' | 'posterior' | 'plantar'

class KeypointFrame(BaseModel):
    timestamp_ms: int
    keypoints: dict  # {kp_id: (x, y, z?, confidence)}
    camera_view: str
    is_valid: bool

class GaitCycle(BaseModel):
    cycle_id: int
    frame_start: int
    frame_end: int
    stance_frames: list[int]
    swing_frames: list[int]
    keypoints: dict
    confidence: float

class AnalysisParams(BaseModel):
    spatiotemporal: SpatiotemporalParams
    kinematics: KinematicsParams
    foot_strike: FootStrikeResult
    pronation: PronationResult
    arch: ArchResult
    symmetry: SymmetryResult

# Profile schema (src/gait/profile/schema.py) — SOURCE OF TRUTH
class GaitPatientProfile(BaseModel):
    patient_id: str
    session_timestamp: str
    anthropometrics: Anthropometrics
    spatiotemporal: SpatiotemporalProfile
    foot_strike: FootStrikeProfile
    pronation: PronationProfile
    arch: ArchProfile
    symmetry_flags: list[str]
    health_assessment: HealthAssessment
    confidence_scores: dict[str, float]

    class Config:
        json_schema_extra = {"$schema": "https://...", ...}
```

---

## 4. Config & Rules Structure

### `configs/thresholds.yaml` (all tunable parameters)

```yaml
# Ingestion
ingestion:
  confidence_threshold: 0.5  # drop keypoints below this

# Events
events:
  hs_velocity_threshold: 0.05  # m/s
  to_velocity_threshold: 0.02

# Analysis
analysis:
  # Foot-strike angle (FSA) cutoffs
  foot_strike_thresholds:
    rearfoot_min_deg: 5.0
    forefoot_max_deg: -5.0
  
  # Pronation/supination cutoffs (rearfoot angle at mid-stance)
  pronation_thresholds:
    overpronation_min_deg: 8.0
    mild_pronation_min_deg: 4.0
    mild_supination_max_deg: 0.0
    oversupination_max_deg: -4.0
  
  # Arch type cutoffs
  arch_thresholds:
    high_arch_min_ahi: 0.35
    low_arch_max_ahi: 0.21
  
  # Symmetry
  asymmetry_flag_threshold_pct: 10.0

# Confidence & gating
gating:
  keypoint_confidence_floor: 0.5
  min_clean_cycles_floor: 4  # below this → RERECORD
  target_clean_cycles: 8  # below this → proceed but warn
```

### `configs/rules.yaml` (recommendation logic - orthotist-editable)

```yaml
# Rule-based shoe recommendations
shoe_recommendations:
  rules:
    - id: "overpronation_low_arch"
      condition:
        pronation_classification: "overpronation"
        arch_type: "low"
      action:
        medial_post: "required"
        post_density: "firm"
        arch_support: "high"
        heel_counter: "rigid"
        heel_drop_mm: 10
        last_shape: "straight"
        cushioning_zone_priority: ["heel", "medial_forefoot"]
    
    - id: "oversupination_high_arch"
      condition:
        pronation_classification: "oversupination"
        arch_type: "high"
      action:
        medial_post: "none"
        arch_support: "minimal"
        last_shape: "curved"
        cushioning_zone_priority: ["lateral_forefoot", "heel"]
    
    - id: "forefoot_striker"
      condition:
        foot_strike_pattern: "forefoot"
      action:
        heel_drop_mm: 6
        forefoot_cushioning: "high"
        heel_cushioning: "moderate"
```

### `configs/pipeline.yaml` (system configuration)

```yaml
pipeline:
  # Model choices
  body_pose_model: "mediapipe"  # or "rtmpose"
  foot_keypoint_model: null  # Phase 2: "custom_foot_model_v1"
  lifting_model: "videpose3d"  # or "motionbert"
  event_detection: "threshold"  # or "cnn"
  
  # Processing parameters
  fps: 120  # assumed input frame rate
  smoothing_type: "1euro"
  smoothing_params:
    mincutoff: 1.0
    beta: 0.1
    dcutoff: 1.0
  
  # Hardware
  gpu_device: 0
  batch_size: 8

# AI agents — all disabled for MVP; enable per-phase
agents:
  enabled: false                          # global kill-switch
  quality_assessment:
    enabled: false                        # Phase 2+
    model_path: models/agents/quality_v1.pth
    confidence_threshold: 0.7
  threshold_tuner:
    enabled: false                        # Phase 3+
    model_path: models/agents/thresholds_v1.pth
    confidence_threshold: 0.8
  recommendation:
    enabled: false                        # Phase 3+
    model_path: models/agents/recommendations_v1.pth
    confidence_threshold: 0.75
  anomaly_detector:
    enabled: false                        # Phase 3+
    model_path: models/agents/anomaly_v1.pth
    confidence_threshold: 0.8
```

---

## 5. Module-by-Module Responsibilities

```
src/gait/
├── capture/              Input → raw streams
│   ├── recorder.py       Live camera capture or file import
│   └── schemas.py        Session metadata types
│
├── ingestion/            Raw → clean frames
│   ├── decode.py         Read video, yield frames
│   ├── calibrate.py      Undistort, apply extrinsics
│   ├── segment_bg.py     Background subtraction (MOG2/SAM2)
│   ├── track.py          Person tracking (ByteTrack)
│   ├── roi.py            ROI crop around subject
│   └── ingest_pipe.py    Orchestrate stages 1-5
│
├── pose/                 Clean frames → keypoints
│   ├── body_2d.py        MediaPipe wrapper (Tier A)
│   ├── foot_kp.py        Custom foot model (Tier B, Phase 2)
│   ├── lift_3d.py        VideoPose3D / MotionBERT
│   ├── triangulate.py    Multi-view triangulation (Phase 3)
│   ├── smooth.py         1-Euro filter
│   └── pose_pipe.py      Orchestrate stages 2
│
├── events/               Keypoints → cycles
│   ├── detect.py         HS/TO detection
│   ├── cnn_events.py     Optional 1D-CNN fallback
│   ├── segment_cycles.py Cycle segmentation
│   └── event_pipe.py     Orchestrate stage 3
│
├── analysis/             Cycles → parameters
│   ├── spatiotemporal.py Cadence, speed, stride, etc.
│   ├── kinematics.py     Joint angles
│   ├── foot_strike.py    FSA classifier
│   ├── pronation.py      Rearfoot angle + classification (headline)
│   ├── arch.py           Arch height index
│   ├── symmetry.py       Bilateral symmetry
│   └── analysis_pipe.py  Orchestrate stage 4
│
├── profile/              Parameters → profile.json
│   ├── schema.py         Pydantic models (SOURCE OF TRUTH for schema)
│   ├── builder.py        Assemble all fields
│   ├── recommend.py      Apply rules.yaml
│   ├── confidence.py     Confidence gating + cycles filtering
│   └── profile_pipe.py   Orchestrate stage 5
│
├── pipeline/             Full orchestration
│   ├── run.py            session_dir → profile.json
│   └── gating.py         Re-record / cycle-drop logic
│
├── agents/               AI agent layer (Phase 2+; all disabled in MVP)
│   ├── base.py           GaitAgent ABC — predict(), get_confidence(), get_reasoning()
│   ├── quality.py        QualityAssessmentAgent (Phase 2): replaces binary cycle gate
│   ├── threshold.py      ThresholdTuningAgent (Phase 3): replaces YAML cutoffs
│   ├── recommend.py      RecommendationAgent (Phase 3): replaces rules.yaml mappings
│   └── anomaly.py        AnomalyDetector (Phase 3): replaces rule-based pathology flag
│
├── common/               Shared utilities
│   ├── geometry.py       Angle math, vector ops, planes
│   ├── signal.py         Filtering, peak detection
│   ├── io.py             Parquet/JSON/video I/O
│   ├── logging.py        Structured logging
│   ├── types.py          Shared dataclasses
│   └── constants.py      Enums, units, defaults
│
└── api/                  REST + async
    ├── main.py           FastAPI app instance
    ├── routes/
    │   ├── sessions.py    Session CRUD
    │   ├── profiles.py    Profile retrieval + overrides
    │   ├── rules.py       Rules management
    │   └── health.py      Liveness/readiness
    ├── tasks.py           Celery job definitions
    ├── deps.py            Auth, DB sessions, RBAC
    └── models.py          Request/response schemas
```

---

## 6. Data Flow Through a Single Session

```
1. Operator creates session (POST /sessions)
   → SessionID assigned, metadata stored in DB
   → Status: created

2. Operator uploads video (POST /sessions/{id}/uploads)
   → Video written to S3 (encrypted)
   → Status: uploaded

3. Operator triggers processing (POST /sessions/{id}/process)
   → FastAPI enqueues Celery task
   → Status: processing
   → Returns TaskID

4. Celery Worker picks up task
   ├─ Load video from S3
   ├─ Run pipeline:
   │  ├─ Ingest (frames, calibrate, BG subtract, track)
   │  ├─ Pose (MediaPipe, smooth)
   │  ├─ Events (HS/TO, cycles)
   │  ├─ Analysis (spatiotemporal, pronation, etc.)
   │  └─ Profile (aggregate, gate, recommend, schema-check)
   ├─ Save profile.json to DB
   ├─ Save Parquet timeseries to S3
   ├─ Update session status → complete
   └─ Or on gate failure: status → needs_rerecord

5. Clinician queries profile (GET /sessions/{id}/profile)
   → profile.json returned
   → Audit log: clinician X read profile Y at time Z

6. (Optional) Clinician adjusts recommendation
   (PATCH /sessions/{id}/profile/recommendations)
   → Update rules or override specific field
   → Audit log: clinician X modified profile Y

7. Profile forwarded to Shoe Design Module
   → profile.json consumed
   → Out of scope for this project
```

---

## 7. Key Interfaces & Contracts

### Pipeline Entry Point
```python
def process_session(
    session_dir: Path,
    config: PipelineConfig,
    models: ModelRegistry,
) -> Union[GaitPatientProfile, GatingDecision]:
    """
    Top-level function: video directory → profile.json or re-record signal.
    
    Returns:
    - GaitPatientProfile if successful
    - GatingDecision.RERECORD if < 4 cycles/foot
    - Raises GaitPipelineException on error
    """
```

### Per-Stage Function Signature
```python
def stage_function(
    input_data: InputType,
    config: StageConfig,
    model: Optional[Model] = None,
) -> OutputType:
    """
    Pure function of input + config + model.
    No hidden state, I/O only at boundaries.
    
    Each function is independently unit-testable.
    """
```

### Confidence Gating
```python
def apply_gates(
    cycles: list[GaitCycle],
    thresholds: GatingThresholds,
) -> tuple[list[GaitCycle], GatingDecision]:
    """
    Drop low-confidence cycles.
    Return decision: RERECORD | PROCEED_WITH_WARNING | PROCEED_OK
    """
```

---

## 8. External Dependencies (Tech Stack)

```
Core computation:
  ├─ numpy              (arrays)
  ├─ scipy              (signal processing, filtering)
  ├─ opencv-python      (video decode, calibration, undistortion)
  ├─ scikit-image       (image processing)
  └─ pydantic           (type safety, schema validation)

Deep learning:
  ├─ torch              (PyTorch)
  ├─ torchvision        (vision models)
  ├─ mediaipe           (pose estimation)
  ├─ mmpose (opt)       (RTMPose, custom foot model)
  └─ videpose3d (opt)   (monocular 2D→3D lifting)

Backend & API:
  ├─ fastapi            (REST API)
  ├─ uvicorn            (ASGI server)
  ├─ celery             (task queue)
  ├─ redis              (broker + cache)
  └─ sqlalchemy         (ORM)

Storage:
  ├─ psycopg2           (PostgreSQL driver)
  ├─ boto3              (S3 / MinIO client)
  └─ pyarrow            (Parquet I/O)

Frontend:
  ├─ react              (UI framework)
  ├─ plotly / recharts  (interactive charts)
  └─ three.js           (3D skeleton overlay)

DevOps & testing:
  ├─ docker             (containerization)
  ├─ docker-compose     (local dev stack)
  ├─ pytest             (testing)
  ├─ black              (formatting)
  ├─ ruff               (linting)
  └─ mypy               (type checking)
```

---

## 9. Database Schema (Simplified)

```sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    patient_id VARCHAR(50),
    status VARCHAR(20),  -- created | uploaded | processing | complete | needs_rerecord
    created_at TIMESTAMP,
    processed_at TIMESTAMP,
    metadata JSONB  -- age, height, weight, foot dims, dominant side
);

CREATE TABLE profiles (
    id UUID PRIMARY KEY,
    session_id UUID REFERENCES sessions(id),
    profile_json JSONB,  -- full profile.json
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(100),
    action VARCHAR(50),  -- read | update | delete
    resource_type VARCHAR(20),  -- profile | session | rules
    resource_id UUID,
    timestamp TIMESTAMP
);

CREATE TABLE rules_versions (
    id BIGSERIAL PRIMARY KEY,
    rules_yaml TEXT,
    version INT,
    created_by VARCHAR(100),
    created_at TIMESTAMP
);

CREATE TABLE timeseries_metadata (
    id UUID PRIMARY KEY,
    session_id UUID REFERENCES sessions(id),
    parquet_s3_key VARCHAR(500),  -- s3://bucket/timeseries/{session_id}.parquet
    created_at TIMESTAMP
);
```

---

## 10. Deployment Topology (MVP)

```
Development (Docker Compose on single workstation):
┌──────────────────────────────────────────────────────┐
│ Docker Network                                       │
├──────────────────────────────────────────────────────┤
│ Service                Port   Image                  │
├──────────────────────────────────────────────────────┤
│ api                   8000   gait:latest             │
│ worker (GPU)          —      gait:latest (cmd exec)  │
│ postgres              5432   postgres:15             │
│ redis                 6379   redis:7                 │
│ minio                 9000   minio:latest            │
│ frontend              3000   gait-frontend:latest    │
└──────────────────────────────────────────────────────┘

Production (Kubernetes, Phase 4):
┌────────────────────────────────────────────────────────┐
│ Kubernetes Cluster                                    │
├────────────────────────────────────────────────────────┤
│ Namespace: gait-analysis                              │
│                                                        │
│ ├─ Deployment: api                                    │
│ │  └─ Replicas: 2–3 (auto-scale on CPU)             │
│ │                                                      │
│ ├─ Deployment: worker                                │
│ │  ├─ NodeSelector: gpu=true                         │
│ │  └─ Replicas: 1–2 (on GPU nodes)                   │
│ │                                                      │
│ ├─ StatefulSet: postgres                             │
│ │  └─ PVC: data volume                               │
│ │                                                      │
│ ├─ StatefulSet: redis                                │
│ │  └─ PVC: data volume                               │
│ │                                                      │
│ ├─ Service: api (LoadBalancer)                       │
│ ├─ Service: postgres (ClusterIP)                     │
│ ├─ Service: redis (ClusterIP)                        │
│ │                                                      │
│ └─ ConfigMap: thresholds.yaml, rules.yaml            │
│                                                        │
│ External:                                             │
│ ├─ S3 bucket (video, timeseries, blurred)            │
│ └─ CloudSQL / RDS (managed postgres)                 │
└────────────────────────────────────────────────────────┘
```

---

## 11. AI Agents Layer (Phase 2+)

Agents are optional model-backed overrides that slot into existing decision points without changing the surrounding code. The static YAML-driven path is always computed first and used as fallback.

### Decision points and their agents

| Where in code | Agent (Phase) | What it learns |
|---|---|---|
| `profile/confidence.py` | Quality Assessment Agent (2) | Session quality score (0–1) from cycle patterns |
| `analysis/pronation.py` | Threshold Tuning Agent (3) | Optimal pronation/supination cutoffs from pressure-mat ground truth |
| `analysis/foot_strike.py` | Threshold Tuning Agent (3) | Optimal FSA cutoffs |
| `profile/recommend.py` | Recommendation Agent (3) | Shoe designs from clinician overrides + outcomes |
| `profile/builder.py` | Anomaly Detector (3) | Pathological gait patterns → `needs_human_review` |

### Integration pattern (consistent at every point)

```python
def classify_pronation(angle: float, config: PipelineConfig) -> str:
    baseline = _static_classify(angle, config.thresholds.pronation)
    if config.agents.enabled and config.agents.threshold_tuner.enabled:
        try:
            result = threshold_agent.predict({"rearfoot_angle": angle})
            if result.confidence >= config.agents.threshold_tuner.confidence_threshold:
                log_agent_decision("threshold_tuner", angle, result)
                return result.classification
        except Exception as exc:
            logger.warning("threshold_agent failed, using baseline", exc_info=exc)
    return baseline
```

### Phase 4: Online learning loop

```
Production clinician overrides → collect feedback → quarterly retrain →
A/B test (new vs. old model) → approve if accuracy ≥ baseline →
update pipeline.yaml model version → deploy
```

See **[AI_AGENTS_INTEGRATION.md](../AI_AGENTS_INTEGRATION.md)** for the full taxonomy, data requirements, and governance workflow.

---

**This document is your "system at a glance" reference. Print it, bookmark it, refer to it often.**

Last updated: 2026-06-12  
Version: 1.1
