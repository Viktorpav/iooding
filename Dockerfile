FROM python:3.12-alpine

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=iooding.settings

# Install system dependencies using apk (Alpine package manager)
RUN apk update && apk add --no-cache \
    gcc \
    musl-dev \
    postgresql-dev \
    jpeg-dev \
    zlib-dev \
    libc-dev \
    curl

# Set working directory
WORKDIR /app

# Copy Python requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY . .

# Expose port for the app
EXPOSE 8000

# Use Uvicorn as entrypoint
CMD ["uvicorn", "iooding.asgi:application", "--host", "0.0.0.0", "--port", "8000"]