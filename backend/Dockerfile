# Python 3.11 slim base image
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered output for real-time logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus \
    UVICORN_WORKERS=2

WORKDIR /app

# Install system runtime & build dependencies for OpenCV, ONNXRuntime, and InsightFace
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    python3-dev \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy backend application code and models
COPY . /app

# Pre-download InsightFace buffalo_l models during build time so the container boots instantly
RUN python -c "from insightface.app import FaceAnalysis; app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider']); app.prepare(ctx_id=-1, det_size=(640, 640))"

# Expose backend API port
EXPOSE 8000

# Health check to ensure the FastAPI app is responding
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start Uvicorn ASGI server. The metrics dir is wiped first: prometheus_client's
# multiprocess mode keeps per-worker files there, and stale ones from a previous
# container run would be summed into the new process's metrics.
# Size UVICORN_WORKERS (x INFERENCE_THREADS) to the host's cores — see README.
CMD ["sh", "-c", "rm -rf \"$PROMETHEUS_MULTIPROC_DIR\" && mkdir -p \"$PROMETHEUS_MULTIPROC_DIR\" && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers \"$UVICORN_WORKERS\""]
