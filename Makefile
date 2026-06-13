.PHONY: help install install-dev lint format type-check test test-unit test-integration test-e2e coverage clean run-api run-worker docker-build docker-up docker-down docker-logs pre-commit-install pre-commit-run

VENV := venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

help:
	@echo "Gait Analysis - Development Commands"
	@echo "====================================="
	@echo ""
	@echo "Setup:"
	@echo "  make install           Install dependencies"
	@echo "  make install-dev       Install dev dependencies"
	@echo "  make pre-commit-install Install pre-commit hooks"
	@echo ""
	@echo "Development:"
	@echo "  make lint              Run ruff linter"
	@echo "  make format            Format code with black"
	@echo "  make type-check        Run mypy type checker"
	@echo "  make test              Run all tests"
	@echo "  make test-unit         Run unit tests only"
	@echo "  make test-integration  Run integration tests only"
	@echo "  make test-e2e          Run end-to-end tests only"
	@echo "  make coverage          Generate coverage report"
	@echo ""
	@echo "Running:"
	@echo "  make run-api           Run FastAPI server (localhost:8000)"
	@echo "  make run-worker        Run Celery worker"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build      Build Docker images"
	@echo "  make docker-up         Start all services (docker-compose up)"
	@echo "  make docker-down       Stop all services"
	@echo "  make docker-logs       View service logs"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean             Remove build artifacts and cache"
	@echo "  make pre-commit-run    Run pre-commit on all files"

# Setup & Installation
install:
	pip install -e .
	@echo "✓ Dependencies installed"

install-dev:
	pip install -e ".[dev]"
	@echo "✓ Development dependencies installed"

pre-commit-install:
	pre-commit install
	@echo "✓ Pre-commit hooks installed"

# Linting & Formatting
lint:
	ruff check src/ tests/
	@echo "✓ Linting passed"

format:
	black src/ tests/ --line-length 100
	ruff check src/ tests/ --fix
	@echo "✓ Code formatted"

type-check:
	mypy src/gait --show-error-codes
	@echo "✓ Type checking passed"

# Testing
test:
	pytest tests/ -v --tb=short
	@echo "✓ All tests passed"

test-unit:
	pytest tests/unit/ -v --tb=short -m unit
	@echo "✓ Unit tests passed"

test-integration:
	pytest tests/integration/ -v --tb=short -m integration
	@echo "✓ Integration tests passed"

test-e2e:
	pytest tests/e2e/ -v --tb=short -m e2e
	@echo "✓ E2E tests passed"

coverage:
	pytest tests/ --cov=src/gait --cov-report=html --cov-report=term-missing
	@echo "✓ Coverage report generated (open htmlcov/index.html)"

# Running Services
run-api:
	uvicorn src.gait.api.main:app --reload --host 0.0.0.0 --port 8000
	@echo "✓ API running at http://localhost:8000"

run-worker:
	celery -A src.gait.api.tasks worker --loglevel=info
	@echo "✓ Celery worker started"

# Docker
docker-build:
	docker-compose build
	@echo "✓ Docker images built"

docker-up:
	docker-compose up -d
	@echo "✓ Services started (docker-compose up -d)"
	@echo "  API: http://localhost:8000"
	@echo "  PostgreSQL: localhost:5432"
	@echo "  Redis: localhost:6379"
	@echo "  MinIO: http://localhost:9000"

docker-down:
	docker-compose down
	@echo "✓ Services stopped"

docker-logs:
	docker-compose logs -f

docker-ps:
	docker-compose ps

# CI/CD
ci: lint type-check test
	@echo "✓ CI pipeline passed (lint → type-check → tests)"

pre-commit-run:
	pre-commit run --all-files
	@echo "✓ Pre-commit hooks ran on all files"

# Cleanup
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/
	@echo "✓ Cleaned up build artifacts"

.PHONY: all
all: install-dev pre-commit-install lint type-check test
	@echo "✓ Full setup complete!"
