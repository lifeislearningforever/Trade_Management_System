"""
Trade Dropdown Service

Provides dropdown options for trade forms by querying:
1. UDF field table (cis_udf_field) for configurable dropdown options
2. Counterparty table for brokers/custodians
3. Lookup tables as fallback

UDF Simplified Logic:
- Object Type: TRADE
- Field Name: The dropdown field (e.g., 'Fund Type', 'Selling Rule')
- Field Value: The dropdown option values (created by admin/system)
"""

import logging
from typing import Dict, List, Any

from core.repositories.impala_connection import impala_manager
from trade.repositories.trade_validation_repository import trade_validation_repository
from udf.repositories.udf_field_repository import udf_field_repository

logger = logging.getLogger(__name__)


class TradeDropdownService:
    """Service for fetching dropdown options for trade forms"""

    DATABASE = 'gmp_cis'
    OBJECT_TYPE = 'TRADE'  # UDF Object Type for Trade entity

    # =========================================================================
    # UDF FIELD HELPER
    # =========================================================================

    def _get_udf_options(self, field_name: str) -> List[Dict[str, Any]]:
        """
        Get dropdown options from UDF field table.

        Args:
            field_name: The field name in UDF table (e.g., 'Fund Type', 'Selling Rule')

        Returns:
            List of options with 'value' and 'label' keys
        """
        try:
            # Query UDF field values for this field_name
            results = udf_field_repository.get_field_values(self.OBJECT_TYPE, field_name)
            if results:
                logger.debug(f"Loaded {len(results)} options from UDF for {field_name}")
                return [
                    {
                        'value': r.get('field_value', ''),
                        'label': r.get('field_value', '').replace('_', ' ').title()
                    }
                    for r in results if r.get('field_value')
                ]
        except Exception as e:
            logger.warning(f"Could not load UDF options for {field_name}: {str(e)}")
        return []

    def get_all_dropdown_options(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all dropdown options for trade form.

        Returns:
            Dictionary with dropdown options for each field
        """
        return {
            'trade_types': self.get_trade_types(),
            'trade_statuses': self.get_trade_statuses(),
            'portfolios': self.get_portfolios(),
            'currencies': self.get_currencies(),
            'securities': self.get_securities(),
            'counterparties': self.get_counterparties(),
            'brokers': self.get_brokers(),
            'gl_fund_types': self.get_gl_fund_types(),
            'gl_cost_centres': self.get_gl_cost_centres(),
            'gl_account_codes': self.get_gl_account_codes(),
            'selling_rules': self.get_selling_rules(),
            'custodians': self.get_custodians(),
            'sub_custodians': self.get_sub_custodians(),
            'open_close_options': self.get_open_close_options(),
            'extensions': self.get_extensions(),
            'fund_types': self.get_fund_types(),
            'income_exp_types': self.get_income_exp_types(),
            'uobn_options': self.get_uobn_options(),
            'section_options': self.get_section_options(),
            'revision_codes': self.get_revision_codes(),
            'amor_methods': self.get_amor_methods(),
            'delivery_types': self.get_delivery_types(),
            'income_types': self.get_income_types(),
            'split_types': self.get_split_types(),
            'reduction_types': self.get_reduction_types(),
        }

    def _execute_lookup_query(self, table_name: str, value_col: str, label_col: str) -> List[Dict[str, Any]]:
        """Execute query on lookup table and return options."""
        try:
            query = f"""
            SELECT {value_col} as value, {label_col} as label
            FROM {self.DATABASE}.{table_name}
            WHERE is_active = true
            ORDER BY display_order, {label_col}
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            return results if results else []
        except Exception as e:
            logger.warning(f"Could not load {table_name}: {str(e)}")
            return []

    # =========================================================================
    # TRADE TYPES
    # =========================================================================

    def get_trade_types(self) -> List[Dict[str, Any]]:
        """Get trade type options."""
        return [
            {'value': 'BUY', 'label': 'Buy'},
            {'value': 'SELL', 'label': 'Sell'},
            {'value': 'ADD_LONG', 'label': 'Add Long'},
            {'value': 'DELIVER_LONG', 'label': 'Deliver Long'},
            {'value': 'REDUCTION_BASIS', 'label': 'Reduction Basis'},
            {'value': 'INCOME', 'label': 'Income'},
            {'value': 'SPLIT_TRANSACTION', 'label': 'Split Transaction'},
        ]

    def get_trade_statuses(self) -> List[Dict[str, Any]]:
        """Get trade status options from lookup table."""
        options = self._execute_lookup_query(
            'cis_trade_status_lookup', 'status_code', 'status_name'
        )
        if not options:
            # Fallback defaults
            options = [
                {'value': 'PENDING', 'label': 'Pending'},
                {'value': 'CONFIRMED', 'label': 'Confirmed'},
                {'value': 'MATCHED', 'label': 'Matched'},
                {'value': 'SETTLED', 'label': 'Settled'},
                {'value': 'FAILED', 'label': 'Failed'},
                {'value': 'CANCELLED', 'label': 'Cancelled'},
            ]
        return options

    # =========================================================================
    # REFERENCES (Portfolio, Security, Counterparty)
    # =========================================================================

    def get_portfolios(self, search: str = None) -> List[Dict[str, Any]]:
        """Get valid portfolios for dropdown."""
        portfolios = trade_validation_repository.get_valid_portfolios(search=search)
        return [
            {
                'value': p.get('portfolio_short_name', ''),
                'label': p.get('portfolio_short_name', ''),
                'currency': p.get('currency', ''),
                'manager': p.get('manager', '')
            }
            for p in portfolios
        ]

    def get_securities(self, search: str = None) -> List[Dict[str, Any]]:
        """Get valid securities for dropdown."""
        securities = trade_validation_repository.get_valid_securities(search=search)
        return [
            {
                'value': s.get('security_label', ''),
                'label': f"{s.get('security_label', '')} ({s.get('ticker', s.get('isin', ''))})",
                'security_type': s.get('security_type', ''),
                'currency': s.get('currency_code', ''),
                'price': s.get('current_price', 0)
            }
            for s in securities
        ]

    def get_counterparties(self, search: str = None) -> List[Dict[str, Any]]:
        """Get valid counterparties (parties) for dropdown."""
        counterparties = trade_validation_repository.get_valid_counterparties(search=search)
        return [
            {
                'value': c.get('party_short_name', ''),
                'label': f"{c.get('party_full_name', '')} ({c.get('party_short_name', '')})",
                'country': c.get('country', ''),
                'is_broker': c.get('is_broker', False)
            }
            for c in counterparties
        ]

    # =========================================================================
    # BROKER & GL OPTIONS
    # =========================================================================

    def get_brokers(self) -> List[Dict[str, Any]]:
        """
        Get broker options - first from cis_trade_charge_lut (for charge calculation),
        then from cis_party table for additional brokers.
        """
        brokers = []
        seen_brokers = set()

        # First, get brokers from cis_trade_charge_lut (these have charges configured)
        try:
            query = f"""
            SELECT DISTINCT broker
            FROM {self.DATABASE}.cis_trade_charge_lut
            WHERE broker IS NOT NULL AND broker != ''
            ORDER BY broker
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                for r in results:
                    broker = r.get('broker', '')
                    if broker and broker not in seen_brokers:
                        brokers.append({
                            'value': broker,
                            'label': broker,
                            'country': '',
                            'has_charges': True
                        })
                        seen_brokers.add(broker)
                logger.debug(f"Loaded {len(brokers)} brokers from cis_trade_charge_lut")
        except Exception as e:
            logger.warning(f"Could not load brokers from cis_trade_charge_lut: {str(e)}")

        # Then add brokers from cis_party table
        try:
            query = f"""
            SELECT party_short_name as value,
                   COALESCE(party_full_name, party_short_name) as label,
                   country
            FROM {self.DATABASE}.cis_party
            WHERE is_broker = true
              AND is_active = true
              AND (is_deleted = false OR is_deleted IS NULL)
            ORDER BY party_short_name
            LIMIT 200
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                for r in results:
                    value = r.get('value', '')
                    label = r.get('label', '')
                    if value and value not in seen_brokers:
                        brokers.append({
                            'value': value,
                            'label': f"{label} ({value})" if label != value else value,
                            'country': r.get('country', ''),
                            'has_charges': False
                        })
                        seen_brokers.add(value)
        except Exception as e:
            logger.warning(f"Could not load brokers from cis_party: {str(e)}")

        if not brokers:
            # Fallback defaults
            brokers = [
                {'value': 'GS', 'label': 'Goldman Sachs', 'has_charges': False},
                {'value': 'MS', 'label': 'Morgan Stanley', 'has_charges': False},
                {'value': 'JPM', 'label': 'JP Morgan', 'has_charges': False},
                {'value': 'UBS', 'label': 'UBS', 'has_charges': False},
                {'value': 'CITI', 'label': 'Citibank', 'has_charges': False},
            ]

        return brokers

    def get_gl_fund_types(self) -> List[Dict[str, Any]]:
        """Get GL fund type options from UDF field table."""
        # Try UDF first
        options = self._get_udf_options('GL Fund Type')
        if options:
            return options

        # Fallback to lookup table
        options = self._execute_lookup_query(
            'cis_gl_fund_type_lookup', 'fund_type_code', 'fund_type_name'
        )
        if not options:
            options = [
                {'value': 'TRADING', 'label': 'Trading Book'},
                {'value': 'BANKING', 'label': 'Banking Book'},
                {'value': 'INVESTMENT', 'label': 'Investment Book'},
                {'value': 'HEDGE', 'label': 'Hedge Book'},
            ]
        return options

    def get_gl_cost_centres(self) -> List[Dict[str, Any]]:
        """Get GL cost centre options from UDF field table."""
        # Try UDF first
        options = self._get_udf_options('GL Cost Centre')
        if options:
            return options

        # Fallback to lookup table
        options = self._execute_lookup_query(
            'cis_gl_cost_centre_lookup', 'cost_centre_code', 'cost_centre_name'
        )
        if not options:
            options = [
                {'value': 'CC-001', 'label': 'Treasury'},
                {'value': 'CC-002', 'label': 'Investment Management'},
                {'value': 'CC-003', 'label': 'Trading Desk'},
            ]
        return options

    def get_gl_account_codes(self) -> List[Dict[str, Any]]:
        """Get GL account code options from UDF field table."""
        # Try UDF first
        options = self._get_udf_options('GL Account Code')
        if options:
            return options

        # Fallback to lookup table
        options = self._execute_lookup_query(
            'cis_gl_account_code_lookup', 'account_code', 'account_name'
        )
        if not options:
            options = [
                {'value': 'ACC-1001', 'label': 'Trading Securities'},
                {'value': 'ACC-1002', 'label': 'Available for Sale'},
                {'value': 'ACC-1003', 'label': 'Held to Maturity'},
            ]
        return options

    # =========================================================================
    # SELLING & CUSTODIAN OPTIONS
    # =========================================================================

    def get_selling_rules(self) -> List[Dict[str, Any]]:
        """Get selling rule options from UDF field table."""
        # Try UDF first
        options = self._get_udf_options('Selling Rule')
        if options:
            return options

        # Fallback to lookup table
        options = self._execute_lookup_query(
            'cis_selling_rule_lookup', 'rule_code', 'rule_name'
        )
        if not options:
            options = [
                {'value': 'FIFO', 'label': 'First In First Out'},
                {'value': 'LIFO', 'label': 'Last In First Out'},
                {'value': 'WAVG', 'label': 'Weighted Average'},
                {'value': 'SPEC', 'label': 'Specific Identification'},
            ]
        return options

    def get_custodians(self) -> List[Dict[str, Any]]:
        """
        Get custodian options from cis_party table where is_custodian=true.
        Falls back to lookup table if party query fails.
        """
        try:
            query = f"""
            SELECT party_short_name as value,
                   COALESCE(party_full_name, party_short_name) as label,
                   country
            FROM {self.DATABASE}.cis_party
            WHERE is_custodian = true
              AND is_active = true
              AND (is_deleted = false OR is_deleted IS NULL)
            ORDER BY party_short_name
            LIMIT 200
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                logger.debug(f"Loaded {len(results)} custodians from cis_party table")
                return [
                    {
                        'value': r.get('value', ''),
                        'label': f"{r.get('label', '')} ({r.get('value', '')})" if r.get('label') != r.get('value') else r.get('value', ''),
                        'country': r.get('country', '')
                    }
                    for r in results
                ]
        except Exception as e:
            logger.warning(f"Could not load custodians from cis_party: {str(e)}")

        # Fallback to lookup table
        options = self._execute_lookup_query(
            'cis_custodian_lookup', 'custodian_code', 'custodian_name'
        )
        if not options:
            options = [
                {'value': 'DBS', 'label': 'DBS Bank'},
                {'value': 'SCB', 'label': 'Standard Chartered'},
                {'value': 'CITI', 'label': 'Citibank'},
                {'value': 'HSBC', 'label': 'HSBC'},
            ]
        return options

    def get_sub_custodians(self) -> List[Dict[str, Any]]:
        """Get sub-custodian options from UDF field table."""
        # Try UDF first
        options = self._get_udf_options('Sub Custodian')
        if options:
            return options

        # Fallback to lookup table
        options = self._execute_lookup_query(
            'cis_sub_custodian_lookup', 'sub_custodian_code', 'sub_custodian_name'
        )
        if not options:
            options = [
                {'value': 'DBS-SG', 'label': 'DBS Bank Singapore'},
                {'value': 'SCB-SG', 'label': 'Standard Chartered SG'},
                {'value': 'CITI-SG', 'label': 'Citibank Singapore'},
            ]
        return options

    # =========================================================================
    # UDF OPTIONS
    # =========================================================================

    def get_open_close_options(self) -> List[Dict[str, Any]]:
        """Get open/close position options from UDF field table."""
        # Try UDF first
        options = self._get_udf_options('Open/Close Position')
        if options:
            return options

        # Fallback defaults
        return [
            {'value': 'OPEN', 'label': 'Open'},
            {'value': 'CLOSE', 'label': 'Close'},
        ]

    def get_extensions(self) -> List[Dict[str, Any]]:
        """Get extension options from UDF field table."""
        # Try UDF first
        options = self._get_udf_options('Extension')
        if options:
            return options

        # Fallback to lookup table
        options = self._execute_lookup_query(
            'cis_extension_lookup', 'extension_code', 'extension_name'
        )
        if not options:
            options = [
                {'value': 'NONE', 'label': 'None'},
                {'value': 'EXT-1D', 'label': '1 Day Extension'},
                {'value': 'EXT-2D', 'label': '2 Day Extension'},
            ]
        return options

    def get_fund_types(self) -> List[Dict[str, Any]]:
        """Get fund type UDF options from UDF field table."""
        # Try UDF first
        options = self._get_udf_options('Fund Type')
        if options:
            return options

        # Fallback to lookup table
        options = self._execute_lookup_query(
            'cis_fund_type_lookup', 'fund_type_code', 'fund_type_name'
        )
        if not options:
            options = [
                {'value': 'EQUITY', 'label': 'Equity'},
                {'value': 'FIXED_INCOME', 'label': 'Fixed Income'},
                {'value': 'MONEY_MARKET', 'label': 'Money Market'},
                {'value': 'BALANCED', 'label': 'Balanced'},
            ]
        return options

    def get_income_exp_types(self) -> List[Dict[str, Any]]:
        """Get income/expense type UDF options from UDF field table."""
        # Try UDF first
        options = self._get_udf_options('Income/Exp Type')
        if options:
            return options

        # Fallback to lookup table
        options = self._execute_lookup_query(
            'cis_income_exp_type_lookup', 'type_code', 'type_name'
        )
        if not options:
            options = [
                {'value': 'TRADING', 'label': 'Trading'},
                {'value': 'INVESTMENT', 'label': 'Investment'},
                {'value': 'DIVIDEND', 'label': 'Dividend'},
                {'value': 'INTEREST', 'label': 'Interest'},
            ]
        return options

    def get_uobn_options(self) -> List[Dict[str, Any]]:
        """Get UOBN/UOBN-HK UDF options from UDF field table."""
        # Try UDF first
        options = self._get_udf_options('UOBN/UOBN-HK')
        if options:
            return options

        # Fallback to lookup table
        options = self._execute_lookup_query(
            'cis_uobn_lookup', 'uobn_code', 'uobn_name'
        )
        if not options:
            options = [
                {'value': 'UOBN-SG', 'label': 'UOBN Singapore'},
                {'value': 'UOBN-HK', 'label': 'UOBN Hong Kong'},
                {'value': 'UOBN-MY', 'label': 'UOBN Malaysia'},
            ]
        return options

    def get_section_options(self) -> List[Dict[str, Any]]:
        """Get Section 31/26 UDF options from UDF field table."""
        # Try UDF first
        options = self._get_udf_options('Section 31/26')
        if options:
            return options

        # Fallback to lookup table
        options = self._execute_lookup_query(
            'cis_section_lookup', 'section_code', 'section_name'
        )
        if not options:
            options = [
                {'value': 'SEC_31', 'label': 'Section 31'},
                {'value': 'SEC_26', 'label': 'Section 26'},
                {'value': 'BOTH', 'label': 'Both'},
                {'value': 'NA', 'label': 'N/A'},
            ]
        return options

    def get_revision_codes(self) -> List[Dict[str, Any]]:
        """Get revision code UDF options from UDF field table."""
        # Try UDF first
        options = self._get_udf_options('Revision Code')
        if options:
            return options

        # Fallback to lookup table
        options = self._execute_lookup_query(
            'cis_revision_code_lookup', 'revision_code', 'revision_name'
        )
        if not options:
            options = [
                {'value': 'REV-001', 'label': 'Revision 001'},
                {'value': 'REV-002', 'label': 'Revision 002'},
                {'value': 'NA', 'label': 'N/A'},
            ]
        return options

    def get_amor_methods(self) -> List[Dict[str, Any]]:
        """Get amortisation method options from UDF field table."""
        # Try UDF first
        options = self._get_udf_options('Amortisation Method')
        if options:
            return options

        # Fallback to lookup table
        options = self._execute_lookup_query(
            'cis_amor_method_lookup', 'method_code', 'method_name'
        )
        if not options:
            options = [
                {'value': 'STD', 'label': 'Standard'},
                {'value': 'EFF_INT', 'label': 'Effective Interest'},
                {'value': 'STRAIGHT', 'label': 'Straight Line'},
                {'value': 'NONE', 'label': 'None'},
            ]
        return options

    # =========================================================================
    # TRADE TYPE SPECIFIC OPTIONS
    # =========================================================================

    def get_delivery_types(self) -> List[Dict[str, Any]]:
        """Get delivery type options for Deliver Long from UDF field table."""
        # Try UDF first
        options = self._get_udf_options('Delivery Type')
        if options:
            return options

        # Fallback to lookup table
        options = self._execute_lookup_query(
            'cis_delivery_type_lookup', 'delivery_type_code', 'delivery_type_name'
        )
        if not options:
            options = [
                {'value': 'TRANSFER', 'label': 'Transfer'},
                {'value': 'CORP_ACTION', 'label': 'Corporate Action'},
                {'value': 'SETTLEMENT', 'label': 'Settlement'},
                {'value': 'REDEMPTION', 'label': 'Redemption'},
            ]
        return options

    def get_income_types(self) -> List[Dict[str, Any]]:
        """Get income type options for Income tab from UDF field table."""
        # Try UDF first
        options = self._get_udf_options('Income Type')
        if options:
            return options

        # Fallback to lookup table
        options = self._execute_lookup_query(
            'cis_income_type_lookup', 'income_type_code', 'income_type_name'
        )
        if not options:
            options = [
                {'value': 'DIVIDEND', 'label': 'Dividend'},
                {'value': 'STOCK_DIV', 'label': 'Stock Dividend'},
                {'value': 'INTEREST', 'label': 'Interest'},
                {'value': 'PREMIUM', 'label': 'Premium'},
                {'value': 'DISTRIBUTION', 'label': 'Distribution'},
            ]
        return options

    def get_split_types(self) -> List[Dict[str, Any]]:
        """Get split type options for Split Transaction from UDF field table."""
        # Try UDF first
        options = self._get_udf_options('Split Type')
        if options:
            return options

        # Fallback to lookup table
        options = self._execute_lookup_query(
            'cis_split_type_lookup', 'split_type_code', 'split_type_name'
        )
        if not options:
            options = [
                {'value': 'STOCK_SPLIT', 'label': 'Stock Split'},
                {'value': 'REVERSE_SPLIT', 'label': 'Reverse Split'},
                {'value': 'LOT_SPLIT', 'label': 'Lot Split'},
                {'value': 'BONUS_ISSUE', 'label': 'Bonus Issue'},
            ]
        return options

    def get_reduction_types(self) -> List[Dict[str, Any]]:
        """Get reduction type options for Reduction Basis from UDF field table."""
        # Try UDF first
        options = self._get_udf_options('Reduction Type')
        if options:
            return options

        # Fallback to lookup table
        options = self._execute_lookup_query(
            'cis_reduction_type_lookup', 'reduction_type_code', 'reduction_type_name'
        )
        if not options:
            options = [
                {'value': 'RETURN_CAPITAL', 'label': 'Return of Capital'},
                {'value': 'AMORTIZATION', 'label': 'Amortization'},
                {'value': 'WRITEDOWN', 'label': 'Write-down'},
                {'value': 'PARTIAL_REDEMP', 'label': 'Partial Redemption'},
            ]
        return options


    # =========================================================================
    # CURRENCY & PRICE METHODS (for cascading dropdown)
    # =========================================================================

    def get_currencies(self) -> List[Dict[str, Any]]:
        """
        Get available currencies from both cis_security_kudu and cis_equity_price.
        Returns combined unique currencies for the currency dropdown.
        """
        currencies_set = set()

        # Get currencies from cis_security_kudu
        try:
            query = f"""
            SELECT DISTINCT currency_code
            FROM {self.DATABASE}.cis_security_kudu
            WHERE (is_active = true OR is_active IS NULL)
              AND currency_code IS NOT NULL
              AND currency_code <> ''
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                for r in results:
                    if r.get('currency_code'):
                        currencies_set.add(r.get('currency_code'))
                logger.debug(f"Loaded {len(results)} currencies from cis_security_kudu")
        except Exception as e:
            logger.warning(f"Could not load currencies from cis_security_kudu: {str(e)}")

        # Get currencies from cis_equity_price (may have additional currencies)
        try:
            query = f"""
            SELECT DISTINCT currency_code
            FROM {self.DATABASE}.cis_equity_price
            WHERE (is_active = true OR is_active IS NULL)
              AND currency_code IS NOT NULL
              AND currency_code <> ''
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                for r in results:
                    if r.get('currency_code'):
                        currencies_set.add(r.get('currency_code'))
                logger.debug(f"Loaded {len(results)} currencies from cis_equity_price")
        except Exception as e:
            logger.warning(f"Could not load currencies from cis_equity_price: {str(e)}")

        # Convert to sorted list of dicts
        if currencies_set:
            return [
                {'value': c, 'label': c}
                for c in sorted(currencies_set)
            ]

        # Fallback to reference_data currencies
        try:
            query = f"""
            SELECT currency_code, currency_name
            FROM {self.DATABASE}.cis_currency
            WHERE is_active = true
            ORDER BY currency_code
            LIMIT 50
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)
            if results:
                return [
                    {
                        'value': r.get('currency_code', ''),
                        'label': f"{r.get('currency_code', '')} - {r.get('currency_name', '')}"
                    }
                    for r in results if r.get('currency_code')
                ]
        except Exception as e:
            logger.warning(f"Could not load currencies: {str(e)}")

        # Final fallback
        return [
            {'value': 'USD', 'label': 'USD - US Dollar'},
            {'value': 'SGD', 'label': 'SGD - Singapore Dollar'},
            {'value': 'EUR', 'label': 'EUR - Euro'},
            {'value': 'GBP', 'label': 'GBP - British Pound'},
        ]

    def get_securities_by_currency(self, currency_code: str) -> List[Dict[str, Any]]:
        """
        Get securities filtered by currency code.
        Combines securities from cis_security_kudu and cis_equity_price.
        Price source: cis_equity_price only (cis_security_kudu price is ignored).
        """
        if not currency_code:
            return []

        securities_dict = {}  # key: security_name, value: security data

        # First, get securities from cis_security_kudu (base data only, price set to 0)
        try:
            query = f"""
            SELECT
                security_name,
                isin,
                exchange_code as market
            FROM {self.DATABASE}.cis_security_kudu
            WHERE currency_code = '{currency_code}'
              AND (is_active = true OR is_active IS NULL)
            ORDER BY security_name
            LIMIT 500
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)

            if results:
                for r in results:
                    sec_name = r.get('security_name', '')
                    if sec_name:
                        securities_dict[sec_name] = {
                            'value': sec_name,
                            'label': f"{sec_name} ({r.get('isin', '')})",
                            'isin': r.get('isin', ''),
                            'price': 0,
                            'market': r.get('market', ''),
                            'price_date': '',
                            'source': 'security'
                        }
                logger.debug(f"Loaded {len(results)} securities from cis_security_kudu for {currency_code}")
        except Exception as e:
            logger.warning(f"Error loading from cis_security_kudu: {str(e)}")

        # Then, overlay equity prices from cis_equity_price (only source for prices)
        try:
            query = f"""
            SELECT
                security_label,
                isin,
                main_closing_price as price,
                price_date
            FROM {self.DATABASE}.cis_equity_price
            WHERE currency_code = '{currency_code}'
              AND (is_active = true OR is_active IS NULL)
            ORDER BY security_label, price_date DESC
            LIMIT 500
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)

            if results:
                for r in results:
                    sec_label = r.get('security_label', '')
                    if sec_label:
                        equity_price = float(r.get('price', 0)) if r.get('price') else 0
                        if sec_label in securities_dict:
                            # Update price from equity_price
                            if equity_price > 0:
                                securities_dict[sec_label]['price'] = equity_price
                                securities_dict[sec_label]['price_date'] = str(r.get('price_date', ''))
                                securities_dict[sec_label]['source'] = 'equity_price'
                        else:
                            # Add new security from equity_price
                            securities_dict[sec_label] = {
                                'value': sec_label,
                                'label': f"{sec_label} ({r.get('isin', '')})",
                                'isin': r.get('isin', ''),
                                'price': equity_price,
                                'market': '',
                                'price_date': str(r.get('price_date', '')),
                                'source': 'equity_price'
                            }
                logger.debug(f"Updated with {len(results)} prices from cis_equity_price for {currency_code}")
        except Exception as e:
            logger.warning(f"Error loading from cis_equity_price: {str(e)}")

        # Convert to sorted list
        result = sorted(securities_dict.values(), key=lambda x: x['value'])
        logger.info(f"Total {len(result)} unique securities for currency {currency_code}")
        return result

    def get_equity_price(self, security_label: str, currency_code: str = None) -> Dict[str, Any]:
        """
        Get the latest closing price for a security from cis_equity_price only.
        """
        if not security_label:
            return {'price': 0, 'found': False}

        currency_filter = ""
        if currency_code:
            currency_filter = f"AND currency_code = '{currency_code}'"

        try:
            query = f"""
            SELECT
                security_label,
                currency_code,
                main_closing_price as price,
                price_date,
                isin
            FROM {self.DATABASE}.cis_equity_price
            WHERE security_label = '{security_label}'
              AND (is_active = true OR is_active IS NULL)
              {currency_filter}
            ORDER BY price_date DESC, price_timestamp DESC
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)

            if results and len(results) > 0:
                r = results[0]
                price = float(r.get('price', 0)) if r.get('price') else 0
                if price > 0:
                    return {
                        'price': price,
                        'currency_code': r.get('currency_code', ''),
                        'price_date': str(r.get('price_date', '')),
                        'market': '',
                        'isin': r.get('isin', ''),
                        'source': 'equity_price',
                        'found': True
                    }
        except Exception as e:
            logger.warning(f"Error getting price from cis_equity_price: {str(e)}")

        return {'price': 0, 'found': False}

    # =========================================================================
    # TRADE CHARGE METHODS
    # =========================================================================

    def get_broker_charges(self, broker: str, exchange: str = None) -> List[Dict[str, Any]]:
        """
        Get all charges for a specific broker from cis_trade_charge_lut.

        Table structure (6 columns):
        - fee_type: Brokerage Fee, FFP/SGX SI FEE, GST, Clearing Fee, Trading Fee
        - broker: Broker name (e.g., 'UOB KAY HIAN PL*')
        - exchange: Exchange code (e.g., 'SGX') or NULL
        - country_of_exchange: Country code (e.g., 'SG') or NULL
        - fee_rule: 'Percent' or 'Flat'
        - fee_value: Fee amount (percentage as whole number e.g., 1.0 for 1%, or flat amount)

        Args:
            broker: Broker name
            exchange: Optional exchange filter (e.g., 'SGX')

        Returns:
            List of charge rules for the broker
        """
        if not broker:
            return []

        try:
            # Escape broker name for SQL
            escaped_broker = broker.replace("'", "''")

            exchange_filter = ""
            if exchange:
                escaped_exchange = exchange.replace("'", "''")
                exchange_filter = f"AND (exchange = '{escaped_exchange}' OR exchange IS NULL)"

            # Try exact match first, then LIKE match for partial broker names
            query = f"""
            SELECT
                fee_type,
                broker,
                exchange,
                country_of_exchange,
                fee_rule,
                fee_value
            FROM {self.DATABASE}.cis_trade_charge_lut
            WHERE (broker = '{escaped_broker}' OR broker LIKE '{escaped_broker}%' OR '{escaped_broker}' LIKE CONCAT(broker, '%'))
              {exchange_filter}
            ORDER BY fee_type
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)

            if results:
                logger.info(f"Loaded {len(results)} charges for broker {broker}")
                return [
                    {
                        'broker': r.get('broker', ''),
                        'fee_type': r.get('fee_type', ''),
                        'exchange': r.get('exchange', '') or '',
                        'country_of_exchange': r.get('country_of_exchange', '') or '',
                        'fee_rule': r.get('fee_rule', ''),
                        'fee_value': float(r.get('fee_value', 0) or 0),
                    }
                    for r in results
                ]
            else:
                logger.warning(f"No charges found for broker: {broker}")
            return []

        except Exception as e:
            logger.warning(f"Error getting broker charges for {broker}: {str(e)}")
            return []

    def calculate_trade_charges(
        self,
        broker: str,
        quantity: float,
        price: float,
        trade_type: str = 'BUY',
        exchange: str = None
    ) -> Dict[str, Any]:
        """
        Calculate all applicable charges for a trade based on broker lookup.

        Fee rules from cis_trade_charge_lut:
        - 'Percent': fee_value is percentage (e.g., 1.0 means 1%, so divide by 100)
        - 'Flat': fee_value is flat amount

        Args:
            broker: Broker name
            quantity: Trade quantity
            price: Trade price per unit
            trade_type: BUY or SELL
            exchange: Optional exchange filter

        Returns:
            Dictionary with calculated charges
        """
        trade_value = float(quantity) * float(price)
        charges = self.get_broker_charges(broker, exchange)

        calculated_charges = []
        total_charges = 0.0

        for charge in charges:
            fee_type = charge.get('fee_type', '')
            fee_rule = charge.get('fee_rule', '')
            fee_value = charge.get('fee_value', 0)

            # Calculate fee based on rule
            calculated_fee = 0.0

            if fee_rule.lower() == 'percent':
                # fee_value is percentage (e.g., 1.0 = 1%, 0.5 = 0.5%)
                # Convert to decimal by dividing by 100
                calculated_fee = trade_value * (fee_value / 100)

            elif fee_rule.lower() == 'flat':
                calculated_fee = fee_value

            calculated_charges.append({
                'fee_type': fee_type,
                'fee_rule': fee_rule,
                'fee_value': fee_value,
                'exchange': charge.get('exchange', ''),
                'country_of_exchange': charge.get('country_of_exchange', ''),
                'calculated_fee': round(calculated_fee, 2)
            })

            total_charges += calculated_fee

        # Calculate grand total based on trade type
        if trade_type.upper() == 'BUY':
            grand_total = trade_value + total_charges
        else:
            grand_total = trade_value - total_charges

        return {
            'broker': broker,
            'charges': calculated_charges,
            'total_charges': round(total_charges, 2),
            'trade_value': round(trade_value, 2),
            'grand_total': round(grand_total, 2),
            'trade_type': trade_type.upper()
        }

    def get_exchanges(self) -> List[Dict[str, Any]]:
        """
        Get distinct exchanges from the charge lookup table.
        """
        try:
            query = f"""
            SELECT DISTINCT exchange, country_of_exchange
            FROM {self.DATABASE}.cis_trade_charge_lut
            WHERE exchange IS NOT NULL
            ORDER BY exchange
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)

            if results:
                return [
                    {
                        'value': r.get('exchange', ''),
                        'label': f"{r.get('exchange', '')} ({r.get('country_of_exchange', '')})" if r.get('country_of_exchange') else r.get('exchange', ''),
                        'country': r.get('country_of_exchange', '') or ''
                    }
                    for r in results if r.get('exchange')
                ]
            return []

        except Exception as e:
            logger.warning(f"Error getting exchanges: {str(e)}")
            return []

    def get_brokers_from_charge_lut(self) -> List[Dict[str, Any]]:
        """
        Get distinct brokers from the charge lookup table.
        """
        try:
            query = f"""
            SELECT DISTINCT broker
            FROM {self.DATABASE}.cis_trade_charge_lut
            WHERE broker IS NOT NULL
            ORDER BY broker
            """
            results = impala_manager.execute_query(query, database=self.DATABASE)

            if results:
                return [
                    {
                        'value': r.get('broker', ''),
                        'label': r.get('broker', '')
                    }
                    for r in results if r.get('broker')
                ]
            return []

        except Exception as e:
            logger.warning(f"Error getting brokers from charge LUT: {str(e)}")
            return []


# Singleton instance
trade_dropdown_service = TradeDropdownService()
