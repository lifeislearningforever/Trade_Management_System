"""
Trade Dropdown Service Tests

Comprehensive tests for TradeDropdownService.
Tests dropdown options retrieval from UDF fields, lookup tables, and fallbacks.
"""

import pytest
from django.test import TestCase
from unittest.mock import patch, Mock, MagicMock

from trade.services.trade_dropdown_service import trade_dropdown_service, TradeDropdownService


class TradeDropdownServiceTestCase(TestCase):
    """Test cases for TradeDropdownService"""

    def setUp(self):
        """Set up test data"""
        self.service = trade_dropdown_service
        self.TradeDropdownServiceClass = TradeDropdownService

    # =========================================================================
    # TRADE TYPES TESTS
    # =========================================================================

    def test_get_trade_types(self):
        """Test fetching trade types"""
        result = self.service.get_trade_types()

        self.assertIsInstance(result, list)
        # Per SA feedback: Only BUY and SELL trade types
        self.assertEqual(len(result), 2)

        # Check specific trade types
        values = [t['value'] for t in result]
        self.assertIn('BUY', values)
        self.assertIn('SELL', values)

    def test_get_trade_types_structure(self):
        """Test trade types have correct structure"""
        result = self.service.get_trade_types()

        for item in result:
            self.assertIn('value', item)
            self.assertIn('label', item)
            self.assertIsInstance(item['value'], str)
            self.assertIsInstance(item['label'], str)

    # =========================================================================
    # TRADE STATUSES TESTS (Static list - no DB query)
    # =========================================================================

    def test_get_trade_statuses(self):
        """Test fetching trade statuses (static workflow statuses)"""
        result = self.service.get_trade_statuses()

        # Should return static workflow statuses
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 6)  # INITIAL, MODIFIED, PENDING_VALIDATION, VALIDATED, SETTLED, CANCELLED
        values = [s['value'] for s in result]
        self.assertIn('INITIAL', values)
        self.assertIn('SETTLED', values)
        self.assertIn('PENDING_VALIDATION', values)

    # =========================================================================
    # PORTFOLIOS DROPDOWN TESTS
    # =========================================================================

    @patch('trade.services.trade_dropdown_service.trade_validation_repository')
    def test_get_portfolios(self, mock_validation_repo):
        """Test fetching portfolios for dropdown"""
        mock_validation_repo.get_valid_portfolios.return_value = [
            {'portfolio_short_name': 'PORT001', 'currency': 'USD', 'manager': 'John'},
            {'portfolio_short_name': 'PORT002', 'currency': 'EUR', 'manager': 'Jane'}
        ]

        result = self.service.get_portfolios()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['value'], 'PORT001')
        self.assertEqual(result[0]['label'], 'PORT001')
        self.assertEqual(result[0]['currency'], 'USD')

    @patch('trade.services.trade_dropdown_service.trade_validation_repository')
    def test_get_portfolios_with_search(self, mock_validation_repo):
        """Test fetching portfolios with search"""
        mock_validation_repo.get_valid_portfolios.return_value = [
            {'portfolio_short_name': 'SEARCH_PORT', 'currency': 'USD', 'manager': 'John'}
        ]

        result = self.service.get_portfolios(search='SEARCH')

        self.assertEqual(len(result), 1)
        mock_validation_repo.get_valid_portfolios.assert_called_with(search='SEARCH')

    @patch('trade.services.trade_dropdown_service.trade_validation_repository')
    def test_get_portfolios_empty(self, mock_validation_repo):
        """Test fetching portfolios when none available"""
        mock_validation_repo.get_valid_portfolios.return_value = []

        result = self.service.get_portfolios()

        self.assertEqual(result, [])

    # =========================================================================
    # SECURITIES DROPDOWN TESTS
    # =========================================================================

    @patch('trade.services.trade_dropdown_service.trade_validation_repository')
    def test_get_securities(self, mock_validation_repo):
        """Test fetching securities for dropdown"""
        mock_validation_repo.get_valid_securities.return_value = [
            {
                'security_label': 'SEC001',
                'ticker': 'TEST',
                'isin': 'US123',
                'security_type': 'EQUITY',
                'currency_code': 'USD',
                'current_price': 50.00
            }
        ]

        result = self.service.get_securities()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['value'], 'SEC001')
        self.assertIn('TEST', result[0]['label'])  # Label includes ticker
        self.assertEqual(result[0]['security_type'], 'EQUITY')

    @patch('trade.services.trade_dropdown_service.trade_validation_repository')
    def test_get_securities_with_isin(self, mock_validation_repo):
        """Test securities label uses ISIN when ticker key is not present"""
        # Note: The service uses s.get('ticker', s.get('isin', '')) which only falls back
        # to ISIN when the ticker key doesn't exist (not when it's empty string)
        mock_validation_repo.get_valid_securities.return_value = [
            {
                'security_label': 'SEC001',
                # ticker key omitted to test fallback to ISIN
                'isin': 'US1234567890',
                'security_type': 'BOND',
                'currency_code': 'USD',
                'current_price': 100.00
            }
        ]

        result = self.service.get_securities()

        self.assertEqual(len(result), 1)
        self.assertIn('US1234567890', result[0]['label'])

    # =========================================================================
    # COUNTERPARTIES DROPDOWN TESTS
    # =========================================================================

    @patch('trade.services.trade_dropdown_service.trade_validation_repository')
    def test_get_counterparties(self, mock_validation_repo):
        """Test fetching counterparties for dropdown"""
        mock_validation_repo.get_valid_counterparties.return_value = [
            {
                'party_short_name': 'CP001',
                'party_full_name': 'Counterparty One',
                'country': 'US',
                'is_broker': True
            }
        ]

        result = self.service.get_counterparties()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['value'], 'CP001')
        self.assertIn('Counterparty One', result[0]['label'])

    # =========================================================================
    # BROKERS TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_brokers_from_counterparty(self, mock_execute):
        """Test fetching brokers from counterparty table"""
        mock_execute.return_value = [
            {'value': 'BROKER1', 'label': 'Broker One', 'country': 'US'},
            {'value': 'BROKER2', 'label': 'Broker Two', 'country': 'UK'}
        ]

        result = self.service.get_brokers()

        self.assertEqual(len(result), 2)
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args[0][0]
        self.assertIn('is_broker = true', call_args)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_brokers_fallback(self, mock_execute):
        """Test brokers fallback when query fails"""
        mock_execute.side_effect = Exception("Database error")

        result = self.service.get_brokers()

        # Should return fallback defaults
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    # =========================================================================
    # GL FUND TYPES TESTS
    # =========================================================================

    @patch.object(TradeDropdownService, '_get_udf_options')
    def test_get_gl_fund_types_from_udf(self, mock_udf):
        """Test fetching GL fund types from UDF"""
        mock_udf.return_value = [
            {'value': 'TRADING', 'label': 'Trading'},
            {'value': 'BANKING', 'label': 'Banking'}
        ]

        result = self.service.get_gl_fund_types()

        self.assertEqual(len(result), 2)
        mock_udf.assert_called_with('GL Fund Type')

    @patch.object(TradeDropdownService, '_get_udf_options')
    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_gl_fund_types_fallback(self, mock_execute, mock_udf):
        """Test GL fund types fallback when UDF empty"""
        mock_udf.return_value = []
        mock_execute.return_value = []

        result = self.service.get_gl_fund_types()

        # Should return hardcoded fallback
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    # =========================================================================
    # GL COST CENTRES TESTS
    # =========================================================================

    @patch.object(TradeDropdownService, '_get_udf_options')
    def test_get_gl_cost_centres_from_udf(self, mock_udf):
        """Test fetching GL cost centres from UDF"""
        mock_udf.return_value = [
            {'value': 'CC-001', 'label': 'Treasury'}
        ]

        result = self.service.get_gl_cost_centres()

        self.assertEqual(len(result), 1)
        mock_udf.assert_called_with('GL Cost Centre')

    # =========================================================================
    # GL ACCOUNT CODES TESTS
    # =========================================================================

    @patch.object(TradeDropdownService, '_get_udf_options')
    def test_get_gl_account_codes_from_udf(self, mock_udf):
        """Test fetching GL account codes from UDF"""
        mock_udf.return_value = [
            {'value': 'ACC-1001', 'label': 'Trading Securities'}
        ]

        result = self.service.get_gl_account_codes()

        self.assertEqual(len(result), 1)
        mock_udf.assert_called_with('GL Account Code')

    # =========================================================================
    # SELLING RULES TESTS
    # =========================================================================

    @patch.object(TradeDropdownService, '_get_udf_options')
    def test_get_selling_rules_from_udf(self, mock_udf):
        """Test fetching selling rules from UDF"""
        mock_udf.return_value = [
            {'value': 'FIFO', 'label': 'First In First Out'},
            {'value': 'LIFO', 'label': 'Last In First Out'}
        ]

        result = self.service.get_selling_rules()

        self.assertEqual(len(result), 2)
        mock_udf.assert_called_with('Selling Rule')

    @patch.object(TradeDropdownService, '_get_udf_options')
    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_selling_rules_fallback(self, mock_execute, mock_udf):
        """Test selling rules fallback"""
        mock_udf.return_value = []
        mock_execute.return_value = []

        result = self.service.get_selling_rules()

        # Should return fallback
        values = [r['value'] for r in result]
        self.assertIn('FIFO', values)
        self.assertIn('LIFO', values)

    # =========================================================================
    # CUSTODIANS TESTS
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_custodians_from_counterparty(self, mock_execute):
        """Test fetching custodians from counterparty table"""
        mock_execute.return_value = [
            {'value': 'CUST1', 'label': 'Custodian One', 'country': 'SG'}
        ]

        result = self.service.get_custodians()

        self.assertEqual(len(result), 1)
        call_args = mock_execute.call_args[0][0]
        self.assertIn('is_custodian = true', call_args)

    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_custodians_fallback(self, mock_execute):
        """Test custodians fallback"""
        mock_execute.side_effect = Exception("Database error")

        result = self.service.get_custodians()

        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    # =========================================================================
    # SUB CUSTODIANS TESTS
    # =========================================================================

    @patch.object(TradeDropdownService, '_get_udf_options')
    def test_get_sub_custodians_from_udf(self, mock_udf):
        """Test fetching sub custodians from UDF"""
        mock_udf.return_value = [
            {'value': 'DBS-SG', 'label': 'DBS Bank Singapore'}
        ]

        result = self.service.get_sub_custodians()

        self.assertEqual(len(result), 1)
        mock_udf.assert_called_with('Sub Custodian')

    # =========================================================================
    # OPEN CLOSE OPTIONS TESTS
    # =========================================================================

    @patch.object(TradeDropdownService, '_get_udf_options')
    def test_get_open_close_options_from_udf(self, mock_udf):
        """Test fetching open/close options from UDF"""
        mock_udf.return_value = [
            {'value': 'OPEN', 'label': 'Open'}
        ]

        result = self.service.get_open_close_options()

        self.assertEqual(len(result), 1)
        mock_udf.assert_called_with('Open/Close Position')

    @patch.object(TradeDropdownService, '_get_udf_options')
    def test_get_open_close_options_fallback(self, mock_udf):
        """Test open/close options fallback"""
        mock_udf.return_value = []

        result = self.service.get_open_close_options()

        values = [r['value'] for r in result]
        self.assertIn('OPEN', values)
        self.assertIn('CLOSE', values)

    # =========================================================================
    # EXTENSIONS TESTS
    # =========================================================================

    @patch.object(TradeDropdownService, '_get_udf_options')
    def test_get_extensions_from_udf(self, mock_udf):
        """Test fetching extensions from UDF"""
        mock_udf.return_value = [
            {'value': 'NONE', 'label': 'None'},
            {'value': 'EXT-1D', 'label': '1 Day Extension'}
        ]

        result = self.service.get_extensions()

        self.assertEqual(len(result), 2)
        mock_udf.assert_called_with('Extension')

    # =========================================================================
    # FUND TYPES TESTS
    # =========================================================================

    @patch.object(TradeDropdownService, '_get_udf_options')
    def test_get_fund_types_from_udf(self, mock_udf):
        """Test fetching fund types from UDF"""
        mock_udf.return_value = [
            {'value': 'EQUITY', 'label': 'Equity'},
            {'value': 'FIXED_INCOME', 'label': 'Fixed Income'}
        ]

        result = self.service.get_fund_types()

        self.assertEqual(len(result), 2)
        mock_udf.assert_called_with('Fund Type')

    # =========================================================================
    # INCOME/EXP TYPES TESTS
    # =========================================================================

    @patch.object(TradeDropdownService, '_get_udf_options')
    def test_get_income_exp_types_from_udf(self, mock_udf):
        """Test fetching income/expense types from UDF"""
        mock_udf.return_value = [
            {'value': 'TRADING', 'label': 'Trading'}
        ]

        result = self.service.get_income_exp_types()

        self.assertEqual(len(result), 1)
        mock_udf.assert_called_with('Income/Exp Type')

    # =========================================================================
    # UOBN OPTIONS TESTS
    # =========================================================================

    @patch.object(TradeDropdownService, '_get_udf_options')
    def test_get_uobn_options_from_udf(self, mock_udf):
        """Test fetching UOBN options from UDF"""
        mock_udf.return_value = [
            {'value': 'UOBN-SG', 'label': 'UOBN Singapore'}
        ]

        result = self.service.get_uobn_options()

        self.assertEqual(len(result), 1)
        mock_udf.assert_called_with('UOBN/UOBN-HK')

    # =========================================================================
    # SECTION OPTIONS TESTS
    # =========================================================================

    @patch.object(TradeDropdownService, '_get_udf_options')
    def test_get_section_options_from_udf(self, mock_udf):
        """Test fetching section 31/26 options from UDF"""
        mock_udf.return_value = [
            {'value': 'SEC_31', 'label': 'Section 31'}
        ]

        result = self.service.get_section_options()

        self.assertEqual(len(result), 1)
        mock_udf.assert_called_with('Section 31/26')

    # =========================================================================
    # REVISION CODES TESTS
    # =========================================================================

    @patch.object(TradeDropdownService, '_get_udf_options')
    def test_get_revision_codes_from_udf(self, mock_udf):
        """Test fetching revision codes from UDF"""
        mock_udf.return_value = [
            {'value': 'REV-001', 'label': 'Revision 001'}
        ]

        result = self.service.get_revision_codes()

        self.assertEqual(len(result), 1)
        mock_udf.assert_called_with('Revision Code')

    # =========================================================================
    # AMORTISATION METHODS TESTS
    # =========================================================================

    @patch.object(TradeDropdownService, '_get_udf_options')
    def test_get_amor_methods_from_udf(self, mock_udf):
        """Test fetching amortisation methods from UDF"""
        mock_udf.return_value = [
            {'value': 'STD', 'label': 'Standard'},
            {'value': 'EFF_INT', 'label': 'Effective Interest'}
        ]

        result = self.service.get_amor_methods()

        self.assertEqual(len(result), 2)
        mock_udf.assert_called_with('Amortisation Method')

    # =========================================================================
    # DELIVERY TYPES TESTS
    # =========================================================================

    @patch.object(TradeDropdownService, '_get_udf_options')
    def test_get_delivery_types_from_udf(self, mock_udf):
        """Test fetching delivery types from UDF"""
        mock_udf.return_value = [
            {'value': 'TRANSFER', 'label': 'Transfer'}
        ]

        result = self.service.get_delivery_types()

        self.assertEqual(len(result), 1)
        mock_udf.assert_called_with('Delivery Type')

    @patch.object(TradeDropdownService, '_get_udf_options')
    @patch('core.repositories.impala_connection.impala_manager.execute_query')
    def test_get_delivery_types_fallback(self, mock_execute, mock_udf):
        """Test delivery types fallback"""
        mock_udf.return_value = []
        mock_execute.return_value = []

        result = self.service.get_delivery_types()

        values = [r['value'] for r in result]
        self.assertIn('TRANSFER', values)

    # =========================================================================
    # INCOME TYPES TESTS
    # =========================================================================

    @patch.object(TradeDropdownService, '_get_udf_options')
    def test_get_income_types_from_udf(self, mock_udf):
        """Test fetching income types from UDF"""
        mock_udf.return_value = [
            {'value': 'DIVIDEND', 'label': 'Dividend'},
            {'value': 'INTEREST', 'label': 'Interest'}
        ]

        result = self.service.get_income_types()

        self.assertEqual(len(result), 2)
        mock_udf.assert_called_with('Income Type')

    # =========================================================================
    # SPLIT TYPES TESTS
    # =========================================================================

    @patch.object(TradeDropdownService, '_get_udf_options')
    def test_get_split_types_from_udf(self, mock_udf):
        """Test fetching split types from UDF"""
        mock_udf.return_value = [
            {'value': 'STOCK_SPLIT', 'label': 'Stock Split'}
        ]

        result = self.service.get_split_types()

        self.assertEqual(len(result), 1)
        mock_udf.assert_called_with('Split Type')

    # =========================================================================
    # REDUCTION TYPES TESTS
    # =========================================================================

    @patch.object(TradeDropdownService, '_get_udf_options')
    def test_get_reduction_types_from_udf(self, mock_udf):
        """Test fetching reduction types from UDF"""
        mock_udf.return_value = [
            {'value': 'RETURN_CAPITAL', 'label': 'Return of Capital'}
        ]

        result = self.service.get_reduction_types()

        self.assertEqual(len(result), 1)
        mock_udf.assert_called_with('Reduction Type')

    # =========================================================================
    # GET ALL DROPDOWN OPTIONS TESTS
    # =========================================================================

    @patch.object(TradeDropdownService, 'get_trade_types')
    @patch.object(TradeDropdownService, 'get_trade_statuses')
    @patch.object(TradeDropdownService, 'get_portfolios')
    @patch.object(TradeDropdownService, 'get_securities')
    @patch.object(TradeDropdownService, 'get_counterparties')
    @patch.object(TradeDropdownService, 'get_brokers')
    @patch.object(TradeDropdownService, 'get_gl_fund_types')
    @patch.object(TradeDropdownService, 'get_gl_cost_centres')
    @patch.object(TradeDropdownService, 'get_gl_account_codes')
    @patch.object(TradeDropdownService, 'get_selling_rules')
    @patch.object(TradeDropdownService, 'get_custodians')
    @patch.object(TradeDropdownService, 'get_sub_custodians')
    @patch.object(TradeDropdownService, 'get_open_close_options')
    @patch.object(TradeDropdownService, 'get_extensions')
    @patch.object(TradeDropdownService, 'get_fund_types')
    @patch.object(TradeDropdownService, 'get_income_exp_types')
    @patch.object(TradeDropdownService, 'get_uobn_options')
    @patch.object(TradeDropdownService, 'get_section_options')
    @patch.object(TradeDropdownService, 'get_revision_codes')
    @patch.object(TradeDropdownService, 'get_amor_methods')
    @patch.object(TradeDropdownService, 'get_delivery_types')
    @patch.object(TradeDropdownService, 'get_income_types')
    @patch.object(TradeDropdownService, 'get_split_types')
    @patch.object(TradeDropdownService, 'get_reduction_types')
    def test_get_all_dropdown_options(self, *mocks):
        """Test fetching all dropdown options"""
        # Set up all mocks to return empty lists
        for mock in mocks:
            mock.return_value = []

        result = self.service.get_all_dropdown_options()

        # Check all expected keys exist
        expected_keys = [
            'trade_types', 'trade_statuses', 'portfolios', 'securities',
            'counterparties', 'brokers', 'gl_fund_types', 'gl_cost_centres',
            'gl_account_codes', 'selling_rules', 'custodians', 'sub_custodians',
            'open_close_options', 'extensions', 'fund_types', 'income_exp_types',
            'uobn_options', 'section_options', 'revision_codes', 'amor_methods',
            'delivery_types', 'income_types', 'split_types', 'reduction_types'
        ]

        for key in expected_keys:
            self.assertIn(key, result)

    # =========================================================================
    # _GET_UDF_OPTIONS TESTS
    # =========================================================================

    @patch('trade.services.trade_dropdown_service.udf_field_repository')
    def test_get_udf_options_success(self, mock_udf_repo):
        """Test _get_udf_options success"""
        mock_udf_repo.get_field_values.return_value = [
            {'field_value': 'VALUE_ONE'},
            {'field_value': 'VALUE_TWO'}
        ]

        result = self.service._get_udf_options('Test Field')

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['value'], 'VALUE_ONE')
        # Label should be title-cased
        mock_udf_repo.get_field_values.assert_called_with('TRADE', 'Test Field')

    @patch('trade.services.trade_dropdown_service.udf_field_repository')
    def test_get_udf_options_empty(self, mock_udf_repo):
        """Test _get_udf_options with no results"""
        mock_udf_repo.get_field_values.return_value = []

        result = self.service._get_udf_options('Test Field')

        self.assertEqual(result, [])

    @patch('trade.services.trade_dropdown_service.udf_field_repository')
    def test_get_udf_options_exception(self, mock_udf_repo):
        """Test _get_udf_options handles exception"""
        mock_udf_repo.get_field_values.side_effect = Exception("UDF error")

        result = self.service._get_udf_options('Test Field')

        self.assertEqual(result, [])

    @patch('trade.services.trade_dropdown_service.udf_field_repository')
    def test_get_udf_options_filters_empty_values(self, mock_udf_repo):
        """Test _get_udf_options filters out empty field values"""
        mock_udf_repo.get_field_values.return_value = [
            {'field_value': 'VALUE_ONE'},
            {'field_value': ''},
            {'field_value': None},
            {'field_value': 'VALUE_TWO'}
        ]

        result = self.service._get_udf_options('Test Field')

        self.assertEqual(len(result), 2)

    # =========================================================================
    # NOTE: _execute_lookup_query removed - lookup tables no longer used
    # All dropdown options now use UDF field table with static fallbacks
    # =========================================================================

    # =========================================================================
    # CONSTANTS TESTS
    # =========================================================================

    def test_database_constant(self):
        """Test DATABASE constant"""
        self.assertEqual(TradeDropdownService.DATABASE, 'gmp_cis')

    def test_object_type_constant(self):
        """Test OBJECT_TYPE constant for UDF"""
        self.assertEqual(TradeDropdownService.OBJECT_TYPE, 'TRADE')


