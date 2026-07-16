# Architecture
## Gait Analysis Module — System Architecture

| Field | Value |
|---|---|
| Document | Architecture |
| Version | 1.0 |
| Related | [PRD.md](./PRD.md), [DATA_FLOW.md](./DATA_FLOW.md), [PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md), [API_AND_SCHEMA.md](./API_AND_SCHEMA.md) |

---

## 1. Architectural overview

The system is a **linear, staged pipeline**. Raw video enters at the top; a structured patient profile exits at the bottom. Each stage has a single responsibility and a well-defined input/output, which makes the pipeline testable stage-by-stage and lets us swap implementations (e.g., upgrade the pose model) without rewriting neighbors.

```
┌─────────────────────────────────────────────────────────────────────┐
│                       CAPTURE LAYER (hardware)                      │
│   Anterior cam │ Sagittal cam │ Posterior cam                       │
│   Calibration board │ Lighting │ Hardware/software sync trigger     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ raw video streams
┌──────────────────────────────▼──────────────────────────────────────┐
│                       INGESTION & PREPROCESSING                     │
│   Frame sync │ Undistort │ Calibrate │ Background subtract │ ROI    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ clean frames
┌──────────────────────────────▼──────────────────────────────────────┐
│                    POSE & FOOT KEYPOINT ESTIMATION                  │
│   Whole-body 2D pose (MediaPipe/MMPose) │ Custom foot-keypoint net  │
│   3D lifting / multi-view triangulation │ Temporal smoothing        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ time-series of 2D/3D keypoints
┌──────────────────────────────▼──────────────────────────────────────┐
│                       GAIT EVENT DETECTION                          │
│   Heel-strike & toe-off │ Stance/swing segmentation │ Cycle norm.   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ segmented cycles
┌──────────────────────────────▼──────────────────────────────────────┐
│                    BIOMECHANICAL ANALYSIS ENGINE                    │
│  Spatiotemporal │ Kinematics │ Rearfoot angle │ Foot progression    │
│  Foot-strike classifier │ Arch index │ Symmetry indices             │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ parameter vector + classifications
┌──────────────────────────────▼──────────────────────────────────────┐
│                    PATIENT PROFILE GENERATOR                        │
│   JSON schema │ Confidence scores │ Footwear-relevant recommendations│
└──────────────────────────────┬──────────────────────────────────────┘
                               │ profile.json
┌──────────────────────────────▼──────────────────────────────────────┐
│         DOWNSTREAM: SHOE DESIGN MODULE (out of scope here)          │
└─────────────────────────────────────────────────────────────────────┘
```

> Visual flow, sequence, and state diagrams are in **[DATA_FLOW.md](./DATA_FLOW.md)**.

### Design principles
1. **Single contract out.** The only artifact other systems depend on is `profile.json`. Everything internal is free to change.
2. **Stage isolation.** Each stage is a pure-ish function of its input + config + model versions. This enables unit testing and reproducibility.
3. **Confidence everywhere.** Low-confidence keypoints and cycles are dropped, not silently trusted.
4. **Config over code.** Thresholds and recommendation rules live in editable config (YAML), not in source.
5. **Fail loudly.** If too little clean data survives, the pipeline refuses to fabricate a profile and asks for a re-record.

---

## 2. Capture layer (hardware)

### 2.1 Camera configuration
A three-view setup gives full clinical coverage while staying affordable.

| View | Purpose | Position |
|------|---------|----------|
| **Anterior (coronal/front)** | Full-body bilateral keypoints, hip drop, base of support, frontal-plane motion | Front of walkway, lens ≈ knee height, 3–4 m away |
| **Sagittal (lateral)** | Stride length, foot-strike pattern, knee/hip flexion, swing phase | Side of walkway, lens ≈ knee height, 3–4 m away |
| **Posterior (dorsal/back)** | Rearfoot/calcaneal eversion → **pronation/supination**, hip asymmetry, pelvis rotation | Behind walkway, lens ≈ mid-calf height, 3–4 m back |

**Required:** All three views must be captured simultaneously: **anterior, sagittal, and posterior**. Each video is uploaded independently and synced by timestamp during ingestion.

### 2.2 Camera specs (minimum)
- **Resolution:** 1080p (1920×1080).
- **Frame rate:** 60 fps minimum; **120 fps strongly recommended** for accurate heel-strike timing; 240 fps if running gait is ever added.
- **Global shutter** preferred — rolling shutter introduces motion artifacts in the posterior view.
- Hardware-synchronized trigger, or software-sync (PTP/NTP) if cost-constrained (accept ~10 ms drift).

