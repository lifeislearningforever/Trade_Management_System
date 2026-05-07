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

    # AllowedHostsOriginValidator is intentionally omitted:
    # it rejects WS connections when ALLOWED_HOSTS contains '*' or CML proxy
    # hostnames that don't exactly match the Origin header sent by the browser.
    # CML already enforces network-level access control, so origin validation
    # here adds no real security while breaking legitimate connections.
    application = ProtocolTypeRouter({
        'http': django_asgi_app,
        'websocket': AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        ),
    })
    logger.info("ASGI: Django Channels loaded — WebSocket notifications enabled")

except ImportError as e:
    # channels not installed — serve HTTP only, WebSocket bell icon will
    # show disconnected but the rest of the app works normally.
    logger.warning(
        f"ASGI: Django Channels not available ({e}) — "
        "running HTTP-only. Install channels==4.2.0 to enable WebSocket notifications."
    )
    application = django_asgi_app
