"""Tests for edge_jobs_py36/position_worker.py."""
import argparse
from unittest.mock import MagicMock, patch

import pytest

from position_worker import Command


def _cmd():
    return Command()


class TestAddArguments:
    def test_registers_action_choices(self):
        parser = argparse.ArgumentParser()
        _cmd().add_arguments(parser)
        args = parser.parse_args(['status'])
        assert args.action == 'status'

    def test_rejects_invalid_action(self):
        parser = argparse.ArgumentParser()
        _cmd().add_arguments(parser)
        with pytest.raises(SystemExit):
            parser.parse_args(['bogus-action'])

    def test_defaults(self):
        parser = argparse.ArgumentParser()
        _cmd().add_arguments(parser)
        args = parser.parse_args(['start'])
        assert args.poll_interval == 10
        assert args.batch_size == 100
        assert args.purge_days == 7

    def test_custom_values(self):
        parser = argparse.ArgumentParser()
        _cmd().add_arguments(parser)
        args = parser.parse_args(['start', '--poll-interval', '5', '--batch-size', '50', '--purge-days', '3'])
        assert args.poll_interval == 5
        assert args.batch_size == 50
        assert args.purge_days == 3


class TestHandleDispatch:
    def test_start_dispatches_to_start_worker(self):
        cmd = _cmd()
        with patch.object(cmd, '_start_worker') as mock_fn:
            cmd.handle(action='start', poll_interval=10, batch_size=100)
        mock_fn.assert_called_once()

    def test_status_dispatches_to_show_status(self):
        cmd = _cmd()
        with patch.object(cmd, '_show_status') as mock_fn:
            cmd.handle(action='status')
        mock_fn.assert_called_once()

    def test_process_dispatches_to_process_once(self):
        cmd = _cmd()
        with patch.object(cmd, '_process_once') as mock_fn:
            cmd.handle(action='process', batch_size=100)
        mock_fn.assert_called_once()

    def test_retry_dispatches_to_retry_failed(self):
        cmd = _cmd()
        with patch.object(cmd, '_retry_failed') as mock_fn:
            cmd.handle(action='retry')
        mock_fn.assert_called_once()

    def test_purge_dispatches_to_purge_completed(self):
        cmd = _cmd()
        with patch.object(cmd, '_purge_completed') as mock_fn:
            cmd.handle(action='purge', purge_days=7)
        mock_fn.assert_called_once()


class TestSignalHandler:
    def test_sets_shutdown_requested_flag(self, capsys):
        cmd = _cmd()
        assert cmd._shutdown_requested is False
        cmd._signal_handler(2, None)
        assert cmd._shutdown_requested is True
        assert 'Shutdown signal received' in capsys.readouterr().out


