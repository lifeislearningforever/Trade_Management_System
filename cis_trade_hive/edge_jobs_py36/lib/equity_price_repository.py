"""
Equity Price Repository

Data access layer for cis_equity_price in Kudu tables. All queries execute
via Impala (no Django ORM). Mirrors
market_data/repositories/equity_price_hive_repository.py's
upsert_equity_price() column list exactly (minus the Django-side audit log
call -- no audit dependency in this Django-free fork, matching the
established pattern in lib/corporate_action_repository.py).
"""

import logging
from datetime import datetime
from typing import Any, Dict

from .impala_connection import impala_manager
from .config import settings

logger = logging.getLogger(__name__)


class EquityPriceRepository:
    """Repository for equity price operations with Kudu via Impala"""

    DATABASE = settings.IMPALA_CONFIG['DATABASE']
    TABLE_NAME = 'cis_equity_price'

    @staticmethod
    def upsert(equity_price_data: Dict[str, Any]) -> bool:
        """
        Insert/update an equity price record using UPSERT (composite key:
        currency_code, security_label, price_date).

        Args:
            equity_price_data: Dictionary with equity price fields

        Returns:
            True if successful, False otherwise
        """
        try:
            currency_code = (equity_price_data.get('currency_code') or '').replace("'", "\\'")
            security_label = (equity_price_data.get('security_label') or '').replace("'", "\\'")
            isin = (equity_price_data.get('isin') or '').replace("'", "\\'")
            price_date = equity_price_data.get('price_date', '')
            main_closing_price = equity_price_data.get('main_closing_price', 0)
            price_timestamp = equity_price_data.get(
                'price_timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            src_system = (equity_price_data.get('src_system') or 'GMP').replace("'", "\\'")
            created_by = (equity_price_data.get('created_by') or 'GMP_ETL').replace("'", "\\'")
            created_at = equity_price_data.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            updated_by = (equity_price_data.get('updated_by') or '').replace("'", "\\'")
            updated_at = equity_price_data.get('updated_at')

            upsert_query = f"""
            UPSERT INTO {EquityPriceRepository.DATABASE}.{EquityPriceRepository.TABLE_NAME} (
                currency_code,
                security_label,
                isin,
                price_date,
                main_closing_price,
                price_timestamp,
                src_system,
                is_active,
                created_by,
                created_at,
                updated_by,
                updated_at
            ) VALUES (
                '{currency_code}',
                '{security_label}',
                {f"'{isin}'" if isin else 'NULL'},
                '{price_date}',
                {main_closing_price},
                {f"'{price_timestamp}'" if price_timestamp is not None else 'NULL'},
                '{src_system}',
                true,
                '{created_by}',
                '{created_at}',
                {f"'{updated_by}'" if updated_by else 'NULL'},
                {f"'{updated_at}'" if updated_at else 'NULL'}
            )
            """

            success = impala_manager.execute_write(upsert_query, database=EquityPriceRepository.DATABASE)
            if success:
                logger.info(f"Successfully upserted equity price {currency_code}/{security_label}/{price_date}")
            else:
                logger.error(f"Failed to upsert equity price {currency_code}/{security_label}/{price_date}")
            return success

        except Exception as e:
            logger.error(f"Error upserting equity price: {str(e)}")
            return False


equity_price_repository = EquityPriceRepository()
