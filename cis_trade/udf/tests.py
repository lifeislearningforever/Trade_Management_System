"""
UDF Module Tests
Comprehensive test cases for UDF models, services, and views.
All tests must pass before commit to GitHub.
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date

from .models import UDF, UDFValue, UDFHistory
from .services import UDFService
from core.models import AuditLog


class UDFModelTest(TestCase):
    """Test UDF model and validation."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user('testuser', 'test@test.com', 'pass123')

    def test_create_text_udf(self):
        """Test creating a TEXT type UDF."""
        udf = UDF.objects.create(
            field_name='test_field',
            label='Test Field',
            field_type='TEXT',
            entity_type='PORTFOLIO',
            max_length=100,
            created_by=self.user
        )

        self.assertEqual(udf.field_name, 'test_field')
        self.assertEqual(udf.field_type, 'TEXT')
        self.assertEqual(udf.max_length, 100)

    def test_create_number_udf(self):
        """Test creating a NUMBER type UDF with min/max values."""
        udf = UDF.objects.create(
            field_name='rating',
            label='Risk Rating',
            field_type='NUMBER',
            entity_type='PORTFOLIO',
            min_value=Decimal('1.0'),
            max_value=Decimal('10.0'),
            created_by=self.user
        )

        self.assertEqual(udf.field_name, 'rating')
        self.assertEqual(udf.min_value, Decimal('1.0'))
        self.assertEqual(udf.max_value, Decimal('10.0'))

    def test_create_dropdown_udf(self):
        """Test creating a DROPDOWN type UDF."""
        udf = UDF.objects.create(
            field_name='status',
            label='Status',
            field_type='DROPDOWN',
            entity_type='TRADE',
            dropdown_options=['Active', 'Inactive', 'Pending'],
            created_by=self.user
        )

        self.assertEqual(len(udf.dropdown_options), 3)
        self.assertIn('Active', udf.dropdown_options)

    def test_dropdown_validation(self):
        """Test dropdown validation in clean method."""
        udf = UDF(
            field_name='status',
            label='Status',
            field_type='DROPDOWN',
            entity_type='TRADE',
            dropdown_options=None,  # Invalid - must have options
            created_by=self.user
        )

        with self.assertRaises(ValidationError):
            udf.full_clean()

    def test_min_max_validation(self):
        """Test min/max value validation."""
        udf = UDF(
            field_name='rating',
            label='Rating',
            field_type='NUMBER',
            entity_type='PORTFOLIO',
            min_value=Decimal('10.0'),
            max_value=Decimal('5.0'),  # Invalid - min > max
            created_by=self.user
        )

        with self.assertRaises(ValidationError):
            udf.full_clean()


