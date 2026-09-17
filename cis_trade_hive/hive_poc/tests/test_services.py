"""
Tests for Hive POC Services

Unit tests for Portfolio and Trade services.
"""

import pytest
from unittest.mock import Mock, patch
from decimal import Decimal
from datetime import date

from hive_poc.services.portfolio_hive_service import PortfolioHiveService, PortfolioDTO
from hive_poc.services.trade_hive_service import TradeHiveService, TradeDTO


class TestPortfolioHiveService:
    """Tests for PortfolioHiveService"""

    def setup_method(self):
        self.service = PortfolioHiveService()

    def test_get_type_choices(self):
        """Test type choices are returned correctly"""
        choices = self.service.get_type_choices()
        assert len(choices) > 0
        assert ('EQUITY', 'Equity') in choices

    def test_get_status_choices(self):
        """Test status choices are returned correctly"""
        choices = self.service.get_status_choices()
        assert len(choices) > 0
        assert ('ACTIVE', 'Active') in choices

    def test_get_currency_choices(self):
        """Test currency choices are returned correctly"""
        choices = self.service.get_currency_choices()
        assert len(choices) > 0
        assert ('USD', 'USD') in choices

    def test_validate_valid_portfolio(self):
        """Test validation passes for valid portfolio"""
        dto = PortfolioDTO(
            portfolio_name='Test Portfolio',
            portfolio_code='TEST',
            portfolio_type='EQUITY',
            currency='USD',
            status='DRAFT'
        )
        errors = self.service._validate(dto)
        assert len(errors) == 0

    def test_validate_invalid_name(self):
        """Test validation fails for short name"""
        dto = PortfolioDTO(
            portfolio_name='AB',  # Too short
            portfolio_code='TEST',
            portfolio_type='EQUITY',
            currency='USD',
            status='DRAFT'
        )
        errors = self.service._validate(dto)
        assert 'portfolio_name' in errors

    def test_validate_invalid_type(self):
        """Test validation fails for invalid type"""
        dto = PortfolioDTO(
            portfolio_name='Test Portfolio',
            portfolio_code='TEST',
            portfolio_type='INVALID',
            currency='USD',
            status='DRAFT'
        )
        errors = self.service._validate(dto)
        assert 'portfolio_type' in errors

    @patch.object(PortfolioHiveService, '__init__', lambda x: None)
    def test_create_success(self):
        """Test successful portfolio creation"""
        service = PortfolioHiveService()
        service.repository = Mock()
        service.repository.find_by_code.return_value = None
        service.repository.create.return_value = True

        dto = PortfolioDTO(
            portfolio_name='Test Portfolio',
            portfolio_code='TEST',
            portfolio_type='EQUITY',
            currency='USD',
            status='DRAFT'
        )

        result = service.create(dto)
        assert result['success'] is True
        assert 'portfolio_id' in result

    @patch.object(PortfolioHiveService, '__init__', lambda x: None)
    def test_create_duplicate_code(self):
        """Test creation fails for duplicate code"""
        service = PortfolioHiveService()
        service.repository = Mock()
        service.repository.find_by_code.return_value = {'portfolio_id': 'existing'}

        dto = PortfolioDTO(
            portfolio_name='Test Portfolio',
            portfolio_code='TEST',
            portfolio_type='EQUITY',
            currency='USD',
            status='DRAFT'
        )

        result = service.create(dto)
        assert result['success'] is False
        assert 'portfolio_code' in result['errors']


class TestTradeHiveService:
    """Tests for TradeHiveService"""

    def setup_method(self):
        self.service = TradeHiveService()

    def test_get_type_choices(self):
        """Test type choices are returned correctly"""
        choices = self.service.get_type_choices()
        assert len(choices) == 2
        assert ('BUY', 'Buy') in choices
        assert ('SELL', 'Sell') in choices

    def test_get_status_choices(self):
        """Test status choices are returned correctly"""
        choices = self.service.get_status_choices()
        assert len(choices) > 0
        assert ('PENDING', 'Pending') in choices

    def test_validate_valid_trade(self):
        """Test validation passes for valid trade"""
        dto = TradeDTO(
            portfolio_id='PF001',
            security_id='US0378331005',
            security_name='Apple Inc',
            trade_type='BUY',
            quantity=Decimal('100'),
            price=Decimal('175.50'),
            currency='USD',
            trade_date=date(2024, 1, 15),
            status='PENDING'
        )
        errors = self.service._validate(dto)
        assert len(errors) == 0

    def test_validate_invalid_quantity(self):
        """Test validation fails for invalid quantity"""
        dto = TradeDTO(
            portfolio_id='PF001',
            security_id='US0378331005',
            security_name='Apple Inc',
            trade_type='BUY',
            quantity=Decimal('0'),  # Invalid
            price=Decimal('175.50'),
            currency='USD',
            trade_date=date(2024, 1, 15),
            status='PENDING'
        )
        errors = self.service._validate(dto)
        assert 'quantity' in errors

    def test_validate_invalid_settlement_date(self):
        """Test validation fails when settlement before trade date"""
        dto = TradeDTO(
            portfolio_id='PF001',
            security_id='US0378331005',
            security_name='Apple Inc',
            trade_type='BUY',
            quantity=Decimal('100'),
            price=Decimal('175.50'),
            currency='USD',
            trade_date=date(2024, 1, 15),
            settlement_date=date(2024, 1, 10),  # Before trade date
            status='PENDING'
        )
        errors = self.service._validate(dto)
        assert 'settlement_date' in errors

    @patch.object(TradeHiveService, '__init__', lambda x: None)
    def test_create_success(self):
        """Test successful trade creation"""
        service = TradeHiveService()
        service.repository = Mock()
        service.portfolio_repository = Mock()
        service.portfolio_repository.find_by_id.return_value = {'portfolio_id': 'PF001'}
        service.repository.create.return_value = True

        dto = TradeDTO(
            portfolio_id='PF001',
            security_id='US0378331005',
            security_name='Apple Inc',
            trade_type='BUY',
            quantity=Decimal('100'),
            price=Decimal('175.50'),
            currency='USD',
            trade_date=date(2024, 1, 15),
            status='PENDING'
        )

        result = service.create(dto)
        assert result['success'] is True
        assert 'trade_id' in result

    @patch.object(TradeHiveService, '__init__', lambda x: None)
    def test_create_invalid_portfolio(self):
        """Test creation fails for invalid portfolio"""
        service = TradeHiveService()
        service.repository = Mock()
        service.portfolio_repository = Mock()
        service.portfolio_repository.find_by_id.return_value = None

        dto = TradeDTO(
            portfolio_id='INVALID',
            security_id='US0378331005',
            security_name='Apple Inc',
            trade_type='BUY',
            quantity=Decimal('100'),
            price=Decimal('175.50'),
            currency='USD',
            trade_date=date(2024, 1, 15),
            status='PENDING'
        )

        result = service.create(dto)
        assert result['success'] is False
        assert 'portfolio_id' in result['errors']
