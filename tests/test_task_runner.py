"""Tests for task runner — retry, backoff, and failure strategies."""
import logging
import pytest

from taskpipe.models import (
    FailureStrategy, RetryConfig, TaskConfig, TaskStatus, TaskType,
)
from taskpipe.scheduler.task_runner import run_task, TaskAbortError

logger = logging.getLogger("test_runner")
logging.basicConfig(level=logging.DEBUG)


def shell_task(name, command, on_failure=FailureStrategy.STOP, retry=None, enabled=True):
    return TaskConfig(
        name=name,
        type=TaskType.SHELL,
        command=command,
        on_failure=on_failure,
        retry=retry or RetryConfig(max_attempts=1, backoff_seconds=0.01),
        enabled=enabled,
    )


class TestTaskRunner:
    def test_success(self):
        task = shell_task("ok", "echo hi")
        result = run_task(task, logger)
        assert result.status == TaskStatus.SUCCESS

    def test_disabled_task_skipped(self):
        task = shell_task("disabled", "echo hi", enabled=False)
        result = run_task(task, logger)
        assert result.status == TaskStatus.SKIPPED

    def test_stop_on_failure_raises(self):
        task = shell_task("bad", "exit 1", on_failure=FailureStrategy.STOP)
        with pytest.raises(TaskAbortError) as exc_info:
            run_task(task, logger)
        assert exc_info.value.result.status == TaskStatus.FAILED

    def test_skip_on_failure(self):
        task = shell_task("bad", "exit 1", on_failure=FailureStrategy.SKIP)
        result = run_task(task, logger)
        assert result.status == TaskStatus.SKIPPED

    def test_retry_eventually_succeeds(self, tmp_path):
        counter = tmp_path / "count.txt"
        counter.write_text("0")
        script = tmp_path / "flaky.sh"
        script.write_text(
            f"#!/bin/bash\n"
            f"n=$(cat {counter})\n"
            f"n=$((n+1))\n"
            f"echo $n > {counter}\n"
            f"[ $n -ge 3 ] && exit 0 || exit 1\n"
        )
        script.chmod(0o755)
        task = TaskConfig(
            name="flaky",
            type=TaskType.SHELL,
            command=f"bash {script}",
            on_failure=FailureStrategy.RETRY,
            retry=RetryConfig(max_attempts=4, backoff_seconds=0.01, backoff_multiplier=1.0),
        )
        result = run_task(task, logger)
        assert result.status == TaskStatus.SUCCESS
        assert result.attempt == 3

    def test_retry_exhausted_raises_stop(self):
        task = TaskConfig(
            name="always_fail",
            type=TaskType.SHELL,
            command="exit 1",
            on_failure=FailureStrategy.RETRY,
            retry=RetryConfig(max_attempts=2, backoff_seconds=0.01),
        )
        with pytest.raises(TaskAbortError):
            run_task(task, logger)

    def test_retry_exhausted_skip(self):
        task = TaskConfig(
            name="always_fail_skip",
            type=TaskType.SHELL,
            command="exit 1",
            on_failure=FailureStrategy.SKIP,
            retry=RetryConfig(max_attempts=1, backoff_seconds=0.01),
        )
        result = run_task(task, logger)
        assert result.status == TaskStatus.SKIPPED
