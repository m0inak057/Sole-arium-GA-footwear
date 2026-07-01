# Sole-Arium Gait Analysis Platform — Product Requirements & System Architecture Document

## Product Information

| Field | Value |
|---|---|
| Document | PRD & System Architecture |
| Version | 2.0 |
| Status | Production-Ready |
| Last Updated | 2026-06-29 |
| Related | [ARCHITECTURE.md](./ARCHITECTURE.md), [API_AND_SCHEMA.md](./API_AND_SCHEMA.md), [DATA_FLOW.md](./DATA_FLOW.md) |

---

## 1. Overview

### 1.1 Vision
Make clinically-grounded, customized orthopedic footwear accessible and affordable by replacing expensive, marker-based motion-capture labs with a **markerless, camera-only gait analysis system** that produces a structured, machine-readable patient profile.

### 1.2 Problem statement
Customized orthopedic footwear today depends on either (a) subjective clinician observation, which is inconsistent and operator-dependent, or (b) marker-based gait labs and pressure plates, which are expensive, slow, and inaccessible outside large hospitals. There is no affordable, repeatable, automated bridge between *capturing how a person walks* and *designing a shoe for them*.

### 1.3 Solution summary
A computer-vision pipeline that:
1. Records a subject walking using ordinary cameras (no body markers).
2. Extracts biomechanical parameters automatically.
3. Classifies foot-strike and pronation/supination behavior.
4. Emits a structured **patient profile JSON** that the shoe-design module consumes directly — so the shoe designer never has to re-examine the video.

### 1.4 Where this module sits
This is **Stage 1** of a larger pipeline. Its single deliverable — `profile.json` — is the contract handed to the downstream **Shoe Design Module** (last design, midsole geometry, medial post, arch support). Everything in this PRD stops at the boundary of that JSON.

---

## SYSTEM ARCHITECTURE & CURRENT IMPLEMENTATION

### Current Technology Stack

**Frontend:**
- React 18 + Vite + Tailwind CSS
- Two-page UI: Upload → Results
- Real-time status polling via REST API

**Backend:**
- FastAPI (Python) - REST API server on port 8000
- Celery - Async task processing (4 concurrent workers)
- PostgreSQL 15 - Persistent data storage
- Redis 7 - Cache, task broker, session state
- MinIO - S3-compatible object storage for video frames
- Flower - Celery task monitoring UI (port 5555)

**Monitoring:**
- Prometheus - 50+ application metrics
- Sentry - Exception tracking & alerting
- Custom health checks for all services

---

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    FRONTEND (React + Vite)                       │
│              Browser UI: Upload → Results Pages                  │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP/REST
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   FASTAPI SERVER (Port 8000)                     │
│  Sessions  │  File Upload  │  Pipeline Trigger  │  Status Poll  │
│  Auth & Rate Limiting  │  Health Checks                          │
└────────┬─────────────────┬──────────────────────────┬───────────┘
         │                 │                          │
         ▼                 ▼                          ▼
    ┌─────────┐      ┌──────────┐            ┌─────────────────┐
    │PostgreSQL│      │  Redis   │            │ MinIO (S3)      │
    │Database  │      │  Cache & │            │ Object Storage  │
    │          │      │  Broker  │            │ (video frames)  │
    └─────────┘      └──────────┘            └─────────────────┘
         ▲                 ▲
         │         Celery Task Queue
         │                 │
┌────────┴─────────────────┴─────────────────────────────────────┐
│           CELERY WORKERS (Concurrent: 4)                        │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │    GAIT ANALYSIS PIPELINE (5-Stage Processing)          │   │
│  │                                                         │   │
│  │  Stage 1: INGESTION & PREPROCESSING                    │   │
│  │  ├─ Video decoding (OpenCV)                            │   │
│  │  ├─ Camera calibration (checkerboard patterns)         │   │
│  │  ├─ Background segmentation                           │   │
│  │  └─ 2D foot tracking                                  │   │
│  │                                                         │   │
│  │  Stage 2: POSE ESTIMATION                              │   │
│  │  ├─ MediaPipe keypoint extraction (33 landmarks)      │   │
│  │  ├─ Trajectory smoothing (Savitzky-Golay)            │   │
│  │  └─ 2D→3D conversion via triangulation               │   │
│  │                                                         │   │
│  │  Stage 3: GAIT EVENT DETECTION                         │   │
│  │  ├─ Velocity filtering (bandpass)                      │   │
│  │  ├─ Heel-strike & toe-off detection                   │   │
│  │  └─ Gait cycle segmentation                           │   │
│  │                                                         │   │
│  │  Stage 4: BIOMECHANICAL ANALYSIS                       │   │
│  │  ├─ Joint angles (ankle, knee, hip)                   │   │
│  │  ├─ Spatiotemporal metrics (cadence, stride length)   │   │
│  │  ├─ Asymmetry indices                                 │   │
│  │  └─ Efficiency metrics                                │   │
│  │                                                         │   │
│  │  Stage 5: PROFILE GENERATION                           │   │
│  │  ├─ Statistical aggregation (mean, std, ICC)          │   │
│  │  ├─ Clinical report generation                        │   │
│  │  ├─ AI Health Coach (Claude API)                      │   │
│  │  ├─ AI Prescription Engine (Claude API)               │   │
│  │  └─ Save profile to PostgreSQL + MinIO               │   │
│  │                                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  FLOWER - Celery Task Monitor (Port 5555)              │   │
│  │  Real-time visibility into task execution              │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

