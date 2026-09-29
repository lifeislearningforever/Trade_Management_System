"""
UDF Models Tests

Comprehensive tests for UDF, UDFValue, and UDFHistory models.
Tests cover:
- Model string representations
- Field validations
- get_value and set_value methods
- Model clean() methods
"""

import pytest
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from unittest.mock import patch, Mock, MagicMock
from decimal import Decimal
from datetime import date, datetime

from udf.models import UDF, UDFValue, UDFHistory


class UDFModelTestCase(TestCase):
    """Test cases for UDF model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_udf_str_representation(self):
        """Test UDF __str__ method"""
        udf = UDF(
            field_name='test_field',
            label='Test Field',
            entity_type='PORTFOLIO',
            field_type='TEXT'
        )

        result = str(udf)

        self.assertEqual(result, 'PORTFOLIO - Test Field')

    def test_udf_field_type_choices(self):
        """Test UDF field type choices"""
        valid_types = [choice[0] for choice in UDF.FIELD_TYPE_CHOICES]

        self.assertIn('TEXT', valid_types)
        self.assertIn('NUMBER', valid_types)
        self.assertIn('DATE', valid_types)
        self.assertIn('BOOLEAN', valid_types)
        self.assertIn('DROPDOWN', valid_types)
        self.assertIn('MULTI_SELECT', valid_types)
        self.assertIn('CURRENCY', valid_types)
        self.assertIn('PERCENTAGE', valid_types)

    def test_udf_entity_type_choices(self):
        """Test UDF entity type choices"""
        valid_entities = [choice[0] for choice in UDF.ENTITY_TYPE_CHOICES]

        self.assertIn('PORTFOLIO', valid_entities)
        self.assertIn('TRADE', valid_entities)
        self.assertIn('POSITION', valid_entities)
        self.assertIn('COUNTERPARTY', valid_entities)

    def test_udf_clean_dropdown_without_options(self):
        """Test UDF clean fails for DROPDOWN without options"""
        udf = UDF(
            field_name='dropdown_field',
            label='Dropdown',
            entity_type='PORTFOLIO',
            field_type='DROPDOWN',
            dropdown_options=None
        )

        with self.assertRaises(ValidationError) as context:
            udf.clean()

        self.assertIn('Dropdown options', str(context.exception))

    def test_udf_clean_dropdown_with_empty_list(self):
        """Test UDF clean fails for DROPDOWN with empty list"""
        udf = UDF(
            field_name='dropdown_field',
            label='Dropdown',
            entity_type='PORTFOLIO',
            field_type='DROPDOWN',
            dropdown_options=[]
        )

        with self.assertRaises(ValidationError) as context:
            udf.clean()

        self.assertIn('Dropdown options', str(context.exception))

    def test_udf_clean_dropdown_with_non_list(self):
        """Test UDF clean fails for DROPDOWN with non-list options"""
        udf = UDF(
            field_name='dropdown_field',
            label='Dropdown',
            entity_type='PORTFOLIO',
            field_type='DROPDOWN',
            dropdown_options="not a list"
        )

        with self.assertRaises(ValidationError) as context:
            udf.clean()

        self.assertIn('Dropdown options', str(context.exception))

    def test_udf_clean_dropdown_with_valid_options(self):
        """Test UDF clean passes for DROPDOWN with valid options"""
        udf = UDF(
            field_name='dropdown_field',
            label='Dropdown',
            entity_type='PORTFOLIO',
            field_type='DROPDOWN',
            dropdown_options=['Option1', 'Option2', 'Option3']
        )

        # Should not raise
        udf.clean()

    def test_udf_clean_multiselect_without_options(self):
        """Test UDF clean fails for MULTI_SELECT without options"""
        udf = UDF(
            field_name='multiselect_field',
            label='Multi Select',
            entity_type='PORTFOLIO',
            field_type='MULTI_SELECT',
            dropdown_options=None
        )

        with self.assertRaises(ValidationError):
            udf.clean()

    def test_udf_clean_number_min_greater_than_max(self):
        """Test UDF clean fails when min > max for NUMBER"""
        udf = UDF(
            field_name='number_field',
            label='Number',
            entity_type='PORTFOLIO',
            field_type='NUMBER',
            min_value=Decimal('100'),
            max_value=Decimal('50')
        )

        with self.assertRaises(ValidationError) as context:
            udf.clean()

        self.assertIn('Minimum value cannot be greater than maximum value', str(context.exception))

    def test_udf_clean_currency_min_greater_than_max(self):
        """Test UDF clean fails when min > max for CURRENCY"""
        udf = UDF(
            field_name='currency_field',
            label='Currency',
            entity_type='PORTFOLIO',
            field_type='CURRENCY',
            min_value=Decimal('1000'),
            max_value=Decimal('100')
        )

        with self.assertRaises(ValidationError):
            udf.clean()

    def test_udf_clean_percentage_min_greater_than_max(self):
        """Test UDF clean fails when min > max for PERCENTAGE"""
        udf = UDF(
            field_name='percentage_field',
            label='Percentage',
            entity_type='PORTFOLIO',
            field_type='PERCENTAGE',
            min_value=Decimal('100'),
            max_value=Decimal('0')
        )

        with self.assertRaises(ValidationError):
            udf.clean()

    def test_udf_clean_number_valid_min_max(self):
        """Test UDF clean passes for NUMBER with valid min/max"""
        udf = UDF(
            field_name='number_field',
            label='Number',
            entity_type='PORTFOLIO',
            field_type='NUMBER',
            min_value=Decimal('0'),
            max_value=Decimal('100')
        )

        # Should not raise
        udf.clean()

    def test_udf_clean_text_type(self):
        """Test UDF clean passes for TEXT type"""
        udf = UDF(
            field_name='text_field',
            label='Text',
            entity_type='PORTFOLIO',
            field_type='TEXT'
        )

        # Should not raise
        udf.clean()


class UDFValueModelTestCase(TestCase):
    """Test cases for UDFValue model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.udf_text = UDF.objects.create(
            field_name='text_field',
            label='Text Field',
            entity_type='PORTFOLIO',
            field_type='TEXT',
            created_by=self.user,
            updated_by=self.user
        )
        self.udf_number = UDF.objects.create(
            field_name='number_field',
            label='Number Field',
            entity_type='PORTFOLIO',
            field_type='NUMBER',
            created_by=self.user,
            updated_by=self.user
        )
        self.udf_date = UDF.objects.create(
            field_name='date_field',
            label='Date Field',
            entity_type='PORTFOLIO',
            field_type='DATE',
            created_by=self.user,
            updated_by=self.user
        )
        self.udf_datetime = UDF.objects.create(
            field_name='datetime_field',
            label='DateTime Field',
            entity_type='PORTFOLIO',
            field_type='DATETIME',
            created_by=self.user,
            updated_by=self.user
        )
        self.udf_boolean = UDF.objects.create(
            field_name='boolean_field',
            label='Boolean Field',
            entity_type='PORTFOLIO',
            field_type='BOOLEAN',
            created_by=self.user,
            updated_by=self.user
        )
        self.udf_dropdown = UDF.objects.create(
            field_name='dropdown_field',
            label='Dropdown Field',
            entity_type='PORTFOLIO',
            field_type='DROPDOWN',
            dropdown_options=['Option1', 'Option2', 'Option3'],
            created_by=self.user,
            updated_by=self.user
        )
        self.udf_multiselect = UDF.objects.create(
            field_name='multiselect_field',
            label='MultiSelect Field',
            entity_type='PORTFOLIO',
            field_type='MULTI_SELECT',
            dropdown_options=['A', 'B', 'C'],
            created_by=self.user,
            updated_by=self.user
        )
        self.udf_currency = UDF.objects.create(
            field_name='currency_field',
            label='Currency Field',
            entity_type='PORTFOLIO',
            field_type='CURRENCY',
            created_by=self.user,
            updated_by=self.user
        )
        self.udf_percentage = UDF.objects.create(
            field_name='percentage_field',
            label='Percentage Field',
            entity_type='PORTFOLIO',
            field_type='PERCENTAGE',
            created_by=self.user,
            updated_by=self.user
        )

    def test_udf_value_str_representation(self):
        """Test UDFValue __str__ method"""
        udf_value = UDFValue(
            udf=self.udf_text,
            entity_type='PORTFOLIO',
            entity_id=1
        )

        result = str(udf_value)

        self.assertEqual(result, 'text_field for PORTFOLIO#1')

    def test_get_value_text(self):
        """Test get_value for TEXT type"""
        udf_value = UDFValue(
            udf=self.udf_text,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_text='Test Value'
        )

        result = udf_value.get_value()

        self.assertEqual(result, 'Test Value')

    def test_get_value_number(self):
        """Test get_value for NUMBER type"""
        udf_value = UDFValue(
            udf=self.udf_number,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_number=Decimal('123.45')
        )

        result = udf_value.get_value()

        self.assertEqual(result, Decimal('123.45'))

    def test_get_value_currency(self):
        """Test get_value for CURRENCY type"""
        udf_value = UDFValue(
            udf=self.udf_currency,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_number=Decimal('1000.00')
        )

        result = udf_value.get_value()

        self.assertEqual(result, Decimal('1000.00'))

    def test_get_value_percentage(self):
        """Test get_value for PERCENTAGE type"""
        udf_value = UDFValue(
            udf=self.udf_percentage,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_number=Decimal('75.5')
        )

        result = udf_value.get_value()

        self.assertEqual(result, Decimal('75.5'))

    def test_get_value_date(self):
        """Test get_value for DATE type"""
        test_date = date(2024, 1, 15)
        udf_value = UDFValue(
            udf=self.udf_date,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_date=test_date
        )

        result = udf_value.get_value()

        self.assertEqual(result, test_date)

    def test_get_value_datetime(self):
        """Test get_value for DATETIME type"""
        test_datetime = datetime(2024, 1, 15, 10, 30, 0)
        udf_value = UDFValue(
            udf=self.udf_datetime,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_datetime=test_datetime
        )

        result = udf_value.get_value()

        self.assertEqual(result, test_datetime)

    def test_get_value_boolean(self):
        """Test get_value for BOOLEAN type"""
        udf_value = UDFValue(
            udf=self.udf_boolean,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_boolean=True
        )

        result = udf_value.get_value()

        self.assertTrue(result)

    def test_get_value_dropdown_with_json(self):
        """Test get_value for DROPDOWN type with JSON value"""
        udf_value = UDFValue(
            udf=self.udf_dropdown,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_json={'key': 'value'}
        )

        result = udf_value.get_value()

        self.assertEqual(result, {'key': 'value'})

    def test_get_value_dropdown_with_text(self):
        """Test get_value for DROPDOWN type with text value"""
        udf_value = UDFValue(
            udf=self.udf_dropdown,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_text='Option1',
            value_json=None
        )

        result = udf_value.get_value()

        self.assertEqual(result, 'Option1')

    def test_get_value_multiselect(self):
        """Test get_value for MULTI_SELECT type"""
        udf_value = UDFValue(
            udf=self.udf_multiselect,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_json=['A', 'B']
        )

        result = udf_value.get_value()

        self.assertEqual(result, ['A', 'B'])

    def test_set_value_text(self):
        """Test set_value for TEXT type"""
        udf_value = UDFValue(
            udf=self.udf_text,
            entity_type='PORTFOLIO',
            entity_id=1
        )

        udf_value.set_value('New Text Value')

        self.assertEqual(udf_value.value_text, 'New Text Value')

    def test_set_value_text_none(self):
        """Test set_value for TEXT type with None"""
        udf_value = UDFValue(
            udf=self.udf_text,
            entity_type='PORTFOLIO',
            entity_id=1
        )

        udf_value.set_value(None)

        self.assertIsNone(udf_value.value_text)

    def test_set_value_number(self):
        """Test set_value for NUMBER type"""
        udf_value = UDFValue(
            udf=self.udf_number,
            entity_type='PORTFOLIO',
            entity_id=1
        )

        udf_value.set_value(Decimal('99.99'))

        self.assertEqual(udf_value.value_number, Decimal('99.99'))

    def test_set_value_date(self):
        """Test set_value for DATE type"""
        test_date = date(2024, 6, 15)
        udf_value = UDFValue(
            udf=self.udf_date,
            entity_type='PORTFOLIO',
            entity_id=1
        )

        udf_value.set_value(test_date)

        self.assertEqual(udf_value.value_date, test_date)

    def test_set_value_datetime(self):
        """Test set_value for DATETIME type"""
        test_datetime = datetime(2024, 6, 15, 14, 30, 0)
        udf_value = UDFValue(
            udf=self.udf_datetime,
            entity_type='PORTFOLIO',
            entity_id=1
        )

        udf_value.set_value(test_datetime)

        self.assertEqual(udf_value.value_datetime, test_datetime)

    def test_set_value_boolean_true(self):
        """Test set_value for BOOLEAN type with True"""
        udf_value = UDFValue(
            udf=self.udf_boolean,
            entity_type='PORTFOLIO',
            entity_id=1
        )

        udf_value.set_value(True)

        self.assertTrue(udf_value.value_boolean)

    def test_set_value_boolean_false(self):
        """Test set_value for BOOLEAN type with False"""
        udf_value = UDFValue(
            udf=self.udf_boolean,
            entity_type='PORTFOLIO',
            entity_id=1
        )

        udf_value.set_value(False)

        self.assertFalse(udf_value.value_boolean)

    def test_set_value_dropdown_list(self):
        """Test set_value for DROPDOWN type with list"""
        udf_value = UDFValue(
            udf=self.udf_dropdown,
            entity_type='PORTFOLIO',
            entity_id=1
        )

        udf_value.set_value(['Option1', 'Option2'])

        self.assertEqual(udf_value.value_json, ['Option1', 'Option2'])

    def test_set_value_dropdown_dict(self):
        """Test set_value for DROPDOWN type with dict"""
        udf_value = UDFValue(
            udf=self.udf_dropdown,
            entity_type='PORTFOLIO',
            entity_id=1
        )

        udf_value.set_value({'selected': 'Option1'})

        self.assertEqual(udf_value.value_json, {'selected': 'Option1'})

    def test_set_value_dropdown_string(self):
        """Test set_value for DROPDOWN type with string"""
        udf_value = UDFValue(
            udf=self.udf_dropdown,
            entity_type='PORTFOLIO',
            entity_id=1
        )

        udf_value.set_value('Option1')

        self.assertEqual(udf_value.value_text, 'Option1')

    def test_clean_entity_type_mismatch(self):
        """Test clean fails on entity type mismatch"""
        udf_value = UDFValue(
            udf=self.udf_text,
            entity_type='TRADE',  # UDF is for PORTFOLIO
            entity_id=1
        )

        with self.assertRaises(ValidationError) as context:
            udf_value.clean()

        self.assertIn('Entity type mismatch', str(context.exception))

    def test_clean_required_field_empty(self):
        """Test clean fails when required field is empty"""
        self.udf_text.is_required = True
        self.udf_text.save()

        udf_value = UDFValue(
            udf=self.udf_text,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_text=None
        )

        with self.assertRaises(ValidationError) as context:
            udf_value.clean()

        self.assertIn('is required', str(context.exception))

    def test_clean_required_field_empty_string(self):
        """Test clean fails when required field is empty string"""
        self.udf_text.is_required = True
        self.udf_text.save()

        udf_value = UDFValue(
            udf=self.udf_text,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_text=''
        )

        with self.assertRaises(ValidationError) as context:
            udf_value.clean()

        self.assertIn('is required', str(context.exception))

    def test_clean_dropdown_invalid_option(self):
        """Test clean fails for invalid dropdown option"""
        udf_value = UDFValue(
            udf=self.udf_dropdown,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_text='InvalidOption'
        )

        with self.assertRaises(ValidationError) as context:
            udf_value.clean()

        self.assertIn('Invalid option', str(context.exception))

    def test_clean_dropdown_valid_option(self):
        """Test clean passes for valid dropdown option"""
        udf_value = UDFValue(
            udf=self.udf_dropdown,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_text='Option1'
        )

        # Should not raise
        udf_value.clean()

    def test_clean_number_below_min(self):
        """Test clean fails when number below minimum"""
        self.udf_number.min_value = Decimal('10')
        self.udf_number.save()

        udf_value = UDFValue(
            udf=self.udf_number,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_number=Decimal('5')
        )

        with self.assertRaises(ValidationError) as context:
            udf_value.clean()

        self.assertIn('at least', str(context.exception))

    def test_clean_number_above_max(self):
        """Test clean fails when number above maximum"""
        self.udf_number.max_value = Decimal('100')
        self.udf_number.save()

        udf_value = UDFValue(
            udf=self.udf_number,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_number=Decimal('150')
        )

        with self.assertRaises(ValidationError) as context:
            udf_value.clean()

        self.assertIn('at most', str(context.exception))

    def test_clean_number_within_range(self):
        """Test clean passes for number within range"""
        self.udf_number.min_value = Decimal('0')
        self.udf_number.max_value = Decimal('100')
        self.udf_number.save()

        udf_value = UDFValue(
            udf=self.udf_number,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_number=Decimal('50')
        )

        # Should not raise
        udf_value.clean()


