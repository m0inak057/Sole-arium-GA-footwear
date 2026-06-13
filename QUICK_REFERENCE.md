# Quick Reference Guide

Fast lookup for common commands and project info.

---

## Setup (Choose One)

### Local Development
```bash
python3.11 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install
```

### Docker (Full Stack)
```bash
make docker-up
# Services at: http://localhost:8000 (API), http://localhost:5555 (Flower)
```

---

## Development Commands

| Command | Purpose |
|---------|---------|
| `make format` | Auto-format code (black + ruff) |
| `make lint` | Check code style |
| `make type-check` | Run type checker (mypy) |
| `make test` | Run all tests |
| `make test-unit` | Unit tests only |
| `make test-e2e` | End-to-end tests |
| `make coverage` | Generate HTML coverage report |
| `make ci` | Full CI pipeline (lint → type → test) |
| `make clean` | Remove build artifacts |

---

## Running Services

| Command | Purpose |
|---------|---------|
| `make run-api` | Start FastAPI server (localhost:8000) |
| `make run-worker` | Start Celery worker |
| `make docker-up` | Start all services |
| `make docker-down` | Stop all services |
| `make docker-logs` | View service logs |

---

## Service Ports

| Service | Port | URL |
|---------|------|-----|
| FastAPI | 8000 | http://localhost:8000 |
| Docs | 8000 | http://localhost:8000/docs |
| PostgreSQL | 5432 | localhost:5432 |
| Redis | 6379 | localhost:6379 |
| MinIO | 9000 | http://localhost:9000 |
| MinIO Console | 9001 | http://localhost:9001 |
| Flower (Celery) | 5555 | http://localhost:5555 |

---

## Database Credentials (Development)

```
PostgreSQL:
  User: gait_user
  Password: gait_password
  Database: gait_analysis
  Host: localhost:5432

MinIO S3:
  Access Key: minioadmin
  Secret Key: minioadmin
  Endpoint: http://localhost:9000
  Bucket: gait-analysis

Redis:
  URL: redis://localhost:6379/0
  Password: redis_password
```

---

## Key Files & Directories

| Path | Purpose |
|------|---------|
| `src/gait/` | Main package source code |
| `configs/` | YAML configuration files |
| `tests/` | Unit, integration, e2e tests |
| `docs/` | Design documentation (10 documents) |
| `scripts/` | Utility scripts (database init, etc.) |
| `pyproject.toml` | Dependency management |
| `.env.example` | Environment template |
| `Makefile` | Development commands |
| `docker-compose.yml` | Local dev stack |

---

## Common Patterns

### Run a Specific Test
```bash
pytest tests/unit/test_geometry.py::TestComputeRearfootAngle::test_neutral_angle -v
```

### Run Tests Matching Pattern
```bash
pytest -k "test_heel" -v  # All tests with "heel" in name
```

### Check Type Errors
```bash
mypy src/gait --show-error-codes
```

### Fix All Code Issues
```bash
make format  # Fixes formatting + auto-fixable linting issues
```

### Test Coverage Report
```bash
make coverage
# Open: htmlcov/index.html
```

---

## Git Workflow

### Create Feature Branch
```bash
git checkout -b feature/your-feature-name
```

### Commit with Convention
```bash
git commit -m "feat(module): description"
# Types: feat, fix, docs, test, refactor, perf, chore
# Examples:
#   feat(pose): add 1-euro filter
#   fix(events): correct heel-strike detection
#   test(analysis): add unit tests
```

### Before Pushing
```bash
make format lint type-check test
```

### Push & Create PR
```bash
git push origin feature/your-feature-name
# GitHub → Create Pull Request
```

---

## Environment Variables

### Key Variables

```bash
# Application
APP_ENV=development        # development or production
APP_PORT=8000

# Database
DATABASE_URL=postgresql://gait_user:gait_password@localhost:5432/gait_analysis

# Redis
REDIS_URL=redis://localhost:6379/0

# S3/MinIO
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_WORKER_CONCURRENCY=4
```

### Full List
See `.env.example` for complete list with documentation.

---

## Documentation Quick Links

