# ─── Builder ──────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev

# Install uv (5-10x faster than pip)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --prefix=/install -r requirements.txt

# ─── Runtime ──────────────────────────────────────────────────────────────────
FROM python:3.13-slim

WORKDIR /app

# GID 100 (users) already exists in Debian slim
RUN useradd -r -u 100 -g 100 django

# Combine runtime deps + directory setup into one layer
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libjpeg62-turbo \
    zlib1g \
    && mkdir -p /app/staticfiles /app/media \
    && chown django:100 /app/staticfiles /app/media

COPY --from=builder /install /usr/local
COPY --chown=django:100 . .

RUN chmod +x /app/docker-entrypoint.sh

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

USER django

RUN SECRET_KEY=dummy DATABASE_URL=sqlite:///:memory: python manage.py collectstatic --noinput --clear

ENTRYPOINT ["/app/docker-entrypoint.sh"]

CMD ["gunicorn", "iooding.asgi:application", \
    "-k", "uvicorn.workers.UvicornWorker", \
    "--bind", "0.0.0.0:8000", \
    "--workers", "2", \
    "--timeout", "60", \
    "--worker-tmp-dir", "/dev/shm", \
    "--access-logfile", "-", \
    "--error-logfile", "-", \
    "--log-level", "warning"]