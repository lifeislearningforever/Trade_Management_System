"""
Process Corporate Actions Management Command Tests

Tests for process_corporate_actions management command with 95%+ coverage target.
"""

import pytest
from django.test import TestCase
from django.core.management import call_command
from django.core.management.base import CommandError
from unittest.mock import patch, Mock, MagicMock
from decimal import Decimal
from io import StringIO


class ProcessCorporateActionsCommandTestCase(TestCase):
    """Test cases for process_corporate_actions management command"""

    def setUp(self):
        """Set up test fixtures"""
        self.sample_queue_entry = {
            'queue_id': 1710758400000,
            'ca_id': 1710758300000,
            'ca_number': 'CA-20260318-00001',
            'ca_type': 'DIVIDEND',
            'security_name': 'AAPL',
            'portfolio_name': None,
            'ex_date': '2026-03-15',
            'record_date': '2026-03-16',
            'payment_date': '2026-03-20',
            'price': Decimal('0.25'),
            'currency': 'USD',
            'status': 'PENDING',
            'retry_count': 0,
            'error_message': None,
            'created_by': 'test_user',
        }

    # =========================================================================
    # Basic command execution tests
    # =========================================================================

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_service')
    def test_command_runs_successfully(self, mock_service, mock_repo):
        """Test command runs without errors"""
        mock_repo.get_pending.return_value = []

        out = StringIO()
        call_command('process_corporate_actions', stdout=out)

        output = out.getvalue()
        self.assertIn('Corporate Action Cash Flow Processing', output)
        self.assertIn('Completed', output)

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_service')
    def test_command_no_pending(self, mock_service, mock_repo):
        """Test command with no pending entries"""
        mock_repo.get_pending.return_value = []

        out = StringIO()
        call_command('process_corporate_actions', stdout=out)

        output = out.getvalue()
        self.assertIn('No pending corporate actions found', output)

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_service')
    def test_command_processes_pending(self, mock_service, mock_repo):
        """Test command processes pending entries"""
        mock_repo.get_pending.return_value = [self.sample_queue_entry]
        mock_service.process_ca_cash_flows.return_value = (
            True, 'Created 2 cash flows', 2, Decimal('500.00')
        )

        out = StringIO()
        call_command('process_corporate_actions', stdout=out)

        output = out.getvalue()
        self.assertIn('Found 1 pending', output)
        self.assertIn('Created 2 cash flows', output)

    # =========================================================================
    # Command argument tests
    # =========================================================================

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_service')
    def test_command_with_date_filter(self, mock_service, mock_repo):
        """Test command with --date argument"""
        mock_repo.get_pending.return_value = []

        out = StringIO()
        call_command('process_corporate_actions', '--date', '2026-03-20', stdout=out)

        output = out.getvalue()
        self.assertIn('Payment Date Filter: 2026-03-20', output)

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_service')
    def test_command_dry_run(self, mock_service, mock_repo):
        """Test command with --dry-run argument"""
        mock_repo.get_pending.return_value = [self.sample_queue_entry]
        mock_service.process_ca_cash_flows.return_value = (
            True, 'Would create 2 cash flows', 2, Decimal('500.00')
        )

        out = StringIO()
        call_command('process_corporate_actions', '--dry-run', stdout=out)

        output = out.getvalue()
        self.assertIn('DRY RUN', output)

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_service')
    def test_command_verbose(self, mock_service, mock_repo):
        """Test command with --verbose-output argument"""
        mock_repo.get_pending.return_value = [self.sample_queue_entry]
        mock_service.process_ca_cash_flows.return_value = (
            True, 'Created 2 cash flows', 2, Decimal('500.00')
        )

        out = StringIO()
        call_command('process_corporate_actions', '--verbose-output', stdout=out)

        output = out.getvalue()
        self.assertIn('CA Number', output)  # Verbose shows table headers

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    def test_command_with_batch_size(self, mock_repo):
        """Test command with --batch-size argument"""
        mock_repo.get_pending.return_value = []

        out = StringIO()
        call_command('process_corporate_actions', '--batch-size', '50', stdout=out)

        mock_repo.get_pending.assert_called_once()
        call_kwargs = mock_repo.get_pending.call_args[1]
        self.assertEqual(call_kwargs['limit'], 50)

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    def test_command_with_user(self, mock_repo):
        """Test command with --user argument"""
        mock_repo.get_pending.return_value = []

        out = StringIO()
        call_command('process_corporate_actions', '--user', 'batch_user', stdout=out)

        output = out.getvalue()
        self.assertIn('Run By: batch_user', output)

    # =========================================================================
    # Status command tests
    # =========================================================================

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    def test_command_status_only(self, mock_repo):
        """Test command with --status argument"""
        mock_repo.get_statistics.return_value = {
            'pending': 5,
            'processing': 1,
            'completed': 10,
            'failed': 2,
            'total_cash_flows': 50,
            'total_amount': Decimal('12500.00'),
        }

        out = StringIO()
        call_command('process_corporate_actions', '--status', stdout=out)

        output = out.getvalue()
        self.assertIn('Queue Statistics', output)
        self.assertIn('Pending:    5', output)
        self.assertIn('Completed:  10', output)
        self.assertIn('Failed:     2', output)

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    def test_command_status_empty(self, mock_repo):
        """Test command --status with empty statistics"""
        mock_repo.get_statistics.return_value = {}

        out = StringIO()
        call_command('process_corporate_actions', '--status', stdout=out)

        output = out.getvalue()
        self.assertIn('No statistics available', output)

    # =========================================================================
    # Specific queue/CA ID tests
    # =========================================================================

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_service')
    def test_command_with_queue_id(self, mock_service, mock_repo):
        """Test command with --queue-id argument"""
        mock_repo.get_by_id.return_value = self.sample_queue_entry
        mock_service.process_ca_cash_flows.return_value = (
            True, 'Created 2 cash flows', 2, Decimal('500.00')
        )

        out = StringIO()
        call_command('process_corporate_actions', '--queue-id', '1710758400000', stdout=out)

        output = out.getvalue()
        self.assertIn('Processing Queue Entry: 1710758400000', output)

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    def test_command_with_queue_id_not_found(self, mock_repo):
        """Test command with --queue-id not found"""
        mock_repo.get_by_id.return_value = None

        out = StringIO()
        call_command('process_corporate_actions', '--queue-id', '999999', stdout=out)

        output = out.getvalue()
        self.assertIn('not found', output)

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_service')
    def test_command_with_ca_id(self, mock_service, mock_repo):
        """Test command with --ca-id argument"""
        mock_repo.get_by_ca_id.return_value = [self.sample_queue_entry]
        mock_service.process_ca_cash_flows.return_value = (
            True, 'Created 2 cash flows', 2, Decimal('500.00')
        )

        out = StringIO()
        call_command('process_corporate_actions', '--ca-id', '1710758300000', stdout=out)

        output = out.getvalue()
        self.assertIn('Processing CA ID: 1710758300000', output)

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    def test_command_with_ca_id_not_found(self, mock_repo):
        """Test command with --ca-id not found"""
        mock_repo.get_by_ca_id.return_value = []

        out = StringIO()
        call_command('process_corporate_actions', '--ca-id', '999999', stdout=out)

        output = out.getvalue()
        self.assertIn('No queue entries found', output)

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_service')
    def test_command_ca_id_skips_completed(self, mock_service, mock_repo):
        """Test command with --ca-id skips completed entries"""
        completed_entry = self.sample_queue_entry.copy()
        completed_entry['status'] = 'COMPLETED'
        mock_repo.get_by_ca_id.return_value = [completed_entry]

        out = StringIO()
        call_command('process_corporate_actions', '--ca-id', '1710758300000', stdout=out)

        output = out.getvalue()
        self.assertIn('Already completed', output)
        mock_service.process_ca_cash_flows.assert_not_called()

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_service')
    def test_command_ca_id_skips_processing(self, mock_service, mock_repo):
        """Test command with --ca-id skips processing entries"""
        processing_entry = self.sample_queue_entry.copy()
        processing_entry['status'] = 'PROCESSING'
        mock_repo.get_by_ca_id.return_value = [processing_entry]

        out = StringIO()
        call_command('process_corporate_actions', '--ca-id', '1710758300000', stdout=out)

        output = out.getvalue()
        self.assertIn('Currently processing', output)
        mock_service.process_ca_cash_flows.assert_not_called()

    # =========================================================================
    # Retry failed tests
    # =========================================================================

    @patch('core.repositories.impala_connection.impala_manager')
    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_service')
    def test_command_retry_failed(self, mock_service, mock_repo, mock_impala):
        """Test command with --retry-failed argument"""
        failed_entry = self.sample_queue_entry.copy()
        failed_entry['status'] = 'FAILED'
        failed_entry['retry_count'] = 1

        mock_impala.execute_query.return_value = [failed_entry]
        mock_repo.reset_for_retry.return_value = True
        mock_service.process_ca_cash_flows.return_value = (
            True, 'Created 2 cash flows', 2, Decimal('500.00')
        )

        out = StringIO()
        call_command('process_corporate_actions', '--retry-failed', stdout=out)

        output = out.getvalue()
        self.assertIn('Retrying Failed Entries', output)

    @patch('core.repositories.impala_connection.impala_manager')
    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    def test_command_retry_failed_none(self, mock_repo, mock_impala):
        """Test command --retry-failed with no failed entries"""
        mock_impala.execute_query.return_value = []

        out = StringIO()
        call_command('process_corporate_actions', '--retry-failed', stdout=out)

        output = out.getvalue()
        self.assertIn('No failed entries to retry', output)

    @patch('core.repositories.impala_connection.impala_manager')
    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_service')
    def test_command_retry_failed_still_fails(self, mock_service, mock_repo, mock_impala):
        """Test command --retry-failed when retry fails again"""
        failed_entry = self.sample_queue_entry.copy()
        failed_entry['status'] = 'FAILED'

        mock_impala.execute_query.return_value = [failed_entry]
        mock_repo.reset_for_retry.return_value = True
        mock_service.process_ca_cash_flows.return_value = (
            False, 'Still failing', 0, Decimal('0')
        )

        out = StringIO()
        call_command('process_corporate_actions', '--retry-failed', stdout=out)

        output = out.getvalue()
        self.assertIn('Failed again', output)

    @patch('core.repositories.impala_connection.impala_manager')
    def test_command_retry_failed_exception(self, mock_impala):
        """Test command --retry-failed handles exceptions"""
        mock_impala.execute_query.side_effect = Exception("Database error")

        out = StringIO()
        call_command('process_corporate_actions', '--retry-failed', stdout=out)

        output = out.getvalue()
        self.assertIn('Error retrying', output)

    # =========================================================================
    # Processing result tests
    # =========================================================================

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_service')
    def test_command_processing_failure(self, mock_service, mock_repo):
        """Test command handles processing failure"""
        mock_repo.get_pending.return_value = [self.sample_queue_entry]
        mock_service.process_ca_cash_flows.return_value = (
            False, 'Processing failed', 0, Decimal('0')
        )

        out = StringIO()
        call_command('process_corporate_actions', stdout=out)

        output = out.getvalue()
        self.assertIn('Failed: 1', output)

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_service')
    def test_command_shows_summary(self, mock_service, mock_repo):
        """Test command shows processing summary"""
        mock_repo.get_pending.return_value = [
            self.sample_queue_entry,
            {**self.sample_queue_entry, 'queue_id': 1710758400001}
        ]
        mock_service.process_ca_cash_flows.side_effect = [
            (True, 'Created 2 cash flows', 2, Decimal('500.00')),
            (False, 'Failed', 0, Decimal('0')),
        ]

        out = StringIO()
        call_command('process_corporate_actions', stdout=out)

        output = out.getvalue()
        self.assertIn('Processing Summary', output)
        self.assertIn('Total Processed: 2', output)
        self.assertIn('Successful: 1', output)
        self.assertIn('Failed: 1', output)

    # =========================================================================
    # Verbose output tests
    # =========================================================================

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    def test_command_verbose_shows_entry_details(self, mock_repo):
        """Test command --verbose-output shows entry details"""
        mock_repo.get_by_id.return_value = self.sample_queue_entry

        out = StringIO()
        call_command(
            'process_corporate_actions',
            '--queue-id', '1710758400000',
            '--verbose-output',
            '--dry-run',
            stdout=out
        )

        output = out.getvalue()
        self.assertIn('Entry Details', output)
        self.assertIn('CA Number:', output)
        self.assertIn('Security:', output)

    # =========================================================================
    # Error handling tests
    # =========================================================================

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    def test_command_handles_exception(self, mock_repo):
        """Test command handles exceptions gracefully"""
        mock_repo.get_pending.side_effect = Exception("Database connection failed")

        out = StringIO()
        err = StringIO()

        with self.assertRaises(CommandError):
            call_command('process_corporate_actions', stdout=out, stderr=err)

    # =========================================================================
    # Display helper tests
    # =========================================================================

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_service')
    def test_command_shows_pending_table(self, mock_service, mock_repo):
        """Test command shows pending entries table"""
        mock_repo.get_pending.return_value = [self.sample_queue_entry]
        mock_service.process_ca_cash_flows.return_value = (
            True, 'OK', 1, Decimal('100')
        )

        out = StringIO()
        call_command('process_corporate_actions', '--verbose-output', stdout=out)

        output = out.getvalue()
        self.assertIn('Pending Entries:', output)
        self.assertIn('Queue ID', output)
        self.assertIn('CA Number', output)
        self.assertIn('AAPL', output)

    @patch('reference_data.management.commands.process_corporate_actions.ca_cash_flow_queue_repository')
    def test_command_entry_details_with_error(self, mock_repo):
        """Test command shows error message in entry details"""
        entry_with_error = self.sample_queue_entry.copy()
        entry_with_error['error_message'] = 'Previous error message'
        mock_repo.get_by_id.return_value = entry_with_error

        out = StringIO()
        call_command(
            'process_corporate_actions',
            '--queue-id', '1710758400000',
            '--verbose-output',
            '--dry-run',
            stdout=out
        )

        output = out.getvalue()
        self.assertIn('Last Error:', output)
        self.assertIn('Previous error message', output)