### 2.3 Walkway
- **Length:** ≥ 6 m so the subject reaches steady-state walking (acceleration + 3–4 cycles + deceleration).
- **Width:** ~1 m, plain matte surface (avoid reflections that confuse background subtraction).
- **Lighting:** diffuse, ≥ 500 lux, no harsh shadows on the feet.

### 2.4 Calibration
- Checkerboard or ChArUco board for **intrinsic** calibration (per camera, one-time).
- Multi-view **extrinsic** calibration via a shared wand or board visible in two views.
- A **scale reference** (known-length object on the walkway) for absolute distance recovery.

### 2.5 Optional sensors (v2 / validation)
- **Pressure mat** (Tekscan / RSScan) — gold standard for plantar pressure & timing validation.
- **IMU on shank** — to validate rearfoot-angle calculation.

---

## 3. Software pipeline — component by component

### 3.1 Ingestion & preprocessing
- Decode streams, demux, timestamp-align across cameras.
- Lens undistortion using stored intrinsics.
- **Background subtraction** (MOG2, or a learned segmenter like SAM2 for robustness) to isolate the subject.
- **Person tracking** (ByteTrack / StrongSORT) to lock onto the patient if multiple people are visible.
- Crop to a centered ROI to reduce downstream compute.

### 3.2 Pose & foot-keypoint estimation
Two-tier strategy:

**Tier A — whole-body 2D pose**
- Models: **MediaPipe Pose** (fast, MVP), **MMPose RTMPose** (better accuracy), or **YOLOv8-Pose**.
- Provides 17–33 keypoints including ankle, knee, hip, shoulder.
- Per-keypoint confidence threshold; reject frames where critical points fall below threshold and interpolate later.

**Tier B — dedicated foot keypoint detector (custom)**
Whole-body models give only 1–3 foot points. For rearfoot angle and foot-strike classification we need:
- Calcaneus (rear of heel)
- Lateral & medial malleoli (the two ankle bones)
- 1st and 5th metatarsal heads (MTP joints)
- Hallux tip (big toe)
- Mid-Achilles point

→ **Fine-tune a model** (HRNet, ViTPose, or RTMPose) on a custom dataset of ~2–5k annotated foot images covering Indian foot morphology, skin tones, and lighting. This is a key prototype investment.

**3D reconstruction**
- Multi-camera: triangulate corresponding 2D keypoints into 3D world coordinates.
- Monocular only: learned 2D→3D lifter (VideoPose3D, MotionBERT); accept ~3–5 cm error.

**Smoothing**
- 1-Euro filter or Savitzky–Golay on each keypoint trajectory before angle computation.
- **Do not** heavily filter the heel-strike frame — it is an event-detection signal.

### 3.3 Gait event detection
The foundation of every downstream parameter.

- **Heel-strike (HS):** local minimum of heel-marker vertical position + forward-velocity zero-crossing of the heel; cross-check with sagittal foot angle (foot rotates flat after HS).
- **Toe-off (TO):** local minimum of toe-marker vertical velocity transitioning positive, often coinciding with a rapid hip-flexion increase.
- **Pipeline:** bandpass-filter the relevant keypoint trajectory, then peak-detect; back up with a small 1D-CNN trained on labeled events if thresholding is unreliable.

Segment each cycle into:
- **Stance** (HS→TO, ~60% of cycle)
- **Swing** (TO→next HS, ~40%)
- Sub-phases: initial contact, loading response, mid-stance, terminal stance, pre-swing, initial/mid/terminal swing.

### 3.4 Biomechanical analysis engine

**Spatiotemporal** (per cycle, then mean ± SD): cadence, walking speed, stride length, step length (L & R), step width, stance/swing time (s and %), double-support time, foot progression angle.

**Kinematics** (joint angles per frame across the cycle): ankle dorsi/plantarflexion, knee flexion/extension, hip flexion/extension and adduction/abduction, pelvic tilt and pelvic drop, trunk lean.

**Foot-strike classifier** (sagittal, at HS) — foot strike angle (FSA) = plantar foot angle vs. ground:
- Rearfoot strike if FSA > +5°
- Midfoot strike if −5° ≤ FSA ≤ +5°
- Forefoot strike if FSA < −5°

