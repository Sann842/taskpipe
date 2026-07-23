"""Tests for shell and python executors."""
import logging

from taskpipe.models import (
    TaskConfig, TaskType, FailureStrategy, TaskStatus
)
from taskpipe.executors import execute_shell, execute_python

logger = logging.getLogger("test")
logging.basicConfig(level=logging.DEBUG)


def make_shell_task(name="t", command="echo hello", timeout=None, on_failure=FailureStrategy.STOP):
    return TaskConfig(
        name=name,
        type=TaskType.SHELL,
        command=command,
        timeout=timeout,
        on_failure=on_failure,
    )


def make_python_task(name="t", script=None, function=None, args=None, kwargs=None, timeout=None):
    return TaskConfig(
        name=name,
        type=TaskType.PYTHON,
        script=script,
        function=function,
        args=args or [],
        kwargs=kwargs or {},
        timeout=timeout,
    )


class TestShellExecutor:
    def test_success(self):
        task = make_shell_task(command="echo hello")
        result = execute_shell(task, attempt=1, logger=logger)
        assert result.status == TaskStatus.SUCCESS
        assert result.return_code == 0
        assert "hello" in result.stdout

    def test_failure(self):
        task = make_shell_task(command="exit 1")
        result = execute_shell(task, attempt=1, logger=logger)
        assert result.status == TaskStatus.FAILED
        assert result.return_code == 1

    def test_timeout(self):
        task = make_shell_task(command="sleep 10", timeout=0.3)
        result = execute_shell(task, attempt=1, logger=logger)
        assert result.status == TaskStatus.FAILED
        assert "timed out" in result.error.lower()

    def test_env_variable(self):
        task = make_shell_task(command="echo $MY_VAR")
        task.env = {"MY_VAR": "taskpipe_test_value"}
        result = execute_shell(task, attempt=1, logger=logger)
        assert result.status == TaskStatus.SUCCESS
        assert "taskpipe_test_value" in result.stdout

    def test_duration_tracked(self):
        task = make_shell_task(command="sleep 0.1")
        result = execute_shell(task, attempt=1, logger=logger)
        assert result.duration >= 0.1

    def test_multiline_stdout(self):
        task = make_shell_task(command="echo line1 && echo line2 && echo line3")
        result = execute_shell(task, attempt=1, logger=logger)
        assert result.status == TaskStatus.SUCCESS
        assert "line1" in result.stdout
        assert "line3" in result.stdout

    def test_stderr_captured(self):
        task = make_shell_task(command="echo err >&2")
        result = execute_shell(task, attempt=1, logger=logger)
        assert "err" in result.stderr


class TestPythonExecutor:
    def test_script_success(self, tmp_path):
        script = tmp_path / "hello.py"
        script.write_text("print('from script')\n")
        task = make_python_task(script=str(script))
        result = execute_python(task, attempt=1, logger=logger)
        assert result.status == TaskStatus.SUCCESS
        assert "from script" in result.stdout

    def test_script_failure(self, tmp_path):
        script = tmp_path / "fail.py"
        script.write_text("import sys; sys.exit(42)\n")
        task = make_python_task(script=str(script))
        result = execute_python(task, attempt=1, logger=logger)
        assert result.status == TaskStatus.FAILED
        assert result.return_code == 42

    def test_script_timeout(self, tmp_path):
        script = tmp_path / "slow.py"
        script.write_text("import time; time.sleep(10)\n")
        task = make_python_task(script=str(script), timeout=0.3)
        result = execute_python(task, attempt=1, logger=logger)
        assert result.status == TaskStatus.FAILED
        assert "timed out" in result.error.lower()

    def test_function_success(self):
        task = make_python_task(function="math:sqrt", args=[16])
        result = execute_python(task, attempt=1, logger=logger)
        assert result.status == TaskStatus.SUCCESS

    def test_function_raises(self):
        task = make_python_task(function="builtins:int", args=["not_a_number"])
        result = execute_python(task, attempt=1, logger=logger)
        assert result.status == TaskStatus.FAILED
        assert result.error is not None

    def test_function_prints_captured(self):
        task = make_python_task(function="builtins:print", args=["captured_output"])
        result = execute_python(task, attempt=1, logger=logger)
        assert result.status == TaskStatus.SUCCESS
        assert "captured_output" in result.stdout

    def test_invalid_function_format(self):
        task = make_python_task(function="no_colon_here")
        result = execute_python(task, attempt=1, logger=logger)
        assert result.status == TaskStatus.FAILED

    def test_missing_script_and_function(self):
        task = make_python_task()
        result = execute_python(task, attempt=1, logger=logger)
        assert result.status == TaskStatus.FAILED

    def test_script_with_args(self, tmp_path):
        script = tmp_path / "args.py"
        script.write_text(
            "import sys\n"
            "print('args:', sys.argv[1:])\n"
        )
        task = make_python_task(script=str(script), args=["foo", "bar"])
        result = execute_python(task, attempt=1, logger=logger)
        assert result.status == TaskStatus.SUCCESS
        assert "foo" in result.stdout
