"""
ASGI config for CIS Trade Hive.

Supports both HTTP (Django) and WebSocket (Django Channels) traffic.
The AuthMiddlewareStack wraps the WebSocket router so that the session
is populated before the consumer's connect() is called — this is how
user_login is available in scope['session'].

Falls back to HTTP-only if Django Channels is not installed, so the
application still starts — WebSocket notifications just won't work until
channels is installed (pip install channels==4.2.0).

Production deployment (choose one):
  daphne -b 0.0.0.0 -p 8000 config.asgi:application
  gunicorn config.asgi:application --worker-class uvicorn.workers.UvicornWorker
"""

import logging
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

logger = logging.getLogger(__name__)

# Initialise Django BEFORE importing channels or consumers so that
# app registry is ready when consumers import Django models/services.
django_asgi_app = get_asgi_application()

try:
    from channels.auth import AuthMiddlewareStack
    from channels.routing import ProtocolTypeRouter, URLRouter
    from core.routing import websocket_urlpatterns

    # AllowedHostsOriginValidator intentionally omitted — it rejects WS when
    # ALLOWED_HOSTS='*' (CML default) because '*' is matched literally, not
    # as a wildcard, causing every WS upgrade to fail with ValueError.
    application = ProtocolTypeRouter({
        'http': django_asgi_app,
        'websocket': AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        ),
    })
    print("ASGI: Django Channels loaded — WebSocket notifications ENABLED")

except Exception as e:
    # Any failure (ImportError, routing error, etc.) — fall back to HTTP only.
    # WebSocket bell icon shows disconnected but all other features work.
    import traceback
    print(f"ASGI: Channels setup failed — running HTTP-only. Reason: {e}")
    print(traceback.format_exc())
    application = django_asgi_app
