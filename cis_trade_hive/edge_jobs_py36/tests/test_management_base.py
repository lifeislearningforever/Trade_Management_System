"""Tests for edge_jobs_py36/lib/management_base.py."""
import io
import sys
from unittest.mock import patch

import pytest

from edge_jobs_py36.lib.management_base import (
    BaseCommand,
    CommandError,
    _OutputWrapper,
    _Style,
    run_command,
)


class TestCommandError:
    def test_is_an_exception(self):
        assert issubclass(CommandError, Exception)

    def test_can_be_raised_and_caught_with_message(self):
        with pytest.raises(CommandError, match='bad input'):
            raise CommandError('bad input')


class TestStyleNonTty:
    """sys.stdout.isatty() is False under pytest, so style functions return
    the text unmodified -- this exercises that branch explicitly."""

    def test_success_returns_plain_text_when_not_a_tty(self):
        with patch('sys.stdout.isatty', return_value=False):
            assert _Style.SUCCESS('ok') == 'ok'

    def test_error_returns_plain_text_when_not_a_tty(self):
        with patch('sys.stdout.isatty', return_value=False):
            assert _Style.ERROR('bad') == 'bad'

    def test_warning_returns_plain_text_when_not_a_tty(self):
        with patch('sys.stdout.isatty', return_value=False):
            assert _Style.WARNING('careful') == 'careful'

    def test_notice_returns_plain_text_when_not_a_tty(self):
        with patch('sys.stdout.isatty', return_value=False):
            assert _Style.NOTICE('fyi') == 'fyi'

    def test_http_info_returns_plain_text_when_not_a_tty(self):
        with patch('sys.stdout.isatty', return_value=False):
            assert _Style.HTTP_INFO('info') == 'info'

    def test_migrate_heading_returns_plain_text_when_not_a_tty(self):
        with patch('sys.stdout.isatty', return_value=False):
            assert _Style.MIGRATE_HEADING('heading') == 'heading'

    def test_migrate_label_returns_plain_text_when_not_a_tty(self):
        with patch('sys.stdout.isatty', return_value=False):
            assert _Style.MIGRATE_LABEL('label') == 'label'


class TestStyleTty:
    def test_success_wraps_in_ansi_codes_when_tty(self):
        with patch('sys.stdout.isatty', return_value=True):
            result = _Style.SUCCESS('ok')
        assert result == '\033[32mok\033[0m'

    def test_error_wraps_in_ansi_codes_when_tty(self):
        with patch('sys.stdout.isatty', return_value=True):
            result = _Style.ERROR('bad')
        assert result == '\033[31mbad\033[0m'


class TestOutputWrapper:
    def test_write_appends_newline_by_default(self):
        stream = io.StringIO()
        wrapper = _OutputWrapper(stream)
        wrapper.write('hello')
        assert stream.getvalue() == 'hello\n'

    def test_write_does_not_double_newline(self):
        stream = io.StringIO()
        wrapper = _OutputWrapper(stream)
        wrapper.write('hello\n')
        assert stream.getvalue() == 'hello\n'

    def test_write_with_custom_ending(self):
        stream = io.StringIO()
        wrapper = _OutputWrapper(stream)
        wrapper.write('hello', ending='!')
        assert stream.getvalue() == 'hello!'

    def test_write_with_empty_ending_appends_nothing(self):
        stream = io.StringIO()
        wrapper = _OutputWrapper(stream)
        wrapper.write('hello', ending='')
        assert stream.getvalue() == 'hello'

    def test_write_default_message_is_empty_string(self):
        stream = io.StringIO()
        wrapper = _OutputWrapper(stream)
        wrapper.write()
        assert stream.getvalue() == '\n'

    def test_write_converts_non_string_message(self):
        stream = io.StringIO()
        wrapper = _OutputWrapper(stream)
        wrapper.write(42)
        assert stream.getvalue() == '42\n'

    def test_write_ignores_style_func_argument(self):
        stream = io.StringIO()
        wrapper = _OutputWrapper(stream)
        wrapper.write('hello', style_func=lambda s: 'STYLED:' + s)
        assert stream.getvalue() == 'hello\n'

    def test_write_flushes_stream(self):
        stream = io.StringIO()
        stream.flush = lambda: setattr(stream, '_flushed', True)
        wrapper = _OutputWrapper(stream)
        wrapper.write('x')
        assert getattr(stream, '_flushed', False) is True


class TestBaseCommand:
    def test_init_sets_up_stdout_stderr_style(self):
        cmd = BaseCommand()
        assert isinstance(cmd.stdout, _OutputWrapper)
        assert isinstance(cmd.stderr, _OutputWrapper)
        assert isinstance(cmd.style, _Style)

    def test_help_default_is_empty_string(self):
        assert BaseCommand.help == ''

    def test_add_arguments_default_does_nothing(self):
        cmd = BaseCommand()
        cmd.add_arguments(None)  # must not raise

    def test_handle_raises_not_implemented(self):
        cmd = BaseCommand()
        with pytest.raises(NotImplementedError):
            cmd.handle()

    def test_subclass_can_override_handle(self):
        class MyCommand(BaseCommand):
            def handle(self, *args, **options):
                return 'handled'
        cmd = MyCommand()
        assert cmd.handle() == 'handled'


class TestRunCommand:
    def test_run_command_invokes_handle_with_parsed_options(self):
        captured = {}

        class MyCommand(BaseCommand):
            help = 'does a thing'

            def add_arguments(self, parser):
                parser.add_argument('--name', default='world')

            def handle(self, *args, **options):
                captured.update(options)

        with patch.object(sys, 'argv', ['prog', '--name', 'jdoe']):
            run_command(MyCommand)

        assert captured == {'name': 'jdoe'}

    def test_run_command_uses_default_argument_when_not_provided(self):
        captured = {}

        class MyCommand(BaseCommand):
            def add_arguments(self, parser):
                parser.add_argument('--name', default='world')

            def handle(self, *args, **options):
                captured.update(options)

        with patch.object(sys, 'argv', ['prog']):
            run_command(MyCommand)

        assert captured == {'name': 'world'}

    def test_run_command_prints_error_and_exits_on_command_error(self):
        class MyCommand(BaseCommand):
            def handle(self, *args, **options):
                raise CommandError('something broke')

        with patch.object(sys, 'argv', ['prog']), \
             pytest.raises(SystemExit) as exc_info:
            run_command(MyCommand)

        assert exc_info.value.code == 1

    def test_run_command_error_message_written_to_stderr(self):
        class MyCommand(BaseCommand):
            def handle(self, *args, **options):
                raise CommandError('boom')

        with patch.object(sys, 'argv', ['prog']), \
             patch('sys.stderr', new_callable=io.StringIO) as fake_stderr:
            with pytest.raises(SystemExit):
                run_command(MyCommand)

        assert 'boom' in fake_stderr.getvalue()

    def test_run_command_uses_help_text_in_argparse_description(self):
        class MyCommand(BaseCommand):
            help = 'my help text'

            def handle(self, *args, **options):
                pass

        with patch.object(sys, 'argv', ['prog']), \
             patch('argparse.ArgumentParser') as mock_parser_cls:
            mock_parser = mock_parser_cls.return_value
            mock_parser.parse_args.return_value = argparse_namespace_stub()
            run_command(MyCommand)

        _, kwargs = mock_parser_cls.call_args
        assert kwargs.get('description') == 'my help text'


def argparse_namespace_stub():
    import argparse
    return argparse.Namespace()
