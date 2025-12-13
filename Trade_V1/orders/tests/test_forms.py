"""
Order Forms Tests
"""
import pytest
from orders.forms import OrderForm, OrderRejectForm, OrderFilterForm
from orders.models import Stock


@pytest.mark.unit
@pytest.mark.django_db
class TestOrderForm:
    """Test Order Form"""

    def test_order_form_valid_data(self, test_stock, test_client, test_broker, maker_user):
        """Test form with valid data"""
        form_data = {
            'stock': test_stock.id,
            'side': 'BUY',
            'order_type': 'MARKET',
            'quantity': 100,
            'client': test_client.id,
            'broker': test_broker.id,
            'validity': 'DAY',
            'notes': 'Test order'
        }
        form = OrderForm(data=form_data, user=maker_user)
        assert form.is_valid()

    def test_order_form_missing_required_fields(self, maker_user):
        """Test form with missing required fields"""
        form = OrderForm(data={}, user=maker_user)
        assert not form.is_valid()
        assert 'stock' in form.errors
        assert 'side' in form.errors
        assert 'quantity' in form.errors

    def test_order_form_limit_order_requires_price(self, test_stock, maker_user):
        """Test LIMIT order requires price"""
        form_data = {
            'stock': test_stock.id,
            'side': 'BUY',
            'order_type': 'LIMIT',
            'quantity': 100,
            'validity': 'DAY'
        }
        form = OrderForm(data=form_data, user=maker_user)
        assert not form.is_valid()
        assert 'price' in form.errors

    def test_order_form_stop_loss_requires_stop_price(self, test_stock, maker_user):
        """Test STOP_LOSS order requires stop_price"""
        form_data = {
            'stock': test_stock.id,
            'side': 'SELL',
            'order_type': 'STOP_LOSS',
            'quantity': 50,
            'validity': 'DAY'
        }
        form = OrderForm(data=form_data, user=maker_user)
        assert not form.is_valid()
        assert 'stop_price' in form.errors

    def test_order_form_negative_quantity(self, test_stock, maker_user):
        """Test form rejects negative quantity"""
        form_data = {
            'stock': test_stock.id,
            'side': 'BUY',
            'order_type': 'MARKET',
            'quantity': -10,
            'validity': 'DAY'
        }
        form = OrderForm(data=form_data, user=maker_user)
        assert not form.is_valid()

    def test_order_form_filters_active_stocks(self, db, maker_user):
        """Test form only shows active stocks"""
        Stock.objects.create(symbol='INACTIVE', name='Inactive Stock', is_active=False)
        form = OrderForm(user=maker_user)
        stock_choices = [choice[1] for choice in form.fields['stock'].choices]
        assert 'INACTIVE' not in str(stock_choices)


@pytest.mark.unit
@pytest.mark.django_db
class TestOrderRejectForm:
    """Test Order Reject Form"""

    def test_reject_form_valid_reason(self):
        """Test form with valid rejection reason"""
        form = OrderRejectForm(data={'rejection_reason': 'Price too high for current market conditions'})
        assert form.is_valid()

    def test_reject_form_missing_reason(self):
        """Test form requires rejection reason"""
        form = OrderRejectForm(data={})
        assert not form.is_valid()
        assert 'rejection_reason' in form.errors

    def test_reject_form_short_reason(self):
        """Test form rejects too short reason"""
        form = OrderRejectForm(data={'rejection_reason': 'Bad'})
        assert not form.is_valid()
        assert 'rejection_reason' in form.errors

    def test_reject_form_strips_whitespace(self):
        """Test form strips whitespace from reason"""
        form = OrderRejectForm(data={'rejection_reason': '  Valid reason here  '})
        assert form.is_valid()
        assert form.cleaned_data['rejection_reason'] == 'Valid reason here'


@pytest.mark.unit
@pytest.mark.django_db
class TestOrderFilterForm:
    """Test Order Filter Form"""

    def test_filter_form_all_empty(self):
        """Test form is valid with all empty fields"""
        form = OrderFilterForm(data={})
        assert form.is_valid()

    def test_filter_form_with_status(self):
        """Test form with status filter"""
        form = OrderFilterForm(data={'status': 'DRAFT'})
        assert form.is_valid()
        assert form.cleaned_data['status'] == 'DRAFT'

    def test_filter_form_with_multiple_filters(self, test_stock):
        """Test form with multiple filters"""
        form = OrderFilterForm(data={
            'status': 'PENDING_APPROVAL',
            'side': 'BUY',
            'stock': test_stock.id
        })
        assert form.is_valid()
