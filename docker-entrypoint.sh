#!/bin/sh
set -e

# Function to run database migrations
run_migrate() {
    echo "Running database migrations..."
    python manage.py migrate --noinput
    
    echo "Indexing blog posts to Redis for RAG..."
    python manage.py index_posts || echo "Indexing failed (no Ollama/Redis), skipping..."

    
    if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
        echo "Ensuring superuser exists..."
        python manage.py shell << pyEOF
from django.contrib.auth import get_user_model
import os
User = get_user_model()
username = os.environ["DJANGO_SUPERUSER_USERNAME"]
password = os.environ["DJANGO_SUPERUSER_PASSWORD"]
email = "admin@iooding.local"
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username=username, email=email, password=password)
    print(f"Created superuser {username}")
else:
    print(f"Superuser {username} already exists")
pyEOF
    fi
}

# Function to collect static files
run_static() {
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
}

# Command dispatch
case "$1" in
    "migrate")
        run_migrate
        ;;
    "static")
        run_static
        ;;
    "deploy")
        echo "Starting full deployment task [$(date)]"
        run_migrate
        run_static
        echo "Deployment task finished [$(date)]"
        ;;
    *)
        exec "$@"
        ;;
esac