### Backend Services Overview

#### 1. FastAPI Server (Port 8000)

**Core Responsibilities:**
- Session creation & management (PostgreSQL)
- Video file upload handling (MinIO storage)
- Pipeline task queuing (Celery)
- Status polling & result retrieval
- Authentication (JWT + API keys)
- Rate limiting (token bucket via Redis)

**Key REST Endpoints:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/v1/sessions` | Create session |
| POST | `/api/v1/sessions/{id}/uploads` | Upload video files |
| POST | `/api/v1/sessions/{id}/process` | Trigger pipeline |
| GET | `/api/v1/sessions/{id}/status` | Poll job status |
| GET | `/api/v1/sessions/{id}/profile` | Retrieve results |
| DELETE | `/api/v1/sessions/{id}` | Delete session |
| GET | `/health` | Service health check |

#### 2. Celery Worker (4 concurrent processes)

**Execution Model:**
- Prefork process pool (4 parallel workers)
- Message broker: Redis DB 0
- Result backend: Redis DB 1
- Task queue: `celery` (default)

**Workflow:**
1. API receives `/process` → Queues task to Redis
2. Idle worker picks up task
3. Executes 5-stage pipeline (see diagram above)
4. Stores results in Redis result backend
5. Persists to PostgreSQL + MinIO
6. Frontend polls `/status` to track progress

#### 3. PostgreSQL Database

**Core Tables:**

| Table | Purpose |
|-------|---------|
| `users` | API user accounts |
| `api_keys` | Authentication tokens |
| `sessions` | Analysis session records |
| `uploads` | Video file metadata |
| `profiles` | Completed gait profiles (JSON) |

**ORM:** SQLAlchemy with Pydantic v2 validation

#### 4. Redis Cache & Message Broker

**Database 0:** Celery task queue (messages)  
**Database 1:** Celery result backend (cached results)  
**General:** Application cache, session state, rate limiting counters

#### 5. MinIO Object Storage

**Bucket:** `gait-analysis`  
**Content:**
- Video frames (decoded, intermediate)
- Analysis artifacts
- Final profile results (JSON, CSV)

**Access:** S3-compatible API (can swap with AWS S3 in production)

---

### Frontend Services Overview

#### React Application (Port 3000 during dev)

**Architecture:**
- Single-page app (SPA) with client-side routing
- Two main routes: `/` (Upload) and `/results/:sessionId`

**Upload Page (`/`):**
1. User creates session → `POST /api/v1/sessions`
2. Upload video files → `POST /api/v1/sessions/{id}/uploads`
3. Click "Analyze" → `POST /api/v1/sessions/{id}/process`
4. Poll status every 2-5s → `GET /api/v1/sessions/{id}/status`
5. On completion → Redirect to results page

**Results Page (`/results/:sessionId`):**
1. Fetch profile → `GET /api/v1/sessions/{id}/profile`
2. Render kinematic charts (joint angles)
3. Display 3D shoe visualization
4. Show clinical findings & AI recommendations
5. Export/download options

**Components:**
- `UploadPage.jsx` — Session & file management
- `ResultsPage.jsx` — Results visualization
- `KinematicCharts.jsx` — Line charts (angles over gait cycle)
- `Shoe3DVisualization.jsx` — Interactive 3D model
- `api.js` — Centralized API client

---

### Complete User Workflow

```
User Opens Browser
        ↓
    Upload Page
        ↓
    [1] POST /sessions → session_id
        ↓
    Select video files (3 cameras)
        ↓
    [2] POST /sessions/{id}/uploads → Store in MinIO
        ↓
    Click "Analyze"
        ↓
    [3] POST /sessions/{id}/process → Queue Celery task
        ↓
        API returns task_id
        ↓
    Frontend starts polling
        ↓
    [4] GET /sessions/{id}/status → "pending"
    [4] GET /sessions/{id}/status → "active" (stage 1/5)
    [4] GET /sessions/{id}/status → "active" (stage 2/5)
        ... (stages 3, 4, 5)
    [4] GET /sessions/{id}/status → "success"
        ↓
    Auto-redirect to Results Page
        ↓
    [5] GET /sessions/{id}/profile → Fetch JSON results
        ↓
    Render Charts + 3D Model + Clinical Report
        ↓
    Display AI Health Coaching & Shoe Recommendations
        ↓
    User Reviews & Downloads Results
