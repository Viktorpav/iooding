# Builder stage
FROM python:3.12-alpine AS builder

WORKDIR /app

# Install build dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    postgresql-dev \
    jpeg-dev \
    zlib-dev

# Install python dependencies to a temporary location
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Runner stage
FROM python:3.12-alpine

WORKDIR /app

# Create a non-root user
RUN addgroup -S django && adduser -S django -G django

# Install runtime dependencies only
RUN apk add --no-cache \
    libpq \
    jpeg \
    zlib \
    bash

# Copy installed python dependencies from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Copy entrypoint script and set permissions
COPY docker-entrypoint.sh /app/
RUN chmod +x /app/docker-entrypoint.sh && \
    chown -R django:django /app

# Expose port for the app
EXPOSE 8000

# Switch to non-root user
USER django

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# Use Uvicorn as default command
CMD ["uvicorn", "iooding.asgi:application", "--host", "0.0.0.0", "--port", "8000"]