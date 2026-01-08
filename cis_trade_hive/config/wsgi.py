"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import atexit
import logging

from django.core.wsgi import get_wsgi_application

logger = logging.getLogger(__name__)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Initialize Django application
application = get_wsgi_application()

# Initialize async audit queue for production
try:
    from core.audit.async_audit_queue import async_audit_queue

    # Start the async queue (spawns worker threads)
    async_audit_queue.start()
    logger.info("Async audit queue started successfully")

    # Register graceful shutdown handler
    def shutdown_audit_queue():
        """Gracefully shutdown async audit queue on application exit"""
        logger.info("Shutting down async audit queue...")
        async_audit_queue.shutdown(timeout=10)
        logger.info("Async audit queue shutdown complete")

    atexit.register(shutdown_audit_queue)

except Exception as e:
    logger.error(f"Failed to initialize async audit queue: {str(e)}")
    logger.error("Audit logging will fall back to synchronous mode")
    # Don't crash the application - audit queue initialization failure
    # should not prevent the app from starting
