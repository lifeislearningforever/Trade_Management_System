"""Help Content Repository - Access help content from Kudu"""
from typing import List, Dict, Optional
from core.repositories.impala_connection import ImpalaConnection

class HelpRepository:
    def __init__(self):
        self.connection = ImpalaConnection()

    def get_help_content(self, module: str, page: str, section: Optional[str] = None) -> List[Dict]:
        """Get help content for a page"""
        query = f"""
            SELECT id, title, content, user_type, display_order
            FROM gmp_cis.cis_help_content
            WHERE module = '{module}'
              AND page = '{page}'
              AND is_active = true
        """
        if section:
            query += f" AND section = '{section}'"
        query += " ORDER BY display_order"

        return self.connection.execute_query(query)

    def get_all_help(self) -> List[Dict]:
        """Get all active help content"""
        query = "SELECT * FROM gmp_cis.cis_help_content WHERE is_active = true ORDER BY module, page, display_order"
        return self.connection.execute_query(query)

help_repository = HelpRepository()
