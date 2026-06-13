# Development Guide

Comprehensive guide for setting up and working on the Gait Analysis Module.

---

## Table of Contents

1. [Initial Setup](#initial-setup)
2. [Development Workflow](#development-workflow)
3. [Testing Strategy](#testing-strategy)
4. [Code Quality](#code-quality)
5. [Debugging](#debugging)
6. [Documentation](#documentation)

---

## Initial Setup

### Option 1: Local Development (Without Docker)

**Requirements:**
- Python 3.11+
- FFmpeg (for video processing)
- Git

**Step 1: Clone & Virtual Environment**
```bash
git clone <repo-url>
cd gait-analysis
python3.11 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

**Step 2: Install Dependencies**
```bash
pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
```

**Step 3: Pre-commit Hooks**
```bash
pre-commit install
```

**Step 4: Environment Configuration**
```bash
cp .env.example .env
# Edit .env for local development
```

**Step 5: Verify Installation**
```bash
make lint type-check test
```

### Option 2: Docker Compose (Recommended)

**Requirements:**
- Docker
- Docker Compose
- Git

**Step 1: Clone Repository**
```bash
git clone <repo-url>
cd gait-analysis
```

**Step 2: Start Services**
```bash
make docker-up
```

**Step 3: Verify Services**
```bash
docker-compose ps
# All services should show "Up"
```

**Step 4: Access Services**
- **API:** http://localhost:8000
- **Flower (Celery monitoring):** http://localhost:5555
- **MinIO (S3):** http://localhost:9000

**Step 5: Run Tests (inside container)**
```bash
docker-compose exec api make test
```

---

## Development Workflow

### Creating a Feature Branch

```bash
git checkout -b feature/your-feature-name
# or bugfix/your-bug-fix
# or docs/your-doc-update
```

### Making Changes

1. **Edit code** in your IDE/editor
2. **Run linting** before committing:
   ```bash
   make format lint type-check
   ```

3. **Run tests** affected by changes:
   ```bash
   make test-unit     # For unit tests
   make test-integration  # For integration tests
   pytest tests/unit/test_specific.py -v  # For specific test file
   ```

4. **Commit with Conventional Commits**:
   ```bash
   git commit -m "feat(module): description of feature"
   # Examples:
   # feat(pose): add 1-euro filter for keypoint smoothing
   # fix(events): correct heel-strike detection threshold
   # docs(api): update endpoint documentation
   # test(analysis): add unit tests for rearfoot angle computation
   ```

5. **Push to remote**:
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Create Pull Request** on GitHub

### Commit Message Convention

**Format:** `<type>(<scope>): <subject>`

**Types:**
- `feat` — New feature
- `fix` — Bug fix
- `docs` — Documentation only
- `style` — Code style (formatting, missing semicolons, etc.)
- `refactor` — Refactoring code (no feature/bug change)
- `perf` — Performance improvement
- `test` — Adding/updating tests
- `chore` — Dependency updates, build scripts

**Scopes:**
- `ingestion`, `pose`, `events`, `analysis`, `profile`, `api`, `pipeline`, `common`, `docs`

**Examples:**
```bash
git commit -m "feat(analysis): add symmetry index computation"
git commit -m "fix(events): correct heel-strike detection boundary"
git commit -m "test(pose): add test for 1-euro filter"
git commit -m "docs(api): update endpoint specs in README"
```

---

## Testing Strategy

### Test Organization

```
tests/
├── unit/              # Isolated function/method tests
├── integration/       # Multi-component tests
├── e2e/              # Full pipeline tests
├── fixtures/         # Test data, mocks, factories
└── conftest.py       # Shared fixtures and configuration
```

### Running Tests

```bash
# All tests
make test

# By category
make test-unit
make test-integration
make test-e2e

# Specific test file
pytest tests/unit/test_geometry.py -v

# Specific test function
pytest tests/unit/test_geometry.py::test_compute_angle -v

# With markers
pytest -m "unit" -v
pytest -m "requires_db" -v

# With coverage
make coverage
open htmlcov/index.html
```

### Writing Tests

**Unit test example** (`tests/unit/test_geometry.py`):
```python
import pytest
from src.gait.common.geometry import compute_rearfoot_angle


@pytest.mark.unit
class TestComputeRearfootAngle:
    def test_neutral_angle(self):
        """Test normal pronation angle."""
        result = compute_rearfoot_angle(
            mid_achilles=(100, 50),
            mid_calf=(100, 150),
            mid_heel=(110, 200)
        )
        assert -4 <= result <= 4, "Expected neutral angle (0 ± 4°)"

    def test_overpronation(self):
        """Test overpronation angle."""
        result = compute_rearfoot_angle(
            mid_achilles=(90, 50),
            mid_calf=(100, 150),
            mid_heel=(110, 200)
        )
        assert result > 8, "Expected overpronation (> 8°)"
```

**Integration test example** (`tests/integration/test_ingestion_pipeline.py`):
```python
import pytest


@pytest.mark.integration
@pytest.mark.requires_redis
class TestIngestionPipeline:
    def test_video_decode_and_preprocess(self, test_data_dir):
        """Test full ingestion pipeline."""
        from src.gait.ingestion import decode, calibrate
        
        video_path = test_data_dir / "sample_video.mp4"
        frames = list(decode.decode_video_stream(video_path))
        assert len(frames) > 0, "Video should produce frames"
        assert frames[0].image.shape[0] > 0, "Frame should have data"
```

### Test Fixtures

**Define reusable fixtures in `tests/fixtures/`**:

```python
# tests/fixtures/keypoints.py
import pytest
import numpy as np


@pytest.fixture
def synthetic_keypoint_series():
    """Generate synthetic keypoint time series."""
    frames = 120
    keypoints = {
        'heel': np.sin(np.linspace(0, 4*np.pi, frames)),
        'ankle': np.cos(np.linspace(0, 4*np.pi, frames)),
    }
    return keypoints
```

---

## Code Quality

### Linting & Formatting

```bash
# Auto-format code
make format

# Check linting
make lint

# Type checking
make type-check

# Run all CI checks locally
make ci
```

### Code Standards

1. **Black** — Code formatting (line length: 100)
2. **Ruff** — Linting (imports, complexity, etc.)
3. **MyPy** — Static type checking
4. **Pre-commit** — Automated checks before each commit

### Type Hints

Always add type hints to functions:

```python
# ✓ Good
def compute_cadence(cycle_duration_sec: float, cycles: int) -> float:
    """Compute cadence in steps per minute."""
    return (cycles / cycle_duration_sec) * 60

# ✗ Bad (missing type hints)
def compute_cadence(cycle_duration_sec, cycles):
    return (cycles / cycle_duration_sec) * 60
```

### Code Review Checklist

Before submitting PR, ensure:

- [ ] Code passes `make lint`
- [ ] Code passes `make type-check`
- [ ] All tests pass: `make test`
- [ ] Coverage maintained or improved
- [ ] Commit messages follow convention
- [ ] Documentation updated (if behavior changed)
- [ ] No hardcoded thresholds (use `configs/*.yaml`)
- [ ] Numeric fields have units in names (e.g., `angle_deg`, `length_m`)
- [ ] Privacy/security reviewed (no PII in logs)

---

## Debugging

### Local API Debugging

```bash
# Start API with reload and debugging
make run-api

# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
# ReDoc at http://localhost:8000/redoc
```

### Testing an Endpoint

```python
# Quick test using httpx
from httpx import Client

client = Client(base_url="http://localhost:8000")

response = client.post(
    "/api/v1/sessions",
    json={
        "patient_name": "John Doe",
        "patient_age": 35
    }
)
print(response.json())
```

### Celery Worker Debugging

```bash
# Run worker with verbose logging
celery -A src.gait.api.tasks worker --loglevel=debug

# In another terminal, send test task
python -c "
from src.gait.api.tasks import process_session_task
process_session_task.delay('test-session-id')
"

# Monitor with Flower
# http://localhost:5555
```

### Database Debugging

```bash
# Connect to PostgreSQL
psql postgresql://gait_user:gait_password@localhost:5432/gait_analysis

# Useful queries
SELECT * FROM gait.sessions WHERE status = 'processing';
SELECT * FROM gait.profiles ORDER BY created_at DESC LIMIT 5;
SELECT * FROM logs.audit_logs ORDER BY created_at DESC LIMIT 10;
```

### Logging

Configure logging in code:

```python
import logging

logger = logging.getLogger(__name__)

logger.debug("Debug message: %s", variable)
logger.info("Processing session: %s", session_id)
logger.warning("Low confidence: %f", confidence)
logger.error("Failed to process: %s", error_msg)
```

View logs:

```bash
# Local
tail -f logs/app.log

# Docker
docker-compose logs -f api
docker-compose logs -f worker
```

---

## Documentation

### Updating Documentation

All docs are in `docs/`. When modifying code behavior:

1. **Update relevant `.md` file** in same PR
2. **Update API schema** if endpoints change
3. **Update `IMPLEMENTATION_PLAYBOOK.md`** if architecture changes
4. **Update `README.md`** if setup process changes

### Code Comments

Minimal comments — code should be self-documenting:

```python
# ✗ Bad
def compute_rearfoot_angle(...):
    # Calculate the angle
    result = atan2(dy, dx) * 180 / pi
    return result

# ✓ Good
def compute_rearfoot_angle(
    mid_achilles: tuple[float, float],
    mid_calf: tuple[float, float],
    mid_heel: tuple[float, float]
) -> float:
    """Compute rearfoot angle in degrees (frontal plane)."""
    dy = mid_calf[1] - mid_heel[1]
    dx = mid_calf[0] - mid_heel[0]
    return atan2(dy, dx) * 180 / pi
```

### Docstring Format

Use Google-style docstrings:

```python
def process_session(session_dir: Path) -> GaitPatientProfile:
    """Orchestrate full pipeline: session_dir → profile.json.
    
    Args:
        session_dir: Directory containing synchronized video files.
    
    Returns:
        GaitPatientProfile: Computed patient biomechanical profile.
    
    Raises:
        FileNotFoundError: If required video files are missing.
        ValueError: If < 4 clean cycles per foot (requires re-record).
    """
```

---

## Troubleshooting Common Issues

### "ModuleNotFoundError: No module named 'gait'"

**Solution:** Install package in editable mode:
```bash
pip install -e .
```

### "pytest: command not found"

**Solution:** Install dev dependencies:
```bash
pip install -e ".[dev]"
```

### Docker image build fails

**Solution:** Clean and rebuild:
```bash
docker-compose down
docker system prune -a
make docker-build
make docker-up
```

### Type checking fails with "missing imports"

**Solution:** Add to `pyproject.toml` under `[tool.mypy.overrides]`:
```toml
[[tool.mypy.overrides]]
module = "problematic_module.*"
ignore_missing_imports = true
```

### Pre-commit hook blocks commit

**Solution:** Run manually and fix:
```bash
pre-commit run --all-files
# Fix issues, then try commit again
```

---

## Next Steps

- Read [IMPLEMENTATION_PLAYBOOK.md](./docs/IMPLEMENTATION_PLAYBOOK.md) for Phase 1 details
- Check [API_AND_SCHEMA.md](./docs/API_AND_SCHEMA.md) for API specification
- Review [ARCHITECTURE.md](./docs/ARCHITECTURE.md) for system design

---

**Questions?** Create an issue on GitHub or contact the team.