**Pronation/supination** (posterior, during stance) — *the headline metric*:
- Three points: mid-Achilles, mid-calf (mid-shank), mid-heel (calcaneus).
- **Rearfoot angle** = angle of mid-calf→mid-Achilles vs. mid-Achilles→mid-calcaneus, frontal plane.
- Track across stance; key instants: heel-strike, **mid-stance (most diagnostic — peak eversion)**, toe-off.

| Peak rearfoot eversion at mid-stance | Classification |
|---|---|
| > +8° (heel rolls inward) | **Overpronation** |
| +4° to +8° | Mild pronation |
| 0° to +4° | **Neutral** |
| −4° to 0° | Mild supination |
| < −4° (heel rolls outward) | **Oversupination** |

Also derive total frontal-plane excursion during stance (mobility) and time-to-peak eversion (early peak = poor shock absorption).

**Arch type** — medial sagittal view: fit a curve along the medial foot (heel→1st MTP), compute **arch height index** = navicular tuberosity height ÷ truncated foot length; optionally complement with a wet-footprint photo (arch index = midfoot width / forefoot width). Classify: high (pes cavus) / normal / low (pes planus).

**Symmetry indices** — for each parameter X with L and R values:

```
Symmetry Index (%) = |X_L − X_R| / (0.5 · (X_L + X_R)) · 100
```

Flag asymmetry > 10% (asymmetric loading drives custom shoe lateralization).

### 3.5 Patient profile generator
Aggregates everything into a structured JSON including a **rule-based** `health_assessment` block with patient-facing findings and personalized improvement plans. Full schema and example in **[API_AND_SCHEMA.md](./API_AND_SCHEMA.md)**.

Assessment rules live in an **editable YAML file** rather than hardcoded — the clinician tunes them as more patients are seen. Examples:
- Overpronation + low arch → defect flag with exercises (short foot, glute bridges).
- Oversupination + high arch → lateral balance exercises, defect notification.
- Forefoot striker → heel-walking drills, phase-specific guidance.
- High step asymmetry → mirror walk exercises, human review flag.

---

## 4. Recommended tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Ecosystem |
| Pose estimation | MediaPipe (MVP), RTMPose / HRNet (custom foot model) | Accuracy vs. speed |
| 3D lifting | MotionBERT or VideoPose3D | If using monocular |
| CV utilities | OpenCV, scikit-image | Calibration, undistortion |
| Signal processing | SciPy, NumPy | Filtering, event detection |
| Deep learning | PyTorch + MMPose / MMCV | Fine-tuning foot model |
| Backend API | FastAPI | Light, async |
| Storage | PostgreSQL (metadata), S3-compatible (videos), Parquet (time-series) | Mixed workload |
| Job queue | Celery + Redis | Async video processing |
| Frontend (clinician) | React + Recharts / D3 | Gait curves, side-by-side cycle plots |
| Visualization (playback) | Three.js or Plotly | 3D skeleton overlay |
| Containerization | Docker, Compose | Reproducibility |
| Orchestration (later) | Kubernetes | When you scale |

---

## 5. Deployment view (prototype)

```
        ┌──────────────┐     enqueue      ┌─────────────┐
 React  │  FastAPI     │ ───────────────► │  Redis      │
 UI ───►│  API server  │                  │  (broker)   │
        └──────┬───────┘                  └──────┬──────┘
               │ metadata                        │ tasks
        ┌──────▼───────┐                  ┌──────▼───────────┐
        │ PostgreSQL   │                  │ Celery worker(s) │
        │ (profiles,   │                  │ GPU: pose, 3D,   │
        │  sessions)   │                  │ analysis engine  │
        └──────────────┘                  └──────┬───────────┘
        ┌──────────────┐   videos/parquet        │
        │ S3-compatible│ ◄───────────────────────┘
        │ object store │
        └──────────────┘
```

- For the prototype, all of this can run on a **single workstation** via Docker Compose.
- The Celery worker holds the GPU-heavy stages; the API stays light and async.
- Scale to Kubernetes only when throughput demands it.

---

## 6. Validation, calibration & QA (summary)
See **[VALIDATION_QA.md](./VALIDATION_QA.md)** for the full plan. Headlines:
- Validate against a pressure mat (timing, foot strike) and a clinician's manual rearfoot-angle measurement; target **ICC > 0.85**.
- Repeatability: re-scan within 30 min; **rearfoot-angle SD < 2°**, **stance-time SD < 5%**.
- Confidence gating: drop low-confidence cycles; if **< 4 cycles per foot** survive, request re-record.
- Quarterly review/re-training of the foot-keypoint model as annotated data accumulates.

