# Gait Analysis Module

A comprehensive gait analysis system that transforms synchronized multi-view video into detailed patient biomechanical profiles for orthopedic footwear design.

**Status:** Phase 0 — Repository Scaffolding  
**Version:** 0.1.0  
**Last Updated:** 2026-06-10

---

## Overview

This system captures synchronized video from multiple camera angles, applies pose estimation and computer vision analysis, detects gait events (heel-strike, toe-off), and computes biomechanical parameters to produce a **`profile.json`** containing:

- **Spatiotemporal parameters** — cadence, stride/step length, walking speed, stance/swing timing
- **Foot-strike classification** — rearfoot, midfoot, or forefoot striking
- **Pronation analysis** — rearfoot eversion angle (neutral, mild, over-pronation, etc.)
- **Arch assessment** — arch height index classification
- **Symmetry flags** — left/right asymmetries > 10%
- **Shoe design recommendations** — YAML-driven orthotist guidance

**Processing pipeline:** Video → Ingestion → Pose → Events → Analysis → Profile (end-to-end in ~60 seconds)

---

## Quick Start

### ⚡ Automatic Setup (One Command)

**Linux/macOS:**
```bash
git clone <repo-url>
cd Orthopedic_Footwear_GA
./startup.sh
```

**Windows:**
```cmd
git clone <repo-url>
cd Orthopedic_Footwear_GA
startup.bat
```

This script automatically:
- ✓ Checks prerequisites (Docker, Node.js)
- ✓ Creates `.env` file
- ✓ Builds Docker images
- ✓ Starts all services
- ✓ Installs frontend dependencies
- ✓ Starts the frontend dev server

Open **http://localhost:5173** when done!

### ⚙️ Manual Setup (3 steps)

**Alternative if you prefer manual control:**

```bash
git clone <repo-url>
cd Orthopedic_Footwear_GA
cp .env.example .env
docker compose build
docker compose up -d
```

Then in another terminal:
```bash
cd frontend && npm install && npm run dev
```

👉 **For detailed instructions and troubleshooting, see [SETUP.md](./SETUP.md)**

### Prerequisites

