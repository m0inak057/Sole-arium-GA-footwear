"""Pytest configuration and shared fixtures."""

import os
from pathlib import Path

import pytest


# Add src directory to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
os.sys.path.insert(0, str(SRC_DIR))


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the project root directory."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """Return the test data directory."""
    data_dir = PROJECT_ROOT / "tests" / "fixtures" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


@pytest.fixture(scope="session")
def configs_dir() -> Path:
    """Return the configs directory."""
    return PROJECT_ROOT / "configs"


@pytest.fixture
def env_setup(monkeypatch):
    """Set up test environment variables."""
    test_env = {
        "APP_ENV": "test",
        "DATABASE_URL": "postgresql://test:test@localhost:5432/gait_test",
        "REDIS_URL": "redis://localhost:6379/0",
        "CELERY_BROKER_URL": "redis://localhost:6379/0",
        "CELERY_RESULT_BACKEND": "redis://localhost:6379/1",
        "S3_BUCKET_NAME": "gait-test",
        "LOG_LEVEL": "DEBUG",
    }
    for key, value in test_env.items():
        monkeypatch.setenv(key, value)
    return test_env


# Mark tests by category
def pytest_configure(config):
    """Register test markers."""
    config.addinivalue_line("markers", "unit: unit tests")
    config.addinivalue_line("markers", "integration: integration tests")
    config.addinivalue_line("markers", "e2e: end-to-end tests")
    config.addinivalue_line("markers", "slow: slow running tests")
    config.addinivalue_line("markers", "requires_db: tests that require database")
    config.addinivalue_line("markers", "requires_redis: tests that require Redis")