| Document | Purpose |
|----------|---------|
| [README.md](./README.md) | Project overview & setup |
| [DEVELOPMENT.md](./DEVELOPMENT.md) | Dev workflow guide |
| **Phase 0 (Complete):** | |
| [TASK1_COMPLETION_CHECKLIST.md](./TASK1_COMPLETION_CHECKLIST.md) | Repository scaffolding verification |
| [TASK2_COMPLETION_SUMMARY.md](./TASK2_COMPLETION_SUMMARY.md) | Schema & config loaders summary |
| [PHASE0_SUMMARY.md](./PHASE0_SUMMARY.md) | Phase 0 executive summary |
| **Phase 1 (In Progress):** | |
| [TASK3_INGESTION_PLAN.md](./TASK3_INGESTION_PLAN.md) | Task 3 architecture & implementation plan |
| [PHASE1_IMPLEMENTATION_STATUS.md](./PHASE1_IMPLEMENTATION_STATUS.md) | Phase 1 progress tracker |
| [AI_AGENTS_INTEGRATION.md](./AI_AGENTS_INTEGRATION.md) | AI agents roadmap (Phase 2+) |
| **Design Documents:** | |
| [docs/00_START_HERE.md](./docs/00_START_HERE.md) | Design doc navigation |
| [docs/IMPLEMENTATION_PLAYBOOK.md](./docs/IMPLEMENTATION_PLAYBOOK.md) | Build roadmap |
| [docs/API_AND_SCHEMA.md](./docs/API_AND_SCHEMA.md) | API specification |
| [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) | System design |

---

## Task 3: Ingestion Module Structure (In Progress)

**The 6-step video preprocessing pipeline:**
```
VideoFileSource → decode_video_stream()
    ↓
align_frames()  [multi-camera sync]
    ↓
CameraCalibrator.apply()  [undistortion]
    ↓
BackgroundSubtractor.apply()  [segment subject]
    ↓
PersonTracker.update()  [track person]
    ↓
crop_roi()  [final ROI]
    ↓
IngestionResult (frames → pose stage)
```

**Key modules:**
- `src/gait/common/types.py` — DTOs + typed exceptions
- `src/gait/common/geometry.py` — Pure 2D math (IoU, angle, etc.)
- `src/gait/common/logging_utils.py` — JSON logging
- `src/gait/ingestion/{decode,sync,calibrate,segment_bg,track,roi}.py` — Sub-steps
- `src/gait/ingestion/preprocessor.py` — Orchestrator

**Test fixtures:**
- `tests/unit/test_geometry.py` — 30+ pure math tests
- `tests/unit/test_ingestion_*.py` — 60+ ingestion tests
- `tests/integration/test_ingestion_pipeline.py` — End-to-end with synthetic video

---

## AI Agents (Future Integration)

**Now:** All parameters in YAML (ready for agents)  
**Phase 2+:** Agents learn optimal values from production data

**Agent types coming later:**
- Quality assessment (replaces binary gates)
- Threshold tuner (learns foot-strike/pronation cutoffs)
- Recommendation engine (learns shoe designs from outcomes)
- Anomaly detector (learns pathological patterns)

**For now:** Agents are **disabled** in `pipeline.yaml`. See [AI_AGENTS_INTEGRATION.md](./AI_AGENTS_INTEGRATION.md) for roadmap.

---

## Code Style Quick Reference

### Type Hints
```python
def process_session(session_dir: Path) -> GaitPatientProfile:
    """Process a gait analysis session."""
    ...
```

### Unit Names
```python
stride_length_m = 1.5           # Always include units
rearfoot_angle_deg = 5.2
processing_time_sec = 0.45
```

### Left/Right Naming
```python
parameters = {
    "L": {"cadence": 120, "angle": 5.2},
    "R": {"cadence": 118, "angle": 5.5}
}
# NOT: left/right, Left/Right, LR, or mixed
```

### Config Loading
```python
# ✓ Good
from src.gait.pipeline.config import load_thresholds
thresholds = load_thresholds("configs/thresholds.yaml")
confidence_gate = thresholds["min_keypoint_confidence"]

# ✗ Bad
confidence_gate = 0.6  # Hardcoded
```

---

## Troubleshooting Quick Fixes

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'gait'` | `pip install -e .` |
| `pytest: command not found` | `pip install -e ".[dev]"` |
| Docker won't start | `make docker-build && make docker-up` |
| Type check fails | `mypy src/gait --show-error-codes` |
| Pre-commit blocks commit | `pre-commit run --all-files` then fix |
| Test failures locally | `make docker-up` then `docker-compose exec api make test` |

---

## Important Principles (Never Break)

1. **One source of truth:** `src/gait/profile/schema.py`
2. **No magic numbers:** All thresholds in `configs/thresholds.yaml`
3. **Orthotist-editable rules:** All logic in `configs/rules.yaml`
4. **Units in names:** `stride_length_m`, `angle_deg`, `time_sec`
5. **L/R always:** Use `{"L": ..., "R": ...}` consistently
6. **Fail loudly:** Never fabricate data (< 4 cycles = RERECORD)
7. **Privacy:** Faces blurred, data encrypted, access audited
8. **Schema versioning:** Breaking changes = new version (v1 → v2)

---

## Contact & Support

- **Issues:** GitHub Issues
- **Email:** moinak.mondal057@gmail.com
- **Docs:** See `docs/` folder
- **Contributing:** See [DEVELOPMENT.md](./DEVELOPMENT.md#contributing)

---

**Last Updated:** 2026-06-10  
**Phase:** 0 (Repository Scaffolding — Complete)
