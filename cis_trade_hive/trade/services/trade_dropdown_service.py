"""
Trade Dropdown Service

Provides dropdown options for trade forms by querying lookup tables in Kudu.
"""

import logging
from typing import Dict, List, Any

from core.repositories.impala_connection import impala_manager
from trade.repositories.trade_validation_repository import trade_validation_repository

logger = logging.getLogger(__name__)


class TradeDropdownService:
    """Service for fetching dropdown options for trade forms"""

    DATABASE = 'gmp_cis'

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
        """Get valid counterparties for dropdown."""
        counterparties = trade_validation_repository.get_valid_counterparties(search=search)
        return [
            {
                'value': c.get('counterparty_short_name', ''),
                'label': f"{c.get('counterparty_full_name', '')} ({c.get('counterparty_short_name', '')})",
                'country': c.get('country', ''),
                'is_broker': c.get('is_broker', False)
            }
            for c in counterparties
        ]

    # =========================================================================
    # BROKER & GL OPTIONS
    # =========================================================================

    def get_brokers(self) -> List[Dict[str, Any]]:
        """Get broker options from lookup table."""
        options = self._execute_lookup_query(
            'cis_broker_lookup', 'broker_code', 'broker_name'
        )
        if not options:
            options = [
                {'value': 'GS', 'label': 'Goldman Sachs'},
                {'value': 'MS', 'label': 'Morgan Stanley'},
                {'value': 'JPM', 'label': 'JP Morgan'},
                {'value': 'UBS', 'label': 'UBS'},
                {'value': 'CITI', 'label': 'Citibank'},
            ]
        return options

    def get_gl_fund_types(self) -> List[Dict[str, Any]]:
        """Get GL fund type options."""
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
        """Get GL cost centre options."""
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
        """Get GL account code options."""
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
        """Get selling rule options."""
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
        """Get custodian options."""
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
        """Get sub-custodian options."""
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
        """Get open/close position options."""
        return [
            {'value': 'OPEN', 'label': 'Open'},
            {'value': 'CLOSE', 'label': 'Close'},
        ]

    def get_extensions(self) -> List[Dict[str, Any]]:
        """Get extension options."""
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
        """Get fund type UDF options."""
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
        """Get income/expense type UDF options."""
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
        """Get UOBN/UOBN-HK UDF options."""
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
        """Get Section 31/26 UDF options."""
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
        """Get revision code UDF options."""
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
        """Get amortisation method options."""
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
        """Get delivery type options for Deliver Long."""
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
        """Get income type options for Income tab."""
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
        """Get split type options for Split Transaction."""
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
        """Get reduction type options for Reduction Basis."""
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


# Singleton instance
trade_dropdown_service = TradeDropdownService()
