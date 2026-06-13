# Project Structure
## Gait Analysis Module — Repository Layout

| Field | Value |
|---|---|
| Document | Project Structure |
| Version | 1.0 |
| Related | [ARCHITECTURE.md](./ARCHITECTURE.md), [ENGINEERING_RULES.md](./ENGINEERING_RULES.md) |

This document defines where code lives and what each module is responsible for. The layout mirrors the pipeline stages in [ARCHITECTURE.md](./ARCHITECTURE.md) so that a stage in the architecture maps to exactly one package in the repo.

---

## 1. Top-level layout

```
gait-analysis/
├── README.md
├── pyproject.toml                # deps, build config (poetry/uv/pip-tools)
├── docker-compose.yml            # full local stack (api, worker, redis, postgres, minio)
├── Dockerfile                    # base image for api + worker
├── .env.example                  # env var template (never commit real .env)
├── Makefile                      # common dev commands (lint, test, run, format)
│
├── docs/                         # THIS documentation suite
│
├── configs/                      # all tunable configuration (no code)
│   ├── cameras/                  # intrinsics/extrinsics per camera
│   │   ├── sagittal.yaml
│   │   ├── posterior.yaml
│   │   └── plantar.yaml
│   ├── thresholds.yaml           # FSA, rearfoot-angle, symmetry, confidence thresholds
│   ├── rules.yaml                # shoe-design recommendation rules (orthotist-editable)
│   └── pipeline.yaml             # which models, fps assumptions, smoothing params
│
├── src/
│   └── gait/
│       ├── __init__.py
│       ├── capture/              # Stage 0: hardware capture + sync (or import of recorded files)
│       │   ├── recorder.py
│       │   ├── sync.py
│       │   └── schemas.py
│       ├── ingestion/            # Stage 1: ingestion & preprocessing
│       │   ├── decode.py
│       │   ├── calibrate.py      # undistort, intrinsics/extrinsics
│       │   ├── segment_bg.py     # background subtraction (MOG2 / SAM2)
│       │   ├── track.py          # person tracking (ByteTrack / StrongSORT)
│       │   └── roi.py
│       ├── pose/                 # Stage 2: pose & foot keypoints
│       │   ├── body_2d.py        # Tier A: MediaPipe / RTMPose / YOLOv8-Pose wrapper
│       │   ├── foot_kp.py        # Tier B: custom foot keypoint detector
│       │   ├── lift_3d.py        # monocular 2D→3D (VideoPose3D / MotionBERT)
│       │   ├── triangulate.py    # multi-view triangulation
│       │   └── smooth.py         # 1-Euro / Savitzky–Golay
│       ├── events/               # Stage 3: gait event detection
│       │   ├── detect.py         # HS / TO detection
│       │   ├── cnn_events.py     # optional 1D-CNN backup
│       │   └── segment_cycles.py # stance/swing + sub-phases + cycle normalization
│       ├── analysis/             # Stage 4: biomechanical analysis engine
│       │   ├── spatiotemporal.py
│       │   ├── kinematics.py
│       │   ├── foot_strike.py    # FSA classifier
│       │   ├── pronation.py      # rearfoot angle + classification (headline)
│       │   ├── arch.py           # arch height index / wet-footprint
│       │   └── symmetry.py
│       ├── profile/              # Stage 5: patient profile generator
│       │   ├── builder.py        # assembles the JSON
│       │   ├── recommend.py      # applies rules.yaml → recommendation block
│       │   ├── schema.py         # pydantic models = source of truth for the schema
│       │   └── confidence.py     # confidence scoring + gating
│       ├── pipeline/             # orchestration of the full pipeline
│       │   ├── run.py            # entrypoint: session_dir → profile.json
│       │   └── gating.py         # re-record / drop-cycle logic
│       ├── agents/               # AI agent layer (Phase 2+; all disabled in MVP)
│       │   ├── base.py           # GaitAgent ABC — predict(), get_confidence(), get_reasoning()
│       │   ├── quality.py        # QualityAssessmentAgent (Phase 2)
│       │   ├── threshold.py      # ThresholdTuningAgent (Phase 3)
│       │   ├── recommend.py      # RecommendationAgent (Phase 3)
│       │   └── anomaly.py        # AnomalyDetector (Phase 3)
│       ├── common/               # shared utilities
│       │   ├── geometry.py       # angle math, vectors, planes
│       │   ├── signal.py         # filters, peak detection helpers
│       │   ├── io.py             # parquet / json / video readers-writers
│       │   ├── logging.py
│       │   └── types.py          # shared dataclasses / type aliases
│       └── api/                  # FastAPI app
│           ├── main.py
│           ├── routes/
│           │   ├── sessions.py
│           │   ├── profiles.py
│           │   └── health.py
│           ├── tasks.py          # Celery task definitions
│           └── deps.py           # auth, db sessions, RBAC
│
├── models/                       # model weights & cards (tracked via LFS / external store)
│   ├── foot_keypoint/
│   │   ├── weights/              # (gitignored; pulled from artifact store)
│   │   └── MODEL_CARD.md
│   ├── event_cnn/
│   │   └── MODEL_CARD.md
│   └── agents/                   # AI agent weights (Phase 2+; gitignored; pulled from artifact store)
│       ├── quality_v1.pth        # QualityAssessmentAgent weights
│       ├── thresholds_v1.pth     # ThresholdTuningAgent weights
│       ├── recommendations_v1.pth # RecommendationAgent weights
│       ├── anomaly_v1.pth        # AnomalyDetector weights
│       └── *.MODEL_CARD.md       # one model card per agent
│
├── data_pipeline/                # dataset & annotation tooling for the custom foot model
│   ├── annotation/               # labeling configs, guidelines
│   ├── ingest.py
│   ├── augment.py
│   └── README.md                 # dataset diversity requirements (skin tone, morphology)
│
├── frontend/                     # clinician UI (React)
│   ├── package.json
│   └── src/
│       ├── components/           # gait curves, side-by-side cycle plots
│       ├── pages/
│       ├── viewer/               # 3D skeleton overlay (Three.js / Plotly)
│       └── api/                  # typed client for the FastAPI endpoints
│
├── migrations/                   # Alembic DB migrations
│
├── tests/
│   ├── unit/                     # per-module: geometry, angle math, classifiers
│   ├── integration/              # stage-to-stage with fixture data
│   ├── e2e/                      # session_dir → profile.json on a golden sample
│   ├── fixtures/                 # small recorded clips, synthetic keypoint series
│   └── schema/                   # validate emitted profiles against the JSON schema
│
├── scripts/                      # one-off ops: calibration capture, retraining triggers
│
└── infra/                        # IaC, deployment manifests (Compose now, K8s later)
    ├── compose/
    └── k8s/
```