class TestStartWorker:
    def test_processes_one_batch_then_stops(self, capsys):
        cmd = _cmd()
        item = {'queue_id': 1}

        def fake_get_pending(limit):
            return [item]

        def fake_process_item(processed_item):
            cmd._shutdown_requested = True  # stop after this item is processed

        with patch('position_worker.position_queue_service') as mock_svc, \
             patch('position_worker.signal.signal'):
            mock_svc.get_pending_items.side_effect = fake_get_pending
            mock_svc._process_item.side_effect = fake_process_item
            mock_svc.get_queue_statistics.return_value = {'pending': 0, 'completed': 1, 'failed': 0}
            cmd._start_worker({'poll_interval': 10, 'batch_size': 100})

        mock_svc._process_item.assert_called_once_with(item)
        out = capsys.readouterr().out
        assert 'Worker stopped.' in out

    def test_sleeps_and_stops_when_no_pending_items(self):
        cmd = _cmd()
        call_count = {'n': 0}

        def fake_get_pending(limit):
            call_count['n'] += 1
            if call_count['n'] >= 2:
                cmd._shutdown_requested = True
            return []

        with patch('position_worker.position_queue_service') as mock_svc, \
             patch('position_worker.signal.signal'), \
             patch('position_worker.time.sleep') as mock_sleep:
            mock_svc.get_pending_items.side_effect = fake_get_pending
            cmd._start_worker({'poll_interval': 10, 'batch_size': 100})

        mock_sleep.assert_called()

    def test_logs_and_continues_on_exception(self, capsys):
        cmd = _cmd()
        call_count = {'n': 0}

        def fake_get_pending(limit):
            call_count['n'] += 1
            if call_count['n'] == 1:
                raise RuntimeError('kudu down')
            cmd._shutdown_requested = True
            return []

        with patch('position_worker.position_queue_service') as mock_svc, \
             patch('position_worker.signal.signal'), \
             patch('position_worker.time.sleep'):
            mock_svc.get_pending_items.side_effect = fake_get_pending
            cmd._start_worker({'poll_interval': 10, 'batch_size': 100})

        out = capsys.readouterr().out
        assert 'Error: kudu down' in out

    def test_stops_mid_batch_when_shutdown_requested(self):
        cmd = _cmd()
        items = [{'queue_id': 1}, {'queue_id': 2}]

        def fake_get_pending(limit):
            return items

        with patch('position_worker.position_queue_service') as mock_svc, \
             patch('position_worker.signal.signal'):
            mock_svc.get_pending_items.side_effect = fake_get_pending
            mock_svc.get_queue_statistics.return_value = {'pending': 1, 'completed': 0, 'failed': 0}

            def process_side_effect(item):
                cmd._shutdown_requested = True  # shutdown mid-loop after first item

            mock_svc._process_item.side_effect = process_side_effect
            cmd._start_worker({'poll_interval': 10, 'batch_size': 100})

        assert mock_svc._process_item.call_count == 1

    def test_registers_signal_handlers(self):
        cmd = _cmd()
        with patch('position_worker.position_queue_service') as mock_svc, \
             patch('position_worker.signal.signal') as mock_signal:
            mock_svc.get_pending_items.side_effect = lambda limit: (
                setattr(cmd, '_shutdown_requested', True) or []
            )
            cmd._start_worker({'poll_interval': 10, 'batch_size': 100})
        assert mock_signal.call_count == 2

    def test_configures_service_poll_interval_and_batch_size(self):
        cmd = _cmd()
        with patch('position_worker.position_queue_service') as mock_svc, \
             patch('position_worker.signal.signal'):
            mock_svc.get_pending_items.side_effect = lambda limit: (
                setattr(cmd, '_shutdown_requested', True) or []
            )
            cmd._start_worker({'poll_interval': 15, 'batch_size': 50})
        assert mock_svc.POLL_INTERVAL == 15
        assert mock_svc.BATCH_SIZE == 50


class TestShowStatus:
    def test_shows_basic_counts(self, capsys):
        cmd = _cmd()
        with patch('position_worker.position_queue_service') as mock_svc:
            mock_svc.get_queue_statistics.return_value = {
                'total': 10, 'pending': 0, 'processing': 0,
                'completed': 8, 'failed': 0, 'dead_letter': 0,
            }
            cmd._show_status()
        out = capsys.readouterr().out
        assert 'Total Items:       10' in out
        assert 'Completed:         8' in out

    def test_shows_failed_in_error_style_when_nonzero(self, capsys):
        cmd = _cmd()
        with patch('position_worker.position_queue_service') as mock_svc:
            mock_svc.get_queue_statistics.return_value = {
                'total': 10, 'pending': 0, 'processing': 0,
                'completed': 5, 'failed': 3, 'dead_letter': 0,
            }
            cmd._show_status()
        out = capsys.readouterr().out
        assert 'Failed:            3' in out

    def test_shows_dead_letter_when_nonzero(self, capsys):
        cmd = _cmd()
        with patch('position_worker.position_queue_service') as mock_svc:
            mock_svc.get_queue_statistics.return_value = {
                'total': 10, 'pending': 0, 'processing': 0,
                'completed': 5, 'failed': 0, 'dead_letter': 2,
            }
            cmd._show_status()
        out = capsys.readouterr().out
        assert 'Dead Letter:       2' in out

    def test_lists_pending_items_when_present(self, capsys):
        cmd = _cmd()
        with patch('position_worker.position_queue_service') as mock_svc:
            mock_svc.get_queue_statistics.return_value = {
                'total': 1, 'pending': 1, 'processing': 0,
                'completed': 0, 'failed': 0, 'dead_letter': 0,
            }
            mock_svc.get_pending_items.return_value = [{
                'queue_id': 42, 'trade_id': 'T1', 'trade_type': 'BUY',
                'quantity': 100, 'price': 10.5, 'queued_at': '2026-09-17',
            }]
            cmd._show_status()
        out = capsys.readouterr().out
        assert '[42] Trade T1 - BUY 100 @ 10.5' in out

    def test_shows_overflow_message_when_more_than_ten_pending(self, capsys):
        cmd = _cmd()
        with patch('position_worker.position_queue_service') as mock_svc:
            mock_svc.get_queue_statistics.return_value = {
                'total': 15, 'pending': 15, 'processing': 0,
                'completed': 0, 'failed': 0, 'dead_letter': 0,
            }
            mock_svc.get_pending_items.return_value = [{'queue_id': i} for i in range(10)]
            cmd._show_status()
        out = capsys.readouterr().out
        assert '... and 5 more' in out

    def test_does_not_query_pending_items_when_zero_pending(self, capsys):
        cmd = _cmd()
        with patch('position_worker.position_queue_service') as mock_svc:
            mock_svc.get_queue_statistics.return_value = {
                'total': 0, 'pending': 0, 'processing': 0,
                'completed': 0, 'failed': 0, 'dead_letter': 0,
            }
            cmd._show_status()
        mock_svc.get_pending_items.assert_not_called()


