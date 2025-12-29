"""
Market Data Model Tests

Tests for the FXRate model including:
- Model creation and validation
- Business logic methods
- Constraints and relationships
"""

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, timedelta
from market_data.models import FXRate


class FXRateModelTestCase(TestCase):
    """Test cases for FXRate model"""

    def setUp(self):
        """Set up test data"""
        self.valid_rate_data = {
            'currency_pair': 'USD/EUR',
            'base_currency': 'USD',
            'quote_currency': 'EUR',
            'rate': Decimal('0.9234567890'),
            'bid_rate': Decimal('0.9234000000'),
            'ask_rate': Decimal('0.9235000000'),
            'mid_rate': Decimal('0.9234500000'),
            'rate_date': timezone.now().date(),
            'rate_time': timezone.now(),
            'source': 'BLOOMBERG',
            'is_active': True,
        }

    def test_create_fx_rate_success(self):
        """Test creating a valid FX rate"""
        fx_rate = FXRate.objects.create(**self.valid_rate_data)
        self.assertIsNotNone(fx_rate.id)
        self.assertEqual(fx_rate.currency_pair, 'USD/EUR')
        self.assertEqual(fx_rate.base_currency, 'USD')
        self.assertEqual(fx_rate.quote_currency, 'EUR')
        self.assertEqual(fx_rate.rate, Decimal('0.9234567890'))

    def test_fx_rate_str_representation(self):
        """Test string representation of FX rate"""
        fx_rate = FXRate.objects.create(**self.valid_rate_data)
        expected_str = f"USD/EUR @ 0.9234567890 ({self.valid_rate_data['rate_date']})"
        self.assertEqual(str(fx_rate), expected_str)

    def test_currency_pair_validation_missing_slash(self):
        """Test validation fails when currency pair missing slash"""
        data = self.valid_rate_data.copy()
        data['currency_pair'] = 'USDEUR'  # Missing slash
        fx_rate = FXRate(**data)
        with self.assertRaises(ValidationError) as context:
            fx_rate.full_clean()
        self.assertIn('Currency pair must be in format', str(context.exception))

    def test_auto_populate_base_quote_from_currency_pair(self):
        """Test auto-population of base and quote from currency_pair"""
        data = self.valid_rate_data.copy()
        data['base_currency'] = ''
        data['quote_currency'] = ''
        fx_rate = FXRate(**data)
        fx_rate.full_clean()
        self.assertEqual(fx_rate.base_currency, 'USD')
        self.assertEqual(fx_rate.quote_currency, 'EUR')

    def test_rate_must_be_positive(self):
        """Test validation fails when rate is zero or negative"""
        data = self.valid_rate_data.copy()
        data['rate'] = Decimal('0')
        fx_rate = FXRate(**data)
        with self.assertRaises(ValidationError) as context:
            fx_rate.full_clean()
        self.assertIn('Rate must be positive', str(context.exception))

        data['rate'] = Decimal('-1.5')
        fx_rate = FXRate(**data)
        with self.assertRaises(ValidationError) as context:
            fx_rate.full_clean()
        self.assertIn('Rate must be positive', str(context.exception))

    def test_bid_cannot_be_greater_than_ask(self):
        """Test validation fails when bid > ask"""
        data = self.valid_rate_data.copy()
        data['bid_rate'] = Decimal('0.9235000000')
        data['ask_rate'] = Decimal('0.9234000000')  # bid > ask
        fx_rate = FXRate(**data)
        with self.assertRaises(ValidationError) as context:
            fx_rate.full_clean()
        self.assertIn('Bid rate cannot be greater than ask rate', str(context.exception))

    def test_auto_calculate_mid_rate(self):
        """Test mid rate is auto-calculated from bid and ask"""
        data = self.valid_rate_data.copy()
        data['mid_rate'] = None
        fx_rate = FXRate(**data)
        fx_rate.full_clean()
        expected_mid = (data['bid_rate'] + data['ask_rate']) / Decimal('2')
        self.assertEqual(fx_rate.mid_rate, expected_mid)

    def test_rate_date_cannot_be_future(self):
        """Test validation fails when rate_date is in the future"""
        data = self.valid_rate_data.copy()
        data['rate_date'] = timezone.now().date() + timedelta(days=1)
        fx_rate = FXRate(**data)
        with self.assertRaises(ValidationError) as context:
            fx_rate.full_clean()
        self.assertIn('Rate date cannot be in the future', str(context.exception))

    def test_get_spread_method(self):
        """Test get_spread() method"""
        fx_rate = FXRate.objects.create(**self.valid_rate_data)
        spread = fx_rate.get_spread()
        expected_spread = Decimal('0.9235000000') - Decimal('0.9234000000')
        self.assertEqual(spread, expected_spread)

    def test_get_spread_method_none_when_missing(self):
        """Test get_spread() returns None when bid/ask missing"""
        data = self.valid_rate_data.copy()
        data['bid_rate'] = None
        data['ask_rate'] = None
        data['mid_rate'] = data['rate']
        fx_rate = FXRate(**data)
        fx_rate.save = lambda *args, **kwargs: None  # Skip save validation
        self.assertIsNone(fx_rate.get_spread())

    def test_get_spread_percentage_method(self):
        """Test get_spread_percentage() method"""
        fx_rate = FXRate.objects.create(**self.valid_rate_data)
        spread_pct = fx_rate.get_spread_percentage()
        spread = fx_rate.get_spread()
        expected_pct = (spread / fx_rate.mid_rate) * Decimal('100')
        self.assertAlmostEqual(float(spread_pct), float(expected_pct), places=8)

    def test_is_fresh_method_true(self):
        """Test is_fresh() returns True for recent rates"""
        data = self.valid_rate_data.copy()
        data['rate_time'] = timezone.now() - timedelta(minutes=30)
        fx_rate = FXRate.objects.create(**data)
        self.assertTrue(fx_rate.is_fresh(hours=1))

    def test_is_fresh_method_false(self):
        """Test is_fresh() returns False for old rates"""
        data = self.valid_rate_data.copy()
        data['rate_time'] = timezone.now() - timedelta(hours=2)
        fx_rate = FXRate.objects.create(**data)
        self.assertFalse(fx_rate.is_fresh(hours=1))

    def test_is_stale_method_true(self):
        """Test is_stale() returns True for old rates"""
        data = self.valid_rate_data.copy()
        data['rate_time'] = timezone.now() - timedelta(hours=25)
        fx_rate = FXRate.objects.create(**data)
        self.assertTrue(fx_rate.is_stale(hours=24))

    def test_is_stale_method_false(self):
        """Test is_stale() returns False for recent rates"""
        data = self.valid_rate_data.copy()
        data['rate_time'] = timezone.now() - timedelta(hours=12)
        fx_rate = FXRate.objects.create(**data)
        self.assertFalse(fx_rate.is_stale(hours=24))

    def test_get_freshness_status_fresh(self):
        """Test get_freshness_status() returns 'fresh' for recent rates"""
        data = self.valid_rate_data.copy()
        data['rate_time'] = timezone.now() - timedelta(minutes=30)
        fx_rate = FXRate.objects.create(**data)
        self.assertEqual(fx_rate.get_freshness_status(), 'fresh')

    def test_get_freshness_status_normal(self):
        """Test get_freshness_status() returns 'normal' for moderate age"""
        data = self.valid_rate_data.copy()
        data['rate_time'] = timezone.now() - timedelta(hours=12)
        fx_rate = FXRate.objects.create(**data)
        self.assertEqual(fx_rate.get_freshness_status(), 'normal')

    def test_get_freshness_status_stale(self):
        """Test get_freshness_status() returns 'stale' for old rates"""
        data = self.valid_rate_data.copy()
        data['rate_time'] = timezone.now() - timedelta(hours=25)
        fx_rate = FXRate.objects.create(**data)
        self.assertEqual(fx_rate.get_freshness_status(), 'stale')

    def test_get_freshness_color(self):
        """Test get_freshness_color() returns correct Bootstrap color"""
        # Fresh rate
        data = self.valid_rate_data.copy()
        data['rate_time'] = timezone.now() - timedelta(minutes=30)
        fx_rate = FXRate.objects.create(**data)
        self.assertEqual(fx_rate.get_freshness_color(), 'success')

        # Stale rate
        data['rate_time'] = timezone.now() - timedelta(hours=25)
        fx_rate2 = FXRate.objects.create(**{**data, 'rate_time': data['rate_time']})
        self.assertEqual(fx_rate2.get_freshness_color(), 'warning')

    def test_source_choices(self):
        """Test all source choices are valid"""
        sources = ['BLOOMBERG', 'REUTERS', 'MANUAL', 'API', 'HIVE']
        for source in sources:
            data = self.valid_rate_data.copy()
            data['source'] = source
            fx_rate = FXRate.objects.create(**data)
            self.assertEqual(fx_rate.source, source)

    def test_decimal_precision(self):
        """Test decimal field precision (20 digits, 10 decimal places)"""
        data = self.valid_rate_data.copy()
        data['rate'] = Decimal('1234567890.1234567890')  # 20 total digits
        fx_rate = FXRate.objects.create(**data)
        self.assertEqual(fx_rate.rate, Decimal('1234567890.1234567890'))

    def test_unique_constraint(self):
        """Test unique constraint on currency_pair, rate_date, rate_time, source"""
        fx_rate1 = FXRate.objects.create(**self.valid_rate_data)

        # Try to create duplicate
        with self.assertRaises(Exception):  # IntegrityError or similar
            fx_rate2 = FXRate.objects.create(**self.valid_rate_data)

    def test_ordering(self):
        """Test default ordering by rate_date DESC, rate_time DESC"""
        # Create rates with different dates
        data1 = self.valid_rate_data.copy()
        data1['rate_date'] = timezone.now().date() - timedelta(days=2)
        data1['rate_time'] = timezone.now() - timedelta(days=2)

        data2 = self.valid_rate_data.copy()
        data2['rate_date'] = timezone.now().date() - timedelta(days=1)
        data2['rate_time'] = timezone.now() - timedelta(days=1)
        data2['source'] = 'REUTERS'  # Different source to avoid unique constraint

        data3 = self.valid_rate_data.copy()
        data3['rate_date'] = timezone.now().date()
        data3['rate_time'] = timezone.now()
        data3['source'] = 'API'  # Different source

        fx1 = FXRate.objects.create(**data1)
        fx2 = FXRate.objects.create(**data2)
        fx3 = FXRate.objects.create(**data3)

        # Get all rates in default order
        rates = list(FXRate.objects.all())

        # Should be ordered newest first
        self.assertEqual(rates[0].id, fx3.id)
        self.assertEqual(rates[1].id, fx2.id)
        self.assertEqual(rates[2].id, fx1.id)

    def test_metadata_json_field(self):
        """Test metadata JSONField"""
        data = self.valid_rate_data.copy()
        data['metadata'] = {'provider': 'Bloomberg Terminal', 'quality': 'A+'}
        fx_rate = FXRate.objects.create(**data)
        self.assertEqual(fx_rate.metadata['provider'], 'Bloomberg Terminal')
        self.assertEqual(fx_rate.metadata['quality'], 'A+')

    def test_notes_field(self):
        """Test notes text field"""
        data = self.valid_rate_data.copy()
        data['notes'] = 'Rate adjusted for market volatility'
        fx_rate = FXRate.objects.create(**data)
        self.assertEqual(fx_rate.notes, 'Rate adjusted for market volatility')

    def test_is_active_default(self):
        """Test is_active defaults to True"""
        data = self.valid_rate_data.copy()
        del data['is_active']
        fx_rate = FXRate.objects.create(**data)
        self.assertTrue(fx_rate.is_active)
