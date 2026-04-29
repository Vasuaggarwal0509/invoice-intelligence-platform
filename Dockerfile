# syntax=docker/dockerfile:1.7
# ----------------------------------------------------------------------
# invoice-intelligence-platform — production runtime image.
#
# Single-stage by design: the build deps (build-essential) are a small
# fraction of the final image (the bulk is rapidocr-onnxruntime weights
# + numpy + pillow), so a multi-stage split saves <50MB. Keeping it
# single-stage simplifies CI cache layering.
#
# Render reads this file directly from the connected repo. Image size
# target: ~700-900 MB (acceptable for free tier; rapidocr ONNX weights
# alone are ~150 MB).
# ----------------------------------------------------------------------

FROM python:3.12-slim

# Don't write .pyc files in the container (pointless layer churn) and
# don't buffer stdout/stderr (streams logs immediately to Render).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps:
#   build-essential     — building cryptography wheel (transitively)
#   libmagic1           — python-magic (file-type sniffing on uploads)
#   libgl1, libglib2.0-0 — onnxruntime + opencv runtime (rapidocr deps)
#   ca-certificates     — outbound HTTPS for Gmail API + future webhooks
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        libmagic1 \
        libgl1 \
        libglib2.0-0 \
        ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Layer 1: dependencies (cacheable until requirements files change) ---
# Copy ONLY the requirement files first so docker can reuse the
# pip-install layer when source code changes but deps don't.
COPY requirements.txt ./
COPY business_layer/requirements.txt business_layer/requirements.txt
COPY extraction_layer/requirements.txt extraction_layer/requirements.txt
RUN pip install --upgrade pip \
 && pip install -r requirements.txt

# --- Layer 2: project source + editable install ---
COPY pyproject.toml ./
COPY config ./config
COPY business_layer ./business_layer
COPY extraction_layer ./extraction_layer
RUN pip install -e .

# --- Layer 3: runtime user + filesystem ownership ---
# Non-root user. Render mounts the persistent disk at /app/data so we
# pre-create it with the right owner.
RUN useradd --no-create-home --shell /bin/false --uid 1000 app \
 && mkdir -p /app/data \
 && chown -R app:app /app

USER app

# --- Runtime config (most overrideable via Render env vars) ---
ENV PLATFORM_ENV=prod \
    PORT=8001

# Render injects PORT — uvicorn binds whatever Render asks for.
# Fallback to 8001 for local `docker run` testing.
EXPOSE 8001

# Health check matches Render's healthCheckPath. 30s grace period for
# the migrations to complete on first boot.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT','8001') + '/health').read()" \
      || exit 1

CMD ["sh", "-c", "uvicorn business_layer.app:app --host 0.0.0.0 --port ${PORT:-8001}"]