class TestProcessOnce:
    def test_no_pending_items_prints_warning(self, capsys):
        cmd = _cmd()
        with patch('position_worker.position_queue_service') as mock_svc:
            mock_svc.get_pending_items.return_value = []
            cmd._process_once({'batch_size': 100})
        out = capsys.readouterr().out
        assert 'No pending items to process' in out

    def test_processes_all_items_successfully(self, capsys):
        cmd = _cmd()
        with patch('position_worker.position_queue_service') as mock_svc:
            mock_svc.get_pending_items.return_value = [{'queue_id': 1}, {'queue_id': 2}]
            cmd._process_once({'batch_size': 100})
        out = capsys.readouterr().out
        assert 'Processed: 2, Failed: 0' in out

    def test_counts_failures_and_continues(self, capsys):
        cmd = _cmd()
        with patch('position_worker.position_queue_service') as mock_svc:
            mock_svc.get_pending_items.return_value = [{'queue_id': 1}, {'queue_id': 2}]
            mock_svc._process_item.side_effect = [RuntimeError('boom'), None]
            cmd._process_once({'batch_size': 100})
        out = capsys.readouterr().out
        assert 'Processed: 1, Failed: 1' in out
        assert 'Error: boom' in out


class TestRetryFailed:
    def test_prints_retried_count(self, capsys):
        cmd = _cmd()
        with patch('position_worker.position_queue_service') as mock_svc:
            mock_svc.retry_failed_items.return_value = {'retried': 3}
            cmd._retry_failed()
        out = capsys.readouterr().out
        assert 'Retried 3 items' in out

    def test_defaults_to_zero_when_key_missing(self, capsys):
        cmd = _cmd()
        with patch('position_worker.position_queue_service') as mock_svc:
            mock_svc.retry_failed_items.return_value = {}
            cmd._retry_failed()
        out = capsys.readouterr().out
        assert 'Retried 0 items' in out


class TestPurgeCompleted:
    def test_prints_purged_count(self, capsys):
        cmd = _cmd()
        with patch('position_worker.position_queue_service') as mock_svc:
            mock_svc.purge_completed.return_value = {'purged': 7}
            cmd._purge_completed({'purge_days': 7})
        out = capsys.readouterr().out
        assert 'Purged 7 items' in out
        mock_svc.purge_completed.assert_called_once_with(days_old=7)

    def test_defaults_to_zero_when_key_missing(self, capsys):
        cmd = _cmd()
        with patch('position_worker.position_queue_service') as mock_svc:
            mock_svc.purge_completed.return_value = {}
            cmd._purge_completed({'purge_days': 7})
        out = capsys.readouterr().out
        assert 'Purged 0 items' in out
