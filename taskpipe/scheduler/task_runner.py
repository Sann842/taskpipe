"""
Task runner: wraps executors with retry / backoff / failure-strategy logic.
"""
from __future__ import annotations
import time
from logging import Logger

from ..executors import execute_shell, execute_python
from ..models import (
    FailureStrategy,
    TaskConfig,
    TaskResult,
    TaskStatus,
    TaskType,
)


class TaskAbortError(Exception):
    """Raised when a task fails with on_failure=STOP and the pipeline must halt."""
    def __init__(self, result: TaskResult):
        self.result = result
        super().__init__(f"Task '{result.task_name}' failed — pipeline aborted.")


def run_task(task: TaskConfig, logger: Logger) -> TaskResult:
    """
    Execute a single task with retry / backoff / failure-strategy.

    Returns a TaskResult. Raises TaskAbortError if on_failure=STOP (or RETRY
    exhausted) and the pipeline must halt.
    """
    if not task.enabled:
        logger.info(f"Task '{task.name}' is disabled — skipping.")
        now = time.time()
        return TaskResult(
            task_name=task.name,
            status=TaskStatus.SKIPPED,
            start_time=now,
            end_time=now,
        )

    max_attempts = task.retry.max_attempts if task.on_failure == FailureStrategy.RETRY else 1
    backoff = task.retry.backoff_seconds
    result: TaskResult | None = None

    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            logger.warning(
                f"Task '{task.name}' retrying in {backoff:.1f}s "
                f"(attempt {attempt}/{max_attempts}) ..."
            )
            time.sleep(backoff)
            backoff *= task.retry.backoff_multiplier

        result = _dispatch(task, attempt, logger)

        if result.status == TaskStatus.SUCCESS:
            logger.info(
                f"Task '{task.name}' completed successfully "
                f"in {result.duration:.2f}s"
            )
            return result

        if attempt < max_attempts and task.on_failure == FailureStrategy.RETRY:
            result = TaskResult(
                task_name=result.task_name,
                status=TaskStatus.RETRYING,
                start_time=result.start_time,
                end_time=result.end_time,
                attempt=attempt,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.return_code,
                error=result.error,
            )
            continue

        break

    if result is None or result.status == TaskStatus.RETRYING:
        now = time.time()
        result = TaskResult(
            task_name=task.name,
            status=TaskStatus.FAILED,
            start_time=now,
            end_time=now,
            attempt=max_attempts,
            error="All retry attempts exhausted.",
        )

    # After retries: apply the failure strategy
    if result.status != TaskStatus.SUCCESS:
        if task.on_failure in (FailureStrategy.STOP, FailureStrategy.RETRY):
            raise TaskAbortError(result)
        if task.on_failure == FailureStrategy.SKIP:
            logger.warning(f"Task '{task.name}' failed — skipping (on_failure=skip).")
            result.status = TaskStatus.SKIPPED

    return result


def _dispatch(task: TaskConfig, attempt: int, logger: Logger) -> TaskResult:
    if task.type == TaskType.SHELL:
        return execute_shell(task, attempt, logger)
    elif task.type == TaskType.PYTHON:
        return execute_python(task, attempt, logger)
    else:
        raise ValueError(f"Unsupported task type: {task.type}")
