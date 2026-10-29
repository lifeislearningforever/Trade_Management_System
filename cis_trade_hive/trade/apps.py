import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)


class TradeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'trade'
    verbose_name = 'Trade Management'

    def ready(self):
        """
        Called when Django starts. Warm UDF cache for faster trade form loading.
        """
        # Only warm cache in non-test environments
        import sys
        if 'test' in sys.argv or 'pytest' in sys.modules:
            return

        # Use a separate thread to avoid blocking startup
        import threading

        def warm_cache():
            try:
                from trade.services.trade_dropdown_service import trade_dropdown_service
                count = trade_dropdown_service.warm_udf_cache()
                logger.info(f"Trade app ready: UDF cache warmed with {count} fields")
            except Exception as e:
                # Don't fail startup if cache warming fails
                logger.warning(f"UDF cache warming failed (non-critical): {str(e)}")

        # Run in background thread to not block Django startup
        thread = threading.Thread(target=warm_cache, daemon=True)
        thread.start()
