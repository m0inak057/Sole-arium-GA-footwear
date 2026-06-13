# Multi-stage build
FROM python:3.11-slim as builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip wheel --no-cache-dir --wheel-dir /wheels -e .

# Production stage
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libglib2.0-0 \
    libopenblas0 \
    postgresql-client \
    redis-tools \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels from builder
COPY --from=builder /wheels /wheels

# Install gait-analysis and dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-index --find-links /wheels /wheels/* && \
    rm -rf /wheels

COPY . .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Create non-root user for security
RUN useradd -m -u 1000 gaituser && \
    chown -R gaituser:gaituser /app && \
    mkdir -p /app/data /app/logs && \
    chown -R gaituser:gaituser /app/data /app/logs

USER gaituser

EXPOSE 8000

# Default to API, can override with Celery worker
CMD ["uvicorn", "src.gait.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
