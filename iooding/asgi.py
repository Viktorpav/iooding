"""
ASGI config for iooding project.
Runs under Gunicorn + uvicorn.workers.UvicornWorker for concurrent async handling.
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iooding.settings')

application = get_asgi_application()
