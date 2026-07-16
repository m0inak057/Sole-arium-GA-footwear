# Multi-stage build
FROM ubuntu:22.04 as builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3-pip \
    python3.11-dev \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml README.md ./
COPY src/ src/

RUN python3.11 -m pip install --upgrade pip setuptools wheel && \
    python3.11 -m pip wheel --no-cache-dir --wheel-dir /wheels -e .

# Production stage
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3-pip \
    # OpenCV and graphics dependencies
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libopenblas0 \
    # MediaPipe Tasks API OpenGL ES dependencies
    libgles2 \
    libgles2-mesa \
    libegl1 \
    libegl-mesa0 \
    # Haar cascade XML files for face_blur.py — opencv-python-headless ships
    # an empty cv2/data/ directory, so these must come from the system package
    opencv-data \
    # Video codec support — required for cv2.VideoCapture to decode H.264/H.265 on Linux
    ffmpeg \
    libavcodec-extra \
    # Database and utilities
    postgresql-client \
    redis-tools \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Copy wheels from builder
COPY --from=builder /wheels /wheels

# Install gait-analysis and dependencies
RUN python3.11 -m pip install --upgrade pip && \
    python3.11 -m pip install --no-index --find-links /wheels /wheels/* && \
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
CMD ["python3.11", "-m", "uvicorn", "src.gait.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
