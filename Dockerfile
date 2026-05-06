# ─── Builder ──────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Enable Caching for Pip
ENV PIP_CACHE_DIR=/root/.cache/pip

# Install build dependencies with apt cache
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    libffi-dev

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install -r requirements.txt


# ─── Runtime ──────────────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Create non-root user for security (UID 100 is required by K8s securityContext)
# In Debian slim, GID 100 already exists as the 'users' group.
RUN useradd -r -u 100 -g 100 django

# Install only necessary runtime libraries with cache
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libjpeg62-turbo \
    zlib1g

# Copy pre-installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code with proper ownership
COPY --chown=django:100 . .

# Prepare directories and permissions in a single layer
RUN mkdir -p /app/staticfiles /app/media && \
    chown django:100 /app/staticfiles /app/media && \
    chmod +x /app/docker-entrypoint.sh

# Environment variables for Python optimization
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:$PATH"

EXPOSE 8000

# Switch to non-root user before running application commands
USER django

# Bake static files into the image securely as the django user
RUN SECRET_KEY=dummy DATABASE_URL=sqlite:///:memory: python manage.py collectstatic --noinput --clear

ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Tune workers for small footprint (2 is optimal for 512MB RAM)
CMD ["gunicorn", "iooding.asgi:application", \
    "-k", "uvicorn.workers.UvicornWorker", \
    "--bind", "0.0.0.0:8000", \
    "--workers", "2", \
    "--timeout", "60", \
    "--worker-tmp-dir", "/dev/shm", \
    "--access-logfile", "-", \
    "--error-logfile", "-", \
    "--log-level", "warning"]