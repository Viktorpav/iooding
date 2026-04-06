# ─── Builder ──────────────────────────────────────────────────────────────────
FROM python:3.12-alpine AS builder

WORKDIR /app

# Install build deps in a single layer
RUN apk add --no-cache gcc musl-dev postgresql-dev jpeg-dev zlib-dev

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─── Runtime ──────────────────────────────────────────────────────────────────
FROM python:3.12-alpine

WORKDIR /app

# Create non-root user
RUN addgroup -S django && adduser -S django -G django

# Runtime libs only (no build tools)
RUN apk add --no-cache libpq jpeg zlib

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code (owned by root, read by django)
COPY --chown=django:django . .

RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

USER django

ENTRYPOINT ["/app/docker-entrypoint.sh"]

# 2 workers is right for low-RAM K8s; tune via GUNICORN_WORKERS env var if needed
CMD ["gunicorn", "iooding.asgi:application", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--worker-tmp-dir", "/dev/shm", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "warning"]