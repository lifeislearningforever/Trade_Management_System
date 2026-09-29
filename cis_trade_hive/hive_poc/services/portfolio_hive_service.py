"""
Portfolio Service for Hive POC

Business logic layer for portfolio operations with Hive managed tables.
"""

import logging
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass, asdict

from ..repositories.portfolio_hive_repository import PortfolioHiveRepository

logger = logging.getLogger('hive_poc')


@dataclass
class PortfolioDTO:
    """Data Transfer Object for Portfolio"""
    portfolio_id: str = ''
    portfolio_name: str = ''
    portfolio_code: str = ''
    portfolio_type: str = 'EQUITY'
    currency: str = 'USD'
    manager_name: str = ''
    description: str = ''
    status: str = 'DRAFT'
    created_by: str = 'system'
    updated_by: str = 'system'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PortfolioHiveService:
    """
    Service class for Portfolio operations.

    Handles business logic and validation for portfolio CRUD operations
    using Hive managed tables with ORC format.
    """

    VALID_TYPES = ['EQUITY', 'FIXED_INCOME', 'BALANCED', 'ALTERNATIVE', 'MONEY_MARKET', 'MULTI_ASSET']
    VALID_STATUSES = ['DRAFT', 'ACTIVE', 'INACTIVE', 'CLOSED']
    VALID_CURRENCIES = ['USD', 'EUR', 'GBP', 'SGD', 'JPY', 'AUD', 'CHF', 'HKD']

    def __init__(self):
        self.repository = PortfolioHiveRepository()

    def get_all(self, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """
        Get all portfolios.

        Args:
            include_deleted: Include soft-deleted portfolios

        Returns:
            List of portfolios
        """
        return self.repository.find_all(include_deleted)

    def get_by_id(self, portfolio_id: str) -> Optional[Dict[str, Any]]:
        """
        Get portfolio by ID.

        Args:
            portfolio_id: Portfolio ID

        Returns:
            Portfolio or None
        """
        return self.repository.find_by_id(portfolio_id)

    def get_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Get portfolio by code.

        Args:
            code: Portfolio code

        Returns:
            Portfolio or None
        """
        return self.repository.find_by_code(code)

    def create(self, dto: PortfolioDTO) -> Dict[str, Any]:
        """
        Create a new portfolio.

        Args:
            dto: Portfolio data transfer object

        Returns:
            Result dict with success status and message
        """
        # Validate
        errors = self._validate(dto)
        if errors:
            return {'success': False, 'errors': errors}

        # Check for duplicate code
        existing = self.repository.find_by_code(dto.portfolio_code)
        if existing:
            return {
                'success': False,
                'errors': {'portfolio_code': 'Portfolio code already exists'}
            }

        # Generate ID if not provided
        if not dto.portfolio_id:
            dto.portfolio_id = f"PF{str(uuid.uuid4())[:8].upper()}"

        # Create record
        data = dto.to_dict()
        data['created_at'] = datetime.now()
        data['updated_at'] = datetime.now()

        success = self.repository.create(data)

        if success:
            logger.info(f"Created portfolio: {dto.portfolio_id}")
            return {
                'success': True,
                'portfolio_id': dto.portfolio_id,
                'message': 'Portfolio created successfully'
            }
        else:
            return {
                'success': False,
                'errors': {'general': 'Failed to create portfolio'}
            }

    def update(self, portfolio_id: str, dto: PortfolioDTO) -> Dict[str, Any]:
        """
        Update an existing portfolio.

        Args:
            portfolio_id: Portfolio ID
            dto: Updated portfolio data

        Returns:
            Result dict with success status and message
        """
        # Check exists
        existing = self.repository.find_by_id(portfolio_id)
        if not existing:
            return {
                'success': False,
                'errors': {'general': 'Portfolio not found'}
            }

        # Validate
        errors = self._validate(dto, is_update=True)
        if errors:
            return {'success': False, 'errors': errors}

        # Check for duplicate code (if changing)
        if dto.portfolio_code != existing.get('portfolio_code'):
            duplicate = self.repository.find_by_code(dto.portfolio_code)
            if duplicate:
                return {
                    'success': False,
                    'errors': {'portfolio_code': 'Portfolio code already exists'}
                }

        # Update record
        data = {
            'portfolio_name': dto.portfolio_name,
            'portfolio_code': dto.portfolio_code,
            'portfolio_type': dto.portfolio_type,
            'currency': dto.currency,
            'manager_name': dto.manager_name,
            'description': dto.description,
            'status': dto.status,
            'updated_by': dto.updated_by,
        }

        success = self.repository.update(portfolio_id, data)

        if success:
            logger.info(f"Updated portfolio: {portfolio_id}")
            return {
                'success': True,
                'message': 'Portfolio updated successfully'
            }
        else:
            return {
                'success': False,
                'errors': {'general': 'Failed to update portfolio'}
            }

    def delete(self, portfolio_id: str, deleted_by: str = 'system') -> Dict[str, Any]:
        """
        Soft delete a portfolio.

        Args:
            portfolio_id: Portfolio ID
            deleted_by: Username

        Returns:
            Result dict with success status
        """
        existing = self.repository.find_by_id(portfolio_id)
        if not existing:
            return {
                'success': False,
                'errors': {'general': 'Portfolio not found'}
            }

        success = self.repository.soft_delete(portfolio_id, deleted_by)

        if success:
            logger.info(f"Soft deleted portfolio: {portfolio_id}")
            return {
                'success': True,
                'message': 'Portfolio deleted successfully'
            }
        else:
            return {
                'success': False,
                'errors': {'general': 'Failed to delete portfolio'}
            }

    def restore(self, portfolio_id: str, restored_by: str = 'system') -> Dict[str, Any]:
        """
        Restore a soft-deleted portfolio.

        Args:
            portfolio_id: Portfolio ID
            restored_by: Username

        Returns:
            Result dict with success status
        """
        existing = self.repository.find_by_id(portfolio_id, include_deleted=True)
        if not existing:
            return {
                'success': False,
                'errors': {'general': 'Portfolio not found'}
            }

        if not existing.get('deleted_at'):
            return {
                'success': False,
                'errors': {'general': 'Portfolio is not deleted'}
            }

        success = self.repository.restore(portfolio_id, restored_by)

        if success:
            logger.info(f"Restored portfolio: {portfolio_id}")
            return {
                'success': True,
                'message': 'Portfolio restored successfully'
            }
        else:
            return {
                'success': False,
                'errors': {'general': 'Failed to restore portfolio'}
            }

    def search(self, search_term: str) -> List[Dict[str, Any]]:
        """Search portfolios by name, code, or description."""
        return self.repository.search(search_term)

    def get_dropdown_options(self) -> List[Dict[str, str]]:
        """Get portfolios for dropdown selection."""
        return self.repository.get_portfolio_dropdown()

    def get_deleted(self) -> List[Dict[str, Any]]:
        """Get all soft-deleted portfolios."""
        return self.repository.find_deleted()

    def _validate(self, dto: PortfolioDTO, is_update: bool = False) -> Dict[str, str]:
        """
        Validate portfolio data.

        Args:
            dto: Portfolio data
            is_update: True if this is an update operation

        Returns:
            Dictionary of field errors (empty if valid)
        """
        errors = {}

        if not dto.portfolio_name or len(dto.portfolio_name.strip()) < 3:
            errors['portfolio_name'] = 'Portfolio name must be at least 3 characters'

        if not dto.portfolio_code or len(dto.portfolio_code.strip()) < 2:
            errors['portfolio_code'] = 'Portfolio code must be at least 2 characters'

        if dto.portfolio_type not in self.VALID_TYPES:
            errors['portfolio_type'] = f'Invalid type. Must be one of: {", ".join(self.VALID_TYPES)}'

        if dto.currency not in self.VALID_CURRENCIES:
            errors['currency'] = f'Invalid currency. Must be one of: {", ".join(self.VALID_CURRENCIES)}'

        if dto.status not in self.VALID_STATUSES:
            errors['status'] = f'Invalid status. Must be one of: {", ".join(self.VALID_STATUSES)}'

        return errors

    @classmethod
    def get_type_choices(cls) -> List[tuple]:
        """Get portfolio type choices for forms."""
        return [(t, t.replace('_', ' ').title()) for t in cls.VALID_TYPES]

    @classmethod
    def get_status_choices(cls) -> List[tuple]:
        """Get status choices for forms."""
        return [(s, s.title()) for s in cls.VALID_STATUSES]

    @classmethod
    def get_currency_choices(cls) -> List[tuple]:
        """Get currency choices for forms."""
        return [(c, c) for c in cls.VALID_CURRENCIES]
