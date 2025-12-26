#!/bin/sh
set -e

# Function to run initialization tasks
run_init() {
    echo "Running migrations..."
    python manage.py migrate --noinput
    
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
    
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

# If the first argument is 'init', run initialization
if [ "$1" = 'init' ]; then
    run_init
    exit 0
fi

# Otherwise execute the command passed (CMD in Dockerfile)
exec "$@"