class UDFHistoryModelTestCase(TestCase):
    """Test cases for UDFHistory model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.udf = UDF.objects.create(
            field_name='test_field',
            label='Test Field',
            entity_type='PORTFOLIO',
            field_type='TEXT',
            created_by=self.user,
            updated_by=self.user
        )
        self.udf_value = UDFValue.objects.create(
            udf=self.udf,
            entity_type='PORTFOLIO',
            entity_id=1,
            value_text='Test Value',
            created_by=self.user,
            updated_by=self.user
        )

    def test_udf_history_str_representation(self):
        """Test UDFHistory __str__ method"""
        history = UDFHistory(
            udf_value=self.udf_value,
            action='UPDATE',
            old_value='Old',
            new_value='New',
            changed_by=self.user
        )
        history.save()

        result = str(history)

        self.assertIn('UPDATE', result)
        self.assertIn('test_field for PORTFOLIO#1', result)

    def test_udf_history_action_choices(self):
        """Test UDFHistory action choices"""
        # Valid actions
        valid_actions = ['CREATE', 'UPDATE', 'DELETE']

        for action in valid_actions:
            history = UDFHistory(
                udf_value=self.udf_value,
                action=action,
                changed_by=self.user
            )
            history.save()
            self.assertEqual(history.action, action)
