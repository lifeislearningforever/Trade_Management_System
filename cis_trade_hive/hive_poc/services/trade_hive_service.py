"""
Trade Service for Hive POC

Business logic layer for trade operations with Hive managed tables.
"""

import logging
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from decimal import Decimal
from dataclasses import dataclass, asdict

from ..repositories.trade_hive_repository import TradeHiveRepository
from ..repositories.portfolio_hive_repository import PortfolioHiveRepository

logger = logging.getLogger('hive_poc')


@dataclass
class TradeDTO:
    """Data Transfer Object for Trade"""
    trade_id: str = ''
    portfolio_id: str = ''
    security_id: str = ''
    security_name: str = ''
    trade_type: str = 'BUY'
    quantity: Decimal = Decimal('0')
    price: Decimal = Decimal('0')
    currency: str = 'USD'
    trade_date: date = None
    settlement_date: date = None
    status: str = 'PENDING'
    broker: str = ''
    notes: str = ''
    created_by: str = 'system'
    updated_by: str = 'system'

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # Convert Decimal to float for database
        data['quantity'] = float(self.quantity) if self.quantity else 0
        data['price'] = float(self.price) if self.price else 0
        data['trade_amount'] = float(self.quantity * self.price) if self.quantity and self.price else 0
        # Convert dates to strings
        if self.trade_date:
            data['trade_date'] = self.trade_date.isoformat() if isinstance(self.trade_date, date) else self.trade_date
        if self.settlement_date:
            data['settlement_date'] = self.settlement_date.isoformat() if isinstance(self.settlement_date, date) else self.settlement_date
        return data


