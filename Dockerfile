# ─── Builder ──────────────────────────────────────────────────────────────────
FROM python:3.12-alpine AS builder

WORKDIR /app

# Enable Caching for Pip
ENV PIP_CACHE_DIR=/root/.cache/pip

# Install build dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    postgresql-dev \
    jpeg-dev \
    zlib-dev \
    libffi-dev

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


# ─── Runtime ──────────────────────────────────────────────────────────────────
FROM python:3.12-alpine

WORKDIR /app

# Create non-root user for security
RUN addgroup -S django && adduser -S django -G django

# Install only necessary runtime libraries
RUN apk add --no-cache libpq jpeg zlib

# Copy pre-installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code with proper ownership
COPY --chown=django:django . .

# Prepare directories and permissions in a single layer
RUN mkdir -p /app/staticfiles /app/media && \
    chown -R django:django /app && \
    chmod +x /app/docker-entrypoint.sh

# Environment variables for Python optimization
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:$PATH"

EXPOSE 8000

USER django

ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Tune workers for small footprint (2 is optimal for 512MB RAM)
CMD ["gunicorn", "iooding.asgi:application", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--worker-tmp-dir", "/dev/shm", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "warning"]