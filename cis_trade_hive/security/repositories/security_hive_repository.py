"""
Security Hive Repository

Data access layer for security master data in Kudu tables.
All queries execute via Impala (no Django ORM).
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import json

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class SecurityHiveRepository:
    """Repository for security operations with Kudu via Impala"""

    DATABASE = 'gmp_cis'
    TABLE_NAME = 'cis_security'
    HISTORY_TABLE = 'cis_security_history'

    @staticmethod
    def escape_value(value: Any) -> str:
        """
        Escape value for SQL query.
        Uses backslash escaping for Impala compatibility.
        """
        if value is None or value == '':
            return 'NULL'
        if isinstance(value, bool):
            return 'true' if value else 'false'
        if isinstance(value, (int, float)):
            return str(value)
        # String - escape backslashes and single quotes
        escaped = str(value).replace('\\', '\\\\').replace("'", "\\'")
        return f"'{escaped}'"

    @staticmethod
    def get_all_securities(
        limit: int = 1000,
        status: Optional[str] = None,
        search: Optional[str] = None,
        currency: Optional[str] = None,
        security_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch all securities from Kudu with optional filters.

        Args:
            limit: Maximum number of records to return
            status: Filter by status (INITIAL, MODIFIED, VALIDATED)
            search: Search term for security_name or ISIN
            currency: Filter by currency_code
            security_type: Filter by security_type

        Returns:
            List of security dictionaries
        """
        try:
            query = f"""
            SELECT *
            FROM {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            WHERE 1=1
            """

            # Apply filters
            if status:
                query += f" AND status = {SecurityHiveRepository.escape_value(status)}"

            if search:
                search_term = f"%{search}%"
                sv = SecurityHiveRepository.escape_value(search_term)
                query += (
                    f" AND (LOWER(security_name) LIKE LOWER({sv})"
                    f" OR LOWER(isin) LIKE LOWER({sv})"
                    f" OR LOWER(security_description) LIKE LOWER({sv}))"
                )

            if currency:
                query += f" AND currency_code = {SecurityHiveRepository.escape_value(currency)}"

            if security_type:
                query += f" AND security_type = {SecurityHiveRepository.escape_value(security_type)}"

            # Order by src_system='CIS' first, then by most recent
            query += " ORDER BY CASE WHEN UPPER(src_system) = 'CIS' THEN 0 ELSE 1 END, created_at DESC"

            # Apply limit
            query += f" LIMIT {limit}"

            result = impala_manager.execute_query(query, database=SecurityHiveRepository.DATABASE)
            return result if result else []

        except Exception as e:
            logger.error(f"Error fetching securities: {str(e)}")
            return []

    @staticmethod
    def get_security_by_id(security_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch a single security by ID.

        Args:
            security_id: Security ID

        Returns:
            Security dictionary or None
        """
        try:
            query = f"""
            SELECT *
            FROM {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            WHERE security_id = {security_id}
            """

            result = impala_manager.execute_query(query, database=SecurityHiveRepository.DATABASE)
            return result[0] if result and len(result) > 0 else None

        except Exception as e:
            logger.error(f"Error fetching security {security_id}: {str(e)}")
            return None

    @staticmethod
    def get_security_by_isin(isin: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single security by ISIN.

        Args:
            isin: International Securities Identification Number

        Returns:
            Security dictionary or None
        """
        try:
            query = f"""
            SELECT *
            FROM {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            WHERE isin = {SecurityHiveRepository.escape_value(isin)}
            """

            result = impala_manager.execute_query(query, database=SecurityHiveRepository.DATABASE)
            return result[0] if result and len(result) > 0 else None

        except Exception as e:
            logger.error(f"Error fetching security by ISIN {isin}: {str(e)}")
            return None

    # -------------------------------------------------------------------------
    # Registry constants
    # -------------------------------------------------------------------------
    REGISTRY_TABLE = 'cis_security_id_registry'
    COUNTER_TABLE  = 'cis_security_id_counter'
    ID_FLOOR       = 100_000_000_000   # 12-digit IDs start here

    @staticmethod
    def _build_natural_key(security_data: Dict[str, Any]) -> tuple:
        """
        Derive the normalised composite natural key and its type.

        Cross-listed securities share the same ISIN but trade on different
        exchanges in different countries (e.g. ANZ Banking Group: same ISIN on
        ASX/AU and NZX/NZ — completely different instruments with different
        currencies and prices).  ISIN alone is therefore NOT unique.

        Priority (first matching rule wins):
          1. ISIN + exchange_code       → "ISIN_EXCH:<isin>:<exch>"
          2. ISIN + country_of_exchange → "ISIN_CTY:<isin>:<country>"
          3. ISIN only                  → "ISIN:<isin>"       (bonds/private)
          4. name + exchange_code       → "NAME_EXCH:<name>:<exch>"
          5. name + country_of_exchange → "NAME_CTY:<name>:<country>"
          6. name only                  → "NAME:<name>"       (last resort)

        Returns:
            (natural_key: str, key_type: str)
        """
        isin   = (security_data.get('isin')                or '').strip().upper()
        name   = (security_data.get('security_name')       or '').strip().upper()
        exch   = (security_data.get('exchange_code')       or '').strip().upper()
        cty    = (security_data.get('country_of_exchange') or '').strip().upper()

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
    def _get_or_allocate_security_id(
        security_data: Dict[str, Any],
        src_system: str,
        created_by: str,
    ) -> int:
        """
        Look up or allocate a stable 12-digit security_id via the registry.

        - If the natural key exists in cis_security_id_registry → return that ID.
        - If not → read cis_security_id_counter, allocate next ID, write both
          registry row and updated counter, then return the new ID.

        Args:
            security_data: Dict containing at least security_name + optionally isin/exchange_code
            src_system:    'CIS' for UI-created, 'GMP' for ETL
            created_by:    username or 'GMP_ETL'

        Returns:
            Stable 12-digit BIGINT security_id
        """
        natural_key, key_type = SecurityHiveRepository._build_natural_key(security_data)
        now_ms = int(datetime.now().timestamp() * 1000)
        db = SecurityHiveRepository.DATABASE
        esc = SecurityHiveRepository.escape_value

        # 1. Check registry
        lookup_sql = f"""
            SELECT security_id
            FROM {db}.{SecurityHiveRepository.REGISTRY_TABLE}
            WHERE natural_key = {esc(natural_key)}
            LIMIT 1
        """
        rows = impala_manager.execute_query(lookup_sql, database=db)
        if rows:
            return int(rows[0]['security_id'])

        # 2. Registry miss — read counter and claim next ID
        counter_sql = f"""
            SELECT next_id
            FROM {db}.{SecurityHiveRepository.COUNTER_TABLE}
            WHERE counter_id = 1
            LIMIT 1
        """
        counter_rows = impala_manager.execute_query(counter_sql, database=db)
        if counter_rows:
            new_id = int(counter_rows[0]['next_id'])
        else:
            # Counter not seeded yet — start at floor+1
            new_id = SecurityHiveRepository.ID_FLOOR + 1

        # 3. Write registry entry for this natural key
        isin_val = (security_data.get('isin')                or '').strip().upper()
        name_val = (security_data.get('security_name')       or '').strip()
        exch_val = (security_data.get('exchange_code')       or '').strip().upper()
        cty_val  = (security_data.get('country_of_exchange') or '').strip().upper()
        registry_sql = f"""
            UPSERT INTO {db}.{SecurityHiveRepository.REGISTRY_TABLE}
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
            UPSERT INTO {db}.{SecurityHiveRepository.COUNTER_TABLE}
            (counter_id, next_id, updated_at)
            VALUES (1, {new_id + 1}, {now_ms})
        """
        impala_manager.execute_write(counter_upsert_sql, database=db)

        logger.info(f"Registry: allocated security_id={new_id} for natural_key='{natural_key}'")
        return new_id

    @staticmethod
    def insert_security(security_data: Dict[str, Any], created_by: str) -> bool:
        """
        Insert a new security record into cis_security via the ID registry.

        The registry assigns a stable 12-digit ID based on the security's
        natural key (ISIN > name+exchange > name).  Subsequent inserts or
        reloads with the same natural key always receive the same ID.

        Args:
            security_data: Dictionary of security fields
            created_by: Username creating the security

        Returns:
            True if successful, False otherwise
        """
        try:
            # Stable 12-digit ID from registry (replaces timestamp-based ID)
            security_id = SecurityHiveRepository._get_or_allocate_security_id(
                security_data,
                src_system='CIS',
                created_by=created_by,
            )
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Build column and value lists
            columns = ['security_id']
            values = [str(security_id)]

            # Add all business fields from security_data
            field_mapping = {
                'record_type': str,
                'security_name': str,
                'isin': str,
                'security_description': str,
                'issuer': str,
                'ticker': str,
                'industry': str,
                'security_type': str,
                'investment_type': str,
                'issuer_type': str,
                'quoted_unquoted': str,
                'country_of_incorporation': str,
                'country_of_exchange': str,
                'country_of_issue': str,
                'exchange_code': str,
                'currency_code': str,
                'price': float,
                'shares_outstanding': int,
                'beta': float,
                'par_value': float,
                'pct_hld_entity_1': str,
                'pct_hld_entity_2': str,
                'pct_hld_entity_3': str,
                'pct_hld_entity_aggr': str,
                'substantial_10_pct': str,
                'cels': str,
                'pevc_s32_devest': str,
                's32_representative': str,
                'basel_iv_fund': str,
                'mas_643_entity_type': str,
                'mas_6d_code': str,
                'fin_nonfin_ind': str,
                'business_unit_head': str,
                'person_in_charge': str,
                'core_noncore': str,
                'fund_index_fund': str,
                'management_limit_classification': str,
                'relative_index': str,
            }

            for field, field_type in field_mapping.items():
                if field in security_data:
                    columns.append(field)
                    values.append(SecurityHiveRepository.escape_value(security_data[field]))

            # Add status
            columns.append('status')
            values.append(SecurityHiveRepository.escape_value(security_data.get('status', 'INITIAL')))

            # Add src_system - 'CIS' for records created via UI
            columns.append('src_system')
            values.append("'CIS'")

            # Add audit fields
            columns.extend(['is_active', 'created_by', 'created_at', 'updated_by', 'updated_at'])
            values.extend([
                'true',
                SecurityHiveRepository.escape_value(created_by),
                f"'{timestamp_str}'",
                SecurityHiveRepository.escape_value(created_by),
                f"'{timestamp_str}'"
            ])

            # Build UPSERT statement
            upsert_sql = f"""
            UPSERT INTO {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            ({', '.join(columns)})
            VALUES ({', '.join(values)})
            """

            success = impala_manager.execute_write(upsert_sql, database=SecurityHiveRepository.DATABASE)

            if success:
                logger.info(f"Successfully inserted security {security_id}")

            return success

        except Exception as e:
            logger.error(f"Error inserting security: {str(e)}")
            return False

    @staticmethod
    def update_security(security_id: int, security_data: Dict[str, Any], updated_by: str) -> bool:
        """
        Update an existing security record in Kudu.

        Args:
            security_id: Security ID to update
            security_data: Dictionary of fields to update
            updated_by: Username updating the security

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Build SET clause
            set_clauses = []

            # Update business fields if provided
            updatable_fields = [
                'record_type', 'security_name', 'isin', 'security_description', 'issuer', 'ticker',
                'industry', 'security_type', 'investment_type', 'issuer_type', 'quoted_unquoted',
                'country_of_incorporation', 'country_of_exchange', 'country_of_issue',
                'exchange_code', 'currency_code',
                'price', 'shares_outstanding', 'beta', 'par_value',
                'pct_hld_entity_1', 'pct_hld_entity_2', 'pct_hld_entity_3', 'pct_hld_entity_aggr',
                'substantial_10_pct', 'cels', 'pevc_s32_devest', 's32_representative',
                'basel_iv_fund', 'mas_643_entity_type', 'mas_6d_code',
                'fin_nonfin_ind', 'business_unit_head', 'person_in_charge', 'core_noncore',
                'fund_index_fund', 'management_limit_classification', 'relative_index',
                'status',
            ]

            for field in updatable_fields:
                if field in security_data:
                    set_clauses.append(f"{field} = {SecurityHiveRepository.escape_value(security_data[field])}")

            # Always update audit fields
            set_clauses.append(f"updated_by = {SecurityHiveRepository.escape_value(updated_by)}")
            set_clauses.append(f"updated_at = '{timestamp_str}'")

            if not set_clauses:
                logger.warning(f"No fields to update for security {security_id}")
                return False

            # Build UPDATE statement
            update_sql = f"""
            UPDATE {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            SET {', '.join(set_clauses)}
            WHERE security_id = {security_id}
            """

            success = impala_manager.execute_write(update_sql, database=SecurityHiveRepository.DATABASE)

            if success:
                logger.info(f"Successfully updated security {security_id}")

            return success

        except Exception as e:
            logger.error(f"Error updating security {security_id}: {str(e)}")
            return False

    @staticmethod
    def update_security_status(security_id: int, status: str, updated_by: str) -> bool:
        """
        Update security status.

        Args:
            security_id: Security ID
            status: New status
            updated_by: Username updating

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            set_clauses = [
                f"status = {SecurityHiveRepository.escape_value(status)}",
                f"updated_by = {SecurityHiveRepository.escape_value(updated_by)}",
                f"updated_at = '{timestamp_str}'"
            ]

            if status == 'VALIDATED':
                set_clauses.append("is_active = true")

            update_sql = f"""
            UPDATE {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            SET {', '.join(set_clauses)}
            WHERE security_id = {security_id}
            """

            success = impala_manager.execute_write(update_sql, database=SecurityHiveRepository.DATABASE)

            if success:
                logger.info(f"Successfully updated security {security_id} status to {status}")

            return success

        except Exception as e:
            logger.error(f"Error updating security status {security_id}: {str(e)}")
            return False

    @staticmethod
    def get_statistics() -> Dict[str, Any]:
        """
        Get security statistics for dashboard.

        Returns:
            Dictionary of statistics
        """
        try:
            # Count by status
            status_query = f"""
            SELECT status, COUNT(*) as count
            FROM {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            GROUP BY status
            """
            status_results = impala_manager.execute_query(status_query, database=SecurityHiveRepository.DATABASE)

            status_counts = {}
            total_securities = 0
            validated_securities = 0
            initial_securities = 0
            modified_securities = 0

            if status_results:
                for row in status_results:
                    status = row.get('status', 'Unknown')
                    count = row.get('count', 0)
                    status_counts[status] = count
                    total_securities += count

                    if status == 'VALIDATED':
                        validated_securities += count
                    elif status == 'INITIAL':
                        initial_securities += count
                    elif status == 'MODIFIED':
                        modified_securities += count

            # Count by Quoted/Unquoted
            quoted_query = f"""
            SELECT quoted_unquoted, COUNT(*) as count
            FROM {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            GROUP BY quoted_unquoted
            ORDER BY count DESC
            """
            quoted_results = impala_manager.execute_query(quoted_query, database=SecurityHiveRepository.DATABASE)

            quoted_unquoted = []
            if quoted_results:
                quoted_unquoted = [{'quoted_unquoted': row.get('quoted_unquoted', 'N/A') or 'N/A', 'count': row.get('count', 0)}
                                  for row in quoted_results]

            # Count by security type
            type_query = f"""
            SELECT security_type, COUNT(*) as count
            FROM {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            GROUP BY security_type
            ORDER BY count DESC
            LIMIT 10
            """
            type_results = impala_manager.execute_query(type_query, database=SecurityHiveRepository.DATABASE)

            security_types = []
            if type_results:
                security_types = [{'security_type': row.get('security_type', 'Unknown'), 'count': row.get('count', 0)}
                                 for row in type_results]

            # Count by currency
            currency_query = f"""
            SELECT currency_code, COUNT(*) as count
            FROM {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            GROUP BY currency_code
            ORDER BY count DESC
            LIMIT 10
            """
            currency_results = impala_manager.execute_query(currency_query, database=SecurityHiveRepository.DATABASE)

            currencies = []
            if currency_results:
                currencies = [{'currency_code': row.get('currency_code', 'Unknown'), 'count': row.get('count', 0)}
                             for row in currency_results]

            # Count by investment type
            investment_query = f"""
            SELECT investment_type, COUNT(*) as count
            FROM {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            GROUP BY investment_type
            ORDER BY count DESC
            LIMIT 10
            """
            investment_results = impala_manager.execute_query(investment_query, database=SecurityHiveRepository.DATABASE)

            investment_types = []
            if investment_results:
                investment_types = [{'investment_type': row.get('investment_type', 'Unknown'), 'count': row.get('count', 0)}
                                   for row in investment_results]

            # Count by industry
            industry_query = f"""
            SELECT industry, COUNT(*) as count
            FROM {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.TABLE_NAME}
            GROUP BY industry
            ORDER BY count DESC
            LIMIT 15
            """
            industry_results = impala_manager.execute_query(industry_query, database=SecurityHiveRepository.DATABASE)

            industries = []
            if industry_results:
                industries = [{'industry': row.get('industry', 'Unknown'), 'count': row.get('count', 0)}
                             for row in industry_results]

            return {
                'total_securities': total_securities,
                'validated_securities': validated_securities,
                'initial_securities': initial_securities,
                'modified_securities': modified_securities,
                'status_breakdown': status_counts,
                'by_quoted_unquoted': quoted_unquoted,
                'by_security_type': security_types,
                'by_currency': currencies,
                'by_investment_type': investment_types,
                'by_industry': industries,
            }

        except Exception as e:
            logger.error(f"Error getting statistics: {str(e)}")
            return {
                'total_securities': 0,
                'validated_securities': 0,
                'initial_securities': 0,
                'modified_securities': 0,
                'status_breakdown': {},
                'by_quoted_unquoted': [],
                'by_security_type': [],
                'by_currency': [],
                'by_investment_type': [],
                'by_industry': [],
            }

    @staticmethod
    def insert_security_history(
        security_id: int,
        security_name: str,
        isin: str,
        action: str,
        status: str,
        changes: Dict[str, Any],
        comments: str,
        performed_by: str
    ) -> bool:
        """
        Insert a security history record.

        Args:
            security_id: Security ID
            security_name: Security name (denormalized)
            isin: ISIN (denormalized)
            action: Action type (CREATE, UPDATE, SUBMIT, APPROVE, REJECT)
            status: Status after action
            changes: Dictionary of changes
            comments: User comments
            performed_by: Username who performed action

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp_ms = int(datetime.now().timestamp() * 1000)
            history_id = timestamp_ms  # PK — keep as BIGINT ms
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Convert changes dict to JSON string
            changes_json = json.dumps(changes) if changes else '{}'

            insert_sql = f"""
            UPSERT INTO {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.HISTORY_TABLE}
            (history_id, security_id, security_name, isin, action, status, changes, comments, performed_by, performed_at)
            VALUES (
                {history_id},
                {security_id},
                {SecurityHiveRepository.escape_value(security_name)},
                {SecurityHiveRepository.escape_value(isin)},
                {SecurityHiveRepository.escape_value(action)},
                {SecurityHiveRepository.escape_value(status)},
                {SecurityHiveRepository.escape_value(changes_json)},
                {SecurityHiveRepository.escape_value(comments)},
                {SecurityHiveRepository.escape_value(performed_by)},
                '{timestamp_str}'
            )
            """

            success = impala_manager.execute_write(insert_sql, database=SecurityHiveRepository.DATABASE)

            if success:
                logger.info(f"Successfully inserted history for security {security_id}, action {action}")

            return success

        except Exception as e:
            logger.error(f"Error inserting security history: {str(e)}")
            return False

    @staticmethod
    def get_security_history(security_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get history records for a security.

        Args:
            security_id: Security ID
            limit: Maximum number of records

        Returns:
            List of history dictionaries
        """
        try:
            query = f"""
            SELECT *
            FROM {SecurityHiveRepository.DATABASE}.{SecurityHiveRepository.HISTORY_TABLE}
            WHERE security_id = {security_id}
            ORDER BY performed_at DESC
            LIMIT {limit}
            """

            result = impala_manager.execute_query(query, database=SecurityHiveRepository.DATABASE)
            return result if result else []

        except Exception as e:
            logger.error(f"Error fetching security history {security_id}: {str(e)}")
            return []


# Create singleton instance
security_hive_repository = SecurityHiveRepository()
