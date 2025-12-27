"""Help Service - Business logic for help content with caching"""
from typing import List, Dict
from django.core.cache import cache
from core.repositories.help_repository import help_repository

class HelpService:
    @staticmethod
    def get_page_help(module: str, page: str) -> List[Dict]:
        """Get help content with caching (1 hour)"""
        cache_key = f'help_{module}_{page}'
        content = cache.get(cache_key)

        if not content:
            content = help_repository.get_help_content(module, page)
            cache.set(cache_key, content, timeout=3600)

        return content

    @staticmethod
    def clear_cache():
        """Clear all help cache (call after updates)"""
        # Would need to track keys or use pattern matching
        pass
