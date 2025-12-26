FROM python:3.12-alpine

# Install system dependencies using apk (Alpine package manager)
RUN apk add --no-cache \
    gcc \
    musl-dev \
    postgresql-dev \
    jpeg-dev \
    zlib-dev

# Set working directory
WORKDIR /app

# Copy Python requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY . .

# Copy entrypoint script
COPY docker-entrypoint.sh /app/
RUN chmod +x /app/docker-entrypoint.sh

# Expose port for the app
EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# Use Uvicorn as default command
CMD ["uvicorn", "iooding.asgi:application", "--host", "0.0.0.0", "--port", "8000"]