class TradeHiveService:
    """
    Service class for Trade operations.

    Handles business logic and validation for trade CRUD operations
    using Hive managed tables with ORC format.
    """

    VALID_TYPES = ['BUY', 'SELL']
    VALID_STATUSES = ['PENDING', 'EXECUTED', 'SETTLED', 'CANCELLED']
    VALID_CURRENCIES = ['USD', 'EUR', 'GBP', 'SGD', 'JPY', 'AUD', 'CHF', 'HKD']

    def __init__(self):
        self.repository = TradeHiveRepository()
        self.portfolio_repository = PortfolioHiveRepository()

    def get_all(self, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """
        Get all trades.

        Args:
            include_deleted: Include soft-deleted trades

        Returns:
            List of trades
        """
        return self.repository.find_all(include_deleted)

    def get_all_with_portfolio(self) -> List[Dict[str, Any]]:
        """Get all trades with portfolio details."""
        return self.repository.get_trades_with_portfolio()

    def get_by_id(self, trade_id: str) -> Optional[Dict[str, Any]]:
        """
        Get trade by ID.

        Args:
            trade_id: Trade ID

        Returns:
            Trade or None
        """
        return self.repository.find_by_id(trade_id)

    def get_by_portfolio(self, portfolio_id: str) -> List[Dict[str, Any]]:
        """Get trades for a portfolio."""
        return self.repository.find_by_portfolio(portfolio_id)

    def get_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get trades by status."""
        return self.repository.find_by_status(status)

    def get_pending_settlement(self) -> List[Dict[str, Any]]:
        """Get trades pending settlement."""
        return self.repository.find_pending_settlement()

    def create(self, dto: TradeDTO) -> Dict[str, Any]:
        """
        Create a new trade.

        Args:
            dto: Trade data transfer object

        Returns:
            Result dict with success status and message
        """
        # Validate
        errors = self._validate(dto)
        if errors:
            return {'success': False, 'errors': errors}

        # Verify portfolio exists
        portfolio = self.portfolio_repository.find_by_id(dto.portfolio_id)
        if not portfolio:
            return {
                'success': False,
                'errors': {'portfolio_id': 'Portfolio not found'}
            }

        # Generate ID if not provided
        if not dto.trade_id:
            dto.trade_id = f"TR{str(uuid.uuid4())[:8].upper()}"

        # Create record
        data = dto.to_dict()
        data['created_at'] = datetime.now()
        data['updated_at'] = datetime.now()

        success = self.repository.create(data)

        if success:
            logger.info(f"Created trade: {dto.trade_id}")
            return {
                'success': True,
                'trade_id': dto.trade_id,
                'message': 'Trade created successfully'
            }
        else:
            return {
                'success': False,
                'errors': {'general': 'Failed to create trade'}
            }

    def update(self, trade_id: str, dto: TradeDTO) -> Dict[str, Any]:
        """
        Update an existing trade.

        Args:
            trade_id: Trade ID
            dto: Updated trade data

        Returns:
            Result dict with success status and message
        """
        # Check exists
        existing = self.repository.find_by_id(trade_id)
        if not existing:
            return {
                'success': False,
                'errors': {'general': 'Trade not found'}
            }

        # Cannot update settled or cancelled trades
        if existing.get('status') in ['SETTLED', 'CANCELLED']:
            return {
                'success': False,
                'errors': {'general': f"Cannot update {existing.get('status').lower()} trade"}
            }

        # Validate
        errors = self._validate(dto, is_update=True)
        if errors:
            return {'success': False, 'errors': errors}

        # Update record
        data = dto.to_dict()
        # Remove fields that shouldn't be updated
        data.pop('trade_id', None)
        data.pop('created_by', None)
        data.pop('created_at', None)

        success = self.repository.update(trade_id, data)

        if success:
            logger.info(f"Updated trade: {trade_id}")
            return {
                'success': True,
                'message': 'Trade updated successfully'
            }
        else:
            return {
                'success': False,
                'errors': {'general': 'Failed to update trade'}
            }

    def delete(self, trade_id: str, deleted_by: str = 'system') -> Dict[str, Any]:
        """
        Soft delete a trade.

        Args:
            trade_id: Trade ID
            deleted_by: Username

        Returns:
            Result dict with success status
        """
        existing = self.repository.find_by_id(trade_id)
        if not existing:
            return {
                'success': False,
                'errors': {'general': 'Trade not found'}
            }

        # Cannot delete settled trades
        if existing.get('status') == 'SETTLED':
            return {
                'success': False,
                'errors': {'general': 'Cannot delete settled trade'}
            }

        success = self.repository.soft_delete(trade_id, deleted_by)

        if success:
            logger.info(f"Soft deleted trade: {trade_id}")
            return {
                'success': True,
                'message': 'Trade deleted successfully'
            }
        else:
            return {
                'success': False,
                'errors': {'general': 'Failed to delete trade'}
            }

    def restore(self, trade_id: str, restored_by: str = 'system') -> Dict[str, Any]:
        """
        Restore a soft-deleted trade.

        Args:
            trade_id: Trade ID
            restored_by: Username

        Returns:
            Result dict with success status
        """
        existing = self.repository.find_by_id(trade_id, include_deleted=True)
        if not existing:
            return {
                'success': False,
                'errors': {'general': 'Trade not found'}
            }

        if not existing.get('deleted_at'):
            return {
                'success': False,
                'errors': {'general': 'Trade is not deleted'}
            }

        success = self.repository.restore(trade_id, restored_by)

        if success:
            logger.info(f"Restored trade: {trade_id}")
            return {
                'success': True,
                'message': 'Trade restored successfully'
            }
        else:
            return {
                'success': False,
                'errors': {'general': 'Failed to restore trade'}
            }

    def update_status(self, trade_id: str, status: str, updated_by: str = 'system') -> Dict[str, Any]:
        """
        Update trade status.

        Args:
            trade_id: Trade ID
            status: New status
            updated_by: Username

        Returns:
            Result dict with success status
        """
        if status not in self.VALID_STATUSES:
            return {
                'success': False,
                'errors': {'status': f'Invalid status. Must be one of: {", ".join(self.VALID_STATUSES)}'}
            }

        existing = self.repository.find_by_id(trade_id)
        if not existing:
            return {
                'success': False,
                'errors': {'general': 'Trade not found'}
            }

        success = self.repository.update_status(trade_id, status, updated_by)

        if success:
            logger.info(f"Updated trade {trade_id} status to {status}")
            return {
                'success': True,
                'message': f'Trade status updated to {status}'
            }
        else:
            return {
                'success': False,
                'errors': {'general': 'Failed to update status'}
            }

    def search(self, search_term: str) -> List[Dict[str, Any]]:
        """Search trades by security name, ID, or broker."""
        return self.repository.search(search_term)

    def get_portfolio_summary(self, portfolio_id: str) -> Dict[str, Any]:
        """Get trade summary for a portfolio."""
        return self.repository.get_portfolio_summary(portfolio_id)

    def get_deleted(self) -> List[Dict[str, Any]]:
        """Get all soft-deleted trades."""
        return self.repository.find_deleted()

    def _validate(self, dto: TradeDTO, is_update: bool = False) -> Dict[str, str]:
        """
        Validate trade data.

        Args:
            dto: Trade data
            is_update: True if this is an update operation

        Returns:
            Dictionary of field errors (empty if valid)
        """
        errors = {}

        if not is_update and not dto.portfolio_id:
            errors['portfolio_id'] = 'Portfolio is required'

        if not dto.security_id or len(dto.security_id.strip()) < 3:
            errors['security_id'] = 'Security ID must be at least 3 characters'

        if not dto.security_name or len(dto.security_name.strip()) < 2:
            errors['security_name'] = 'Security name must be at least 2 characters'

        if dto.trade_type not in self.VALID_TYPES:
            errors['trade_type'] = f'Invalid type. Must be one of: {", ".join(self.VALID_TYPES)}'

        if not dto.quantity or dto.quantity <= 0:
            errors['quantity'] = 'Quantity must be greater than 0'

        if not dto.price or dto.price <= 0:
            errors['price'] = 'Price must be greater than 0'

        if dto.currency not in self.VALID_CURRENCIES:
            errors['currency'] = f'Invalid currency. Must be one of: {", ".join(self.VALID_CURRENCIES)}'

        if not dto.trade_date:
            errors['trade_date'] = 'Trade date is required'

        if dto.settlement_date and dto.trade_date:
            if dto.settlement_date < dto.trade_date:
                errors['settlement_date'] = 'Settlement date cannot be before trade date'

        if dto.status not in self.VALID_STATUSES:
            errors['status'] = f'Invalid status. Must be one of: {", ".join(self.VALID_STATUSES)}'

        return errors

    @classmethod
    def get_type_choices(cls) -> List[tuple]:
        """Get trade type choices for forms."""
        return [(t, t.title()) for t in cls.VALID_TYPES]

    @classmethod
    def get_status_choices(cls) -> List[tuple]:
        """Get status choices for forms."""
        return [(s, s.title()) for s in cls.VALID_STATUSES]

    @classmethod
    def get_currency_choices(cls) -> List[tuple]:
        """Get currency choices for forms."""
        return [(c, c) for c in cls.VALID_CURRENCIES]
