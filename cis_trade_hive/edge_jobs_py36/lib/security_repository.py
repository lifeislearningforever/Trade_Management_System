"""
Security Repository

Data access layer for security master data in Kudu tables.
All queries execute via Impala (no Django ORM).
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from .impala_connection import impala_manager
from .config import settings

logger = logging.getLogger(__name__)


class SecurityRepository:
    """Repository for security operations with Kudu via Impala"""

    DATABASE = settings.IMPALA_CONFIG['DATABASE']
    TABLE_NAME = 'cis_security'
    HISTORY_TABLE = 'cis_security_history'

    @staticmethod
    def escape_value(value: Any) -> str:
        """Escape value for SQL query. Uses backslash escaping for Impala compatibility."""
        if value is None or value == '':
            return 'NULL'
        if isinstance(value, bool):
            return 'true' if value else 'false'
        if isinstance(value, (int, float)):
            return str(value)
        escaped = str(value).replace('\\', '\\\\').replace("'", "\\'")
        return f"'{escaped}'"

    @staticmethod
    def get_security_by_isin(isin: str) -> Optional[Dict[str, Any]]:
        """Fetch a single security by ISIN."""
        try:
            query = f"""
            SELECT *
            FROM {SecurityRepository.DATABASE}.{SecurityRepository.TABLE_NAME}
            WHERE isin = {SecurityRepository.escape_value(isin)}
            """
            result = impala_manager.execute_query(query, database=SecurityRepository.DATABASE)
            return result[0] if result and len(result) > 0 else None
        except Exception as e:
            logger.error(f"Error fetching security by ISIN {isin}: {str(e)}")
            return None

    # -------------------------------------------------------------------------
    # Registry constants — mirrors security/repositories/security_hive_repository.py
    # exactly. The GMP sync MUST use the same stable-ID registry the live CIS
    # app uses (not a raw hash of security_name) -- otherwise a security
    # touched via both the UI and this sync would get two different,
    # incompatible security_id values for what is really the same instrument.
    # -------------------------------------------------------------------------
    REGISTRY_TABLE = 'cis_security_id_registry'
    COUNTER_TABLE  = 'cis_security_id_counter'
    ID_FLOOR       = 100_000_000_000   # 12-digit IDs start here

    @staticmethod
    def _build_natural_key(security_data: Dict[str, Any]) -> tuple:
        """
        Derive the normalised composite natural key and its type.

        Cross-listed securities share the same ISIN but trade on different
        exchanges in different countries -- ISIN alone is therefore NOT
        unique. Priority (first matching rule wins):
          1. ISIN + exchange_code       -> "ISIN_EXCH:<isin>:<exch>"
          2. ISIN + country_of_exchange -> "ISIN_CTY:<isin>:<country>"
          3. ISIN only                  -> "ISIN:<isin>"
          4. name + exchange_code       -> "NAME_EXCH:<name>:<exch>"
          5. name + country_of_exchange -> "NAME_CTY:<name>:<country>"
          6. name only                  -> "NAME:<name>"
        """
        isin = (security_data.get('isin') or '').strip().upper()
        name = (security_data.get('security_name') or '').strip().upper()
        exch = (security_data.get('exchange_code') or '').strip().upper()
        cty  = (security_data.get('country_of_exchange') or '').strip().upper()

        if isin and exch:
            return f'ISIN_EXCH:{isin}:{exch}', 'ISIN_EXCH'
        if isin and cty:
            return f'ISIN_CTY:{isin}:{cty}',   'ISIN_CTY'
        if isin:
            return f'ISIN:{isin}',              'ISIN'
        if exch:
            return f'NAME_EXCH:{name}:{exch}',  'NAME_EXCH'
        if cty:
            return f'NAME_CTY:{name}:{cty}',    'NAME_CTY'
        return f'NAME:{name}',                  'NAME'

    @staticmethod
    def get_or_allocate_security_id(
        security_data: Dict[str, Any],
        src_system: str,
        created_by: str,
    ) -> int:
        """
        Look up or allocate a stable 12-digit security_id via the registry.

        - If the natural key exists in cis_security_id_registry -> return that ID.
        - If not -> read cis_security_id_counter, allocate next ID, write both
          registry row and updated counter, then return the new ID.
        """
        natural_key, key_type = SecurityRepository._build_natural_key(security_data)
        now_ms = int(datetime.now().timestamp() * 1000)
        db = SecurityRepository.DATABASE
        esc = SecurityRepository.escape_value

        # 1. Check registry
        lookup_sql = f"""
            SELECT security_id
            FROM {db}.{SecurityRepository.REGISTRY_TABLE}
            WHERE natural_key = {esc(natural_key)}
            LIMIT 1
        """
        rows = impala_manager.execute_query(lookup_sql, database=db)
        if rows:
            return int(rows[0]['security_id'])

        # 2. Registry miss — read counter and claim next ID
        counter_sql = f"""
            SELECT next_id
            FROM {db}.{SecurityRepository.COUNTER_TABLE}
            WHERE counter_id = 1
            LIMIT 1
        """
        counter_rows = impala_manager.execute_query(counter_sql, database=db)
        if counter_rows:
            new_id = int(counter_rows[0]['next_id'])
        else:
            new_id = SecurityRepository.ID_FLOOR + 1

        # 3. Write registry entry for this natural key
        isin_val = (security_data.get('isin') or '').strip().upper()
        name_val = (security_data.get('security_name') or '').strip()
        exch_val = (security_data.get('exchange_code') or '').strip().upper()
        cty_val  = (security_data.get('country_of_exchange') or '').strip().upper()
        registry_sql = f"""
            UPSERT INTO {db}.{SecurityRepository.REGISTRY_TABLE}
            (natural_key, security_id, key_type, isin, security_name,
             exchange_code, country_of_exchange, src_system, created_by, created_at)
            VALUES (
                {esc(natural_key)},
                {new_id},
                {esc(key_type)},
                {esc(isin_val) if isin_val else 'NULL'},
                {esc(name_val)},
                {esc(exch_val) if exch_val else 'NULL'},
                {esc(cty_val)  if cty_val  else 'NULL'},
                {esc(src_system)},
                {esc(created_by)},
                {now_ms}
            )
        """
        impala_manager.execute_write(registry_sql, database=db)

        # 4. Advance the counter
        counter_upsert_sql = f"""
            UPSERT INTO {db}.{SecurityRepository.COUNTER_TABLE}
            (counter_id, next_id, updated_at)
            VALUES (1, {new_id + 1}, {now_ms})
        """
        impala_manager.execute_write(counter_upsert_sql, database=db)

        logger.info(f"Registry: allocated security_id={new_id} for natural_key='{natural_key}'")
        return new_id

    @staticmethod
    def upsert_security(security_data: Dict[str, Any], created_by: str) -> bool:
        """
        Insert/update a security record into cis_security via the ID registry.

        Args:
            security_data: Dictionary of security fields (see field_mapping below)
            created_by: Username/process creating the security (e.g. 'GMP_ETL')

        Returns:
            True if successful, False otherwise
        """
        try:
            security_id = SecurityRepository.get_or_allocate_security_id(
                security_data,
                src_system=security_data.get('src_system', 'GMP'),
                created_by=created_by,
            )
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            columns = ['security_id']
            values = [str(security_id)]

            # Mirrors security/repositories/security_hive_repository.py's
            # insert_security() field_mapping exactly (verified against the
            # live code, not just the source DDL, which was found to be stale
            # for several of these columns).
            field_mapping = {
                'security_name': str,
                'isin': str,
                'security_description': str,
                'issuer': str,
                'ticker': str,
                'industry': str,
                'security_type': str,
                'security_sub_type': str,
                'investment_type': str,
                'security_investment': str,
                'issuer_type': str,
                'quoted_unquoted': str,
                'market': str,
                'country_of_incorporation': str,
                'country_of_exchange': str,
                'country_of_issue': str,
                'country_of_primary_exchange': str,
                'udf_country_issue': str,
                'exchange_code': str,
                'currency_code': str,
                'shares_outstanding': int,
                'beta': float,
                'par_value': float,
                'price_source': str,
                'pct_hld_entity_1': str,
                'pct_hld_entity_2': str,
                'pct_hld_entity_3': str,
                'pct_hld_entity_aggr': str,
                'substantial_10_pct': str,
                'pevc_s32_devest': str,
                's32_representative': str,
                'approved_s32': str,
                'fintech_speculative': str,
                'unlistedeq_speculative': str,
                'related_company': str,
                'mas_6d_code': str,
                'mas_643_entity_type': str,
                'fin_nonfin_ind': str,
                'base_liv_fund': str,
                'fund_index_fund': str,
                'core_noncore': str,
                'management_limit_classification': str,
                'relative_index': str,
                'business_unit_head': str,
                'person_in_charge': str,
            }

            for field, field_type in field_mapping.items():
                if field in security_data:
                    columns.append(field)
                    values.append(SecurityRepository.escape_value(security_data[field]))

            columns.append('status')
            values.append(SecurityRepository.escape_value(security_data.get('status', 'VALIDATED')))

            columns.append('src_system')
            values.append(SecurityRepository.escape_value(security_data.get('src_system', 'GMP')))

            columns.extend(['is_active', 'created_by', 'created_at', 'updated_by', 'updated_at'])
            values.extend([
                'true' if security_data.get('is_active', True) else 'false',
                SecurityRepository.escape_value(created_by),
                f"'{timestamp_str}'",
                SecurityRepository.escape_value(created_by),
                f"'{timestamp_str}'",
            ])

            upsert_sql = f"""
            UPSERT INTO {SecurityRepository.DATABASE}.{SecurityRepository.TABLE_NAME}
            ({', '.join(columns)})
            VALUES ({', '.join(values)})
            """

            success = impala_manager.execute_write(upsert_sql, database=SecurityRepository.DATABASE)
            if success:
                logger.info(f"Successfully upserted security {security_id} ({security_data.get('security_name')})")
            return success

        except Exception as e:
            logger.error(f"Error upserting security: {str(e)}")
            return False


security_repository = SecurityRepository()