```

---

### 5-Stage Pipeline Deep Dive

#### Stage 1: Ingestion & Preprocessing
**Input:** 3 synchronized video files (anterior, lateral, posterior)  
**Operations:**
- Frame-by-frame video decoding
- Camera intrinsic calibration (stored parameters)
- Background subtraction (foreground mask)
- 2D foot tracking in each view

**Output:** Calibrated frame sequences, foot center locations

#### Stage 2: Pose Estimation
**Input:** Video frames  
**Model:** MediaPipe Pose (33 keypoints per frame)  
**Operations:**
- Keypoint extraction (confidence scores)
- Trajectory smoothing (remove jitter)
- 3D triangulation from multi-view 2D points

**Output:** 3D joint coordinates, velocities, accelerations

#### Stage 3: Gait Event Detection
**Input:** Foot velocity signals  
**Operations:**
- Bandpass filtering (0.5-3 Hz)
- Peak/valley detection for foot contacts
- Event classification (heel-strike, toe-off, etc.)
- Gait cycle segmentation

**Output:** Event timestamps, cycle boundaries, pass IDs

#### Stage 4: Biomechanical Analysis
**Input:** 3D joint trajectories + events  
**Computations:**
- **Joint angles:** Ankle (dorsi/plantarflex, invert/evert), knee (flex/extend), hip (flex/extend)
- **Spatiotemporal:** Cadence, stride length, gait speed, swing/stance time ratios
- **Asymmetry:** Left-right difference percentages
- **Efficiency:** Energy expenditure proxies
- **Foot strike:** Classification (rearfoot/midfoot/forefoot)
- **Pronation:** Rearfoot angle at mid-stance

**Output:** Per-cycle metrics, aggregated statistics

#### Stage 5: Profile Generation
**Input:** Aggregated metrics from all cycles  
**Operations:**
1. Statistical summary (mean, SD, ICC for reliability)
2. Clinical interpretation (normal ranges)
3. AI Health Coach reasoning (Claude API)
4. AI Prescription Engine (shoe design specs)
5. Persist to PostgreSQL + MinIO

**Output:** Structured `profile.json` + human-readable report

---

## 2. Goals & non-goals

### 2.1 Goals (v1 prototype)
- **G1** — Capture a walking subject with an affordable multi-camera rig.
- **G2** — Produce all standard spatiotemporal gait parameters automatically.
- **G3** — Classify pronation/supination per foot, with a confidence score. *(headline metric)*
- **G4** — Classify foot-strike pattern (rearfoot / midfoot / forefoot) per foot.
- **G5** — Estimate arch type per foot.
- **G6** — Compute bilateral symmetry indices and flag clinically meaningful asymmetry.
- **G7** — Emit a validated `profile.json` conforming to a fixed schema.
- **G8** — Generate a first-pass, rule-based shoe-design recommendation block.
- **G9** — Return results within ~60 seconds of capture completion.
- **G10** — Comply with India's DPDP Act 2023 for handling sensitive health video.

### 2.2 Non-goals (explicitly out of scope for v1)
- **NG1** — Plantar pressure mapping (deferred to v2; possible pressure-mat fusion).
- **NG2** — Running gait analysis (focus is walking only).
- **NG3** — Pathological / neurological gait *diagnosis*. The system **refers**, it does not diagnose.
- **NG4** — Manufacturing the shoe (handled downstream).
- **NG5** — Real-time / live overlay during walking (batch processing is acceptable for v1).
- **NG6** — Mobile / phone-only capture (controlled-room capture first; ruggedization later).

---

## 3. Target users & personas

| Persona | Role | What they need from the module |
|---|---|---|
| **Orthotist / Clinician** | Assesses the patient, reviews output, tunes rules | Trustworthy parameters, clear visualizations, ability to override and adjust recommendation rules |
| **Capture Operator** | Runs the recording sessions | A simple, reliable capture protocol and clear "re-record" prompts when data is bad |
| **Shoe Designer** | Consumes `profile.json` downstream | A stable, well-documented schema; never wants to touch raw video |
| **System Admin / Engineer** | Deploys & maintains the system | Reproducible deployment, monitoring, model-retraining workflow |
| **Patient / Subject** | The person being analyzed | Privacy, consent, a quick and non-invasive session |

---

## 4. User stories

### Capture & analysis
- As an **operator**, I can register a subject (ID, age, height, weight, foot dimensions, dominant side) before capture.
- As an **operator**, I can run a static calibration trial and at least 6 dynamic walking passes.
- As an **operator**, I am told immediately if too few clean gait cycles survived and I need to re-record.
- As the **system**, I automatically discard acceleration/deceleration cycles from each pass.

### Results & review
- As a **clinician**, I can view spatiotemporal parameters with mean ± SD across cycles.
- As a **clinician**, I can see the pronation/supination classification per foot with its confidence score.
- As a **clinician**, I can view gait curves and side-by-side left/right cycle plots.
- As a **clinician**, I can compare barefoot vs. shod trials.
- As a **clinician**, I can override a recommendation and adjust the underlying rules.

### Output & integration
- As the **system**, I emit a `profile.json` validated against the published schema.
- As a **shoe designer**, I receive a recommendation block (medial post, arch support, heel counter, heel drop, cushioning zones, last shape) derived from the analysis.
- As an **integrator**, I can rely on the schema being versioned and backward-compatible.

### Privacy
- As a **patient**, I give informed consent before capture and can request deletion.
- As the **system**, I blur faces in stored video once the pipeline has run.

---

## 5. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-1 | Ingest synchronized multi-camera video and timestamp-align frames | Must |
| FR-2 | Undistort and calibrate frames using stored intrinsics/extrinsics | Must |
| FR-3 | Isolate and track the subject (background subtraction + person tracking) | Must |
| FR-4 | Estimate whole-body 2D pose keypoints | Must |
| FR-5 | Estimate dedicated foot keypoints (calcaneus, malleoli, MTP heads, hallux, mid-Achilles) | Must |
| FR-6 | Reconstruct 3D keypoints (multi-view triangulation) or lift monocular 2D→3D | Should |
| FR-7 | Smooth keypoint trajectories without destroying event signals | Must |
| FR-8 | Detect heel-strike and toe-off events robustly | Must |
| FR-9 | Segment gait cycles into stance/swing and sub-phases | Must |
| FR-10 | Compute spatiotemporal parameters per cycle and aggregate (mean ± SD) | Must |
| FR-11 | Compute joint-angle kinematics across the cycle | Should |
| FR-12 | Classify foot-strike pattern from foot-strike angle at HS | Must |
| FR-13 | Compute rearfoot angle and classify pronation/supination at mid-stance | Must |
| FR-14 | Estimate arch type (arch height index and/or wet-footprint method) | Must |
| FR-15 | Compute bilateral symmetry indices and flag asymmetry > 10% | Must |
| FR-16 | Generate confidence scores for key classifications | Must |
| FR-17 | Apply editable, rule-based shoe-design recommendation mapping (YAML) | Must |
| FR-18 | Emit schema-valid `profile.json` | Must |
| FR-19 | Provide a clinician-facing viewer (curves, cycle plots, playback) | Should |
| FR-20 | Support barefoot vs. shod comparison | Should |
| FR-21 | Drop low-confidence cycles and require re-record below a cycle threshold | Must |
| FR-22 | Log every pipeline decision with a `confidence` score and `reasoning` dict (enables agent training data from day 1) | Must |
| FR-23 | Support optional AI agent overrides at threshold classification and recommendation stages; static YAML baseline always computed first and used as fallback when agent is disabled or low-confidence (Phase 2+) | Should |
| FR-24 | Provide an agent management endpoint (`GET /agents/status`) to inspect which agents are enabled and which model versions are active (Phase 3+) | Could |

---

## 6. Non-functional requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-1 | **Performance** | End-to-end processing ≤ ~60 s for a standard 6-pass session on the reference machine |
| NFR-2 | **Accuracy** | Inter-method agreement ICC > 0.85 vs. ground truth (pressure mat / goniometer) |
| NFR-3 | **Repeatability** | Same-subject re-scan within 30 min: rearfoot-angle SD < 2°, stance-time SD < 5% |
| NFR-4 | **Reliability** | If < 4 clean cycles per foot survive, fail loudly and request re-record |
| NFR-5 | **Privacy** | Treat all captures as sensitive personal health data; DPDP 2023 compliant |
| NFR-6 | **Security** | Encrypt video at rest; signed URLs for retrieval; role-based access; audit logging |
| NFR-7 | **Fairness** | Custom foot model trained on diverse skin tones and Indian foot morphology |
| NFR-8 | **Reproducibility** | Containerized; deterministic given same input + model versions |
| NFR-9 | **Maintainability** | Recommendation rules editable without code changes (YAML); agents deployable by updating `pipeline.yaml` model version only |
| NFR-10 | **Observability** | Log per-stage timings, confidence distributions, and dropped-cycle counts |
| NFR-11 | **Portability** | Runs on a single workstation for the prototype; container-orchestratable later |
| NFR-12 | **Usability** | Operator can run a full session with minimal training and clear prompts |

---

## 7. Scope boundaries

### In scope (v1)
Markerless 2D/3D pose & foot-keypoint estimation · gait cycle segmentation · spatiotemporal parameters · foot-strike classification · pronation/supination quantification · bilateral symmetry · arch type estimation · JSON patient profile · rule-based recommendation block.

### Out of scope (v1)
Plantar pressure mapping · running gait · pathological diagnosis · shoe manufacturing · live real-time overlay · phone-only capture.

---

## 8. Success metrics

| Metric | Target |
|---|---|
| Processing time per session | ≤ ~60 s |
| Pronation classification agreement with clinician | ICC > 0.85 |
| Rearfoot-angle repeatability (SD) | < 2° |
| Stance-time repeatability (SD) | < 5% |
| Clean-cycle yield per session | ≥ 8 cycles per foot target; ≥ 4 minimum |
| Schema validation pass rate of emitted profiles | 100% |
| Operator re-record rate (after training) | Low and trending down |
| Clinician trust / override rate | Tracked; recommendation rules tuned to reduce avoidable overrides; Phase 3 Recommendation Agent learns from override history |
| Agent confidence (Phase 2+) | Mean agent confidence ≥ 0.75 across production sessions |
| Agent override rate by clinician (Phase 2+) | Tracked per agent; target < 20% (signals high clinician agreement) |

---

## 9. Assumptions

- Capture happens in a **controlled room** with stable lighting for v1.
- Subjects can walk unaided at a self-selected speed.
- The protocol mandating **ankle/lower-shin visibility** is followed (no long trousers).
- A reference workstation with a capable GPU is available for the prototype.
- A clinician/orthotist is available to validate output and tune rules.

---

## 10. Dependencies

| Dependency | Used for | Notes |
|---|---|---|
| Multi-camera hardware + sync rig | Capture | See [DATA_CAPTURE_PROTOCOL.md](./DATA_CAPTURE_PROTOCOL.md) |
| Pose-estimation models (MediaPipe / RTMPose / HRNet) | Keypoints | Off-the-shelf for MVP; custom foot model later |
| Annotated foot-keypoint dataset (~2–5k images) | Custom model | Key prototype investment; diversity required |
| Pressure mat / goniometer | Validation ground truth | See [VALIDATION_QA.md](./VALIDATION_QA.md) |
| Downstream Shoe Design Module | Consumes `profile.json` | Schema is the contract |

---

## 11. Risks (summary)

See [ARCHITECTURE.md §Known Limitations](./ARCHITECTURE.md) for detail. Headline risks:
- Clothing occlusion destroying rearfoot accuracy → protocol mandates ankle visibility.
- Skin-tone bias in off-the-shelf models → diverse custom dataset.
- Treadmill vs. overground gait differences → validate if a treadmill plantar view is adopted.
- Too few cycles per session → multi-pass protocol + re-record gating.
- Pathological gait → human review required; never auto-finalize.

---

## 12. Release definition — "Done" for the prototype

A deployable module that, given 6 walking passes, returns within ~60 s a `profile.json` containing:
1. All standard spatiotemporal gait parameters.
2. A clinically interpretable pronation/supination classification per foot, with confidence.
3. A foot-strike pattern classification per foot.
4. An arch type estimate per foot.
5. A symmetry assessment.
6. A first-pass shoe-design recommendation block.

That JSON is the contract with the rest of the orthopedic footwear system.
