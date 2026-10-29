"""Tests for edge_jobs_py36/run_via_spark.py.

pyspark is not installed in this environment (and isn't needed to run
these Impala-only jobs directly) -- run_via_spark.py imports it lazily
inside main(), so tests inject a fake pyspark.sql module into sys.modules
before calling main(), exactly like they would on a cluster node where
pyspark IS installed but we don't want a real SparkSession/YARN app here.
"""
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

import run_via_spark


@pytest.fixture
def fake_pyspark(monkeypatch):
    """Install a fake pyspark.sql.SparkSession into sys.modules for the
    duration of a test, then remove it (never leak into other tests)."""
    fake_session = MagicMock()
    fake_builder = MagicMock()
    fake_builder.appName.return_value.getOrCreate.return_value = fake_session

    fake_sql_module = types.ModuleType('pyspark.sql')
    fake_sql_module.SparkSession = MagicMock()
    fake_sql_module.SparkSession.builder = fake_builder

    fake_pyspark_module = types.ModuleType('pyspark')
    fake_pyspark_module.sql = fake_sql_module

    monkeypatch.setitem(sys.modules, 'pyspark', fake_pyspark_module)
    monkeypatch.setitem(sys.modules, 'pyspark.sql', fake_sql_module)
    return fake_session, fake_builder


class TestUsageError:
    def test_exits_with_usage_message_when_no_target_given(self, capsys):
        with patch.object(sys, 'argv', ['run_via_spark.py']), \
             pytest.raises(SystemExit) as exc_info:
            run_via_spark.main()
        assert exc_info.value.code == 1
        assert 'Usage:' in capsys.readouterr().err

    def test_exits_with_usage_when_only_prog_name_present(self, capsys):
        with patch.object(sys, 'argv', ['run_via_spark.py']):
            with pytest.raises(SystemExit):
                run_via_spark.main()


class TestSparkSessionLifecycle:
    def test_creates_spark_session_with_app_name_containing_target(self, fake_pyspark, tmp_path):
        fake_session, fake_builder = fake_pyspark
        target = tmp_path / 'noop_job.py'
        target.write_text("if __name__ == '__main__':\n    pass\n")

        with patch.object(sys, 'argv', ['run_via_spark.py', str(target)]):
            run_via_spark.main()

        fake_builder.appName.assert_called_once()
        app_name_arg = fake_builder.appName.call_args[0][0]
        assert str(target) in app_name_arg or 'cis_edge_job' in app_name_arg

    def test_stops_spark_session_after_successful_run(self, fake_pyspark, tmp_path):
        fake_session, _ = fake_pyspark
        target = tmp_path / 'noop_job.py'
        target.write_text("if __name__ == '__main__':\n    pass\n")

        with patch.object(sys, 'argv', ['run_via_spark.py', str(target)]):
            run_via_spark.main()

        fake_session.stop.assert_called_once()

    def test_stops_spark_session_even_when_target_raises(self, fake_pyspark, tmp_path):
        fake_session, _ = fake_pyspark
        target = tmp_path / 'raiser.py'
        target.write_text(
            "if __name__ == '__main__':\n"
            "    raise RuntimeError('job failed')\n"
        )

        with patch.object(sys, 'argv', ['run_via_spark.py', str(target)]), \
             pytest.raises(RuntimeError, match='job failed'):
            run_via_spark.main()

        fake_session.stop.assert_called_once()


class TestArgvRewriting:
    def test_target_script_can_assert_its_own_argv(self, fake_pyspark, tmp_path):
        target = tmp_path / 'assert_argv.py'
        target.write_text(
            "import sys\n"
            "if __name__ == '__main__':\n"
            "    assert sys.argv[1:] == ['--run-type', 'EOD'], sys.argv\n"
        )

        with patch.object(sys, 'argv', ['run_via_spark.py', str(target), '--run-type', 'EOD']):
            run_via_spark.main()  # would raise AssertionError inside runpy if wrong


class TestSystemExitHandling:
    def test_target_sys_exit_zero_is_swallowed(self, fake_pyspark, tmp_path):
        target = tmp_path / 'exits_zero.py'
        target.write_text(
            "import sys\n"
            "if __name__ == '__main__':\n"
            "    sys.exit(0)\n"
        )
        with patch.object(sys, 'argv', ['run_via_spark.py', str(target)]):
            run_via_spark.main()  # must not raise/propagate

    def test_target_sys_exit_none_is_swallowed(self, fake_pyspark, tmp_path):
        target = tmp_path / 'exits_none.py'
        target.write_text(
            "import sys\n"
            "if __name__ == '__main__':\n"
            "    sys.exit()\n"
        )
        with patch.object(sys, 'argv', ['run_via_spark.py', str(target)]):
            run_via_spark.main()  # must not raise/propagate

    def test_target_sys_exit_nonzero_propagates(self, fake_pyspark, tmp_path):
        target = tmp_path / 'exits_nonzero.py'
        target.write_text(
            "import sys\n"
            "if __name__ == '__main__':\n"
            "    sys.exit(2)\n"
        )
        with patch.object(sys, 'argv', ['run_via_spark.py', str(target)]), \
             pytest.raises(SystemExit) as exc_info:
            run_via_spark.main()
        assert exc_info.value.code == 2

    def test_spark_stops_even_when_nonzero_exit_propagates(self, fake_pyspark, tmp_path):
        fake_session, _ = fake_pyspark
        target = tmp_path / 'exits_nonzero.py'
        target.write_text(
            "import sys\n"
            "if __name__ == '__main__':\n"
            "    sys.exit(2)\n"
        )
        with patch.object(sys, 'argv', ['run_via_spark.py', str(target)]), \
             pytest.raises(SystemExit):
            run_via_spark.main()
        fake_session.stop.assert_called_once()
