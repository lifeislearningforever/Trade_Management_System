"""
UDF Service
Business logic for User-Defined Fields operations following SOLID principles.

SOLID Principles Applied:
- Single Responsibility: Each method has one clear purpose
- Open/Closed: Extensible for new field types
- Liskov Substitution: Service layer can be substituted
- Interface Segregation: Clean service interface
- Dependency Inversion: Depends on abstractions (models), not concrete implementations
"""

from typing import List, Dict, Optional, Any
from django.db.models import Q, QuerySet
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import date, datetime

from udf.models import UDF, UDFValue, UDFHistory
from core.audit.audit_kudu_repository import audit_log_kudu_repository
from udf.repositories import (
    udf_definition_repository,
    udf_option_repository,
    udf_value_repository,
    reference_data_repository
)


class UDFService:
    """
    Service for User-Defined Fields business logic.

    Handles:
    - UDF definition CRUD operations
    - UDF value management
    - Validation and type conversion
    - Audit logging
    """

    @staticmethod
    def create_udf(user: User, data: Dict) -> UDF:
        """
        Create a new UDF definition.

        Args:
            user: User creating the UDF
            data: UDF configuration dictionary

        Returns:
            Created UDF instance

        Raises:
            ValidationError: If data is invalid
        """
        # Validate required fields
        required_fields = ['field_name', 'label', 'field_type', 'entity_type']
        for field in required_fields:
            if field not in data or not data[field]:
                raise ValidationError(f"{field} is required")

        # Check for duplicate field_name
        if UDF.objects.filter(field_name=data['field_name']).exists():
            raise ValidationError(f"UDF with field_name {data['field_name']} already exists")

        # Validate field_type
        valid_types = [choice[0] for choice in UDF.FIELD_TYPE_CHOICES]
        if data['field_type'] not in valid_types:
            raise ValidationError(f"Invalid field_type. Must be one of: {', '.join(valid_types)}")

        # Validate entity_type
        valid_entities = [choice[0] for choice in UDF.ENTITY_TYPE_CHOICES]
        if data['entity_type'] not in valid_entities:
            raise ValidationError(f"Invalid entity_type. Must be one of: {', '.join(valid_entities)}")

        # Create UDF in Django
        udf = UDF.objects.create(
            field_name=data['field_name'],
            label=data['label'],
            description=data.get('description', ''),
            field_type=data['field_type'],
            entity_type=data['entity_type'],
            is_required=data.get('is_required', False),
            is_unique=data.get('is_unique', False),
            default_value=data.get('default_value'),
            dropdown_options=data.get('dropdown_options'),
            min_value=data.get('min_value'),
            max_value=data.get('max_value'),
            max_length=data.get('max_length'),
            display_order=data.get('display_order', 0),
            group_name=data.get('group_name', ''),
            is_active=data.get('is_active', True),
            created_by=user,
            updated_by=user
        )

        # Save to Kudu table
        try:
            import time
            # Prepare data for Kudu (timestamps as BIGINT milliseconds)
            kudu_data = {
                'udf_id': udf.id,
                'field_name': udf.field_name,
                'label': udf.label,
                'description': udf.description or '',
                'field_type': udf.field_type,
                'entity_type': udf.entity_type,
                'is_required': udf.is_required,
                'is_unique': udf.is_unique,
                'max_length': udf.max_length,
                'display_order': udf.display_order or 0,
                'group_name': udf.group_name or '',
                'is_active': udf.is_active,
                'created_by': user.username,
                'created_at': int(udf.created_at.timestamp() * 1000),  # BIGINT milliseconds
                'updated_by': user.username,
                'updated_at': int(udf.updated_at.timestamp() * 1000)   # BIGINT milliseconds
            }

            # Add default values based on type
            if udf.field_type == 'TEXT':
                kudu_data['default_string'] = udf.default_value or ''
            elif udf.field_type == 'NUMBER':
                kudu_data['default_decimal'] = str(udf.default_value) if udf.default_value else None
            elif udf.field_type == 'DATE':
                kudu_data['default_datetime'] = int(time.time() * 1000) if udf.default_value else None
            elif udf.field_type == 'BOOLEAN':
                kudu_data['default_bool'] = bool(udf.default_value) if udf.default_value is not None else None
            elif udf.field_type == 'INTEGER':
                kudu_data['default_int'] = int(udf.default_value) if udf.default_value else None

            # Add min/max values if present
            if udf.min_value:
                kudu_data['min_value_decimal'] = str(udf.min_value)
            if udf.max_value:
                kudu_data['max_value_decimal'] = str(udf.max_value)

            # Insert into Kudu
            success = udf_definition_repository.insert_definition(kudu_data)
            if not success:
                logger.warning(f"Failed to save UDF {udf.field_name} to Kudu")
        except Exception as e:
            logger.error(f"Error saving UDF to Kudu: {e}")
            import traceback
            traceback.print_exc()

        # Log creation to Kudu - General audit log
        audit_log_kudu_repository.log_action(
            user_id=str(user.id),
            username=user.username,
            user_email=user.email or '',
            action_type='CREATE',
            entity_type='UDF',
            entity_id=str(udf.id),
            entity_name=udf.field_name,
            field_name='created_by',
            old_value=None,
            new_value=user.get_full_name() or user.username,
            action_description=f"Created UDF {udf.field_name} ({udf.label}) for {udf.entity_type}",
            module_name='udf.services.udf_service',
            function_name='create_udf',
            status='SUCCESS'
        )

        # Log UDF-specific audit
        audit_log_kudu_repository.log_udf_action(
            user_id=str(user.id),
            username=user.username,
            action_type='CREATE',
            udf_id=udf.id,
            field_name=udf.field_name,
            label=udf.label,
            entity_type=udf.entity_type,
            changes=f"field_type={udf.field_type}, is_required={udf.is_required}, created_by={user.get_full_name() or user.username}",
            action_description=f"Created UDF definition for {udf.entity_type}",
            status='SUCCESS'
        )

        return udf

    @staticmethod
    def update_udf(udf: UDF, user: User, data: Dict) -> UDF:
        """
        Update UDF definition.

        Args:
            udf: UDF instance to update
            user: User performing the update
            data: Updated data dictionary

        Returns:
            Updated UDF instance

        Raises:
            ValidationError: If data is invalid
        """
        # Track changes
        changes = []

        # Update fields
        editable_fields = [
            'label', 'description', 'is_required', 'is_unique', 'default_value',
            'dropdown_options', 'min_value', 'max_value', 'max_length',
            'display_order', 'group_name', 'is_active'
        ]

        for field in editable_fields:
            if field in data:
                old_value = getattr(udf, field)
                new_value = data[field]
                if old_value != new_value:
                    changes.append(f"{field}: {old_value} -> {new_value}")
                    setattr(udf, field, new_value)

        udf.updated_by = user
        udf.full_clean()  # Validate
        udf.save()

        # Log update to Kudu
        if changes:
            # General audit log
            audit_log_kudu_repository.log_action(
                user_id=str(user.id),
                username=user.username,
                action_type='UPDATE',
                entity_type='UDF',
                entity_id=str(udf.id),
                entity_name=udf.field_name,
                action_description=f"Updated UDF {udf.field_name}: {'; '.join(changes)}",
                module_name='udf.services.udf_service',
                function_name='update_udf',
                status='SUCCESS'
            )

            # UDF-specific audit log
            audit_log_kudu_repository.log_udf_action(
                user_id=str(user.id),
                username=user.username,
                action_type='UPDATE',
                udf_id=udf.id,
                field_name=udf.field_name,
                label=udf.label,
                entity_type=udf.entity_type,
                changes='; '.join(changes),
                action_description=f"Updated {len(changes)} field(s)",
                status='SUCCESS'
            )

        return udf

    @staticmethod
    def delete_udf(udf: UDF, user: User) -> None:
        """
        Delete UDF definition (soft delete by deactivating).

        Args:
            udf: UDF to delete
            user: User performing the deletion
        """
        udf.is_active = False
        udf.updated_by = user
        udf.save()

        # Log deletion to Kudu
        # General audit log
        audit_log_kudu_repository.log_action(
            user_id=str(user.id),
            username=user.username,
            action_type='DELETE',
            entity_type='UDF',
            entity_id=str(udf.id),
            entity_name=udf.field_name,
            action_description=f"Deactivated UDF {udf.field_name} ({udf.label})",
            module_name='udf.services.udf_service',
            function_name='delete_udf',
            status='SUCCESS'
        )

        # UDF-specific audit log
        audit_log_kudu_repository.log_udf_action(
            user_id=str(user.id),
            username=user.username,
            action_type='DELETE',
            udf_id=udf.id,
            field_name=udf.field_name,
            label=udf.label,
            entity_type=udf.entity_type,
            changes='is_active=False',
            action_description='Deactivated UDF definition',
            status='SUCCESS'
        )

    @staticmethod
    def set_udf_value(
        udf: UDF,
        entity_type: str,
        entity_id: int,
        value: Any,
        user: User
    ) -> UDFValue:
        """
        Set UDF value for an entity.

        Args:
            udf: UDF definition
            entity_type: Type of entity (PORTFOLIO, TRADE, etc.)
            entity_id: ID of the entity
            value: Value to set
            user: User setting the value

        Returns:
            Created or updated UDFValue instance

        Raises:
            ValidationError: If value is invalid
        """
        # Validate entity_type matches UDF
        if entity_type != udf.entity_type:
            raise ValidationError(
                f"Entity type mismatch: UDF is for {udf.entity_type}, but {entity_type} provided"
            )

        # Get or create UDFValue
        udf_value, created = UDFValue.objects.get_or_create(
            udf=udf,
            entity_type=entity_type,
            entity_id=entity_id,
            defaults={
                'created_by': user,
                'updated_by': user
            }
        )

        # Store old value for history
        old_value = str(udf_value.get_value()) if not created else None

        # Set new value
        udf_value.set_value(value)
        udf_value.updated_by = user
        udf_value.full_clean()  # Validate
        udf_value.save()

        # Also save to Hive
        try:
            udf_value_repository.insert_value({
                'value_id': udf_value.id,
                'udf_id': udf.id,
                'field_name': udf.field_name,
                'entity_type': entity_type,
                'entity_id': entity_id,
                'value_string': udf_value.value_text,
                'value_int': int(udf_value.value_number) if udf_value.value_number else None,
                'value_decimal': float(udf_value.value_number) if udf_value.value_number else None,
                'value_date': udf_value.value_date.strftime('%Y-%m-%d') if udf_value.value_date else None,
                'value_bool': udf_value.value_boolean,
                'value_json': udf_value.value_json,
                'is_active': True,
                'created_by': user.username,
                'created_at': udf_value.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_by': user.username,
                'updated_at': udf_value.updated_at.strftime('%Y-%m-%d %H:%M:%S')
            })
        except Exception as e:
            print(f"Warning: Failed to save UDF value to Hive: {e}")

        # Create history record
        UDFHistory.objects.create(
            udf_value=udf_value,
            action='CREATE' if created else 'UPDATE',
            old_value=old_value,
            new_value=str(value),
            changed_by=user
        )

        # Log action to Kudu
        action_type = 'CREATE' if created else 'UPDATE'

        # General audit log
        audit_log_kudu_repository.log_action(
            user_id=str(user.id),
            username=user.username,
            action_type=action_type,
            entity_type='UDF_VALUE',
            entity_id=str(udf_value.id),
            entity_name=udf.field_name,
            action_description=f"{action_type} UDF value: {udf.field_name} = {value} for {entity_type}#{entity_id}",
            old_value=old_value,
            new_value=str(value),
            field_name=udf.field_name,
            module_name='udf.services.udf_service',
            function_name='set_udf_value',
            status='SUCCESS'
        )

        # UDF value-specific audit log
        audit_log_kudu_repository.log_udf_value_action(
            user_id=str(user.id),
            username=user.username,
            action_type=action_type,
            udf_id=udf.id,
            field_name=udf.field_name,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=old_value,
            new_value=str(value),
            value_type=udf.field_type,
            action_description=f"{'Created' if created else 'Updated'} {udf.label}",
            status='SUCCESS'
        )

        return udf_value

    @staticmethod
    def get_udf_value(udf: UDF, entity_type: str, entity_id: int) -> Optional[Any]:
        """
        Get UDF value for an entity.

        Args:
            udf: UDF definition
            entity_type: Type of entity
            entity_id: ID of the entity

        Returns:
            Value or None if not set
        """
        try:
            udf_value = UDFValue.objects.get(
                udf=udf,
                entity_type=entity_type,
                entity_id=entity_id
            )
            return udf_value.get_value()
        except UDFValue.DoesNotExist:
            return udf.default_value

    @staticmethod
    def get_entity_udf_values(entity_type: str, entity_id: int) -> Dict[str, Any]:
        """
        Get all UDF values for an entity.

        Args:
            entity_type: Type of entity
            entity_id: ID of the entity

        Returns:
            Dictionary mapping field_name to value
        """
        udf_values = UDFValue.objects.filter(
            entity_type=entity_type,
            entity_id=entity_id
        ).select_related('udf')

        result = {}
        for udf_value in udf_values:
            result[udf_value.udf.field_name] = udf_value.get_value()

        # Include active UDFs with default values if not set
        active_udfs = UDF.objects.filter(
            entity_type=entity_type,
            is_active=True
        )
        for udf in active_udfs:
            if udf.field_name not in result:
                result[udf.field_name] = udf.default_value

        return result

    @staticmethod
    def set_entity_udf_values(
        entity_type: str,
        entity_id: int,
        values: Dict[str, Any],
        user: User
    ) -> List[UDFValue]:
        """
        Set multiple UDF values for an entity.

        Args:
            entity_type: Type of entity
            entity_id: ID of the entity
            values: Dictionary mapping field_name to value
            user: User setting the values

        Returns:
            List of created/updated UDFValue instances

        Raises:
            ValidationError: If any value is invalid
        """
        results = []
        errors = []

        for field_name, value in values.items():
            try:
                # Get UDF definition
                udf = UDF.objects.get(
                    field_name=field_name,
                    entity_type=entity_type,
                    is_active=True
                )

                # Set value
                udf_value = UDFService.set_udf_value(
                    udf=udf,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    value=value,
                    user=user
                )
                results.append(udf_value)

            except UDF.DoesNotExist:
                errors.append(f"UDF {field_name} not found for {entity_type}")
            except Exception as e:
                errors.append(f"Error setting {field_name}: {str(e)}")

        if errors:
            raise ValidationError("; ".join(errors))

        return results

    @staticmethod
    def delete_udf_value(udf_value: UDFValue, user: User) -> None:
        """
        Delete UDF value.

        Args:
            udf_value: UDFValue to delete
            user: User performing the deletion
        """
        # Store old value for history
        old_value = str(udf_value.get_value())

        # Create history record
        UDFHistory.objects.create(
            udf_value=udf_value,
            action='DELETE',
            old_value=old_value,
            new_value=None,
            changed_by=user
        )

        # Log deletion to Kudu
        # General audit log
        audit_log_kudu_repository.log_action(
            user_id=str(user.id),
            username=user.username,
            action_type='DELETE',
            entity_type='UDF_VALUE',
            entity_id=str(udf_value.id),
            entity_name=udf_value.udf.field_name,
            action_description=f"Deleted UDF value: {udf_value.udf.field_name} for {udf_value.entity_type}#{udf_value.entity_id}",
            old_value=old_value,
            field_name=udf_value.udf.field_name,
            module_name='udf.services.udf_service',
            function_name='delete_udf_value',
            status='SUCCESS'
        )

        # UDF value-specific audit log
        audit_log_kudu_repository.log_udf_value_action(
            user_id=str(user.id),
            username=user.username,
            action_type='DELETE',
            udf_id=udf_value.udf.id,
            field_name=udf_value.udf.field_name,
            entity_type=udf_value.entity_type,
            entity_id=udf_value.entity_id,
            old_value=old_value,
            new_value=None,
            value_type=udf_value.udf.field_type,
            action_description=f"Deleted {udf_value.udf.label}",
            status='SUCCESS'
        )

        # Delete
        udf_value.delete()

    @staticmethod
    def validate_udf_values(entity_type: str, values: Dict[str, Any]) -> None:
        """
        Validate UDF values against UDF definitions.

        Args:
            entity_type: Type of entity
            values: Dictionary mapping field_name to value

        Raises:
            ValidationError: If validation fails
        """
        errors = []

        # Get all active UDFs for this entity type
        udfs = UDF.objects.filter(entity_type=entity_type, is_active=True)

        # Check required fields
        for udf in udfs:
            if udf.is_required:
                if udf.field_name not in values or values[udf.field_name] in [None, '']:
                    errors.append(f"{udf.label} is required")

        # Validate provided values
        for field_name, value in values.items():
            try:
                udf = udfs.get(field_name=field_name)

                # Type-specific validation
                if udf.field_type == 'TEXT' and value:
                    if udf.max_length and len(str(value)) > udf.max_length:
                        errors.append(f"{udf.label} exceeds maximum length of {udf.max_length}")

                elif udf.field_type in ['NUMBER', 'CURRENCY', 'PERCENTAGE'] and value is not None:
                    try:
                        numeric_value = Decimal(str(value))
                        if udf.min_value is not None and numeric_value < udf.min_value:
                            errors.append(f"{udf.label} must be at least {udf.min_value}")
                        if udf.max_value is not None and numeric_value > udf.max_value:
                            errors.append(f"{udf.label} must be at most {udf.max_value}")
                    except (ValueError, TypeError):
                        errors.append(f"{udf.label} must be a valid number")

                elif udf.field_type == 'DROPDOWN' and value:
                    if value not in udf.dropdown_options:
                        errors.append(f"{udf.label} must be one of: {', '.join(udf.dropdown_options)}")

                elif udf.field_type == 'MULTI_SELECT' and value:
                    if not isinstance(value, list):
                        errors.append(f"{udf.label} must be a list")
                    else:
                        for v in value:
                            if v not in udf.dropdown_options:
                                errors.append(f"{udf.label}: {v} is not a valid option")

            except UDF.DoesNotExist:
                errors.append(f"UDF {field_name} not found for {entity_type}")

        if errors:
            raise ValidationError("; ".join(errors))

    @staticmethod
    def get_udf_by_id(udf_id: int) -> Optional[UDF]:
        """Get UDF by ID."""
        try:
            return UDF.objects.select_related('created_by', 'updated_by').get(id=udf_id)
        except UDF.DoesNotExist:
            return None

    @staticmethod
    def get_udf_by_field_name(field_name: str, entity_type: str) -> Optional[UDF]:
        """Get UDF by field name and entity type."""
        try:
            return UDF.objects.get(field_name=field_name, entity_type=entity_type)
        except UDF.DoesNotExist:
            return None

    @staticmethod
    def list_udfs(
        entity_type: Optional[str] = None,
        is_active: Optional[bool] = True,
        search: Optional[str] = None
    ) -> QuerySet:
        """
        List UDFs with optional filtering.

        Args:
            entity_type: Filter by entity type
            is_active: Filter by active status
            search: Search in field_name, label

        Returns:
            QuerySet of UDFs
        """
        queryset = UDF.objects.select_related(
            'created_by', 'updated_by'
        ).order_by('entity_type', 'display_order', 'field_name')

        if entity_type:
            queryset = queryset.filter(entity_type=entity_type)

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        if search:
            queryset = queryset.filter(
                Q(field_name__icontains=search) |
                Q(label__icontains=search) |
                Q(description__icontains=search)
            )

        return queryset

    @staticmethod
    def get_udf_history(udf_value: UDFValue) -> QuerySet:
        """Get change history for a UDF value."""
        return UDFHistory.objects.filter(
            udf_value=udf_value
        ).select_related('changed_by').order_by('-changed_at')

    @staticmethod
    def get_entity_udf_history(entity_type: str, entity_id: int) -> QuerySet:
        """Get all UDF change history for an entity."""
        return UDFHistory.objects.filter(
            udf_value__entity_type=entity_type,
            udf_value__entity_id=entity_id
        ).select_related('udf_value__udf', 'changed_by').order_by('-changed_at')

    # ========================
    # Hive Integration Methods
    # ========================

    @staticmethod
    def get_dropdown_options_from_hive(field_name: str) -> List[Dict[str, str]]:
        """
        Get dropdown options for a UDF field from Hive.

        Args:
            field_name: The UDF field name (e.g., 'account_group', 'entity_group')

        Returns:
            List of dictionaries with 'value' and 'label' keys
        """
        try:
            options = udf_option_repository.get_options_by_field_name(field_name)
            return [
                {'value': opt['option_value'], 'label': opt['option_value']}
                for opt in options if opt.get('is_active', True)
            ]
        except Exception as e:
            # If Hive fetch fails, return empty list
            return []

    @staticmethod
    def get_currency_options() -> List[Dict[str, str]]:
        """
        Get currency options from Hive reference data.

        Returns:
            List of dictionaries with 'value' (iso_code) and 'label' (name + symbol)
        """
        try:
            currencies = reference_data_repository.get_currencies()
            return [
                {
                    'value': c['iso_code'],
                    'label': f"{c['name']} ({c['iso_code']}) - {c.get('symbol', '')}"
                }
                for c in currencies if c.get('iso_code')
            ]
        except Exception as e:
            return []

    @staticmethod
    def get_country_options() -> List[Dict[str, str]]:
        """
        Get country options from Hive reference data.

        Returns:
            List of dictionaries with 'value' (label) and 'label' (full_name)
        """
        try:
            countries = reference_data_repository.get_countries()
            return [
                {
                    'value': c['label'],
                    'label': f"{c['full_name']} ({c['label']})"
                }
                for c in countries if c.get('label')
            ]
        except Exception as e:
            return []

    @staticmethod
    def get_calendar_options() -> List[Dict[str, str]]:
        """
        Get calendar options from Hive reference data.

        Returns:
            List of dictionaries with 'value' and 'label'
        """
        try:
            calendars = reference_data_repository.get_calendars()
            return [
                {
                    'value': c['calendar_label'],
                    'label': f"{c['calendar_label']} - {c.get('calendar_description', '')}"
                }
                for c in calendars if c.get('calendar_label')
            ]
        except Exception as e:
            return []

    @staticmethod
    def get_counterparty_options(counterparty_type: Optional[str] = None) -> List[Dict[str, str]]:
        """
        Get counterparty options from Hive reference data.

        Args:
            counterparty_type: Optional filter - 'broker', 'custodian', 'issuer', or None for all

        Returns:
            List of dictionaries with 'value' (counterparty_name) and 'label'
        """
        try:
            if counterparty_type == 'broker':
                counterparties = reference_data_repository.get_brokers()
            elif counterparty_type == 'custodian':
                counterparties = reference_data_repository.get_custodians()
            elif counterparty_type == 'issuer':
                counterparties = reference_data_repository.get_issuers()
            else:
                counterparties = reference_data_repository.get_counterparties()

            return [
                {
                    'value': cp['counterparty_name'],
                    'label': f"{cp['counterparty_name']} - {cp.get('city', '')}, {cp.get('country', '')}"
                }
                for cp in counterparties if cp.get('counterparty_name')
            ]
        except Exception as e:
            return []

    @staticmethod
    def get_account_group_options() -> List[Dict[str, str]]:
        """
        Get account group options for Portfolio UDF dropdown.

        Returns:
            List of dictionaries with 'value' and 'label'
        """
        try:
            return reference_data_repository.get_account_groups()
        except Exception as e:
            # Fallback to default options
            return [
                {'value': 'TRADING', 'label': 'Trading'},
                {'value': 'INVESTMENT', 'label': 'Investment'},
                {'value': 'HEDGING', 'label': 'Hedging'},
                {'value': 'TREASURY', 'label': 'Treasury'},
                {'value': 'OPERATIONS', 'label': 'Operations'},
            ]

    @staticmethod
    def get_entity_group_options() -> List[Dict[str, str]]:
        """
        Get entity group options for Portfolio UDF dropdown.

        Returns:
            List of dictionaries with 'value' and 'label'
        """
        try:
            return reference_data_repository.get_entity_groups()
        except Exception as e:
            # Fallback to default options
            return [
                {'value': 'CORPORATE', 'label': 'Corporate'},
                {'value': 'INSTITUTIONAL', 'label': 'Institutional'},
                {'value': 'RETAIL', 'label': 'Retail'},
                {'value': 'GOVERNMENT', 'label': 'Government'},
                {'value': 'FUND', 'label': 'Fund'},
            ]

    @staticmethod
    def get_udf_dropdown_options(field_name: str, field_type: str = 'DROPDOWN') -> List[Dict[str, str]]:
        """
        Get dropdown options for any UDF field, checking both Hive and local definitions.

        This method intelligently routes to the appropriate data source:
        - For 'account_group': fetches from Hive UDF options or returns defaults
        - For 'entity_group': fetches from Hive UDF options or returns defaults
        - For currency-related fields: fetches from currency reference data
        - For country-related fields: fetches from country reference data
        - For calendar-related fields: fetches from calendar reference data
        - For counterparty fields: fetches from counterparty reference data
        - For other fields: fetches from UDF options table

        Args:
            field_name: The UDF field name
            field_type: The field type (default: 'DROPDOWN')

        Returns:
            List of option dictionaries
        """
        # Portfolio-specific fields
        if field_name == 'account_group':
            return UDFService.get_account_group_options()
        elif field_name == 'entity_group':
            return UDFService.get_entity_group_options()

        # Reference data fields
        elif 'currency' in field_name.lower():
            return UDFService.get_currency_options()
        elif 'country' in field_name.lower():
            return UDFService.get_country_options()
        elif 'calendar' in field_name.lower():
            return UDFService.get_calendar_options()
        elif 'counterparty' in field_name.lower() or 'broker' in field_name.lower() or 'custodian' in field_name.lower():
            # Determine counterparty type from field name
            cp_type = None
            if 'broker' in field_name.lower():
                cp_type = 'broker'
            elif 'custodian' in field_name.lower():
                cp_type = 'custodian'
            elif 'issuer' in field_name.lower():
                cp_type = 'issuer'
            return UDFService.get_counterparty_options(cp_type)

        # Generic UDF options from Hive
        else:
            return UDFService.get_dropdown_options_from_hive(field_name)