- **Docker & Docker Compose:** [install Docker Desktop](https://www.docker.com/products/docker-desktop/)
- **Node.js 18+:** [install Node.js](https://nodejs.org/)
- **Git:** for cloning

### Services & Endpoints

Once running, services are accessible at:

| Service | URL | Status |
|---------|-----|--------|
| **Frontend** | http://localhost:5173 | React dev server |
| **API** | http://localhost:8000 | FastAPI + Swagger docs |
| **MinIO (S3)** | http://localhost:9001 | File storage UI |
| **Celery Flower** | http://localhost:5555 | Task monitoring |
| **PostgreSQL** | localhost:5444 | Database |
| **Redis** | localhost:6380 | Cache & broker |

### Alternative: Local Python Development (Advanced)

If you prefer not to use Docker:

```bash
git clone <repo-url>
cd Orthopedic_Footwear_GA

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Still need Docker for database, cache, storage
# Or set up PostgreSQL, Redis, MinIO separately

# Install pre-commit hooks
pre-commit install

# Run tests
pytest tests/
```

Services still need to be running (PostgreSQL, Redis, MinIO) — easiest via Docker:
```bash
docker compose up -d postgres redis minio
```

---

## Development Workflow

### Common Commands

```bash
# Formatting & Linting
make format          # Auto-format code (black + ruff)
make lint            # Check code style (ruff)
make type-check      # Type checking (mypy)

# Testing
make test            # Run all tests
make test-unit       # Unit tests only
make test-integration # Integration tests
make test-e2e        # End-to-end tests
make coverage        # Generate coverage report

# Running Services
make run-api         # Start FastAPI server (localhost:8000)
make run-worker      # Start Celery worker

# Docker
make docker-build    # Build images
make docker-up       # Start stack
make docker-down     # Stop stack
make docker-logs     # View logs

# CI/CD
make ci              # Run full CI pipeline (lint → type-check → test)
make pre-commit-run  # Run pre-commit on all files

# Cleanup
make clean           # Remove build artifacts and caches
```

### Project Structure

```
gait-analysis/
├── README.md
├── pyproject.toml               # Dependencies & build config
├── Makefile                     # Development commands
├── Dockerfile                   # Container image
├── docker-compose.yml           # Local dev stack
├── .env.example                 # Environment template
├── .pre-commit-config.yaml      # Code quality hooks
├── .github/
│   └── workflows/ci.yml         # GitHub Actions CI/CD
├── docs/                        # 10-document design suite
│   ├── 00_START_HERE.md
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── DATA_FLOW.md
│   ├── API_AND_SCHEMA.md
│   ├── IMPLEMENTATION_PLAYBOOK.md
│   └── ...
├── src/gait/
│   ├── __init__.py
│   ├── capture/                 # Hardware recording / import
│   ├── ingestion/               # Video preprocessing
│   │   ├── decode.py
│   │   ├── calibrate.py
│   │   ├── segment_bg.py
│   │   ├── track.py
│   │   └── roi.py
│   ├── pose/                    # Keypoint estimation
│   │   ├── body_2d.py           # MediaPipe wrapper
│   │   ├── foot_kp.py           # Foot-specific (Phase 2)
│   │   ├── lift_3d.py           # 2D→3D monocular (MVP)
│   │   └── smooth.py            # 1-Euro filter
│   ├── events/                  # Gait event detection
│   │   ├── detect.py            # HS/TO detection
│   │   └── segment_cycles.py    # Cycle segmentation
│   ├── analysis/                # Biomechanical computation
│   │   ├── spatiotemporal.py
│   │   ├── foot_strike.py
│   │   ├── pronation.py
│   │   ├── arch.py
│   │   └── symmetry.py
│   ├── profile/                 # Output generation
│   │   ├── schema.py            # Pydantic models (source of truth)
│   │   ├── builder.py           # Profile assembly
│   │   ├── recommend.py         # Rule-based recommendations
│   │   ├── confidence.py        # Gating & quality control
│   │   └── validator.py         # JSON schema validation
│   ├── pipeline/                # Orchestration
│   │   ├── run.py               # Main entry point
│   │   └── config.py            # Config loading
│   ├── common/                  # Shared utilities
│   │   ├── types.py             # Data models
│   │   ├── geometry.py          # Vector math
│   │   └── constants.py         # Global defaults
│   └── api/                     # FastAPI application
│       ├── main.py              # App factory
│       ├── routes/
│       │   ├── sessions.py
│       │   ├── profiles.py
│       │   └── health.py
│       ├── tasks.py             # Celery task definitions
│       ├── schemas.py           # Request/response models
│       └── middleware.py        # Auth, logging, CORS
├── configs/                     # Editable YAML configs
│   ├── cameras/
│   │   ├── anterior.yaml        # Intrinsics/extrinsics (post-calibration)
│   │   ├── sagittal.yaml
│   │   └── posterior.yaml
│   ├── thresholds.yaml          # ALL tunable parameters
│   ├── rules.yaml               # Shoe-design recommendations
│   └── pipeline.yaml            # Model choice, fps, smoothing
├── models/                      # Model weights (external, not in repo)
├── data_pipeline/               # Annotation & dataset tools
│   └── annotation/
├── migrations/                  # Alembic database migrations
├── tests/
│   ├── unit/                    # Isolated unit tests
│   ├── integration/             # Multi-component tests
│   ├── e2e/                     # Full pipeline tests
│   ├── fixtures/                # Test data & mocks
│   └── conftest.py              # Pytest configuration
├── scripts/
│   ├── init-db.sql              # PostgreSQL initialization
│   ├── calibrate_cameras.py     # Hardware calibration tool
│   └── generate_schema.py       # JSON schema export
├── infra/                       # Infrastructure as Code
│   ├── kubernetes/
│   └── terraform/
├── frontend/                    # MVP Streamlit viewer (Phase 1)
│   └── app.py
└── logs/                        # Runtime logs (gitignored)
```

---

## Configuration

All system parameters are **YAML-editable**, not hardcoded. This ensures flexibility for hardware integration and parameter tuning.

### Key Config Files

**`configs/pipeline.yaml`** — Processing parameters
```yaml
ingestion:
  fps: 120
  resolution: [1920, 1080]
  sync_tolerance_ms: 10

pose:
  model: mediapipe
  confidence_threshold: 0.5
  smoothing_window: 5

events:
  heel_strike_threshold: 0.3
  toe_off_threshold: 0.2
```

**`configs/thresholds.yaml`** — Clinical decision thresholds
```yaml
confidence_gates:
  min_cycles_per_foot: 4
  min_keypoint_confidence: 0.6
  drop_cycle_threshold: 0.5

pronation:
  overpronation_threshold: 8.0  # degrees
  neutral_range: [0.0, 4.0]
  oversupination_threshold: -4.0
```

**`configs/rules.yaml`** — Orthopedic recommendations (orthotist-editable)
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
```

**`configs/cameras/*.yaml`** — Camera calibration matrices (populated post-hardware setup)
```yaml
sagittal:
  intrinsics:
    K: [[fx, 0, cx], [0, fy, cy], [0, 0, 1]]
    D: [k1, k2, p1, p2]  # distortion coefficients
  extrinsics:
    R: [[...], [...], [...]]      # rotation matrix
    t: [tx, ty, tz]               # translation vector
```

---

## Environment Setup

Copy `.env.example` to `.env` and adjust for your environment:

```bash
cp .env.example .env
```

**Key variables:**
- `APP_ENV`: `development` or `production`
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `S3_*`: MinIO/S3 storage credentials
- `CELERY_*`: Task queue configuration
- Timeouts, feature flags, retention policies

---

## API Overview

### Core Endpoints (Phase 1 MVP)

```
POST /api/v1/sessions
  → Register a new patient session
  ← Returns session_id

POST /api/v1/sessions/{session_id}/uploads
  → Upload synchronized video files
  ← Stores video, returns file references

POST /api/v1/sessions/{session_id}/process
  → Enqueue pipeline processing
  ← Returns task_id (Celery task)

GET /api/v1/sessions/{session_id}/status
  → Check session status (created | uploaded | processing | complete | needs_rerecord | failed)

GET /api/v1/sessions/{session_id}/profile
  → Retrieve computed profile.json (if complete)

GET /api/v1/health
  → System health check
```

See [API_AND_SCHEMA.md](./docs/API_AND_SCHEMA.md) for complete specification.

---

## Key Principles (Never Break These)

1. **`src/gait/profile/schema.py` is the single source of truth** for patient-profile schema.
2. **All thresholds come from `configs/thresholds.yaml`** — no magic numbers in code.
3. **All recommendation logic lives in `configs/rules.yaml`** — orthotist-editable, not hardcoded.
4. **Every numeric field carries a unit in its name:** `stride_length_m`, `rearfoot_angle_deg`, `mass_kg`.
5. **Always use `{"L": ..., "R": ...}` for left/right data** — never mix `left`/`right` with `L`/`R`.
6. **Fail loudly on bad data:** if < 4 clean cycles/foot, refuse to emit a profile and request re-record.
7. **Confidence gates are respected:** low-confidence cycles are dropped, never silently trusted.
8. **Privacy non-negotiable:** faces are blurred post-pipeline, data is encrypted at rest, all access is audit-logged.
9. **Schema-breaking changes require a version bump** (`profile/v1` → `profile/v2`) and a migration note.

---

## Testing

### Unit Tests
```bash
make test-unit
```
Isolated tests for individual functions (geometry, filters, classifiers).

### Integration Tests
```bash
make test-integration
```
Multi-component tests (ingestion → pose → events, etc.) with mock data.

### End-to-End Tests
```bash
make test-e2e
```
Full pipeline: synthetic video → profile.json validation.

### Coverage
```bash
make coverage
open htmlcov/index.html
```

---

## CI/CD Pipeline

All commits trigger GitHub Actions:

1. **Lint** — Ruff + Black formatting check
2. **Type Check** — MyPy static analysis
3. **Tests** — Unit + Integration + E2E
4. **Security** — Bandit + Safety audit
5. **Build** — Package assembly
6. **Docker** — Image build (on main/develop)

See `.github/workflows/ci.yml` for details.

---

## Privacy & Compliance

✓ **DPDP 2023 compliant** — data pseudonymization, encryption, consent tracking  
✓ **Face blur** — automatic post-pipeline video masking  
✓ **Audit logging** — all profile reads logged with timestamp/user  
✓ **Data retention** — automatic purge beyond configured window  
✓ **Encryption at rest** — S3, PostgreSQL, Redis  
✓ **TLS in transit** — all API communication encrypted

See [PRIVACY_COMPLIANCE.md](./docs/PRIVACY_COMPLIANCE.md) for full details.

---

## Development Phases

- **Phase 0** (Current) — Repository scaffolding, calibration framework
- **Phase 1** — MVP pipeline: MediaPipe pose + biomechanical analysis (~6–8 weeks)
- **Phase 2** — Custom foot-keypoint model fine-tuning (~6 weeks)
- **Phase 3** — 3D multi-view + clinical validation study (~6–8 weeks)
- **Phase 4** — Productionization, Kubernetes, monitoring (ongoing)

See [IMPLEMENTATION_PLAYBOOK.md](./docs/IMPLEMENTATION_PLAYBOOK.md) for detailed roadmap.

---

## Documentation

All design docs are in `docs/`:

- **[00_START_HERE.md](./docs/00_START_HERE.md)** — Navigation guide
- **[PRD.md](./docs/PRD.md)** — Product requirements & use cases
- **[ARCHITECTURE.md](./docs/ARCHITECTURE.md)** — System design & data flow
- **[API_AND_SCHEMA.md](./docs/API_AND_SCHEMA.md)** — API spec + JSON schema
- **[IMPLEMENTATION_PLAYBOOK.md](./docs/IMPLEMENTATION_PLAYBOOK.md)** — Build roadmap
- **[PRIVACY_COMPLIANCE.md](./docs/PRIVACY_COMPLIANCE.md)** — Legal & security
- **[VALIDATION_QA.md](./docs/VALIDATION_QA.md)** — Test strategy & acceptance criteria

---

## Troubleshooting

### Docker services won't start
```bash
# Check Docker daemon
docker ps

# View specific service logs
docker-compose logs postgres
docker-compose logs redis

# Rebuild images
make docker-build

# Clean up & restart
docker-compose down -v
make docker-up
```

### Type checking fails
```bash
mypy src/gait --show-error-codes
```

### Tests fail locally but pass in CI
```bash
# Ensure test databases are accessible
make docker-up
make test
```

### Pre-commit hooks blocking commits
```bash
# Run hooks manually to debug
pre-commit run --all-files

# Fix issues, then try commit again
```

---

## Contributing

1. Create feature branch: `feature/<short-desc>`
2. Commit with Conventional Commits: `feat(analysis): add time-to-peak-eversion`
3. Push → PR
4. **All required checks must pass:**
   - ✓ Lint (Ruff + Black)
   - ✓ Type check (MyPy)
   - ✓ Tests (unit + integration + e2e)
   - ✓ Coverage (maintain ≥ 80%)
5. **Update docs** in same PR if behavior/schema changes
6. Reviewer checklist: no magic numbers, units in names, schema sync, tests, privacy checks

---

## License

MIT — See LICENSE file

---

## Support

- **Issues:** [GitHub Issues](https://github.com/sole-arium/gait-analysis/issues)
- **Email:** moinak.mondal057@gmail.com
- **Documentation:** See `docs/` folder

---

**Next Step:** Begin Phase 1 implementation. Start with [Task 2: Pipeline Schema & Stubs](./docs/IMPLEMENTATION_PLAYBOOK.md#2-phase-1--mvp-pipeline-6–8-weeks).
