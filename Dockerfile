# syntax=docker/dockerfile:1
FROM python:3.13-slim

# Predictable, log-friendly Python; no pip cache in the image layer.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install runtime dependencies first so this layer caches across code changes.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Application code and configuration (no tests, docs, secrets — see .dockerignore).
COPY src/ ./src/
COPY config.yaml ./

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Liveness via the app's own /health endpoint (no curl in the slim image).
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

# The model API key (e.g. ANTHROPIC_API_KEY) is supplied at runtime via env,
# never baked into the image.
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
