#!/bin/sh
set -euo pipefail

# ─── Helpers ──────────────────────────────────────────────────────────────────
log() { echo "[entrypoint] $*"; }

wait_for_db() {
    log "Waiting for PostgreSQL at ${DB_HOST:-postgres}:${DB_PORT:-5432}..."
    until python -c "
import sys, os
import psycopg2
try:
    psycopg2.connect(
        host=os.environ.get('DB_HOST','postgres'),
        port=os.environ.get('DB_PORT','5432'),
        dbname=os.environ.get('DB_NAME','iooding'),
        user=os.environ.get('DB_USER','iooding'),
        password=os.environ.get('DB_PASSWORD','postgres'),
        connect_timeout=3,
    ).close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
        log "  ...not ready, retrying in 3s"
        sleep 3
    done
    log "PostgreSQL is ready."
}

run_migrate() {
    wait_for_db
    log "Running migrations..."
    python manage.py migrate --noinput

    log "Attempting RAG index sync..."
    python manage.py index_posts 2>/dev/null || log "  Skipped (Ollama/Redis unavailable)"

    if [ -n "${DJANGO_SUPERUSER_USERNAME-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD-}" ]; then
        log "Ensuring superuser '${DJANGO_SUPERUSER_USERNAME}' exists..."
        python manage.py shell -c "
from django.contrib.auth import get_user_model
import os
User = get_user_model()
u = os.environ['DJANGO_SUPERUSER_USERNAME']
if not User.objects.filter(username=u).exists():
    User.objects.create_superuser(u, 'admin@iooding.local', os.environ['DJANGO_SUPERUSER_PASSWORD'])
    print(f'Created superuser {u}')
else:
    print(f'Superuser {u} already exists')
"
    fi
}

run_static() {
    log "Collecting static files..."
    python manage.py collectstatic --noinput --clear
}

# ─── Command dispatch ─────────────────────────────────────────────────────────
case "${1:-}" in
    migrate)
        run_migrate
        ;;
    static)
        run_static
        ;;
    deploy)
        log "=== Full deploy start ==="
        run_migrate
        run_static
        log "=== Full deploy complete ==="
        ;;
    *)
        exec "$@"
        ;;
esac
