"""
Django-free stand-in for django.core.management.base.BaseCommand /
CommandError, used by every forked management command in this package.

Reproduces the subset of Django's Command interface these commands actually
use: self.style.{SUCCESS,ERROR,WARNING,HTTP_INFO,MIGRATE_HEADING}(),
self.stdout.write() / self.stderr.write(), add_arguments(parser),
handle(*args, **options). Each forked command's `class Command(BaseCommand):`
body -- add_arguments()/handle() -- is otherwise byte-for-byte identical to
the original; only the import line changes, plus a trailing
`if __name__ == '__main__': run_command(Command)` in place of manage.py's
dispatch machinery.
"""
import argparse
import sys


class CommandError(Exception):
    """Mirrors django.core.management.base.CommandError."""
    pass


def _wrap(code):
    def _style_func(text):
        return '\033[{}m{}\033[0m'.format(code, text) if sys.stdout.isatty() else text
    return _style_func


class _Style:
    SUCCESS = staticmethod(_wrap('32'))            # green
    ERROR = staticmethod(_wrap('31'))              # red
    WARNING = staticmethod(_wrap('33'))            # yellow
    NOTICE = staticmethod(_wrap('33'))             # yellow
    HTTP_INFO = staticmethod(_wrap('36'))          # cyan
    MIGRATE_HEADING = staticmethod(_wrap('36;1'))  # bold cyan
    MIGRATE_LABEL = staticmethod(_wrap('1'))       # bold


class _OutputWrapper:
    def __init__(self, stream):
        self._stream = stream

    def write(self, msg='', style_func=None, ending='\n'):
        text = str(msg)
        if ending and not text.endswith(ending):
            text += ending
        self._stream.write(text)
        self._stream.flush()


class BaseCommand:
    help = ''

    def __init__(self):
        self.stdout = _OutputWrapper(sys.stdout)
        self.stderr = _OutputWrapper(sys.stderr)
        self.style = _Style()

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        raise NotImplementedError('subclasses of BaseCommand must provide a handle() method')


def run_command(command_cls):
    """
    Standalone CLI entrypoint, replacing manage.py's dispatch for a single
    command. Usage at the bottom of each forked script:

        if __name__ == '__main__':
            run_command(Command)
    """
    cmd = command_cls()
    parser = argparse.ArgumentParser(description=cmd.help or command_cls.__doc__ or '')
    cmd.add_arguments(parser)
    args = parser.parse_args()
    options = vars(args)
    try:
        cmd.handle(**options)
    except CommandError as e:
        cmd.stderr.write(cmd.style.ERROR('Error: {}'.format(e)))
        sys.exit(1)