---

## 2. Module responsibilities

| Package | Owns | Input → Output |
|---|---|---|
| `capture/` | Recording / importing synchronized video | hardware/files → raw streams + timestamps |
| `ingestion/` | Cleaning frames | raw streams → calibrated, ROI-cropped, subject-isolated frames |
| `pose/` | Landmarks | clean frames → smoothed 2D/3D keypoint time-series |
| `events/` | Temporal structure | keypoint series → segmented gait cycles |
| `analysis/` | Biomechanics | cycles → parameters + classifications |
| `profile/` | Output contract | parameters → schema-valid `profile.json` |
| `pipeline/` | Orchestration | session directory → final profile (or re-record signal) |
| `api/` | Service surface | HTTP/queue → triggers pipeline, serves results |
| `common/` | Shared math & IO | used by all stages |
| `agents/` | Optional AI overrides (Phase 2+) | gait params → learned classification/recommendation (with fallback to static baseline) |

---

## 3. Key invariants

1. **`profile/schema.py` is the single source of truth** for the patient-profile schema. The JSON Schema in [API_AND_SCHEMA.md](./API_AND_SCHEMA.md) is generated from / kept in sync with it.
2. **No thresholds in code.** Anything tunable (FSA cutoffs, rearfoot-angle bands, symmetry %, confidence gates) lives in `configs/thresholds.yaml`.
3. **No recommendation logic hardcoded.** It lives in `configs/rules.yaml` and is applied by `profile/recommend.py`.
4. **Camera calibration is data, not code.** Intrinsics/extrinsics live under `configs/cameras/`.
5. **Stages are independently testable.** Each `analysis/` and `pose/` function should run on a fixture without the full pipeline.
6. **Models are external artifacts.** Weights are never committed to git; they are pulled from an artifact store and pinned by version.
7. **Agents are optional overrides, not hard dependencies.** Every decision point in `analysis/` and `profile/` computes a static baseline first. An agent result is used only when the agent is enabled AND its confidence exceeds the configured threshold; otherwise the pipeline falls back to the static result transparently.
8. **Agent config lives in `pipeline.yaml`.** The `agents:` section is the single place to enable/disable agents and pin model versions. All agents start as `enabled: false`.

---

## 4. Naming & conventions (pointer)
See [ENGINEERING_RULES.md](./ENGINEERING_RULES.md) for module, function, file, and branch naming, plus the commit and PR conventions that keep this structure consistent.