---

## 7. Known limitations & risks
- **Clothing occlusion** — long trousers kill rearfoot-angle accuracy; protocol mandates ankle visibility.
- **Skin-tone bias** — off-the-shelf pose models underperform on darker skin tones; the custom dataset must be intentionally diverse.
- **Treadmill vs. overground** — gait differs slightly; if adopting a plantar-view treadmill, validate against overground for the same subject.
- **Single-pass cycles** — fewer cycles lower reliability; protocol insists on multiple passes.
- **Pathological gait** — neurological abnormalities need human review of the rule-based recommendation logic.
- **Lighting variability** — keep the capture room controlled; clinic/mobile use needs a separate ruggedness pass.
- **Hardcoded thresholds** — initial YAML thresholds are based on clinical heuristics; Phase 3 agents replace them with data-driven values tuned to the actual population.

---

## 8. AI agents layer (Phase 2+)

Starting in Phase 2, **optional AI agents** progressively replace hardcoded decision points with data-driven models. The pipeline is designed so agents can be added without breaking existing behavior.

### 8.1 Core design invariant

An agent is always an **optional override** of a static baseline. If an agent is disabled, missing, or throws an exception, the pipeline falls back to the YAML-driven decision transparently. The pipeline never hard-depends on an agent.

```python
# Pattern used at every agent integration point
baseline = _static_classify(params, config.thresholds)
if config.agents.enabled and config.agents.threshold_tuner.enabled:
    try:
        agent_result = threshold_agent.predict(params)
        if agent_result.confidence >= config.agents.threshold_tuner.confidence_threshold:
            return agent_result.classification   # agent wins
    except Exception:
        pass                                      # silent fallback
return baseline                                   # static baseline always works
```

### 8.2 Integration points

| Pipeline stage | Agent | Replaces | Phase |
|---|---|---|---|
| Profile / gating | Quality Assessment Agent | Binary `< 4 cycles → reject` | 2 |
| Analysis / pronation + foot-strike | Threshold Tuning Agent | Hardcoded `thresholds.yaml` cutoffs | 3 |
| Profile / recommend | Recommendation Agent | Static `rules.yaml` mappings | 3 |
| Profile / builder | Anomaly Detector | Rule-based `pathological_gait` flag | 3 |
| Pose | Model Selector Agent | Static `pipeline.yaml: model=mediapipe` | 2 |

### 8.3 Agent directory

```
src/gait/agents/
├── base.py          # GaitAgent ABC — predict(), get_confidence(), get_reasoning()
├── quality.py       # QualityAssessmentAgent (Phase 2)
├── threshold.py     # ThresholdTuningAgent (Phase 3)
├── recommend.py     # RecommendationAgent (Phase 3)
└── anomaly.py       # AnomalyDetector (Phase 3)

configs/pipeline.yaml → agents: section (all disabled for MVP)
models/agents/       → versioned model weights (gitignored; pulled from artifact store)
```

### 8.4 Agent config (in `configs/pipeline.yaml`)

```yaml
agents:
  enabled: false                       # global kill-switch; false for MVP
  quality_assessment:
    enabled: false                     # Phase 2+
    model_path: models/agents/quality_v1.pth
    confidence_threshold: 0.7
  threshold_tuner:
    enabled: false                     # Phase 3+
    model_path: models/agents/thresholds_v1.pth
    confidence_threshold: 0.8
  recommendation:
    enabled: false                     # Phase 3+
    model_path: models/agents/recommendations_v1.pth
    confidence_threshold: 0.75
  anomaly_detector:
    enabled: false                     # Phase 3+
    model_path: models/agents/anomaly_v1.pth
    confidence_threshold: 0.8
```

### 8.5 Governance

- Each agent ships with a `MODEL_CARD.md` (training data, known limitations, fairness notes).
- A new agent model may only be deployed if its accuracy on a held-out validation set **≥ static baseline**.
- Fairness check: accuracy must not systematically drop across demographic subgroups.
- Rollback = edit `pipeline.yaml` model version; no code change needed.
- Every agent decision is audit-logged (input, output, confidence, was_overridden).

> Full roadmap: **[AI_AGENTS_INTEGRATION.md](../AI_AGENTS_INTEGRATION.md)**

