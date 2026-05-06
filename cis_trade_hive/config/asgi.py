"""
ASGI config for CIS Trade Hive.

Supports both HTTP (Django) and WebSocket (Django Channels) traffic.
The AuthMiddlewareStack wraps the WebSocket router so that the session
is populated before the consumer's connect() is called — this is how
user_login is available in scope['session'].

Production deployment (choose one):
  daphne -b 0.0.0.0 -p 8000 config.asgi:application
  uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --workers 4

Both HTTP and WebSocket are handled in the same process.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Initialise Django BEFORE importing channels or consumers so that
# app registry is ready when consumers import Django models/services.
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack                           # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter             # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator    # noqa: E402

from core.routing import websocket_urlpatterns                          # noqa: E402

application = ProtocolTypeRouter({
    # Standard Django HTTP — views, DRF, WhiteNoise static files
    'http': django_asgi_app,

    # WebSocket wrapped in:
    #   AllowedHostsOriginValidator — reject WS from non-ALLOWED_HOSTS origins
    #   AuthMiddlewareStack         — populate scope['session'] from Django session
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