class TradeDropdownServiceFallbackTestCase(TestCase):
    """
    Test cases for dropdown service fallback paths.

    NOTE: Lookup tables have been removed. All dropdown options now use:
    1. UDF field values from cis_udf_field
    2. Static default values as fallback

    This improves trade load/create/edit performance by eliminating
    queries to non-existent lookup tables.
    """

    def setUp(self):
        """Set up test data"""
        self.service = trade_dropdown_service

    # =========================================================================
    # TEST DEFAULT FALLBACKS (when UDF returns empty)
    # =========================================================================

    @patch('trade.services.trade_dropdown_service.udf_field_repository')
    def test_get_gl_cost_centres_fallback_defaults(self, mock_udf_repo):
        """Test GL cost centres falls back to hardcoded defaults"""
        mock_udf_repo.get_field_values.return_value = []

        result = self.service.get_gl_cost_centres()

        self.assertEqual(len(result), 3)
        values = [r['value'] for r in result]
        self.assertIn('CC-001', values)

    @patch('trade.services.trade_dropdown_service.udf_field_repository')
    def test_get_fund_types_fallback_defaults(self, mock_udf_repo):
        """Test fund types falls back to hardcoded defaults"""
        mock_udf_repo.get_field_values.return_value = []

        result = self.service.get_fund_types()

        self.assertEqual(len(result), 4)
        values = [r['value'] for r in result]
        self.assertIn('EQUITY', values)

    @patch('trade.services.trade_dropdown_service.udf_field_repository')
    def test_get_selling_rules_fallback_defaults(self, mock_udf_repo):
        """Test selling rules falls back to hardcoded defaults"""
        mock_udf_repo.get_field_values.return_value = []

        result = self.service.get_selling_rules()

        self.assertEqual(len(result), 4)
        values = [r['value'] for r in result]
        self.assertIn('FIFO', values)
        self.assertIn('WAVG', values)

    @patch('trade.services.trade_dropdown_service.udf_field_repository')
    def test_get_delivery_types_fallback_defaults(self, mock_udf_repo):
        """Test delivery types falls back to hardcoded defaults"""
        mock_udf_repo.get_field_values.return_value = []

        result = self.service.get_delivery_types()

        self.assertEqual(len(result), 3)
        values = [r['value'] for r in result]
        self.assertIn('TRANSFER', values)

    @patch('trade.services.trade_dropdown_service.udf_field_repository')
    def test_get_income_types_fallback_defaults(self, mock_udf_repo):
        """Test income types falls back to hardcoded defaults"""
        mock_udf_repo.get_field_values.return_value = []

        result = self.service.get_income_types()

        self.assertEqual(len(result), 3)
        values = [r['value'] for r in result]
        self.assertIn('DIVIDEND', values)

    @patch('trade.services.trade_dropdown_service.udf_field_repository')
    def test_get_split_types_fallback_defaults(self, mock_udf_repo):
        """Test split types falls back to hardcoded defaults"""
        mock_udf_repo.get_field_values.return_value = []

        result = self.service.get_split_types()

        self.assertEqual(len(result), 3)
        values = [r['value'] for r in result]
        self.assertIn('STOCK_SPLIT', values)

    @patch('trade.services.trade_dropdown_service.udf_field_repository')
    def test_get_reduction_types_fallback_defaults(self, mock_udf_repo):
        """Test reduction types falls back to hardcoded defaults"""
        mock_udf_repo.get_field_values.return_value = []

        result = self.service.get_reduction_types()

        self.assertEqual(len(result), 3)
        values = [r['value'] for r in result]
        self.assertIn('RETURN_CAPITAL', values)