class UDFValueTest(TestCase):
    """Test UDFValue model and polymorphic storage."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user('testuser', 'test@test.com', 'pass123')

        # Create different types of UDFs
        self.text_udf = UDF.objects.create(
            field_name='notes',
            label='Notes',
            field_type='TEXT',
            entity_type='PORTFOLIO',
            created_by=self.user
        )

        self.number_udf = UDF.objects.create(
            field_name='risk_score',
            label='Risk Score',
            field_type='NUMBER',
            entity_type='PORTFOLIO',
            min_value=Decimal('0'),
            max_value=Decimal('100'),
            created_by=self.user
        )

        self.dropdown_udf = UDF.objects.create(
            field_name='priority',
            label='Priority',
            field_type='DROPDOWN',
            entity_type='PORTFOLIO',
            dropdown_options=['High', 'Medium', 'Low'],
            created_by=self.user
        )

        self.boolean_udf = UDF.objects.create(
            field_name='is_active',
            label='Is Active',
            field_type='BOOLEAN',
            entity_type='PORTFOLIO',
            created_by=self.user
        )

    def test_text_value_storage(self):
        """Test storing and retrieving TEXT values."""
        udf_value = UDFValue.objects.create(
            udf=self.text_udf,
            entity_type='PORTFOLIO',
            entity_id=1,
            created_by=self.user
        )
        udf_value.set_value('Test note content')
        udf_value.save()

        self.assertEqual(udf_value.get_value(), 'Test note content')
        self.assertEqual(udf_value.value_text, 'Test note content')

    def test_number_value_storage(self):
        """Test storing and retrieving NUMBER values."""
        udf_value = UDFValue.objects.create(
            udf=self.number_udf,
            entity_type='PORTFOLIO',
            entity_id=1,
            created_by=self.user
        )
        udf_value.set_value(Decimal('75.5'))
        udf_value.save()

        self.assertEqual(udf_value.get_value(), Decimal('75.5'))
        self.assertEqual(udf_value.value_number, Decimal('75.5'))

    def test_boolean_value_storage(self):
        """Test storing and retrieving BOOLEAN values."""
        udf_value = UDFValue.objects.create(
            udf=self.boolean_udf,
            entity_type='PORTFOLIO',
            entity_id=1,
            created_by=self.user
        )
        udf_value.set_value(True)
        udf_value.save()

        self.assertEqual(udf_value.get_value(), True)
        self.assertTrue(udf_value.value_boolean)

    def test_dropdown_value_validation(self):
        """Test dropdown value validation."""
        udf_value = UDFValue(
            udf=self.dropdown_udf,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_text='Invalid',  # Not in dropdown_options
            created_by=self.user
        )

        with self.assertRaises(ValidationError):
            udf_value.full_clean()

    def test_number_min_max_validation(self):
        """Test number min/max validation."""
        udf_value = UDFValue(
            udf=self.number_udf,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_number=Decimal('150'),  # Exceeds max of 100
            created_by=self.user
        )

        with self.assertRaises(ValidationError):
            udf_value.full_clean()

    def test_entity_type_mismatch(self):
        """Test entity type validation."""
        udf_value = UDFValue(
            udf=self.text_udf,  # For PORTFOLIO
            entity_type='TRADE',  # Mismatch!
            entity_id=1,
            created_by=self.user
        )

        with self.assertRaises(ValidationError):
            udf_value.full_clean()


class UDFServiceTest(TestCase):
    """Test UDF Service layer."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user('testuser', 'test@test.com', 'pass123')

    def test_create_udf_service(self):
        """Test creating UDF via service."""
        data = {
            'field_name': 'compliance_status',
            'label': 'Compliance Status',
            'field_type': 'DROPDOWN',
            'entity_type': 'PORTFOLIO',
            'dropdown_options': ['Compliant', 'Non-Compliant', 'Under Review'],
            'is_required': True,
        }

        udf = UDFService.create_udf(self.user, data)

        self.assertEqual(udf.field_name, 'compliance_status')
        self.assertTrue(udf.is_required)
        self.assertEqual(len(udf.dropdown_options), 3)

        # Check audit log
        audit = AuditLog.objects.filter(
            action='CREATE',
            object_type='UDF',
            object_id=str(udf.id)
        ).first()
        self.assertIsNotNone(audit)

    def test_create_duplicate_field_name(self):
        """Test creating UDF with duplicate field_name."""
        data = {
            'field_name': 'duplicate_field',
            'label': 'Original',
            'field_type': 'TEXT',
            'entity_type': 'PORTFOLIO',
        }

        UDFService.create_udf(self.user, data)

        # Try to create with same field_name
        with self.assertRaises(ValidationError):
            UDFService.create_udf(self.user, data)

    def test_set_udf_value(self):
        """Test setting UDF value via service."""
        # Create UDF
        data = {
            'field_name': 'manager_notes',
            'label': 'Manager Notes',
            'field_type': 'TEXT',
            'entity_type': 'PORTFOLIO',
        }
        udf = UDFService.create_udf(self.user, data)

        # Set value
        udf_value = UDFService.set_udf_value(
            udf=udf,
            entity_type='PORTFOLIO',
            entity_id=123,
            value='Important notes here',
            user=self.user
        )

        self.assertEqual(udf_value.get_value(), 'Important notes here')

        # Check history was created
        history = UDFHistory.objects.filter(udf_value=udf_value).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.action, 'CREATE')

    def test_update_udf_value(self):
        """Test updating existing UDF value."""
        # Create UDF
        data = {
            'field_name': 'score',
            'label': 'Score',
            'field_type': 'NUMBER',
            'entity_type': 'PORTFOLIO',
        }
        udf = UDFService.create_udf(self.user, data)

        # Set initial value
        udf_value = UDFService.set_udf_value(
            udf=udf,
            entity_type='PORTFOLIO',
            entity_id=123,
            value=Decimal('50'),
            user=self.user
        )

        # Update value
        udf_value = UDFService.set_udf_value(
            udf=udf,
            entity_type='PORTFOLIO',
            entity_id=123,
            value=Decimal('75'),
            user=self.user
        )

        self.assertEqual(udf_value.get_value(), Decimal('75'))

        # Check history has both CREATE and UPDATE
        history_count = UDFHistory.objects.filter(udf_value=udf_value).count()
        self.assertEqual(history_count, 2)

    def test_get_entity_udf_values(self):
        """Test getting all UDF values for an entity."""
        # Create multiple UDFs
        udf1 = UDFService.create_udf(self.user, {
            'field_name': 'field1',
            'label': 'Field 1',
            'field_type': 'TEXT',
            'entity_type': 'PORTFOLIO',
        })

        udf2 = UDFService.create_udf(self.user, {
            'field_name': 'field2',
            'label': 'Field 2',
            'field_type': 'NUMBER',
            'entity_type': 'PORTFOLIO',
        })

        # Set values
        UDFService.set_udf_value(udf1, 'PORTFOLIO', 1, 'Value 1', self.user)
        UDFService.set_udf_value(udf2, 'PORTFOLIO', 1, Decimal('100'), self.user)

        # Get all values
        values = UDFService.get_entity_udf_values('PORTFOLIO', 1)

        self.assertEqual(values['field1'], 'Value 1')
        self.assertEqual(values['field2'], Decimal('100'))

    def test_validate_udf_values(self):
        """Test UDF value validation."""
        # Create required UDF
        UDFService.create_udf(self.user, {
            'field_name': 'required_field',
            'label': 'Required Field',
            'field_type': 'TEXT',
            'entity_type': 'PORTFOLIO',
            'is_required': True,
        })

        # Test validation fails without required field
        with self.assertRaises(ValidationError):
            UDFService.validate_udf_values('PORTFOLIO', {})

        # Test validation passes with required field
        try:
            UDFService.validate_udf_values('PORTFOLIO', {
                'required_field': 'Some value'
            })
        except ValidationError:
            self.fail("Validation should pass with required field")

    def test_list_udfs(self):
        """Test listing UDFs with filters."""
        # Create UDFs for different entities
        UDFService.create_udf(self.user, {
            'field_name': 'portfolio_field',
            'label': 'Portfolio Field',
            'field_type': 'TEXT',
            'entity_type': 'PORTFOLIO',
        })

        UDFService.create_udf(self.user, {
            'field_name': 'trade_field',
            'label': 'Trade Field',
            'field_type': 'TEXT',
            'entity_type': 'TRADE',
        })

        # List all UDFs
        all_udfs = UDFService.list_udfs()
        self.assertEqual(all_udfs.count(), 2)

        # List only PORTFOLIO UDFs
        portfolio_udfs = UDFService.list_udfs(entity_type='PORTFOLIO')
        self.assertEqual(portfolio_udfs.count(), 1)
        self.assertEqual(portfolio_udfs.first().field_name, 'portfolio_field')

    def test_set_entity_udf_values(self):
        """Test setting multiple UDF values at once."""
        # Create UDFs
        UDFService.create_udf(self.user, {
            'field_name': 'field1',
            'label': 'Field 1',
            'field_type': 'TEXT',
            'entity_type': 'PORTFOLIO',
        })

        UDFService.create_udf(self.user, {
            'field_name': 'field2',
            'label': 'Field 2',
            'field_type': 'NUMBER',
            'entity_type': 'PORTFOLIO',
        })

        # Set multiple values
        values = {
            'field1': 'Text value',
            'field2': Decimal('42'),
        }

        result = UDFService.set_entity_udf_values(
            entity_type='PORTFOLIO',
            entity_id=1,
            values=values,
            user=self.user
        )

        self.assertEqual(len(result), 2)

        # Verify values were set
        entity_values = UDFService.get_entity_udf_values('PORTFOLIO', 1)
        self.assertEqual(entity_values['field1'], 'Text value')
        self.assertEqual(entity_values['field2'], Decimal('42'))
